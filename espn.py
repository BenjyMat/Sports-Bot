"""
espn.py -- ESPN Public API (100% free, no key needed)
SMS optimized -- every message under 160 chars.
"""

import requests
from datetime import datetime
import time as _time

BASE    = "https://site.api.espn.com/apis/site/v2/sports"
CDNBASE = "https://site.web.api.espn.com/apis/site/v2/sports"
TIMEOUT = 20

SPORT_MAP = {
    "nhl": ("hockey",     "nhl"),
    "nba": ("basketball", "nba"),
    "nfl": ("football",   "nfl"),
    "mlb": ("baseball",   "mlb"),
}

# Cache: { key: (timestamp, result) }
_cache = {}
CACHE_SHORT = 10    # 10 seconds (scores, news)
CACHE_LONG  = 1800  # 30 minutes (schedule, roster, standings)

def _cached(key, ttl, fetch_fn):
    now = _time.time()
    if key in _cache:
        ts, val = _cache[key]
        if now - ts < ttl:
            return val
    result = fetch_fn()
    if result:
        _cache[key] = (now, result)
    return result

def url(league, path=""):
    sport, lg = SPORT_MAP[league]
    return f"{BASE}/{sport}/{lg}{path}"

def safe_get(endpoint, params=None):
    try:
        r = requests.get(endpoint, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


# -- Teams ---------------------------------------------------------------------
def get_teams(league):
    return _cached(f"teams-{league}", 21600, lambda: _get_teams_raw(league))

def _get_teams_raw(league):
    data = safe_get(url(league, "/teams"), {"limit": 50})
    if not data:
        return []
    teams = []
    for t in data.get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", []):
        team = t.get("team", {})
        teams.append({
            "id":     team.get("id", ""),
            "name":   team.get("displayName", team.get("name", "?")),
            "abbrev": team.get("abbreviation", ""),
        })
    return sorted(teams, key=lambda x: x["name"])


# -- Scores --------------------------------------------------------------------
# Returns a LIST of short SMS messages
def get_scores(league, team_id, team_name):
    data = safe_get(url(league, "/scoreboard"))
    if not data:
        return [f"No scores for {team_name}."]

    msgs  = []
    found = 0

    for event in data.get("events", []):
        comps = event.get("competitions", [])
        if not comps:
            continue
        comp       = comps[0]
        teams_data = comp.get("competitors", [])
        our_team   = None
        other_team = None
        for t in teams_data:
            if t.get("team", {}).get("id") == team_id:
                our_team = t
            else:
                other_team = t
        if not our_team or not other_team:
            continue

        found      += 1
        our_score   = our_team.get("score", "?")
        other_score = other_team.get("score", "?")
        other_abbr  = other_team.get("team", {}).get("abbreviation", "OPP")
        home_away   = "vs" if our_team.get("homeAway") == "home" else "@"
        status      = event.get("status", {})
        state       = status.get("type", {}).get("state", "pre")
        detail      = status.get("type", {}).get("shortDetail", "")

        if state == "in":
            msgs.append(f"LIVE {detail}: {our_score}-{other_score} {home_away} {other_abbr}")
        elif state == "post":
            won  = int(our_score or 0) > int(other_score or 0)
            icon = "W" if won else "L"
            msgs.append(f"{icon} {our_score}-{other_score} {home_away} {other_abbr}")
        else:
            game_date = event.get("date", "")
            try:
                dt       = datetime.fromisoformat(game_date.replace("Z", "+00:00"))
                date_str = dt.strftime("%a %b %-d")
            except Exception:
                date_str = "TBD"
            msgs.append(f"Next: {date_str} {home_away} {other_abbr}")

    if not msgs:
        return [f"No games found for {team_name}."]
    return msgs


# -- Schedule ------------------------------------------------------------------
def get_schedule(league, team_id, team_name):
    data = safe_get(url(league, f"/teams/{team_id}/schedule"))
    if not data:
        return [f"No schedule for {team_name}."]

    msgs   = []
    events = data.get("events", [])

    for event in events:
        status = event.get("competitions", [{}])[0].get("status", {})
        state  = status.get("type", {}).get("state", "pre")
        if state != "pre":
            continue
        comp      = event.get("competitions", [{}])[0]
        game_date = event.get("date", "")
        opponents = comp.get("competitors", [])
        home_away = "vs"
        opp_abbr  = "TBD"
        for t in opponents:
            if t.get("team", {}).get("id") != team_id:
                opp_abbr  = t.get("team", {}).get("abbreviation", "OPP")
                home_away = "vs" if t.get("homeAway") == "away" else "@"
        try:
            dt       = datetime.fromisoformat(game_date.replace("Z", "+00:00"))
            date_str = dt.strftime("%a %b %-d %-I:%M%p")
        except Exception:
            date_str = "TBD"
        msgs.append(f"{date_str} {home_away} {opp_abbr}")
        if len(msgs) >= 6:
            break

    if not msgs:
        return ["No upcoming games found."]
    return msgs


# -- Roster --------------------------------------------------------------------
def get_roster(league, team_id, team_name):
    data = safe_get(url(league, f"/teams/{team_id}/roster"))
    if not data:
        return [f"No roster for {team_name}."]

    athletes = data.get("athletes", [])
    players  = []

    if athletes and isinstance(athletes[0], dict) and "items" in athletes[0]:
        for group in athletes:
            pos_label = group.get("position", "")
            for p in group.get("items", []):
                players.append((p, pos_label))
    else:
        for p in athletes:
            players.append((p, ""))

    if not players:
        return ["No roster data available."]

    # Each message: header + up to 8 players (keeps well under 160 chars)
    msgs   = []
    chunk  = 8
    chunks = [players[i:i+chunk] for i in range(0, len(players), chunk)]
    total  = len(chunks)

    for idx, group in enumerate(chunks):
        lines = [f"{team_name[:10]} ROSTER {idx+1}/{total}"]
        for player, group_pos in group:
            name   = player.get("displayName", player.get("fullName", "?"))
            # Use last name only to save space
            lname  = name.split()[-1] if name else "?"
            pos    = player.get("position", {}).get("abbreviation", group_pos) if isinstance(player.get("position"), dict) else group_pos
            jersey = player.get("jersey", "")
            num_str = f"#{jersey}" if jersey else ""
            pos_str = f"({pos})" if pos else ""
            lines.append(f"{num_str} {lname} {pos_str}".strip())
        msgs.append("\n".join(lines))

    return msgs


# -- News ----------------------------------------------------------------------
def get_news(league, team_id, team_name):
    sport, lg = SPORT_MAP[league]
    attempts = [
        (url(league, f"/teams/{team_id}/news"),                          None),
        (url(league, "/news"),                                           {"team": team_id}),
        (f"{CDNBASE}/{sport}/{lg}/teams/{team_id}/news",                 None),
        ("https://site.api.espn.com/apis/site/v2/sports/news",          {"team": team_id}),
        (f"https://site.api.espn.com/apis/v2/sports/{sport}/{lg}/news", {"team": team_id}),
    ]
    articles = []
    for endpoint, params in attempts:
        data = safe_get(endpoint, params)
        if data:
            articles = data.get("articles", [])
            if articles:
                break

    if not articles:
        return ["No news found right now."]

    msgs = []
    for article in articles[:5]:
        headline = article.get("headline", "No headline")
        pub      = article.get("published", "")
        try:
            dt      = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            pub_str = dt.strftime("%b %-d")
        except Exception:
            pub_str = ""
        # Truncate headline to fit in SMS
        if len(headline) > 130:
            headline = headline[:127] + "..."
        line = f"{pub_str}: {headline}" if pub_str else headline
        msgs.append(line)

    return msgs


# -- Standings -----------------------------------------------------------------
def _parse_entries(entries, team_name, msgs):
    for entry in entries[:10]:
        team   = entry.get("team", {}).get("displayName", "?")
        abbr   = entry.get("team", {}).get("abbreviation", team[:3].upper())
        stats  = {s["name"]: s["displayValue"] for s in entry.get("stats", [])}
        wins   = stats.get("wins",   stats.get("W",   stats.get("w",   "?")))
        losses = stats.get("losses", stats.get("L",   stats.get("l",   "?")))
        marker = "<" if team_name.lower() in team.lower() else ""
        msgs.append(f"{abbr}: {wins}-{losses} {marker}".strip())


def get_standings(league, team_id, team_name):
    sport, lg = SPORT_MAP[league]
    data = None
    for endpoint in [
        f"https://site.web.api.espn.com/apis/v2/sports/{sport}/{lg}/standings?season=2025&type=0",
        f"https://site.web.api.espn.com/apis/v2/sports/{sport}/{lg}/standings",
        f"https://cdn.espn.com/core/{sport}/{lg}/standings?xhr=1&render=false&device=desktop&userab=18",
        f"https://site.api.espn.com/apis/v2/sports/{sport}/{lg}/standings",
    ]:
        data = safe_get(endpoint)
        if data and (data.get("children") or data.get("standings") or data.get("groups")):
            break
        data = None

    if not data:
        return [f"No standings for {league.upper()}."]

    msgs = []

    def crawl(node, depth=0):
        name    = node.get("name", node.get("abbreviation", ""))
        entries = (node.get("standings") or {}).get("entries", [])
        if not entries:
            entries = node.get("entries", [])
        if entries:
            if name and depth > 0:
                msgs.append(name)
            _parse_entries(entries, team_name, msgs)
        for key in ("children", "groups", "divisions", "conferences"):
            for child in node.get(key, []):
                crawl(child, depth + 1)

    roots_to_try = [data]
    for wrapper in ("content", "standings", "sports"):
        val = data.get(wrapper)
        if val:
            roots_to_try.append(val[0] if isinstance(val, list) else val)

    for root in roots_to_try:
        crawl(root)

    if not msgs:
        return ["No standings data found."]
    return msgs


# -- Dispatcher ----------------------------------------------------------------
def get_data(league, team_id, team_name, category):
    key = f"{league}-{team_id}-{category}"
    ttl = CACHE_SHORT if category in ("scores", "news") else CACHE_LONG

    def fetch():
        if category == "scores":
            return get_scores(league, team_id, team_name)
        elif category == "schedule":
            return get_schedule(league, team_id, team_name)
        elif category == "roster":
            return get_roster(league, team_id, team_name)
        elif category == "news":
            return get_news(league, team_id, team_name)
        elif category == "standings":
            return get_standings(league, team_id, team_name)
        return ["Unknown category."]

    return _cached(key, ttl, fetch)
