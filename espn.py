"""
espn.py -- ESPN Public API
SMS optimized. EST times.
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


# -- Scores --------------------------------------------------------------------
def get_scores(league, team_id, team_name):
    data = safe_get(sport_url(league, "/scoreboard"))
    if not data:
        return ["No scores found."]
    msgs = []
    for event in data.get("events", []):
        comp       = event.get("competitions", [{}])[0]
        teams_data = comp.get("competitors", [])
        our  = next((t for t in teams_data if t.get("team", {}).get("id") == team_id), None)
        opp  = next((t for t in teams_data if t.get("team", {}).get("id") != team_id), None)
        if not our or not opp:
            continue
        our_score = our.get("score", "?")
        opp_score = opp.get("score", "?")
        opp_abbr  = opp.get("team", {}).get("abbreviation", "OPP")
        home_away = "vs" if our.get("homeAway") == "home" else "@"
        state     = event.get("status", {}).get("type", {}).get("state", "pre")
        detail    = event.get("status", {}).get("type", {}).get("shortDetail", "")
        if state == "in":
            msgs.append("LIVE " + detail + ": " + our_score + "-" + opp_score + " " + home_away + " " + opp_abbr)
        elif state == "post":
            icon = "W" if int(our_score or 0) > int(opp_score or 0) else "L"
            msgs.append(icon + " " + our_score + "-" + opp_score + " " + home_away + " " + opp_abbr)
        else:
            msgs.append("Next: " + fmt_time(event.get("date", "")) + " " + home_away + " " + opp_abbr)
    return msgs or ["No games found for " + team_name + "."]


# -- Score details -------------------------------------------------------------
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
        plays = comp.get("scoringPlays", [])
        if plays:
            for play in plays:
                period = play.get("period", {}).get("displayValue", "")
                clock  = play.get("clock", {}).get("displayValue", "")
                text   = play.get("text", "")
                score  = str(play.get("awayScore", "")) + "-" + str(play.get("homeScore", ""))
                line   = period + " " + clock + " " + score + ": " + text
                if len(line) > 155:
                    line = line[:152] + "..."
                msgs.append(line)
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
    msgs = []
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
            name    = player.get("displayName", player.get("fullName", "?"))
            pos     = player.get("position", {}).get("abbreviation", group_pos) if isinstance(player.get("position"), dict) else group_pos
            jersey  = player.get("jersey", "")
            num_str = "#" + jersey if jersey else ""
            pos_str = "(" + pos + ")" if pos else ""
            lines.append((num_str + " " + name + " " + pos_str).strip())
        msgs.append("\n".join(lines))
    return msgs


# -- News ----------------------------------------------------------------------
def get_news(league, team_id, team_name):
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


# -- Injuries ------------------------------------------------------------------
def get_injuries(league, team_id, team_name):
    data = safe_get(sport_url(league, "/teams/" + team_id + "/injuries"))
    if not data:
        # Try alternate endpoint
        data = safe_get(sport_url(league, "/injuries"), {"team": team_id})
    if not data:
        return ["No injury data found."]
    injuries = data.get("injuries", data.get("items", []))
    if not injuries:
        return [team_name + ": No injuries reported."]
    msgs = []
    for inj in injuries[:10]:
        athlete = inj.get("athlete", {})
        name    = athlete.get("displayName", athlete.get("fullName", "?"))
        status  = inj.get("status", inj.get("type", {}).get("description", "?"))
        detail  = inj.get("details", {}).get("type", "")
        line    = name + " - " + status
        if detail:
            line += " (" + detail + ")"
        msgs.append(line)
    return msgs or [team_name + ": No injuries reported."]


# -- Transactions --------------------------------------------------------------
def get_transactions(league, team_id, team_name):
    sport, lg = SPORT_MAP[league]
    data = safe_get(
        "https://site.api.espn.com/apis/site/v2/sports/" + sport + "/" + lg + "/transactions",
        {"team": team_id, "limit": 10}
    )
    if not data:
        return ["No transaction data found."]
    items = data.get("transactions", data.get("items", []))
    if not items:
        return [team_name + ": No recent transactions."]
    msgs = []
    for item in items[:8]:
        date_str = fmt_date(item.get("date", ""))
        desc     = item.get("description", item.get("headline", "?"))
        if len(desc) > 130:
            desc = desc[:127] + "..."
        msgs.append((date_str + ": " + desc) if date_str else desc)
    return msgs or [team_name + ": No recent transactions."]


# -- Player lookup -------------------------------------------------------------
def get_player(league, player_name):
    sport, lg = SPORT_MAP[league]
    data = safe_get(
        BASE + "/" + sport + "/" + lg + "/athletes",
        {"limit": 5, "search": player_name}
    )
    if not data:
        return ["Player not found."]
    athletes = data.get("items", data.get("athletes", []))
    if not athletes:
        return ["No player found matching: " + player_name]
    player  = athletes[0]
    name    = player.get("displayName", player.get("fullName", "?"))
    pos     = player.get("position", {}).get("abbreviation", "")
    team    = player.get("team", {}).get("displayName", "")
    jersey  = player.get("jersey", "")
    age     = str(player.get("age", ""))
    pid     = player.get("id", "")
    # Get stats
    stats_data = safe_get(BASE + "/" + sport + "/" + lg + "/athletes/" + pid + "/statistics") if pid else None
    msgs = []
    header = name
    if pos:
        header += " " + pos
    if team:
        header += " | " + team
    if jersey:
        header += " #" + jersey
    msgs.append(header)
    if stats_data:
        splits = stats_data.get("statistics", {}).get("splits", {}).get("categories", [])
        for cat in splits[:3]:
            cat_name = cat.get("displayName", "")
            stat_lines = []
            for stat in cat.get("stats", [])[:5]:
                sname = stat.get("shortDisplayName", stat.get("displayName", ""))
                sval  = stat.get("displayValue", "")
                if sname and sval and sval != "0" and sval != "0.0":
                    stat_lines.append(sname + ":" + sval)
            if stat_lines:
                msgs.append(cat_name + ": " + " ".join(stat_lines))
    return msgs or [name + ": No stats available."]


# -- Head to head --------------------------------------------------------------
def get_head_to_head(league, team1_id, team1_name, team2_abbr):
    data = safe_get(sport_url(league, "/scoreboard"))
    if not data:
        return ["No data found."]
    # Look through past events for matchups
    all_events = data.get("events", [])
    results    = []
    for event in all_events:
        comp  = event.get("competitions", [{}])[0]
        teams = comp.get("competitors", [])
        ids   = [t.get("team", {}).get("id") for t in teams]
        abbrs = [t.get("team", {}).get("abbreviation", "").lower() for t in teams]
        if team1_id in ids and team2_abbr.lower() in abbrs:
            state = event.get("status", {}).get("type", {}).get("state", "pre")
            if state == "post":
                our  = next((t for t in teams if t.get("team", {}).get("id") == team1_id), None)
                opp  = next((t for t in teams if t.get("team", {}).get("abbreviation", "").lower() == team2_abbr.lower()), None)
                if our and opp:
                    our_score = our.get("score", "?")
                    opp_score = opp.get("score", "?")
                    icon      = "W" if int(our_score or 0) > int(opp_score or 0) else "L"
                    date_str  = fmt_date(event.get("date", ""))
                    results.append(date_str + " " + icon + " " + our_score + "-" + opp_score)
    if not results:
        return [team1_name + " vs " + team2_abbr.upper() + ": No recent matchups found."]
    return [team1_name + " vs " + team2_abbr.upper() + ":"] + results


# -- Home/Away record ----------------------------------------------------------
def get_home_away(league, team_id, team_name):
    data = safe_get(sport_url(league, "/teams/" + team_id + "/schedule"))
    if not data:
        return ["No data found."]
    home_w = home_l = away_w = away_l = 0
    for event in data.get("events", []):
        comp  = event.get("competitions", [{}])[0]
        state = comp.get("status", {}).get("type", {}).get("state", "pre")
        if state != "post":
            continue
        our = next((t for t in comp.get("competitors", []) if t.get("team", {}).get("id") == team_id), None)
        if not our:
            continue
        is_home = our.get("homeAway") == "home"
        won     = our.get("winner", False)
        if is_home:
            if won: home_w += 1
            else:   home_l += 1
        else:
            if won: away_w += 1
            else:   away_l += 1
    return [
        team_name + " records:",
        "Home: " + str(home_w) + "-" + str(home_l),
        "Away: " + str(away_w) + "-" + str(away_l),
    ]


# -- Playoff bracket -----------------------------------------------------------
def get_bracket(league):
    sport, lg = SPORT_MAP[league]
    data = safe_get(
        "https://site.api.espn.com/apis/v2/sports/" + sport + "/" + lg + "/playoff-bracket"
    )
    if not data:
        data = safe_get(WEBBASE + "/" + sport + "/" + lg + "/playoff-bracket")
    if not data:
        return ["No playoff bracket found."]
    msgs   = []
    rounds = data.get("rounds", data.get("bracket", {}).get("rounds", []))
    for rnd in rounds:
        rnd_name = rnd.get("name", rnd.get("displayName", "Round"))
        msgs.append("-- " + rnd_name + " --")
        for series in rnd.get("series", rnd.get("matchups", [])):
            t1   = series.get("competitors", [{}])[0]
            t2   = series.get("competitors", [{}])[1] if len(series.get("competitors", [])) > 1 else {}
            n1   = t1.get("team", {}).get("abbreviation", "?")
            n2   = t2.get("team", {}).get("abbreviation", "?")
            w1   = str(t1.get("wins", 0))
            w2   = str(t2.get("wins", 0))
            msgs.append(n1 + "(" + w1 + ") vs " + n2 + "(" + w2 + ")")
    return msgs or [league.upper() + " playoffs not available yet."]


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
                pts  = stats.get("points",  stats.get("pts", "?"))
                wins = stats.get("wins",    stats.get("w",   "?"))
                loss = stats.get("losses",  stats.get("l",   "?"))
                otl  = stats.get("otLosses",stats.get("ot",  stats.get("otl", "?")))
                mark = " <" if team_name.lower() in team.lower() else ""
                msgs.append(abbr + ": " + str(pts) + "pts " + str(wins) + "-" + str(loss) + "-" + str(otl) + mark)
            else:
                wins = stats.get("wins",   stats.get("w", stats.get("W", "?")))
                loss = stats.get("losses", stats.get("l", stats.get("L", "?")))
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


# -- League-wide ---------------------------------------------------------------
def get_league_data(league, category):
    if category == "league_scores":    return get_league_scores(league)
    if category == "league_schedule":  return get_league_schedule(league)
    if category == "league_news":      return get_league_news(league)
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
        home    = next((t for t in teams if t.get("homeAway") == "home"), teams[0])
        away    = next((t for t in teams if t.get("homeAway") == "away"), teams[1])
        h_abbr  = home.get("team", {}).get("abbreviation", "?")
        a_abbr  = away.get("team", {}).get("abbreviation", "?")
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


# -- Check if game just ended (for alerts) ------------------------------------
def check_game_finished(league, team_id):
    """Returns final score string if team's game just ended, else None."""
    data = safe_get(sport_url(league, "/scoreboard"))
    if not data:
        return None
    for event in data.get("events", []):
        comp       = event.get("competitions", [{}])[0]
        teams_data = comp.get("competitors", [])
        our = next((t for t in teams_data if t.get("team", {}).get("id") == team_id), None)
        opp = next((t for t in teams_data if t.get("team", {}).get("id") != team_id), None)
        if not our or not opp:
            continue
        state = event.get("status", {}).get("type", {}).get("state", "pre")
        if state == "post":
            our_score = our.get("score", "?")
            opp_score = opp.get("score", "?")
            opp_abbr  = opp.get("team", {}).get("abbreviation", "OPP")
            home_away = "vs" if our.get("homeAway") == "home" else "@"
            icon      = "W" if int(our_score or 0) > int(opp_score or 0) else "L"
            team_name = our.get("team", {}).get("displayName", "Team")
            return "FINAL: " + team_name + " " + icon + " " + our_score + "-" + opp_score + " " + home_away + " " + opp_abbr
    return None


# -- Dispatcher ----------------------------------------------------------------
def get_data(league, team_id, team_name, category):
    key = league + "-" + team_id + "-" + category
    ttl = CACHE_SHORT if category in ("scores", "news") else CACHE_LONG

    def fetch():
        if category == "scores":       return get_scores(league, team_id, team_name)
        if category == "schedule":     return get_schedule(league, team_id, team_name)
        if category == "roster":       return get_roster(league, team_id, team_name)
        if category == "news":         return get_news(league, team_id, team_name)
        if category == "standings":    return get_standings(league, team_id, team_name)
        if category == "injuries":     return get_injuries(league, team_id, team_name)
        if category == "transactions": return get_transactions(league, team_id, team_name)
        if category == "homeaway":     return get_home_away(league, team_id, team_name)
        return ["Unknown category."]

    return _cached(key, ttl, fetch)
