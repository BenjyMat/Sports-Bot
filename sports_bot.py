"""
sports_bot.py -- GroupMe Sports Bot
SMS optimized. No emojis. Works on any basic phone.
"""

from flask import Flask, request, jsonify
import os, requests, espn, threading, time

app = Flask(__name__)

BOT_ID       = os.environ.get("GROUPME_BOT_ID",       "YOUR_BOT_ID_HERE")
ACCESS_TOKEN = os.environ.get("GROUPME_ACCESS_TOKEN", "YOUR_TOKEN_HERE")

sessions   = {}
bans       = {}
favorites  = {}
alerts     = {}      # { user_id: [(league, team_id, team_name), ...] }
alert_sent = {}      # { league+team_id: last_final_score } prevent repeat alerts

PRANK_USER  = "18483671827"
PRANK_ASKED = set()
MSG_LIMIT   = 155

LEAGUES = {
    "1":"nhl","2":"nba","3":"nfl","4":"mlb",
    "nhl":"nhl","nba":"nba","nfl":"nfl","mlb":"mlb",
    "hockey":"nhl","basketball":"nba","football":"nfl","baseball":"mlb"
}
CATEGORIES = {
    "1":"scores",      "s":"scores",
    "2":"schedule",    "sc":"schedule",
    "3":"roster",      "r":"roster",
    "4":"news",        "n":"news",
    "5":"standings",   "st":"standings",
    "6":"injuries",    "i":"injuries",
    "7":"transactions","t":"transactions",
    "8":"homeaway",    "ha":"homeaway",
    "scores":"scores","schedule":"schedule","roster":"roster",
    "news":"news","standings":"standings","injuries":"injuries",
    "transactions":"transactions","homeaway":"homeaway",
    "home":"homeaway","away":"homeaway","record":"homeaway",
}
LEAGUE_CATS = {
    "1":"league_scores","scores":"league_scores","s":"league_scores",
    "2":"league_schedule","schedule":"league_schedule","sc":"league_schedule",
    "3":"league_news","news":"league_news","n":"league_news",
}

WELCOME = (
    "SPORTS BOT\n"
    "----------\n"
    "Pick a league:\n"
    "1.NHL 2.NBA\n"
    "3.NFL 4.MLB\n"
    "Or type league name.\n"
    "Text !CMDS for shortcuts."
)

CATEGORY_MENU = (
    "1.Scores  2.Schedule\n"
    "3.Roster  4.News\n"
    "5.Standings 6.Injuries\n"
    "7.Transactions 8.H/A Record"
)

LEAGUE_CAT_MENU = (
    "WHOLE LEAGUE:\n"
    "1.Scores 2.Schedule 3.News"
)

AFTER_MENU = "1.Same 2.NewTeam 3.NewLeague"

COMMANDS_MSG = (
    "!CMDS - SHORTCUTS\n"
    "-----------------\n"
    "QUICK: nba lakers s\n"
    "  leagues: nhl nba nfl mlb\n"
    "  cats: s sc r n st\n"
    "        i t ha\n"
    "        (scores schedule\n"
    "         roster news\n"
    "         standings injuries\n"
    "         transactions\n"
    "         home/away record)\n"
    "\n"
    "PLAYER: nba lebron james\n"
    "H2H: nhl bos vs tor\n"
    "BRACKET: nhl bracket\n"
    "\n"
    "ALERTS:\n"
    "ALERT nba lakers - on\n"
    "ALERTS - list yours\n"
    "DELALERT nba lakers - off\n"
    "\n"
    "FAVS:\n"
    "FAV - set favorites\n"
    "MY  - use favorite\n"
    "\n"
    "OTHER:\n"
    "LAST - repeat last result\n"
    "0    - whole league view\n"
    "INFO - score details\n"
    "MENU - restart"
)


# -- Messaging -----------------------------------------------------------------
def send_group(text):
    for _ in range(2):
        try:
            r = requests.post(
                "https://api.groupme.com/v3/bots/post",
                json={"bot_id": BOT_ID, "text": text},
                timeout=10,
            )
            if r.status_code == 202:
                return True
        except Exception:
            pass
    return False

def chunk_message(text):
    if len(text) <= MSG_LIMIT:
        return [text]
    parts   = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > MSG_LIMIT:
            if current:
                parts.append(current.strip())
            current = line
        else:
            current = current + "\n" + line if current else line
    if current:
        parts.append(current.strip())
    return parts

def reply(user_id, text):
    for i, chunk in enumerate(chunk_message(text)):
        if i > 0:
            time.sleep(2)
        send_group(chunk)

def send_results(user_id, result, s):
    uname = s.get("name", "Someone")
    tag   = "[" + uname + "]"
    NL    = "\n"
    combined = []
    current  = tag
    for msg in result:
        candidate = (tag + " " + msg) if current == tag else (current + NL + msg)
        if len(candidate) <= MSG_LIMIT:
            current = candidate
        else:
            if current != tag:
                combined.append(current)
            current = msg
    if current and current != tag:
        combined.append(current)
    for i, msg in enumerate(combined):
        if i > 0:
            time.sleep(3)
        reply(user_id, msg)
    # Store last result for LAST command
    s["last_result"] = result
    time.sleep(3)
    reply(user_id, AFTER_MENU)


# -- Session -------------------------------------------------------------------
def session(uid):
    if uid not in sessions:
        sessions[uid] = {"step": "LEAGUE"}
    return sessions[uid]

def reset(uid):
    sessions[uid] = {"step": "LEAGUE"}


# -- Team helpers --------------------------------------------------------------
def team_abbrev_list(teams):
    chunks  = []
    current = ""
    for i, t in enumerate(teams):
        abbrev = t.get("abbrev", t["name"][:3].upper())
        entry  = str(i+1) + "." + abbrev + " "
        if len(current) + len(entry) > 140:
            chunks.append(current.strip())
            current = entry
        else:
            current += entry
    if current:
        chunks.append(current.strip())
    return chunks

def pick_team(text, teams):
    t = text.strip().lower()
    try:
        idx = int(t) - 1
        if 0 <= idx < len(teams):
            return teams[idx]
    except ValueError:
        pass
    for team in teams:
        if t == team.get("abbrev", "").lower():
            return team
    for team in teams:
        if t in team["name"].lower():
            return team
    return None


# -- Quick command parser ------------------------------------------------------
_teams_cache = {}

def parse_quick_command(tl):
    words = tl.split()
    if len(words) < 2:
        return None

    result = {"league": None, "team": None, "category": None,
              "info": False, "player": None, "h2h": None, "bracket": False}

    # Check bracket
    if "bracket" in words:
        lg = LEAGUES.get(words[0])
        if lg:
            result["league"]  = lg
            result["bracket"] = True
            return result

    # Check h2h: "nhl bos vs tor"
    if "vs" in words:
        try:
            vs_idx = words.index("vs")
            lg     = LEAGUES.get(words[0])
            if lg and vs_idx >= 2:
                team1_query = " ".join(words[1:vs_idx])
                team2_abbr  = words[vs_idx+1] if vs_idx+1 < len(words) else ""
                teams = _teams_cache.get(lg) or espn.get_teams(lg)
                if teams:
                    _teams_cache[lg] = teams
                    team1 = pick_team(team1_query, teams)
                    if team1 and team2_abbr:
                        result["league"] = lg
                        result["team"]   = team1
                        result["h2h"]    = team2_abbr
                        return result
        except Exception:
            pass

    # Check info at end
    if words[-1] in ("info", "details", "more"):
        result["info"] = True
        words = words[:-1]

    # Find league
    lg = LEAGUES.get(words[0])
    if not lg:
        return None
    result["league"] = lg

    # Find category
    for w in words[1:]:
        if w in CATEGORIES:
            result["category"] = CATEGORIES[w]

    # Find team or player
    non_league = [w for w in words[1:] if w not in CATEGORIES and w not in LEAGUES]
    if not non_league:
        return None

    query = " ".join(non_league)
    teams = _teams_cache.get(lg) or espn.get_teams(lg)
    if teams:
        _teams_cache[lg] = teams
        team = pick_team(query, teams)
        if team:
            result["team"] = team
        else:
            # Try as player name
            result["player"] = query

    return result


# -- Run with timeout ----------------------------------------------------------
def run_fetch(fn):
    holder = [None]
    def go():
        holder[0] = fn()
    t = threading.Thread(target=go)
    t.start()
    t.join(timeout=10)
    if t.is_alive():
        reply(None, "Still loading...")
        t.join(timeout=15)
    return holder[0]


# -- Alert checker (called by cron every minute) --------------------------------
@app.route("/check-alerts", methods=["GET"])
def check_alerts():
    for uid, alert_list in list(alerts.items()):
        for (league, team_id, team_name) in alert_list:
            key    = league + "-" + team_id
            result = espn.check_game_finished(league, team_id)
            if result and alert_sent.get(key) != result:
                alert_sent[key] = result
                send_group("[ALERT] " + result)
    return "ok", 200


# -- Webhook -------------------------------------------------------------------
@app.route("/groupme", methods=["POST"])
def groupme_webhook():
    data        = request.get_json(force=True)
    sender_type = data.get("sender_type", "")
    text        = data.get("text", "").strip()
    if sender_type == "bot" or not text:
        return jsonify({}), 200
    threading.Thread(
        target=handle_message,
        args=(data.get("user_id", ""), data),
        daemon=True
    ).start()
    return jsonify({}), 200


@app.route("/", methods=["GET"])
def health():
    return "Sports Bot is running!", 200


# -- Main handler --------------------------------------------------------------
def handle_message(user_id, data):
    text = data.get("text", "").strip()
    tl   = text.lower().strip()
    name = data.get("name", "Someone")

    if user_id:
        s = session(user_id)
        s["name"] = name

    # Ban check
    if user_id in bans:
        if time.time() < bans[user_id]:
            mins = int((bans[user_id] - time.time()) / 60) + 1
            reply(user_id, "Banned " + str(mins) + " more min.\nKnicks fan.")
            return
        else:
            del bans[user_id]

    # Prank
    phone      = data.get("sender_id", data.get("user_id", ""))
    normalized = phone.replace("+","").replace("-","").replace(" ","")
    if PRANK_USER in normalized or normalized in PRANK_USER:
        if user_id not in PRANK_ASKED:
            PRANK_ASKED.add(user_id)
            reply(user_id, "Answer one question:\nLakers or Knicks?")
            return
        elif any(x in tl for x in ("knicks","new york","ny")):
            bans[user_id] = time.time() + 3600
            PRANK_ASKED.discard(user_id)
            reply(user_id, "WRONG. Banned 1 hour.\nShame on you.")
            return
        elif any(x in tl for x in ("lakers","la lakers","los angeles lakers")):
            PRANK_ASKED.discard(user_id)
            reply(user_id, "Correct!\n\n" + WELCOME)
            return
        elif user_id in PRANK_ASKED:
            reply(user_id, "Lakers or Knicks?")
            return

    # Global commands
    if tl in ("menu","restart","reset","start","hi","hello"):
        reset(user_id)
        reply(user_id, WELCOME)
        return

    if tl in ("!help","!cmds","!commands","cmds","commands","shortcuts","help"):
        reply(user_id, HELP_1)
        time.sleep(3)
        reply(user_id, HELP_2)
        time.sleep(3)
        reply(user_id, HELP_3)
        time.sleep(3)
        reply(user_id, HELP_4)
        return

    if tl == "last":
        s = session(user_id)
        last = s.get("last_result")
        if last:
            send_results(user_id, last, s)
        else:
            reply(user_id, "No previous result.\nText MENU to start.")
        return

    # Alerts
    if tl == "alerts":
        s        = session(user_id)
        my_alerts = alerts.get(user_id, [])
        if not my_alerts:
            reply(user_id, "No alerts set.\nText: ALERT nba lakers")
        else:
            lines = ["Your alerts:"]
            for (lg, tid, tname) in my_alerts:
                lines.append(lg.upper() + " " + tname)
            reply(user_id, "\n".join(lines))
        return

    if tl.startswith("alert "):
        qc = parse_quick_command(tl[6:].strip())
        if qc and qc["team"]:
            if user_id not in alerts:
                alerts[user_id] = []
            entry = (qc["league"], qc["team"]["id"], qc["team"]["name"])
            if entry not in alerts[user_id]:
                alerts[user_id].append(entry)
            reply(user_id, "Alert set for " + qc["team"]["name"] + "!")
        else:
            reply(user_id, "Couldn't find that team.\nTry: ALERT nba lakers")
        return

    if tl.startswith("delalert "):
        qc = parse_quick_command(tl[9:].strip())
        if qc and qc["team"] and user_id in alerts:
            alerts[user_id] = [(l,t,n) for (l,t,n) in alerts[user_id] if t != qc["team"]["id"]]
            reply(user_id, "Alert removed for " + qc["team"]["name"] + ".")
        else:
            reply(user_id, "Couldn't find that team.")
        return

    # FAV
    if tl == "fav":
        favs = favorites.get(user_id, {})
        s    = session(user_id)
        s["step"] = "FAV_LEAGUE"
        reply(user_id,
            "Your favorites:\n"
            "NHL:" + favs.get("nhl",{}).get("name","not set") + "\n"
            "NBA:" + favs.get("nba",{}).get("name","not set") + "\n"
            "NFL:" + favs.get("nfl",{}).get("name","not set") + "\n"
            "MLB:" + favs.get("mlb",{}).get("name","not set") + "\n"
            "\nSet: 1.NHL 2.NBA 3.NFL 4.MLB"
        )
        return

    # MY
    if tl == "my":
        favs     = favorites.get(user_id, {})
        set_favs = [(lg, favs[lg]) for lg in ("nhl","nba","nfl","mlb") if favs.get(lg)]
        if not set_favs:
            reply(user_id, "No favorites set.\nText FAV to set them.")
            return
        lines = ["Your favorites:"]
        for i, (lg, team) in enumerate(set_favs, 1):
            lines.append(str(i) + ". " + lg.upper() + " " + team["name"])
        lines.append("Pick one.")
        s            = session(user_id)
        s["step"]    = "MY_PICK"
        s["my_favs"] = set_favs
        reply(user_id, "\n".join(lines))
        return

    # Quick command: starts with league name
    words = tl.split()
    if words and words[0] in LEAGUES and len(words) >= 2:
        qc = parse_quick_command(tl)
        if qc:
            s = session(user_id)

            # Bracket
            if qc["bracket"]:
                result = run_fetch(lambda: espn.get_bracket(qc["league"]))
                result = result or ["No bracket available."]
                s["step"] = "AGAIN"
                send_results(user_id, result, s)
                return

            # H2H
            if qc["h2h"] and qc["team"]:
                league = qc["league"]
                team   = qc["team"]
                h2h    = qc["h2h"]
                result = run_fetch(lambda: espn.get_head_to_head(league, team["id"], team["name"], h2h))
                result = result or ["No matchup data."]
                s["step"] = "AGAIN"
                send_results(user_id, result, s)
                return

            # Player lookup
            if qc["player"] and not qc["team"]:
                league = qc["league"]
                player = qc["player"]
                result = run_fetch(lambda: espn.get_player(league, player))
                result = result or ["Player not found."]
                s["step"] = "AGAIN"
                send_results(user_id, result, s)
                return

            # Normal team+category
            if qc["team"]:
                league   = qc["league"]
                team     = qc["team"]
                category = qc["category"]
                s["league"]    = league
                s["team_id"]   = team["id"]
                s["team_name"] = team["name"]
                s["step"]      = "AGAIN"
                if not category:
                    s["step"] = "CATEGORY"
                    reply(user_id, team["name"] + "\n" + CATEGORY_MENU)
                    return
                result = run_fetch(lambda: espn.get_data(league, team["id"], team["name"], category))
                result = result or ["Could not load data."]
                send_results(user_id, result, s)
                if qc["info"] and category == "scores":
                    time.sleep(2)
                    info = run_fetch(lambda: espn.get_score_details(league, team["id"], team["name"]))
                    info = info or ["No detail available."]
                    uname = s.get("name","Someone")
                    tag   = "[" + uname + "]"
                    for i, msg in enumerate(info):
                        if i > 0: time.sleep(2)
                        reply(user_id, tag + " " + msg if i == 0 else msg)
                return

    s    = session(user_id)
    step = s.get("step", "LEAGUE")

    # FAV_LEAGUE
    if step == "FAV_LEAGUE":
        league = LEAGUES.get(tl)
        if not league:
            reply(user_id, "Pick: 1.NHL 2.NBA 3.NFL 4.MLB")
            return
        teams = espn.get_teams(league)
        if not teams:
            reply(user_id, "Couldn't load teams.")
            return
        s["fav_league"] = league
        s["teams"]      = teams
        s["step"]       = "FAV_TEAM"
        chunks = team_abbrev_list(teams)
        reply(user_id, league.upper() + " fav - type name:")
        for chunk in chunks:
            time.sleep(2)
            reply(user_id, chunk)
        return

    # FAV_TEAM
    if step == "FAV_TEAM":
        teams  = s.get("teams", [])
        team   = pick_team(text, teams)
        league = s.get("fav_league")
        if not team:
            reply(user_id, "Not found. Type team name or number.")
            return
        if user_id not in favorites:
            favorites[user_id] = {}
        favorites[user_id][league] = {"id": team["id"], "name": team["name"]}
        s["step"] = "LEAGUE"
        reply(user_id, team["name"] + " saved as " + league.upper() + " fav!")
        return

    # MY_PICK
    if step == "MY_PICK":
        my_favs = s.get("my_favs", [])
        chosen  = None
        try:
            idx = int(tl) - 1
            if 0 <= idx < len(my_favs):
                chosen = my_favs[idx]
        except ValueError:
            for lg, team in my_favs:
                if tl in team["name"].lower() or tl == lg:
                    chosen = (lg, team)
                    break
        if not chosen:
            reply(user_id, "Pick 1-" + str(len(my_favs)) + ".")
            return
        league, team   = chosen
        s["league"]    = league
        s["team_id"]   = team["id"]
        s["team_name"] = team["name"]
        s["step"]      = "CATEGORY"
        reply(user_id, team["name"] + "\n" + CATEGORY_MENU)
        return

    # LEAGUE_CAT
    if step == "LEAGUE_CAT":
        cat = LEAGUE_CATS.get(tl)
        if not cat:
            reply(user_id, LEAGUE_CAT_MENU)
            return
        league         = s.get("league")
        s["step"]      = "AGAIN"
        s["team_name"] = league.upper() + " (All)"
        result = run_fetch(lambda: espn.get_league_data(league, cat))
        result = result or ["Could not load data."]
        send_results(user_id, result, s)
        return

    # STEP 1: League
    if step == "LEAGUE":
        league = LEAGUES.get(tl)
        if not league:
            reply(user_id, '"' + text + '" not recognized.\n' + WELCOME)
            return
        s["league"] = league
        teams = espn.get_teams(league)
        if not teams:
            reply(user_id, "Couldn't load teams.\nText MENU to restart.")
            reset(user_id)
            return
        _teams_cache[league] = teams
        s["teams"] = teams
        s["step"]  = "TEAM"
        chunks = team_abbrev_list(teams)
        reply(user_id, league.upper() + " teams:")
        for chunk in chunks:
            time.sleep(2)
            reply(user_id, chunk)
        time.sleep(2)
        reply(user_id, "Type name, # or abbrev.\n0=whole league view")

    # STEP 2: Team
    elif step == "TEAM":
        if tl == "0":
            s["step"] = "LEAGUE_CAT"
            reply(user_id, LEAGUE_CAT_MENU)
            return
        teams = s.get("teams", [])
        team  = pick_team(text, teams)
        if not team:
            reply(user_id, '"' + text + '" not found.\nType name or number.\nMENU to restart.')
            return
        s["team_id"]   = team["id"]
        s["team_name"] = team["name"]
        s["step"]      = "CATEGORY"
        reply(user_id, team["name"] + "\n" + CATEGORY_MENU)

    # STEP 3: Category
    elif step == "CATEGORY":
        try:
            if int(tl) > 8:
                reply(user_id, "Pick 1-8:\n" + CATEGORY_MENU)
                return
        except ValueError:
            pass
        cat = CATEGORIES.get(tl)
        if not cat:
            reply(user_id, '"' + text + '" not recognized.\n' + CATEGORY_MENU)
            return
        league    = s["league"]
        team_id   = s["team_id"]
        team_name = s["team_name"]
        s["step"]     = "AGAIN"
        s["last_cat"] = cat
        result = run_fetch(lambda: espn.get_data(league, team_id, team_name, cat))
        result = result or ["Could not load data."]
        send_results(user_id, result, s)

    # STEP 4: After results
    elif step == "AGAIN":
        if tl in ("info","details","who scored","scorers"):
            league    = s.get("league")
            team_id   = s.get("team_id")
            team_name = s.get("team_name","")
            if league and team_id:
                result = run_fetch(lambda: espn.get_score_details(league, team_id, team_name))
                result = result or ["No detail available."]
                send_results(user_id, result, s)
            else:
                reply(user_id, "No score loaded yet.")
            return
        if tl in ("1","same","same team"):
            s["step"] = "CATEGORY"
            reply(user_id, s["team_name"] + "\n" + CATEGORY_MENU)
        elif tl in ("2","new team","team"):
            league = s["league"]
            teams  = s.get("teams") or espn.get_teams(league)
            s["teams"] = teams
            s["step"]  = "TEAM"
            chunks = team_abbrev_list(teams)
            reply(user_id, league.upper() + " teams:")
            for chunk in chunks:
                time.sleep(2)
                reply(user_id, chunk)
            time.sleep(2)
            reply(user_id, "Type name, # or abbrev.\n0=whole league view")
        elif tl in ("3","new league","league"):
            reset(user_id)
            reply(user_id, WELCOME)
        else:
            reply(user_id, "Reply 1, 2, or 3.\nOr text MENU.")
    else:
        reset(user_id)
        reply(user_id, WELCOME)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
