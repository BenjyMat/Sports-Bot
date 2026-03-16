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
alerts     = {}
alert_sent = {}

PRANK_USER  = "18483671827"
PRANK_ASKED = set()
MSG_LIMIT   = 155

LEAGUES = {
    "1":"nhl","2":"nba","3":"nfl","4":"mlb",
    "nhl":"nhl","nba":"nba","nfl":"nfl","mlb":"mlb",
    "hockey":"nhl","basketball":"nba","football":"nfl","baseball":"mlb"
}

# All category aliases
CATEGORIES = {
    "1":"scores",      "s":"scores",      "scores":"scores",
    "2":"schedule",    "sc":"schedule",   "schedule":"schedule",
    "3":"roster",      "r":"roster",      "roster":"roster",
    "4":"news",        "n":"news",        "news":"news",
    "5":"standings",   "st":"standings",  "standings":"standings",
    "6":"injuries",    "i":"injuries",    "injuries":"injuries",
    "7":"transactions","t":"transactions","transactions":"transactions",
    "8":"homeaway",    "ha":"homeaway",   "homeaway":"homeaway",
    "home":"homeaway","away":"homeaway","record":"homeaway",
}

LEAGUE_CATS = {
    "1":"league_scores",   "scores":"league_scores",   "s":"league_scores",
    "2":"league_schedule", "schedule":"league_schedule","sc":"league_schedule",
    "3":"league_news",     "news":"league_news",        "n":"league_news",
}

# Common alternate abbreviations ESPN doesn't use
ABBREV_ALIASES = {
    "nyk":"NY","knicks":"NY","nyk":"NY",
    "gsw":"GS","warriors":"GS",
    "phx":"PHX","suns":"PHX",
    "lac":"LAC","clippers":"LAC",
    "lal":"LAL","lakers":"LAL",
    "sa":"SA","spurs":"SA",
    "no":"NO","pelicans":"NO",
    "utah":"UTAH",
    "mem":"MEM","grizzlies":"MEM",
    "cha":"CHA","hornets":"CHA",
    "bkn":"BKN","nets":"BKN",
    "wsh":"WSH","wsh":"WSH",
}

WELCOME = (
    "SPORTS BOT\n"
    "----------\n"
    "Pick a league:\n"
    "1.NHL 2.NBA\n"
    "3.NFL 4.MLB\n"
    "Or type league name.\n"
    "Text !HELP for full guide."
)

CATEGORY_MENU = (
    "1.Scores  2.Schedule\n"
    "3.Roster  4.News\n"
    "5.Standings 6.Injuries\n"
    "7.Transactions 8.H/A Rec"
)

LEAGUE_CAT_MENU = (
    "WHOLE LEAGUE:\n"
    "1.Scores 2.Schedule 3.News"
)

AFTER_MENU = "1.Same 2.NewTeam 3.NewLeague"

HELP_1 = (
    "SPORTS BOT HELP (1/4)\n"
    "---------------------\n"
    "STEP BY STEP:\n"
    "1. Pick league:\n"
    "   1=NHL 2=NBA\n"
    "   3=NFL 4=MLB\n"
    "2. Pick team by name,\n"
    "   number, or abbrev\n"
    "   (0 = whole league)\n"
    "3. Pick category 1-8\n"
    "4. After results:\n"
    "   1=same team\n"
    "   2=new team\n"
    "   3=new league"
)

HELP_2 = (
    "SPORTS BOT HELP (2/4)\n"
    "---------------------\n"
    "QUICK COMMANDS:\n"
    "Type it all at once:\n"
    "[league] [team] [cat]\n"
    "\n"
    "Examples:\n"
    "nba lakers s\n"
    "nhl kings standings\n"
    "mlb dodgers schedule\n"
    "nfl cowboys t\n"
    "nba lakers s info\n"
    "\n"
    "SHORT CODES:\n"
    "s=scores  sc=schedule\n"
    "r=roster  n=news\n"
    "st=standings i=injuries\n"
    "t=transactions\n"
    "ha=home/away record"
)

HELP_3 = (
    "SPORTS BOT HELP (3/4)\n"
    "---------------------\n"
    "CATEGORIES:\n"
    "1.Scores - live+results\n"
    "2.Schedule - next 6 games\n"
    "3.Roster - all players\n"
    "4.News - headlines\n"
    "5.Standings - league table\n"
    "6.Injuries - injury report\n"
    "7.Transactions - trades\n"
    "8.H/A - home vs away rec\n"
    "\n"
    "SPECIAL:\n"
    "nhl bos vs tor = H2H\n"
    "nhl bracket = playoffs\n"
    "INFO after scores =\n"
    "  who scored / leaders"
)

HELP_4 = (
    "SPORTS BOT HELP (4/4)\n"
    "---------------------\n"
    "FAVORITES:\n"
    "FAV - set fav teams\n"
    "MY  - use your fav\n"
    "\n"
    "ALERTS (final score):\n"
    "ALERT nba lakers\n"
    "ALERTS - list yours\n"
    "DELALERT nba lakers\n"
    "\n"
    "OTHER:\n"
    "LAST - repeat last result\n"
    "INFO - scorer details\n"
    "MENU - start over\n"
    "!HELP - this guide\n"
    "\n"
    "Works on any phone/SMS!"
)


# -- System message filter -----------------------------------------------------
SYSTEM_PHRASES = [
    "changed the group", "removed ", "added ", "joined the group",
    "left the group", "changed the name", "changed the avatar",
    "changed the topic", "changed the cover", "pinned a message",
    "type to be ", "setting for ", "has been ",
]

def is_system_message(data):
    sender_type = data.get("sender_type", "")
    if sender_type in ("system", "bot"):
        return True
    text = data.get("text", "")
    tl   = text.lower()
    for phrase in SYSTEM_PHRASES:
        if phrase in tl:
            return True
    return False


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
    """Combine results into minimum SMS messages and send."""
    if not result:
        result = ["No data available."]
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
    if not combined:
        combined = [tag + " No data."]
    # Save for LAST
    s["last_result"]   = result
    s["last_combined"] = combined
    for i, msg in enumerate(combined):
        if i > 0:
            time.sleep(3)
        reply(user_id, msg)
    time.sleep(3)
    reply(user_id, AFTER_MENU)


# -- Session -------------------------------------------------------------------
def session(uid):
    if uid not in sessions:
        sessions[uid] = {"step": "LEAGUE"}
    return sessions[uid]

def reset(uid):
    last = sessions.get(uid, {}).get("last_result")
    lc   = sessions.get(uid, {}).get("last_combined")
    sessions[uid] = {"step": "LEAGUE", "last_result": last, "last_combined": lc}


# -- Team helpers --------------------------------------------------------------
_teams_cache = {}

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

def pick_team(query, teams):
    """Find a team by number, abbreviation, or partial name."""
    t = query.strip().lower()
    # By number
    try:
        idx = int(t) - 1
        if 0 <= idx < len(teams):
            return teams[idx]
    except ValueError:
        pass
    # Check alias map
    canonical = ABBREV_ALIASES.get(t)
    if canonical:
        for team in teams:
            if team.get("abbrev", "").upper() == canonical.upper():
                return team
    # Exact abbreviation
    for team in teams:
        if t == team.get("abbrev", "").lower():
            return team
    # Partial name
    for team in teams:
        if t in team["name"].lower():
            return team
    # Each word
    for word in t.split():
        for team in teams:
            if word in team["name"].lower() or word == team.get("abbrev","").lower():
                return team
    return None

def split_team_and_cat(text, teams):
    """
    Try to split something like 'Ducks sc' or 'La s' into team + category.
    Returns (team, category) or (None, None).
    """
    words = text.strip().lower().split()
    # Try progressively shorter team queries, last word as category
    for split in range(len(words)-1, 0, -1):
        team_query = " ".join(words[:split])
        cat_query  = words[split]
        if cat_query in CATEGORIES:
            team = pick_team(team_query, teams)
            if team:
                return team, CATEGORIES[cat_query]
    return None, None


# -- Quick command parser ------------------------------------------------------
def parse_quick_command(tl):
    words = tl.split()
    if len(words) < 2:
        return None

    result = {"league": None, "team": None, "category": None,
              "info": False, "h2h": None, "bracket": False}

    # Bracket: "nhl bracket"
    if "bracket" in words:
        lg = LEAGUES.get(words[0])
        if lg:
            result["league"]  = lg
            result["bracket"] = True
            return result

    # H2H: "nhl bos vs tor"
    if "vs" in words:
        try:
            vi  = words.index("vs")
            lg  = LEAGUES.get(words[0])
            if lg and vi >= 2:
                t1q  = " ".join(words[1:vi])
                t2ab = words[vi+1] if vi+1 < len(words) else ""
                teams = _teams_cache.get(lg) or espn.get_teams(lg)
                if teams:
                    _teams_cache[lg] = teams
                    t1 = pick_team(t1q, teams)
                    if t1 and t2ab:
                        result["league"] = lg
                        result["team"]   = t1
                        result["h2h"]    = t2ab
                        return result
        except Exception:
            pass

    # Info suffix
    if words[-1] in ("info","details","more"):
        result["info"] = True
        words = words[:-1]

    lg = LEAGUES.get(words[0])
    if not lg:
        return None
    result["league"] = lg

    # "stats" keyword = player lookup
    PLAYER_WORDS = {"stats", "player", "stat"}

    # Category
    for w in words[1:]:
        if w in CATEGORIES:
            result["category"] = CATEGORIES[w]

    # Team — everything that isn't league, category, or player keyword
    team_words = [w for w in words[1:] if w not in CATEGORIES and w not in LEAGUES and w not in PLAYER_WORDS]
    if not team_words:
        result["league_wide"] = True
        return result

    query = " ".join(team_words)
    teams = _teams_cache.get(lg) or espn.get_teams(lg)
    if teams:
        _teams_cache[lg] = teams
        team = pick_team(query, teams)
        if team:
            result["team"] = team
        else:
            # No team matched — treat as player name
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


# -- Alert endpoint ------------------------------------------------------------
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
    data = request.get_json(force=True)
    if is_system_message(data):
        return jsonify({}), 200
    text = data.get("text", "").strip()
    if not text:
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
        elif any(x in tl for x in ("knicks","new york","ny knicks")):
            bans[user_id] = time.time() + 3600
            PRANK_ASKED.discard(user_id)
            reply(user_id, "WRONG. Banned 1 hour.\nShame on you.")
            return
        elif any(x in tl for x in ("lakers","la lakers")):
            PRANK_ASKED.discard(user_id)
            reply(user_id, "Correct!\n\n" + WELCOME)
            return
        elif user_id in PRANK_ASKED:
            reply(user_id, "Lakers or Knicks?")
            return

    # ---- Global commands (always work regardless of step) --------------------

    if tl in ("menu","restart","reset","start","hi","hello"):
        reset(user_id)
        reply(user_id, WELCOME)
        return

    if tl in ("!help","help","!cmds","cmds","commands","shortcuts"):
        reply(user_id, HELP_1)
        time.sleep(3)
        reply(user_id, HELP_2)
        time.sleep(3)
        reply(user_id, HELP_3)
        time.sleep(3)
        reply(user_id, HELP_4)
        return

    if tl in ("last","again","repeat"):
        s = session(user_id)
        combined = s.get("last_combined")
        if combined:
            for i, msg in enumerate(combined):
                if i > 0:
                    time.sleep(3)
                reply(user_id, msg)
            time.sleep(3)
            reply(user_id, AFTER_MENU)
        else:
            reply(user_id, "No previous result.\nText MENU to start.")
        return

    if tl in ("fav","favs","favorites","favourite","favourites"):
        favs = favorites.get(user_id, {})
        s    = session(user_id)
        s["step"] = "FAV_LEAGUE"
        reply(user_id,
            "Your favorites:\n"
            "NHL: " + favs.get("nhl",{}).get("name","not set") + "\n"
            "NBA: " + favs.get("nba",{}).get("name","not set") + "\n"
            "NFL: " + favs.get("nfl",{}).get("name","not set") + "\n"
            "MLB: " + favs.get("mlb",{}).get("name","not set") + "\n"
            "\nSet: 1.NHL 2.NBA 3.NFL 4.MLB"
        )
        return

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

    if tl == "alerts":
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
        rest = tl[6:].strip()
        qc   = parse_quick_command("nba placeholder") # dummy
        # Parse manually: "alert nba lakers"
        words = rest.split()
        lg    = LEAGUES.get(words[0]) if words else None
        if lg and len(words) > 1:
            teams = _teams_cache.get(lg) or espn.get_teams(lg)
            if teams:
                _teams_cache[lg] = teams
                team = pick_team(" ".join(words[1:]), teams)
                if team:
                    if user_id not in alerts:
                        alerts[user_id] = []
                    entry = (lg, team["id"], team["name"])
                    if entry not in alerts[user_id]:
                        alerts[user_id].append(entry)
                    reply(user_id, "Alert set for " + team["name"] + "!\nText ALERTS to list.")
                    return
        reply(user_id, "Format: ALERT nba lakers")
        return

    if tl.startswith("delalert "):
        rest  = tl[9:].strip()
        words = rest.split()
        lg    = LEAGUES.get(words[0]) if words else None
        if lg and len(words) > 1 and user_id in alerts:
            teams = _teams_cache.get(lg) or espn.get_teams(lg)
            if teams:
                team = pick_team(" ".join(words[1:]), teams)
                if team:
                    alerts[user_id] = [(l,t,n) for (l,t,n) in alerts[user_id] if t != team["id"]]
                    reply(user_id, "Alert removed for " + team["name"] + ".")
                    return
        reply(user_id, "Format: DELALERT nba lakers")
        return

    # INFO command (works from AGAIN step)
    if tl in ("info","details","who scored","scorers"):
        s      = session(user_id)
        league = s.get("league")
        tid    = s.get("team_id")
        tname  = s.get("team_name","")
        if league and tid:
            result = run_fetch(lambda: espn.get_score_details(league, tid, tname))
            result = result or ["No detail available."]
            send_results(user_id, result, s)
        else:
            reply(user_id, "No score loaded.\nnText MENU to start.")
        return

    # ---- Quick commands: starts with league word ----------------------------
    words = tl.split()
    if words and words[0] in LEAGUES and len(words) >= 2:
        qc = parse_quick_command(tl)
        if qc:
            s      = session(user_id)
            league = qc["league"]

            # Bracket
            if qc.get("bracket"):
                result = run_fetch(lambda: espn.get_bracket(league))
                result = result or ["No bracket available."]
                s["step"] = "AGAIN"
                send_results(user_id, result, s)
                return

            # H2H
            if qc.get("h2h") and qc.get("team"):
                team = qc["team"]
                h2h  = qc["h2h"]
                result = run_fetch(lambda: espn.get_head_to_head(league, team["id"], team["name"], h2h))
                result = result or ["No matchup data."]
                s["step"] = "AGAIN"
                send_results(user_id, result, s)
                return

            # League-wide (no team given)
            if qc.get("league_wide") or not qc.get("team"):
                cat = qc.get("category")
                lc  = LEAGUE_CATS.get(cat.replace("league_","") if cat else "") or LEAGUE_CATS.get(cat or "")
                if not lc and cat:
                    # map scores->league_scores etc
                    mapping = {"scores":"league_scores","schedule":"league_schedule","news":"league_news"}
                    lc = mapping.get(cat)
                if lc:
                    s["step"]      = "AGAIN"
                    s["league"]    = league
                    s["team_name"] = league.upper() + " (All)"
                    result = run_fetch(lambda: espn.get_league_data(league, lc))
                    result = result or ["No data available."]
                    send_results(user_id, result, s)
                else:
                    # Just set league, show team list
                    teams = _teams_cache.get(league) or espn.get_teams(league)
                    if teams:
                        _teams_cache[league] = teams
                        s["league"] = league
                        s["teams"]  = teams
                        s["step"]   = "TEAM"
                        chunks = team_abbrev_list(teams)
                        reply(user_id, league.upper() + " teams:")
                        for chunk in chunks:
                            time.sleep(2)
                            reply(user_id, chunk)
                        time.sleep(2)
                        reply(user_id, "Type name, # or abbrev.\n0=whole league view")
                return

            # Player lookup
            if qc.get("player") and not qc.get("team"):
                player = qc["player"]
                result = run_fetch(lambda: espn.get_player(league, player))
                result = result or ["Player not found."]
                s["step"] = "AGAIN"
                send_results(user_id, result, s)
                return

            # Team + optional category
            team     = qc["team"]
            category = qc.get("category")
            do_info  = qc.get("info", False)
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

            if do_info and category == "scores":
                time.sleep(2)
                info = run_fetch(lambda: espn.get_score_details(league, team["id"], team["name"]))
                info = info or ["No detail available."]
                uname = s.get("name","Someone")
                tag   = "[" + uname + "]"
                for i, msg in enumerate(info):
                    if i > 0:
                        time.sleep(2)
                    reply(user_id, tag + " " + msg if i == 0 else msg)
            return

    # ---- Step-based flow -----------------------------------------------------
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
        _teams_cache[league] = teams
        s["fav_league"] = league
        s["teams"]      = teams
        s["step"]       = "FAV_TEAM"
        chunks = team_abbrev_list(teams)
        reply(user_id, league.upper() + " - type team name:")
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
            reply(user_id, "Not found. Type name or #.")
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

        # Try "teamname + category" in one text e.g. "Ducks sc"
        team, cat = split_team_and_cat(text, teams)
        if team and cat:
            s["team_id"]   = team["id"]
            s["team_name"] = team["name"]
            s["step"]      = "AGAIN"
            result = run_fetch(lambda: espn.get_data(s["league"], team["id"], team["name"], cat))
            result = result or ["Could not load data."]
            send_results(user_id, result, s)
            return

        team = pick_team(text, teams)
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
        league    = s.get("league","")
        team_id   = s.get("team_id","")
        team_name = s.get("team_name","")
        s["step"]     = "AGAIN"
        s["last_cat"] = cat
        result = run_fetch(lambda: espn.get_data(league, team_id, team_name, cat))
        result = result or ["Could not load data."]
        send_results(user_id, result, s)

    # STEP 4: After results
    elif step == "AGAIN":
        if tl in ("1","same","same team"):
            s["step"] = "CATEGORY"
            reply(user_id, s.get("team_name","") + "\n" + CATEGORY_MENU)
        elif tl in ("2","new team","team"):
            league = s.get("league","")
            teams  = s.get("teams") or espn.get_teams(league)
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
