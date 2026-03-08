"""
espn.py -- ESPN Public API (100% free, no key needed)
No emojis -- works on any basic phone via SMS.
"""

import requests
from datetime import datetime

BASE    = "https://site.api.espn.com/apis/site/v2/sports"

# Simple cache: { "nba-celtics-scores": (timestamp, result) }
# Scores/news cache 2 min, schedule/roster/standings cache 30 min
import time as _time
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
CDNBASE = "https://site.web.api.espn.com/apis/site/v2/sports"
TIMEOUT = 20

SPORT_MAP = {
    "nhl": ("hockey",     "nhl"),
    "nba": ("basketball", "nba"),
    "nfl": ("football",   "nfl"),
    "mlb": ("baseball",   "mlb"),
}


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
def get_scores(league, team_id, team_name):
    data = safe_get(url(league, "/scoreboard"))
    if not data:
        return f"Couldn't fetch scores for {team_name}."

    lines = [f"SCORES: {team_name.upper()}"]
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
        other_name  = other_team.get("team", {}).get("shortDisplayName", "Opponent")
        home_away   = "vs" if our_team.get("homeAway") == "home" else "@"
        status      = event.get("status", {})
        state       = status.get("type", {}).get("state", "pre")
        detail      = status.get("type", {}).get("shortDetail", "")

        if state == "in":
            line = f"LIVE {detail}\n  {team_name} {our_score} {home_away} {other_name} {other_score}"
        elif state == "post":
            won  = int(our_score or 0) > int(other_score or 0)
            icon = "W" if won else "L"
            line = f"{icon} {our_score}-{other_score} {home_away} {other_name}"
        else:
            game_date = event.get("date", "")
            try:
                dt       = datetime.fromisoformat(game_date.replace("Z", "+00:00"))
                date_str = dt.strftime("%a %b %-d")
            except Exception:
                date_str = game_date[:10]
            line = f"Next: {date_str} {home_away} {other_name}"

        lines.append(line)

    if found == 0:
        lines.append("No recent games found.")

    return "\n".join(lines)


# -- Schedule ------------------------------------------------------------------
def get_schedule(league, team_id, team_name):
    data = safe_get(url(league, f"/teams/{team_id}/schedule"))
    if not data:
        return f"Couldn't fetch schedule for {team_name}."

    lines    = [f"SCHEDULE: {team_name.upper()}", "------------------"]
    events   = data.get("events", [])
    upcoming = []

    for event in events:
        status = event.get("competitions", [{}])[0].get("status", {})
        state  = status.get("type", {}).get("state", "pre")
        if state == "pre":
            upcoming.append(event)

    if not upcoming:
        lines.append("No upcoming games found.")
        return "\n".join(lines)

    for event in upcoming[:6]:
        comp      = event.get("competitions", [{}])[0]
        game_date = event.get("date", "")
        opponents = comp.get("competitors", [])
        home_away = "vs"
        opp_name  = "TBD"

        for t in opponents:
            if t.get("team", {}).get("id") != team_id:
                opp_name  = t.get("team", {}).get("shortDisplayName", "Opponent")
                home_away = "vs" if t.get("homeAway") == "away" else "@"

        try:
            dt       = datetime.fromisoformat(game_date.replace("Z", "+00:00"))
            date_str = dt.strftime("%a %b %-d %-I:%M%p")
        except Exception:
            date_str = game_date[:10]

        lines.append(f"{date_str}\n  {home_away} {opp_name}")

    return "\n".join(lines)


# -- Roster --------------------------------------------------------------------
def get_roster(league, team_id, team_name):
    """Returns a LIST of messages so long rosters split into multiple texts."""
    data = safe_get(url(league, f"/teams/{team_id}/roster"))
    if not data:
        return [f"Couldn't fetch roster for {team_name}."]

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
        return [f"ROSTER: {team_name.upper()}\n------------------\nNo roster data available."]

    # Build all player lines
    all_lines = []
    for player, group_pos in players:
        name    = player.get("displayName", player.get("fullName", "?"))
        pos     = player.get("position", {}).get("abbreviation", group_pos) if isinstance(player.get("position"), dict) else group_pos
        jersey  = player.get("jersey", "")
        num_str = f"#{jersey} " if jersey else ""
        pos_str = f" ({pos})" if pos else ""
        all_lines.append(f"{num_str}{name}{pos_str}")

    # Split into chunks of 20 players per message
    CHUNK = 20
    messages = []
    chunks = [all_lines[i:i+CHUNK] for i in range(0, len(all_lines), CHUNK)]
    for idx, chunk in enumerate(chunks):
        part = f" (Part {idx+1}/{len(chunks)})" if len(chunks) > 1 else ""
        header = f"ROSTER: {team_name.upper()}{part}\n------------------"
        messages.append(header + "\n" + "\n".join(chunk))

    return messages


# -- News ----------------------------------------------------------------------
def get_news(league, team_id, team_name):
    sport, lg = SPORT_MAP[league]
    attempts = [
        (url(league, f"/teams/{team_id}/news"),                           None),
        (url(league, "/news"),                                            {"team": team_id}),
        (f"{CDNBASE}/{sport}/{lg}/teams/{team_id}/news",                  None),
        ("https://site.api.espn.com/apis/site/v2/sports/news",           {"team": team_id}),
        (f"https://site.api.espn.com/apis/v2/sports/{sport}/{lg}/news",  {"team": team_id}),
        (url(league, "/news"),                                            None),
    ]

    articles = []
    for endpoint, params in attempts:
        data = safe_get(endpoint, params)
        if data:
            articles = data.get("articles", [])
            if articles:
                break

    lines = [f"NEWS: {team_name.upper()}"]

    if not articles:
        lines.append("No news found right now.")
        return "\n".join(lines)

    for article in articles[:5]:
        headline = article.get("headline", "No headline")
        desc     = article.get("description", "")
        pub      = article.get("published", "")

        try:
            dt      = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            pub_str = dt.strftime("%b %-d")
        except Exception:
            pub_str = ""

        date_tag = f" [{pub_str}]" if pub_str else ""
        lines.append(f"- {headline}{date_tag}")
        if desc:
            short_desc = desc[:120] + ("..." if len(desc) > 120 else "")
            lines.append(f"  {short_desc}")
        lines.append("")

    return "\n".join(lines).strip()


# -- Standings -----------------------------------------------------------------
def _parse_entries(entries, team_name, lines):
    for entry in entries[:10]:
        team   = entry.get("team", {}).get("displayName", "?")
        stats  = {s["name"]: s["displayValue"] for s in entry.get("stats", [])}
        wins   = stats.get("wins",       stats.get("W",   stats.get("w",   "?")))
        losses = stats.get("losses",     stats.get("L",   stats.get("l",   "?")))
        pct    = stats.get("winPercent", stats.get("PCT", stats.get("pct", "")))
        pct_str = f" ({pct})" if pct and pct not in ("0", "0.0", ".000") else ""
        marker  = " <--YOU" if team_name.lower() in team.lower() else ""
        lines.append(f"  {team}: {wins}-{losses}{pct_str}{marker}")


def get_standings(league, team_id, team_name):
    sport, lg = SPORT_MAP[league]
    # The correct ESPN standings endpoint is the v2 web API
    data = None
    for endpoint in [
        f"https://site.web.api.espn.com/apis/v2/sports/{sport}/{lg}/standings?season=2025&type=0",
        f"https://site.web.api.espn.com/apis/v2/sports/{sport}/{lg}/standings",
        f"https://cdn.espn.com/core/{sport}/{lg}/standings?xhr=1&render=false&device=desktop&userab=18",
        f"https://site.api.espn.com/apis/v2/sports/{sport}/{lg}/standings",
    ]:
        data = safe_get(endpoint)
        # Make sure we got real data, not just a fullViewLink stub
        if data and (data.get("children") or data.get("standings") or data.get("groups")):
            break
        data = None

    if not data:
        return f"Couldn't fetch standings for {league.upper()}."

    lines = [f"STANDINGS: {league.upper()}"]

    def crawl(node, depth=0):
        name    = node.get("name", node.get("abbreviation", ""))
        # Check both "standings.entries" and direct "entries"
        entries = (node.get("standings") or {}).get("entries", [])
        if not entries:
            entries = node.get("entries", [])
        if entries:
            if name and depth > 0:
                lines.append(f"\n{name}")
            _parse_entries(entries, team_name, lines)
        # Recurse into children, groups, divisions — whatever ESPN calls them
        for key in ("children", "groups", "divisions", "conferences"):
            for child in node.get(key, []):
                crawl(child, depth + 1)

    # Try every possible root
    roots_to_try = [data]
    for wrapper in ("content", "standings", "sports"):
        val = data.get(wrapper)
        if val:
            roots_to_try.append(val[0] if isinstance(val, list) else val)

    for root in roots_to_try:
        crawl(root)

    if len(lines) <= 2:
        lines.append("No standings data found.")

    return "\n".join(lines)


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
        return "Unknown category."

    return _cached(key, ttl, fetch)


def get_teams(league):
    """Cached team list - rarely changes so cache for 6 hours."""
    return _cached(f"teams-{league}", 21600, lambda: _get_teams_raw(league))
