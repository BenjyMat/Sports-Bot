"""
espn.py -- Sports data fetcher
Uses ESPN, NHL API, MLB Stats API, stats.nba.com, The Odds API
"""

import requests, os
from datetime import datetime, timezone, timedelta
import time as _time

BASE    = "https://site.api.espn.com/apis/site/v2/sports"
WEBBASE = "https://site.web.api.espn.com/apis/v2/sports"
TIMEOUT = 25
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
    data = safe_get("https://site.api.espn.com/apis/v2/sports/" + sport + "/" + lg + "/playoff-bracket")
    if not data:
        data = safe_get(WEBBASE + "/" + sport + "/" + lg + "/playoff-bracket")
    if not data:
        return [league.upper() + " bracket not available yet."]
    msgs   = []
    rounds = data.get("rounds", data.get("bracket", {}).get("rounds", []))
    for rnd in rounds:
        rnd_name = rnd.get("name", rnd.get("displayName", "Round"))
        msgs.append("-- " + rnd_name + " --")
        for series in rnd.get("series", rnd.get("matchups", [])):
            t1  = series.get("competitors", [{}])[0]
            t2  = series.get("competitors", [{}])[1] if len(series.get("competitors", [])) > 1 else {}
            n1  = t1.get("team", {}).get("abbreviation", "?")
            n2  = t2.get("team", {}).get("abbreviation", "?")
            w1  = str(t1.get("wins", 0))
            w2  = str(t2.get("wins", 0))
            msgs.append(n1 + "(" + w1 + ") vs " + n2 + "(" + w2 + ")")
    return msgs or [league.upper() + " playoffs not started yet."]


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
                pts  = stats.get("points",   stats.get("pts", "?"))
                wins = stats.get("wins",     stats.get("w",   "?"))
                loss = stats.get("losses",   stats.get("l",   "?"))
                otl  = stats.get("otLosses", stats.get("ot",  stats.get("otl", "?")))
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
    if category == "league_scores":   return get_league_scores(league)
    if category == "league_schedule": return get_league_schedule(league)
    if category == "league_news":     return get_league_news(league)
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


# -- Check game finished (for alerts) -----------------------------------------
def check_game_finished(league, team_id):
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


# -- NHL stat leaders (official NHL API) ---------------------------------------
def get_nhl_leaders(stat_type="points"):
    NHL_CATS = {
        "points":"points","pts":"points","scoring":"points",
        "goals":"goals","g":"goals","goal":"goals",
        "assists":"assists","a":"assists",
        "plusminus":"plusMinus","pm":"plusMinus",
        "wins":"wins","w":"wins",
        "gaa":"goalsAgainstAverage","savepct":"savePctg","sv":"savePctg",
        "shutouts":"shutouts",
    }
    cat       = NHL_CATS.get(stat_type.lower(), "points")
    is_goalie = cat in ("goalsAgainstAverage", "savePctg", "wins", "shutouts")
    try:
        import urllib.request, json as _json
        base_url = "https://api-web.nhle.com/v1/"
        if is_goalie:
            url = base_url + "goalie-stats-leaders/current?categories=" + cat + "&limit=10"
        else:
            url = base_url + "skater-stats-leaders/current?categories=" + cat + "&limit=10"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read().decode())
        if not isinstance(data, dict):
            return None
        target  = cat if cat in data else "points"
        leaders = data.get(target, [])
        if not leaders:
            return None
        label = target
        msgs  = ["NHL " + label + " leaders:"]
        for i, p in enumerate(leaders[:10], 1):
            fname = p.get("firstName", {}).get("default", "") if isinstance(p.get("firstName"), dict) else str(p.get("firstName", ""))
            lname = p.get("lastName",  {}).get("default", "") if isinstance(p.get("lastName"),  dict) else str(p.get("lastName",  ""))
            tobj  = p.get("teamAbbrev", {})
            team  = tobj.get("default", "") if isinstance(tobj, dict) else str(tobj)
            val   = p.get("value", p.get(target, "?"))
            msgs.append(str(i) + ". " + fname + " " + lname + " (" + team + "): " + str(val))
        return msgs
    except Exception as e:
        print("NHL leaders error for cat=" + cat + ":", e, flush=True)
        # fallback to points
        if cat != "points":
            try:
                import urllib.request, json as _json
                url = "https://api-web.nhle.com/v1/skater-stats-leaders/current?categories=points&limit=10"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = _json.loads(resp.read().decode())
                if isinstance(data, dict) and "points" in data:
                    leaders = data["points"]
                    msgs = ["NHL points leaders:"]
                    for i, p in enumerate(leaders[:10], 1):
                        fname = p.get("firstName", {}).get("default", "") if isinstance(p.get("firstName"), dict) else str(p.get("firstName", ""))
                        lname = p.get("lastName",  {}).get("default", "") if isinstance(p.get("lastName"),  dict) else str(p.get("lastName",  ""))
                        tobj  = p.get("teamAbbrev", {})
                        team  = tobj.get("default", "") if isinstance(tobj, dict) else str(tobj)
                        val   = p.get("value", "?")
                        msgs.append(str(i) + ". " + fname + " " + lname + " (" + team + "): " + str(val))
                    return msgs
            except Exception:
                pass
    return None


# -- MLB stat leaders (official MLB Stats API) ---------------------------------
def get_mlb_leaders(stat_type="homeRuns"):
    STAT_MAP = {
        "hr":"homeRuns","homeruns":"homeRuns",
        "avg":"battingAverage","average":"battingAverage","batting":"battingAverage",
        "rbi":"runsBattedIn","rbis":"runsBattedIn",
        "sb":"stolenBases","stolenbases":"stolenBases",
        "era":"earnedRunAverage","wins":"wins","w":"wins",
        "strikeouts":"strikeouts","so":"strikeouts","k":"strikeouts",
        "saves":"saves","sv":"saves",
        "hits":"hits","h":"hits",
        "runs":"runs","r":"runs",
    }
    cat = STAT_MAP.get(stat_type.lower(), stat_type)
    print("MLB leaders: stat_type=" + stat_type + " cat=" + cat, flush=True)
    from datetime import datetime as _dt
    cur_year = _dt.now().year
    season   = cur_year if _dt.now().month >= 4 else cur_year - 1
    print("MLB season:", season, flush=True)
    try:
        data = safe_get(
            "https://statsapi.mlb.com/api/v1/stats/leaders",
            params={"leaderCategories": cat, "season": season, "limit": 10, "statGroup": "hitting", "sportId": 1}
        )
        if data:
            cats = data.get("leagueLeaders", [])
            if cats:
                leaders = cats[0].get("leaders", [])
                if leaders:
                    msgs = ["MLB " + cat + " (" + str(season) + "):"]
                    for i, p in enumerate(leaders, 1):
                        name = p.get("person", {}).get("fullName", "?")
                        team = p.get("team",   {}).get("abbreviation", "")
                        val  = p.get("value",  "?")
                        msgs.append(str(i) + ". " + name + " (" + team + "): " + str(val))
                    return msgs
        data2 = safe_get(
            "https://statsapi.mlb.com/api/v1/stats/leaders",
            params={"leaderCategories": cat, "season": season, "limit": 10, "statGroup": "pitching", "sportId": 1}
        )
        if data2:
            cats2 = data2.get("leagueLeaders", [])
            if cats2:
                leaders2 = cats2[0].get("leaders", [])
                if leaders2:
                    msgs = ["MLB " + cat + " (" + str(season) + "):"]
                    for i, p in enumerate(leaders2, 1):
                        name = p.get("person", {}).get("fullName", "?")
                        team = p.get("team",   {}).get("abbreviation", "")
                        val  = p.get("value",  "?")
                        msgs.append(str(i) + ". " + name + " (" + team + "): " + str(val))
                    return msgs
    except Exception as e:
        print("MLB leaders error:", e, flush=True)
    return None


# -- NFL stat leaders ----------------------------------------------------------
def get_nfl_leaders(stat_type="passing"):
    try:
        for season in ["2025", "2024"]:
            url  = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/leaders?season=" + season
            data = safe_get(url)
            if not data:
                continue
            categories = data.get("categories", [])
            for c in categories:
                cname = c.get("name", "").lower()
                cdisp = c.get("displayName", "").lower()
                if stat_type.lower() in cname or stat_type.lower() in cdisp:
                    leaders = c.get("leaders", [])
                    if leaders:
                        msgs = ["NFL " + c.get("displayName", stat_type) + " (" + season + "):"]
                        for i, l in enumerate(leaders[:10], 1):
                            aname = l.get("athlete", {}).get("displayName", "?")
                            team  = l.get("team",    {}).get("abbreviation", "")
                            val   = l.get("displayValue", "?")
                            msgs.append(str(i) + ". " + aname + " (" + team + "): " + val)
                        return msgs
            if categories:
                msgs = ["NFL leaders (" + season + "):"]
                for c in categories[:8]:
                    leaders = c.get("leaders", [])
                    if leaders:
                        top   = leaders[0]
                        aname = top.get("athlete", {}).get("displayName", "?")
                        val   = top.get("displayValue", "?")
                        team  = top.get("team", {}).get("abbreviation", "")
                        disp  = c.get("displayName", "")
                        msgs.append(disp + ": " + aname + " (" + team + ") " + val)
                if len(msgs) > 1:
                    return msgs
    except Exception as e:
        print("NFL leaders error:", e, flush=True)
    return None


# -- NBA stat leaders (stats.nba.com) -----------------------------------------
def get_nba_leaders_bdl(stat_type):
    STAT_MAP = {
        "points":"PTS","pts":"PTS","scoring":"PTS",
        "rebounds":"REB","reb":"REB",
        "assists":"AST","ast":"AST",
        "steals":"STL","stl":"STL",
        "blocks":"BLK","blk":"BLK",
        "fg":"FG_PCT","3p":"FG3_PCT","ft":"FT_PCT",
    }
    stat_col = STAT_MAP.get(stat_type.lower(), "PTS")
    try:
        import urllib.request, json as _json
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer":    "https://www.nba.com/",
            "Origin":     "https://www.nba.com",
            "Accept":     "application/json",
        }
        url = ("https://stats.nba.com/stats/leagueleaders"
               "?LeagueID=00&PerMode=PerGame&Scope=S&Season=2024-25"
               "&SeasonType=Regular+Season&StatCategory=" + stat_col)
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = _json.loads(resp.read().decode())
        result = data["resultSet"]
        cols   = result["headers"]
        rows   = result["rowSet"]
        print("NBA leaders:", stat_col, len(rows), "players", flush=True)
        if not rows:
            return None
        rank_idx = cols.index("RANK")   if "RANK"   in cols else 0
        name_idx = cols.index("PLAYER") if "PLAYER" in cols else 1
        team_idx = cols.index("TEAM")   if "TEAM"   in cols else 2
        stat_idx = cols.index(stat_col) if stat_col in cols else 3
        msgs = ["NBA " + stat_col + "/g leaders:"]
        for row in rows[:10]:
            msgs.append(str(row[rank_idx]) + ". " + str(row[name_idx]) + " (" + str(row[team_idx]) + "): " + str(row[stat_idx]))
        return msgs if len(msgs) > 1 else None
    except Exception as e:
        print("NBA leaders stats.nba error:", e, flush=True)
        return None


# -- NBA player stats (stats.nba.com) -----------------------------------------
def get_nba_player_stats(player_name):
    try:
        import urllib.request, json as _json
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer":    "https://www.nba.com/",
            "Origin":     "https://www.nba.com",
            "Accept":     "application/json",
        }
        url = "https://stats.nba.com/stats/commonallplayers?LeagueID=00&Season=2024-25&IsOnlyCurrentSeason=1"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read().decode())
        rows         = data["resultSets"][0]["rowSet"]
        headers_list = data["resultSets"][0]["headers"]
        pid_idx      = headers_list.index("PERSON_ID")
        name_idx     = headers_list.index("DISPLAY_FIRST_LAST")
        query        = player_name.lower()
        player_id    = None
        full_name    = None
        for row in rows:
            if query in row[name_idx].lower():
                player_id = row[pid_idx]
                full_name = row[name_idx]
                break
        if not player_id:
            return None
        stats_url = "https://stats.nba.com/stats/playercareerstats?PlayerID=" + str(player_id) + "&PerMode=PerGame"
        req2 = urllib.request.Request(stats_url, headers=headers)
        with urllib.request.urlopen(req2, timeout=10) as resp2:
            sdata = _json.loads(resp2.read().decode())
        result_set = sdata["resultSets"][0]
        col        = result_set["headers"]
        rows2      = result_set["rowSet"]
        if not rows2:
            return None
        row    = rows2[-1]
        def v(key):
            try:    return row[col.index(key)]
            except: return "?"
        season = v("SEASON_ID")
        gp     = v("GP")
        pts    = v("PTS")
        reb    = v("REB")
        ast    = v("AST")
        stl    = v("STL")
        blk    = v("BLK")
        fg     = v("FG_PCT")
        fg3    = v("FG3_PCT")
        ft     = v("FT_PCT")
        mins   = v("MIN")
        return [
            full_name + " " + str(season) + " (" + str(gp) + " GP):",
            "PTS:" + str(pts) + " REB:" + str(reb) + " AST:" + str(ast),
            "STL:" + str(stl) + " BLK:" + str(blk) + " MIN:" + str(mins),
            "FG:" + str(fg) + " 3P:" + str(fg3) + " FT:" + str(ft),
        ]
    except Exception as e:
        print("NBA stats.nba.com error:", e, flush=True)
        return None

def get_balldontlie_stats(player_name):
    return get_nba_player_stats(player_name)


# -- Stat leaders dispatcher ---------------------------------------------------
def get_stat_leaders(league, stat_type="points"):
    if league == "nhl":
        result = get_nhl_leaders(stat_type)
    elif league == "mlb":
        result = get_mlb_leaders(stat_type)
    elif league == "nfl":
        result = get_nfl_leaders(stat_type)
    elif league == "nba":
        result = get_nba_leaders_bdl(stat_type)
    else:
        result = None
    return result or [league.upper() + " " + stat_type + " leaders not available."]


# -- Championship odds (The Odds API) -----------------------------------------
def get_odds(league, odds_type="championship"):
    SPORT_KEYS = {
        "nhl": "icehockey_nhl_championship_winner",
        "nba": "basketball_nba_championship_winner",
        "nfl": "americanfootball_nfl_super_bowl_winner",
        "mlb": "baseball_mlb_world_series_winner",
    }
    ODDS_KEY  = os.environ.get("ODDS_API_KEY", "")
    if not ODDS_KEY:
        return [league.upper() + " odds: add ODDS_API_KEY to Render env vars."]
    sport_key = SPORT_KEYS.get(league)
    if not sport_key:
        return [league.upper() + " odds not available."]
    keys_to_try = [sport_key]
    if league == "nfl":
        keys_to_try = ["americanfootball_nfl_super_bowl_winner", "americanfootball_nfl"]
    odds_data = None
    for sk in keys_to_try:
        odds_data = safe_get(
            "https://api.the-odds-api.com/v4/sports/" + sk + "/odds",
            params={"apiKey": ODDS_KEY, "regions": "us", "markets": "outrights", "oddsFormat": "american"}
        )
        print("Odds API:", sk, "result:", type(odds_data), len(odds_data) if isinstance(odds_data, list) else odds_data, flush=True)
        if odds_data and isinstance(odds_data, list) and len(odds_data) > 0:
            break
    if not (odds_data and isinstance(odds_data, list) and len(odds_data) > 0):
        return [league.upper() + " odds not available right now."]
    msgs = [league.upper() + " " + odds_type.title() + " Odds:"]
    seen = {}
    for event in odds_data:
        for bookmaker in event.get("bookmakers", [])[:1]:
            for market in bookmaker.get("markets", []):
                for outcome in market.get("outcomes", []):
                    name  = outcome.get("name",  "?")
                    price = outcome.get("price", "?")
                    if name not in seen:
                        seen[name] = price
    sorted_odds = sorted(seen.items(), key=lambda x: float(x[1]) if isinstance(x[1], (int, float)) else 9999)
    for name, price in sorted_odds[:12]:
        prefix = "+" if isinstance(price, (int, float)) and price > 0 else ""
        msgs.append(name + ": " + prefix + str(price))
    return msgs if len(msgs) > 1 else [league.upper() + " odds not available right now."]


def get_league_leaders(league, stat_type="points"):
    return _cached("leaders-" + league + "-" + stat_type, CACHE_LONG, lambda: get_stat_leaders(league, stat_type))

def get_league_odds(league, odds_type="championship"):
    return _cached("odds-" + league + "-" + odds_type, 3600, lambda: get_odds(league, odds_type))


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


# -- Player lookup (scans rosters) --------------------------------------------
def get_player(league, player_name):
    sport, lg = SPORT_MAP[league]
    query     = player_name.lower().strip()
    teams     = _get_teams_raw(league)
    if not teams:
        return ["Could not load teams."]
    found_pid  = None
    found_name = None
    found_pos  = None
    found_jer  = None
    found_team = None
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
    msgs   = [header]
    if league == "nba":
        nba_stats = get_nba_player_stats(found_name)
        if nba_stats:
            msgs.extend(nba_stats[1:])
            return msgs
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
                if sname and sval and sval not in ("0", "0.0", "--", "", "null"):
                    stat_bits.append(sname + ":" + sval)
            if stat_bits:
                cname = cat.get("displayName") or cat.get("name") or ""
                msgs.append(cname + ": " + " ".join(stat_bits))
    if len(msgs) == 1:
        msgs.append("Season stats unavailable.")
        msgs.append("For game stats: " + league + " " + found_team.split()[-1].lower() + " s")
        msgs.append("then: info")
    return msgs
