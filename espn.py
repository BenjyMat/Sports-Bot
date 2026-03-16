"""
espn.py -- ESPN Public API
SMS optimized. EST times.
"""

import requests
import os
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

def safe_get(endpoint, params=None, timeout_override=None, headers=None):
    try:
        t = timeout_override if timeout_override else TIMEOUT
        r = requests.get(endpoint, params=params, timeout=t, headers=headers or {})
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


# -- Player lookup (searches all team rosters + athlete overview) -------------
def get_player(league, player_name):
    sport, lg = SPORT_MAP[league]
    query = player_name.lower().strip()
    teams = _get_teams_raw(league)
    if not teams:
        return ["Could not load teams."]

    found_pid  = None
    found_name = None
    found_pos  = None
    found_jer  = None
    found_team = None

    # Step 1: Find player in rosters - use short timeout per request
    for team in teams:
        data = safe_get(sport_url(league, "/teams/" + team["id"] + "/roster"), timeout_override=5)
        if not data:
            continue
        athletes = data.get("athletes", [])
        players  = []
        if athletes and isinstance(athletes[0], dict) and "items" in athletes[0]:
            for group in athletes:
                for p in group.get("items", []):
                    players.append(p)
        else:
            players = athletes
        for player in players:
            name = player.get("displayName", player.get("fullName", ""))
            if query in name.lower():
                found_pid  = player.get("id", "")
                found_name = name
                found_pos  = player.get("position", {}).get("abbreviation", "") if isinstance(player.get("position"), dict) else ""
                found_jer  = player.get("jersey", "")
                found_team = team["name"]
                break
        if found_pid:
            break

    if not found_pid:
        return ["Player not found: " + player_name, "Try last name only."]

    header = found_name
    if found_pos: header += " (" + found_pos + ")"
    if found_jer: header += " #" + found_jer
    header += " | " + found_team
    msgs = [header]

    # Try balldontlie for NBA player stats first
    if league == "nba":
        print("Trying balldontlie for:", found_name, "key set:", bool(os.environ.get("BALLDONTLIE_KEY","")), flush=True)
        bdl = get_balldontlie_stats(found_name)
        print("BDL result:", bdl, flush=True)
        if bdl:
            msgs.extend(bdl)
            return msgs

    # Try ESPN stat call
    sdata = safe_get(
        BASE + "/" + sport + "/" + lg + "/athletes/" + found_pid + "/statistics/0",
        timeout_override=5
    )
    if sdata:
        cats = []
        if sdata.get("statistics", {}).get("splits", {}).get("categories"):
            cats = sdata["statistics"]["splits"]["categories"]
        elif sdata.get("splits", {}).get("categories"):
            cats = sdata["splits"]["categories"]
        for cat in cats[:3]:
            stat_bits = []
            for stat in cat.get("stats", [])[:8]:
                sname = stat.get("shortDisplayName") or stat.get("abbreviation") or ""
                sval  = str(stat.get("displayValue") or stat.get("value") or "")
                if sname and sval and sval not in ("0","0.0","--","","null"):
                    stat_bits.append(sname + ":" + sval)
            if stat_bits:
                cname = cat.get("displayName") or cat.get("name") or ""
                msgs.append(cname + ": " + " ".join(stat_bits))

    if len(msgs) == 1:
        print("STATS: no stats found for pid", found_pid, flush=True)
        # Try balldontlie for NBA
        if league == "nba":
            bdl_msgs = get_balldontlie_stats(found_name)
            if bdl_msgs:
                msgs.extend(bdl_msgs)
            else:
                msgs.append("Stats unavailable.")
        else:
            msgs.append("Season stats unavailable.")
            msgs.append("For game stats:")
            msgs.append(league + " " + found_team.split()[-1].lower() + " s")
            msgs.append("then: info")

    return msgs


def get_balldontlie_stats(player_name):
    """Fetch NBA season stats from balldontlie.io (requires free API key)."""
    BDL_KEY = os.environ.get("BALLDONTLIE_KEY","")
    if not BDL_KEY:
        return None
    try:
        search = safe_get(
            "https://api.balldontlie.io/v1/players",
            params={"search": player_name, "per_page": 1},
            headers={"Authorization": BDL_KEY}
        )
        if not search:
            return None
        players = search.get("data", [])
        if not players:
            return None
        p   = players[0]
        pid = p.get("id")
        if not pid:
            return None

        # Get current season averages
        stats = safe_get(
            "https://api.balldontlie.io/v1/season_averages",
            params={"player_ids[]": pid, "season": 2024},
            headers={"Authorization": BDL_KEY}
        )
        if not stats:
            return None
        avgs = stats.get("data", [])
        if not avgs:
            return None
        a = avgs[0]
        lines = []
        gp  = a.get("games_played", "?")
        pts = a.get("pts",  "?")
        reb = a.get("reb",  "?")
        ast = a.get("ast",  "?")
        stl = a.get("stl",  "?")
        blk = a.get("blk",  "?")
        fg  = a.get("fg_pct",  "?")
        fg3 = a.get("fg3_pct", "?")
        ft  = a.get("ft_pct",  "?")
        min_ = a.get("min", "?")
        lines.append("2024-25 per game (" + str(gp) + " GP):")
        lines.append("PTS:" + str(pts) + " REB:" + str(reb) + " AST:" + str(ast))
        lines.append("STL:" + str(stl) + " BLK:" + str(blk) + " MIN:" + str(min_))
        lines.append("FG:" + str(fg) + " 3P:" + str(fg3) + " FT:" + str(ft))
        return lines
    except Exception:
        return None


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


# -- League stat leaders ------------------------------------------------------
def get_stat_leaders(league, stat_type="points"):
    sport, lg = SPORT_MAP[league]

    # Stat type aliases
    STAT_MAP = {
        # NBA
        "points":"pointsPerGame", "pts":"pointsPerGame",
        "rebounds":"reboundsPerGame", "reb":"reboundsPerGame",
        "assists":"assistsPerGame", "ast":"assistsPerGame",
        "steals":"stealsPerGame", "stl":"stealsPerGame",
        "blocks":"blocksPerGame", "blk":"blocksPerGame",
        # NHL
        "goals":"goals", "g":"goals",
        "assists":"assists",
        "plusminus":"plusMinus", "pm":"plusMinus",
        "saves":"saves",
        # NFL
        "passing":"passingYards", "passyards":"passingYards",
        "rushing":"rushingYards", "rushyards":"rushingYards",
        "receiving":"receivingYards", "recyards":"receivingYards",
        "touchdowns":"touchdowns", "td":"touchdowns",
        "sacks":"sacks",
        # MLB
        "era":"ERA", "avg":"avg", "hr":"homeRuns",
        "rbi":"RBI", "sb":"stolenBases",
        "strikeouts":"strikeouts", "so":"strikeouts",
        "wins":"wins",
    }

    stat_key = STAT_MAP.get(stat_type.lower(), stat_type)

    # Try ESPN leaders endpoint
    endpoints = [
        BASE + "/" + sport + "/" + lg + "/leaders",
        "https://site.web.api.espn.com/apis/v2/sports/" + sport + "/" + lg + "/leaders",
    ]

    for endpoint in endpoints:
        data = safe_get(endpoint)
        print("LEADERS endpoint:", endpoint, "keys:", list(data.keys()) if data else "None", flush=True)
        if not data:
            continue
        categories = data.get("categories", [])
        print("LEADERS categories count:", len(categories), [c.get("name","") for c in categories[:5]], flush=True)
        for cat in categories:
            name = cat.get("name","").lower()
            disp = cat.get("displayName","")
            if stat_key.lower() in name or stat_key.lower() in disp.lower():
                leaders = cat.get("leaders", [])
                if not leaders:
                    continue
                msgs = [league.upper() + " " + disp + " leaders:"]
                for i, leader in enumerate(leaders[:10], 1):
                    aname = leader.get("athlete", {}).get("displayName","?")
                    val   = leader.get("displayValue", leader.get("value","?"))
                    team  = leader.get("team", {}).get("abbreviation","")
                    line  = str(i) + ". " + aname
                    if team: line += " (" + team + ")"
                    line += ": " + str(val)
                    msgs.append(line)
                return msgs

        # If specific stat not found, return all available categories
        if categories:
            msgs = [league.upper() + " stat leaders:"]
            for cat in categories[:8]:
                disp    = cat.get("displayName","")
                leaders = cat.get("leaders", [])
                if leaders and disp:
                    top     = leaders[0]
                    aname   = top.get("athlete", {}).get("displayName","?")
                    val     = top.get("displayValue","?")
                    team    = top.get("team", {}).get("abbreviation","")
                    line    = disp + ": " + aname
                    if team: line += " (" + team + ")"
                    line += " " + str(val)
                    msgs.append(line)
            return msgs

    # Use sport-specific APIs
    if league == "nhl":
        result = get_nhl_leaders(stat_type)
        if result:
            return result
    elif league == "mlb":
        result = get_mlb_leaders(stat_type)
        if result:
            return result
    elif league == "nfl":
        result = get_nfl_leaders(stat_type)
        if result:
            return result
    elif league == "nba":
        result = get_nba_leaders_bdl(stat_type)
        if result:
            return result

    return [league.upper() + " " + stat_type + " leaders not available."]


def get_nba_leaders_bdl(stat_type):
    """NBA stat leaders via balldontlie.io (requires free API key)."""
    STAT_MAP = {
        "points":"pts","pts":"pts",
        "rebounds":"reb","reb":"reb",
        "assists":"ast","ast":"ast",
        "steals":"stl","stl":"stl",
        "blocks":"blk","blk":"blk",
    }
    key = STAT_MAP.get(stat_type.lower(), "pts")
    BDL_KEY = os.environ.get("BALLDONTLIE_KEY","")
    print("BDL leaders key present:", bool(BDL_KEY), flush=True)
    if not BDL_KEY:
        return ["NBA leaders: set BALLDONTLIE_KEY in Render."]
    try:
        data = safe_get(
            "https://api.balldontlie.io/v1/season_averages",
            params={"season": 2024, "per_page": 100},
            headers={"Authorization": BDL_KEY}
        )
        print("BDL leaders data:", type(data), flush=True)
        if not data:
            return None
        players = sorted(
            [p for p in data.get("data",[]) if p.get(key) is not None],
            key=lambda x: float(x.get(key,0)),
            reverse=True
        )[:10]
        if not players:
            return None
        msgs = ["NBA " + key.upper() + " leaders:"]
        for i, p in enumerate(players, 1):
            name = p.get("player",{}).get("last_name","?") + " " + p.get("player",{}).get("first_name","?")[0]
            team = p.get("team",{}).get("abbreviation","")
            val  = p.get(key,"?")
            msgs.append(str(i) + ". " + name + " (" + team + "): " + str(val))
        return msgs
    except Exception:
        return None


def get_nhl_leaders(stat_type="points"):
    """NHL stat leaders via official NHL API (no key needed)."""
    STAT_MAP = {
        "points":"points","pts":"points",
        "goals":"goals","g":"goals",
        "assists":"assists","a":"assists",
        "plusminus":"plusMinus","pm":"plusMinus",
        "wins":"wins","w":"wins",
        "gaa":"goalsAgainstAverage",
        "savepct":"savePctg","sv":"savePctg",
        "shutouts":"shutouts",
    }
    cat = STAT_MAP.get(stat_type.lower(), stat_type.lower())
    try:
        import urllib.request, json as _json
        url = "https://api-web.nhle.com/v1/skater-stats-leaders/current?categories=" + cat + "&limit=10"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read().decode())
        print("NHL leaders data keys:", list(data.keys()) if isinstance(data, dict) else type(data), flush=True)
        if isinstance(data, dict) and cat in data:
            leaders = data[cat]
            msgs = ["NHL " + cat + " leaders:"]
            for i, p in enumerate(leaders[:10], 1):
                fname = p.get("firstName",{}).get("default","") if isinstance(p.get("firstName"), dict) else str(p.get("firstName",""))
                lname = p.get("lastName",{}).get("default","") if isinstance(p.get("lastName"), dict) else str(p.get("lastName",""))
                tobj  = p.get("teamAbbrev",{})
                team  = tobj.get("default","") if isinstance(tobj, dict) else str(tobj)
                val   = p.get("value", p.get(cat,"?"))
                msgs.append(str(i) + ". " + fname + " " + lname + " (" + team + "): " + str(val))
            return msgs
        # Try all keys to find leaders
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, list) and len(v) > 0:
                    msgs = ["NHL " + k + " leaders:"]
                    for i, p in enumerate(v[:10], 1):
                        fname = p.get("firstName",{}).get("default","") if isinstance(p.get("firstName"), dict) else str(p.get("firstName",""))
                        lname = p.get("lastName",{}).get("default","") if isinstance(p.get("lastName"), dict) else str(p.get("lastName",""))
                        tobj  = p.get("teamAbbrev",{})
                        team  = tobj.get("default","") if isinstance(tobj, dict) else str(tobj)
                        val   = p.get("value","?")
                        msgs.append(str(i) + ". " + fname + " " + lname + " (" + team + "): " + str(val))
                    return msgs
    except Exception as e:
        print("NHL leaders error:", e, flush=True)
    return None


def get_mlb_leaders(stat_type="homeRuns"):
    """MLB stat leaders via official MLB Stats API (no key needed)."""
    STAT_MAP = {
        "hr":"homeRuns","homeruns":"homeRuns","homeRuns":"homeRuns",
        "avg":"battingAverage","average":"battingAverage",
        "rbi":"runsBattedIn","rbis":"runsBattedIn",
        "sb":"stolenBases","stolenbases":"stolenBases",
        "era":"earnedRunAverage","wins":"wins","w":"wins",
        "strikeouts":"strikeouts","so":"strikeouts","k":"strikeouts",
        "saves":"saves","sv":"saves",
        "hits":"hits","h":"hits",
        "runs":"runs","r":"runs",
    }
    cat = STAT_MAP.get(stat_type.lower(), stat_type)
    try:
        # Hitting leaders
        from datetime import datetime as _dt
        cur_year = _dt.now().year
        season   = cur_year if _dt.now().month >= 4 else cur_year - 1
        data = safe_get(
            "https://statsapi.mlb.com/api/v1/stats/leaders",
            params={
                "leaderCategories": cat,
                "season": season,
                "limit": 10,
                "statGroup": "hitting",
                "sportId": 1,
            }
        )
        if data:
            cats = data.get("leagueLeaders", [])
            if cats:
                leaders = cats[0].get("leaders", [])
                if leaders:
                    msgs = ["MLB " + cat + " (" + str(season) + "):"]
                    for i, p in enumerate(leaders, 1):
                        name = p.get("person",{}).get("fullName","?")
                        team = p.get("team",{}).get("abbreviation","")
                        val  = p.get("value","?")
                        msgs.append(str(i) + ". " + name + " (" + team + "): " + str(val))
                    return msgs
        # Try pitching
        data2 = safe_get(
            "https://statsapi.mlb.com/api/v1/stats/leaders",
            params={
                "leaderCategories": cat,
                "season": season,
                "limit": 10,
                "statGroup": "pitching",
                "sportId": 1,
            }
        )
        if data2:
            cats2 = data2.get("leagueLeaders", [])
            if cats2:
                leaders2 = cats2[0].get("leaders", [])
                if leaders2:
                    msgs = ["MLB " + cat + " (" + str(season) + "):"]
                    for i, p in enumerate(leaders2, 1):
                        name = p.get("person",{}).get("fullName","?")
                        team = p.get("team",{}).get("abbreviation","")
                        val  = p.get("value","?")
                        msgs.append(str(i) + ". " + name + " (" + team + "): " + str(val))
                    return msgs
    except Exception as e:
        print("MLB leaders error:", e, flush=True)
    return None


def get_nfl_leaders(stat_type="passing"):
    """NFL stat leaders - uses 2024 season (most recent completed)."""
    STAT_MAP = {
        "passing":"passing","passyards":"passing",
        "rushing":"rushing","rushyards":"rushing",
        "receiving":"receiving","recyards":"receiving",
        "touchdowns":"scoring","td":"scoring",
        "sacks":"defense","interceptions":"defense","int":"defense",
        "tackles":"defense","defense":"defense",
    }
    cat = STAT_MAP.get(stat_type.lower(), "passing")
    try:
        # Try ESPN season leaders with year
        for season in ["2025","2024"]:
            url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/leaders?season=" + season
            data = safe_get(url)
            print("NFL leaders season", season, "keys:", list(data.keys()) if data else "None", flush=True)
            if not data:
                continue
            categories = data.get("categories", [])
            print("NFL categories:", [c.get("name","") for c in categories[:5]], flush=True)
            for c in categories:
                cname = c.get("name","").lower()
                cdisp = c.get("displayName","").lower()
                if cat.lower() in cname or cat.lower() in cdisp or stat_type.lower() in cname:
                    leaders = c.get("leaders",[])
                    if leaders:
                        msgs = ["NFL " + c.get("displayName",cat) + " (" + season + "):"]
                        for i, l in enumerate(leaders[:10], 1):
                            aname = l.get("athlete",{}).get("displayName","?")
                            team  = l.get("team",{}).get("abbreviation","")
                            val   = l.get("displayValue","?")
                            msgs.append(str(i) + ". " + aname + " (" + team + "): " + val)
                        return msgs
            if categories:
                msgs = ["NFL leaders (" + season + "):"]
                for c in categories[:8]:
                    leaders = c.get("leaders",[])
                    if leaders:
                        top   = leaders[0]
                        aname = top.get("athlete",{}).get("displayName","?")
                        val   = top.get("displayValue","?")
                        team  = top.get("team",{}).get("abbreviation","")
                        disp  = c.get("displayName","")
                        msgs.append(disp + ": " + aname + " (" + team + ") " + val)
                if len(msgs) > 1:
                    return msgs
    except Exception as e:
        print("NFL leaders error:", e, flush=True)
    return None


# -- Championship / futures odds -----------------------------------------------
def get_odds(league, odds_type="championship"):
    sport, lg = SPORT_MAP[league]

    SPORT_KEYS = {
        "nhl": "icehockey_nhl_championship_winner",
        "nba": "basketball_nba_championship_winner",
        "nfl": "americanfootball_nfl_super_bowl_winner",
        "mlb": "baseball_mlb_world_series_winner",
    }

    ODDS_KEY = os.environ.get("ODDS_API_KEY","")
    if not ODDS_KEY:
        return [league.upper() + " odds: add ODDS_API_KEY to Render env vars."]

    sport_key = SPORT_KEYS.get(league)
    if not sport_key:
        return [league.upper() + " odds not available."]

    # Try both the specific futures key and the general sport key
    keys_to_try = [sport_key, sport_key.replace("_super_bowl_winner","").replace("_championship_winner","").replace("_world_series_winner","")]
    odds_data = None
    for sk in keys_to_try:
        odds_data = safe_get(
            "https://api.the-odds-api.com/v4/sports/" + sk + "/odds",
            params={
                "apiKey": ODDS_KEY,
                "regions": "us",
                "markets": "outrights",
                "oddsFormat": "american",
            }
        )
        print("Odds API:", sk, "result:", type(odds_data), len(odds_data) if isinstance(odds_data, list) else odds_data, flush=True)
        if odds_data and isinstance(odds_data, list) and len(odds_data) > 0:
            break

    if odds_data and isinstance(odds_data, list) and len(odds_data) > 0:
        msgs = [league.upper() + " " + odds_type.title() + " Odds:"]
        seen = {}
        for event in odds_data:
            for bookmaker in event.get("bookmakers", [])[:1]:
                for market in bookmaker.get("markets", []):
                    for outcome in market.get("outcomes", []):
                        name  = outcome.get("name","?")
                        price = outcome.get("price","?")
                        if name not in seen:
                            seen[name] = price
        sorted_odds = sorted(seen.items(), key=lambda x: float(x[1]) if isinstance(x[1],(int,float)) else 9999)
        for name, price in sorted_odds[:12]:
            prefix = "+" if isinstance(price,(int,float)) and price > 0 else ""
            msgs.append(name + ": " + prefix + str(price))
        if len(msgs) > 1:
            return msgs

    if league == "nfl":
        return ["NFL Super Bowl odds not available.", "Try during the season (Sep-Feb)."]
    return [league.upper() + " odds not available right now."]


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


def get_league_leaders(league, stat_type="points"):
    return _cached("leaders-" + league + "-" + stat_type, CACHE_LONG,
                   lambda: get_stat_leaders(league, stat_type))

def get_league_odds(league, odds_type="championship"):
    return _cached("odds-" + league + "-" + odds_type, 3600,
                   lambda: get_odds(league, odds_type))

    return _cached(key, ttl, fetch)
