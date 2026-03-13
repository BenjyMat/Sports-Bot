"""
espn.py -- ESPN Public API fetcher
SMS optimized. EST times. All 4 leagues.
"""

import requests
from datetime import datetime, timezone, timedelta
import time as _time

BASE    = "https://site.api.espn.com/apis/site/v2/sports"
WEBBASE = "https://site.web.api.espn.com/apis/v2/sports"
TIMEOUT = 20
EST     = timezone(timedelta(hours=-5))

SPORT_MAP = {
    "nhl": ("hockey",     "nhl"),
    "nba": ("basketball", "nba"),
    "nfl": ("football",   "nfl"),
    "mlb": ("baseball",   "mlb"),
}

_cache = {}
CACHE_SHORT = 10
CACHE_LONG  = 1800

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

def sport_url(league, path=""):
    sport, lg = SPORT_MAP[league]
    return BASE + "/" + sport + "/" + lg + path

def safe_get(endpoint, params=None):
    try:
        r = requests.get(endpoint, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def fmt_time(iso_str):
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone(EST)
        return dt.strftime("%a %b %-d %-I:%M%p ET")
    except Exception:
        return "TBD"

def fmt_date(iso_str):
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone(EST)
        return dt.strftime("%b %-d")
    except Exception:
        return ""


# -- Teams ---------------------------------------------------------------------
def get_teams(league):
    return _cached("teams-" + league, 21600, lambda: _get_teams_raw(league))

def _get_teams_raw(league):
    data = safe_get(sport_url(league, "/teams"), {"limit": 50})
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


# -- Scores (team) -------------------------------------------------------------
def get_scores(league, team_id, team_name):
    data = safe_get(sport_url(league, "/scoreboard"))
    if not data:
        return ["No scores found."]
    msgs  = []
    for event in data.get("events", []):
        comp       = event.get("competitions", [{}])[0]
        teams_data = comp.get("competitors", [])
        our        = next((t for t in teams_data if t.get("team", {}).get("id") == team_id), None)
        opp        = next((t for t in teams_data if t.get("team", {}).get("id") != team_id), None)
        if not our or not opp:
            continue
        our_score  = our.get("score", "?")
        opp_score  = opp.get("score", "?")
        opp_abbr   = opp.get("team", {}).get("abbreviation", "OPP")
        home_away  = "vs" if our.get("homeAway") == "home" else "@"
        state      = event.get("status", {}).get("type", {}).get("state", "pre")
        detail     = event.get("status", {}).get("type", {}).get("shortDetail", "")
        if state == "in":
            msgs.append("LIVE " + detail + ": " + our_score + "-" + opp_score + " " + home_away + " " + opp_abbr)
        elif state == "post":
            icon = "W" if int(our_score or 0) > int(opp_score or 0) else "L"
            msgs.append(icon + " " + our_score + "-" + opp_score + " " + home_away + " " + opp_abbr)
        else:
            msgs.append("Next: " + fmt_time(event.get("date", "")) + " " + home_away + " " + opp_abbr)
    return msgs or ["No games found for " + team_name + "."]


# -- Score details (who scored) ------------------------------------------------
def get_score_details(league, team_id, team_name):
    data = safe_get(sport_url(league, "/scoreboard"))
    if not data:
        return ["No detail available."]
    msgs = []
    for event in data.get("events", []):
        comp       = event.get("competitions", [{}])[0]
        teams_data = comp.get("competitors", [])
        our = next((t for t in teams_data if t.get("team", {}).get("id") == team_id), None)
        if not our:
            continue
        state = event.get("status", {}).get("type", {}).get("state", "pre")
        if state == "pre":
            continue
        # Scoring plays
        plays = comp.get("scoringPlays", [])
        if plays:
            for play in plays:
                period  = play.get("period", {}).get("displayValue", "")
                clock   = play.get("clock", {}).get("displayValue", "")
                text    = play.get("text", "")
                score   = play.get("awayScore", "") + "-" + play.get("homeScore", "")
                line    = period + " " + clock + " " + score + ": " + text
                if len(line) > 155:
                    line = line[:152] + "..."
                msgs.append(line)
        # Leaders/stats
        leaders = our.get("leaders", [])
        for leader in leaders:
            cat   = leader.get("displayName", "")
            athl  = leader.get("leaders", [{}])[0]
            aname = athl.get("athlete", {}).get("displayName", "")
            val   = athl.get("displayValue", "")
            if aname and val:
                msgs.append(cat + ": " + aname + " " + val)
        break
    return msgs or ["No scoring detail available."]


# -- Schedule ------------------------------------------------------------------
def get_schedule(league, team_id, team_name):
    data = safe_get(sport_url(league, "/teams/" + team_id + "/schedule"))
    if not data:
        return ["No schedule found."]
    msgs   = []
    for event in data.get("events", []):
        comp  = event.get("competitions", [{}])[0]
        state = comp.get("status", {}).get("type", {}).get("state", "pre")
        if state != "pre":
            continue
        opp_abbr  = "TBD"
        home_away = "vs"
        for t in comp.get("competitors", []):
            if t.get("team", {}).get("id") != team_id:
                opp_abbr  = t.get("team", {}).get("abbreviation", "OPP")
                home_away = "vs" if t.get("homeAway") == "away" else "@"
        msgs.append(fmt_time(event.get("date", "")) + " " + home_away + " " + opp_abbr)
        if len(msgs) >= 6:
            break
    return msgs or ["No upcoming games found."]


# -- Roster --------------------------------------------------------------------
def get_roster(league, team_id, team_name):
    data = safe_get(sport_url(league, "/teams/" + team_id + "/roster"))
    if not data:
        return ["No roster found."]
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
        return ["No roster data."]
    msgs  = []
    chunk = 8
    parts = [players[i:i+chunk] for i in range(0, len(players), chunk)]
    total = len(parts)
    for idx, group in enumerate(parts):
        lines = [team_name[:10] + " ROSTER " + str(idx+1) + "/" + str(total)]
        for player, group_pos in group:
            name   = player.get("displayName", player.get("fullName", "?"))
            pos    = player.get("position", {}).get("abbreviation", group_pos) if isinstance(player.get("position"), dict) else group_pos
            jersey = player.get("jersey", "")
            num_str = "#" + jersey if jersey else ""
            pos_str = "(" + pos + ")" if pos else ""
            lines.append((num_str + " " + name + " " + pos_str).strip())
        msgs.append("\n".join(lines))
    return msgs


# -- News ----------------------------------------------------------------------
def get_news(league, team_id, team_name):
    sport, lg = SPORT_MAP[league]
    attempts = [
        (sport_url(league, "/teams/" + team_id + "/news"), None),
        (sport_url(league, "/news"), {"team": team_id}),
        ("https://site.api.espn.com/apis/site/v2/sports/news", {"team": team_id}),
    ]
    articles = []
    for endpoint, params in attempts:
        data = safe_get(endpoint, params)
        if data:
            articles = data.get("articles", [])
            if articles:
                break
    if not articles:
        return ["No news found."]
    msgs = []
    for article in articles[:5]:
        headline = article.get("headline", "No headline")
        pub_str  = fmt_date(article.get("published", ""))
        if len(headline) > 130:
            headline = headline[:127] + "..."
        msgs.append((pub_str + ": " + headline) if pub_str else headline)
    return msgs


# -- Standings -----------------------------------------------------------------
def get_standings(league, team_id, team_name):
    sport, lg = SPORT_MAP[league]
    data = None
    for endpoint in [
        WEBBASE + "/" + sport + "/" + lg + "/standings?season=2026&type=0",
        WEBBASE + "/" + sport + "/" + lg + "/standings?season=2025&type=0",
        WEBBASE + "/" + sport + "/" + lg + "/standings",
    ]:
        data = safe_get(endpoint)
        if data and (data.get("children") or data.get("standings") or data.get("groups")):
            break
        data = None
    if not data:
        return ["No standings found."]

    msgs = []

    def parse_entries(entries, section_name=""):
        if section_name:
            msgs.append("-- " + section_name + " --")
        for entry in entries:
            team  = entry.get("team", {}).get("displayName", "?")
            abbr  = entry.get("team", {}).get("abbreviation", team[:3].upper())
            stats = {s["name"]: s["displayValue"] for s in entry.get("stats", [])}

            if league == "nhl":
                pts  = stats.get("points", stats.get("pts", "?"))
                wins = stats.get("wins",   stats.get("w",   "?"))
                loss = stats.get("losses", stats.get("l",   "?"))
                otl  = stats.get("otLosses", stats.get("ot", stats.get("otl", "?")))
                mark = " <" if team_name.lower() in team.lower() else ""
                msgs.append(abbr + ": " + str(pts) + "pts " + str(wins) + "-" + str(loss) + "-" + str(otl) + mark)
            else:
                wins = stats.get("wins",   stats.get("w",   stats.get("W",   "?")))
                loss = stats.get("losses", stats.get("l",   stats.get("L",   "?")))
                mark = " <" if team_name.lower() in team.lower() else ""
                msgs.append(abbr + ": " + str(wins) + "-" + str(loss) + mark)

    def crawl(node, depth=0):
        name    = node.get("name", node.get("abbreviation", ""))
        entries = (node.get("standings") or {}).get("entries", [])
        if not entries:
            entries = node.get("entries", [])
        if entries:
            parse_entries(entries, name if depth > 0 else "")
        for key in ("children", "groups", "divisions", "conferences"):
            for child in node.get(key, []):
                crawl(child, depth + 1)

    for wrapper in (None, "content", "standings", "sports"):
        if wrapper is None:
            root = data
        else:
            val = data.get(wrapper)
            if not val:
                continue
            root = val[0] if isinstance(val, list) else val
        crawl(root)
        if msgs:
            break

    return msgs or ["No standings data found."]


# -- League-wide data ----------------------------------------------------------
def get_league_data(league, category):
    if category == "league_scores":
        return get_league_scores(league)
    elif category == "league_schedule":
        return get_league_schedule(league)
    elif category == "league_news":
        return get_league_news(league)
    return ["Unknown category."]

def get_league_scores(league):
    data = safe_get(sport_url(league, "/scoreboard"))
    if not data:
        return ["No scores found."]
    msgs = []
    for event in data.get("events", []):
        comp  = event.get("competitions", [{}])[0]
        teams = comp.get("competitors", [])
        if len(teams) < 2:
            continue
        home = next((t for t in teams if t.get("homeAway") == "home"), teams[0])
        away = next((t for t in teams if t.get("homeAway") == "away"), teams[1])
        h_abbr = home.get("team", {}).get("abbreviation", "?")
        a_abbr = away.get("team", {}).get("abbreviation", "?")
        h_score = home.get("score", "")
        a_score = away.get("score", "")
        state   = event.get("status", {}).get("type", {}).get("state", "pre")
        detail  = event.get("status", {}).get("type", {}).get("shortDetail", "")
        if state == "in":
            msgs.append("LIVE " + a_abbr + " " + a_score + " @ " + h_abbr + " " + h_score + " (" + detail + ")")
        elif state == "post":
            msgs.append(a_abbr + " " + a_score + " @ " + h_abbr + " " + h_score + " FINAL")
        else:
            msgs.append(fmt_time(event.get("date", "")) + " " + a_abbr + " @ " + h_abbr)
    return msgs or ["No games today."]

def get_league_schedule(league):
    data = safe_get(sport_url(league, "/scoreboard"))
    if not data:
        return ["No schedule found."]
    msgs = []
    for event in data.get("events", []):
        state = event.get("status", {}).get("type", {}).get("state", "pre")
        if state != "pre":
            continue
        comp  = event.get("competitions", [{}])[0]
        teams = comp.get("competitors", [])
        if len(teams) < 2:
            continue
        home   = next((t for t in teams if t.get("homeAway") == "home"), teams[0])
        away   = next((t for t in teams if t.get("homeAway") == "away"), teams[1])
        h_abbr = home.get("team", {}).get("abbreviation", "?")
        a_abbr = away.get("team", {}).get("abbreviation", "?")
        msgs.append(fmt_time(event.get("date", "")) + " " + a_abbr + " @ " + h_abbr)
        if len(msgs) >= 10:
            break
    return msgs or ["No upcoming games found."]

def get_league_news(league):
    data = safe_get(sport_url(league, "/news"))
    if not data:
        return ["No news found."]
    msgs = []
    for article in data.get("articles", [])[:8]:
        headline = article.get("headline", "No headline")
        pub_str  = fmt_date(article.get("published", ""))
        if len(headline) > 130:
            headline = headline[:127] + "..."
        msgs.append((pub_str + ": " + headline) if pub_str else headline)
    return msgs or ["No news found."]


# -- Dispatcher ----------------------------------------------------------------
def get_data(league, team_id, team_name, category):
    key = league + "-" + team_id + "-" + category
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
