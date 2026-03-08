"""
sports_bot.py -- GroupMe Sports Bot
Receives messages from a group, replies via PRIVATE DM to each user.
No emojis -- works on any basic phone via SMS.
"""

from flask import Flask, request, jsonify
import os
import requests
import espn
import threading

app = Flask(__name__)

BOT_ID       = os.environ.get("GROUPME_BOT_ID",       "YOUR_BOT_ID_HERE")
ACCESS_TOKEN = os.environ.get("GROUPME_ACCESS_TOKEN", "YOUR_TOKEN_HERE")

sessions = {}
bans = {}      # { user_id: ban_expiry_timestamp }
favorites = {} # { user_id: { "nhl": {id, name}, "nba": ..., "nfl": ..., "mlb": ... } }

# -- Prank config --------------------------------------------------------------
import time
PRANK_USER = "18483671827"  # Shimshy's number (E.164 format)
PRANK_ASKED = set()  # track if we've asked him the question

LEAGUES    = {"1": "nhl", "2": "nba", "3": "nfl", "4": "mlb",
              "nhl": "nhl", "nba": "nba", "nfl": "nfl", "mlb": "mlb"}
CATEGORIES = {"1": "scores", "2": "schedule", "3": "roster", "4": "news", "5": "standings",
              "scores": "scores", "schedule": "schedule", "roster": "roster",
              "news": "news", "standings": "standings"}

WELCOME = (
    "SPORTS BOT\n"
    "----------\n"
    "Pick a league:\n"
    "1. NHL\n"
    "2. NBA\n"
    "3. NFL\n"
    "4. MLB\n"
    "Reply with number or name."
)

CATEGORY_MENU = (
    "What do you want?\n"
    "1. Scores\n"
    "2. Schedule\n"
    "3. Roster\n"
    "4. News\n"
    "5. Standings\n"
    "Reply with number or word."
)

AFTER_MENU = (
    "Want more?\n"
    "1. Same team\n"
    "2. New team\n"
    "3. New league\n"
    "Or text MENU to restart."
)


# -- Messaging -----------------------------------------------------------------
def send_dm(user_id, text):
    try:
        requests.post(
            "https://api.groupme.com/v3/direct_messages",
            params={"token": ACCESS_TOKEN},
            json={
                "direct_message": {
                    "source_guid": f"sports-{user_id}-{hash(text)}",
                    "recipient_id": user_id,
                    "text": text,
                }
            },
            timeout=5,
        )
    except Exception:
        pass


# GroupMe message hard limit is 1000 chars — split anything longer
MSG_LIMIT = 900

def send_group(text):
    """Send one message, retry once on failure."""
    for attempt in range(2):
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
    """Split a message into <=900 char pieces, breaking on newlines."""
    if len(text) <= MSG_LIMIT:
        return [text]

    parts = []
    current = ""
    for line in text.split("\n"):
        # +1 for the newline character
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
    """Send a reply, automatically splitting if over GroupMe limit."""
    chunks = chunk_message(text)
    for i, chunk in enumerate(chunks):
        if i > 0:
            time.sleep(0.8)  # wait between chunks so they arrive in order
        send_group(chunk)


# -- Session helpers -----------------------------------------------------------
def session(uid):
    if uid not in sessions:
        sessions[uid] = {"step": "LEAGUE"}
    return sessions[uid]

def reset(uid):
    sessions[uid] = {"step": "LEAGUE"}


# -- Team helpers --------------------------------------------------------------
def team_list_text(teams):
    lines = [f"{i+1}. {t['name']}" for i, t in enumerate(teams)]
    if len(lines) > 16:
        mid = len(lines) // 2
        return "\n".join(lines[:mid]) + "\n\n(cont.)\n" + "\n".join(lines[mid:])
    return "\n".join(lines)

def pick_team(text, teams):
    t = text.strip().lower()
    try:
        idx = int(t) - 1
        if 0 <= idx < len(teams):
            return teams[idx]
    except ValueError:
        pass
    for team in teams:
        if t in team["name"].lower() or t == team.get("abbrev", "").lower():
            return team
    return None


# -- Main webhook --------------------------------------------------------------
@app.route("/groupme", methods=["POST"])
def handle_message(user_id, data):
    text = data.get("text", "").strip()
    tl   = text.lower()
    name = data.get("name", "Someone")

    if user_id:
        s = session(user_id)
        s["name"] = name

    # -- Ban check -------------------------------------------------------------
    if user_id in bans:
        if time.time() < bans[user_id]:
            mins_left = int((bans[user_id] - time.time()) / 60) + 1
            reply(user_id, "You are banned for " + str(mins_left) + " more minute(s).\nKnicks fan.")
            return
        else:
            del bans[user_id]

    # -- Prank for Shimshy -----------------------------------------------------
    phone      = data.get("sender_id", data.get("user_id", ""))
    normalized = phone.replace("+", "").replace("-", "").replace(" ", "")
    if PRANK_USER in normalized or normalized in PRANK_USER:
        if user_id not in PRANK_ASKED:
            PRANK_ASKED.add(user_id)
            reply(user_id, "Before you can use Sports Bot\nyou must answer one question:\n\nWho is better,\nthe Lakers or the Knicks?")
            return
        elif any(x in tl for x in ("knicks", "new york", "ny")):
            bans[user_id] = time.time() + 3600
            PRANK_ASKED.discard(user_id)
            reply(user_id, "WRONG.\n\nYou have been banned\nfor 1 hour.\n\nShame on you.")
            return
        elif any(x in tl for x in ("lakers", "la lakers", "los angeles lakers")):
            PRANK_ASKED.discard(user_id)
            reply(user_id, "Correct! Good taste.\nWelcome to Sports Bot!\n\n" + WELCOME)
            return
        elif user_id in PRANK_ASKED:
            reply(user_id, "Just answer the question:\nLakers or Knicks?")
            return

    # -- Global commands -------------------------------------------------------
    if tl in ("menu", "restart", "reset", "start", "hi", "hello"):
        reset(user_id)
        reply(user_id, WELCOME)
        return

    if tl == "help":
        reply(user_id, "SPORTS BOT HELP\n---------------\nMENU - restart\nFAV  - set favorites\nMY   - use favorites\nPick league, team,\nthen what you want.")
        return

    # -- FAV command -----------------------------------------------------------
    if tl == "fav":
        favs      = favorites.get(user_id, {})
        nhl_name  = favs.get("nhl", {}).get("name", "not set")
        nba_name  = favs.get("nba", {}).get("name", "not set")
        nfl_name  = favs.get("nfl", {}).get("name", "not set")
        mlb_name  = favs.get("mlb", {}).get("name", "not set")
        s         = session(user_id)
        s["step"] = "FAV_LEAGUE"
        reply(user_id, "Your favorites:\nNHL: " + nhl_name + "\nNBA: " + nba_name + "\nNFL: " + nfl_name + "\nMLB: " + mlb_name + "\n\nSet one:\n1. NHL  2. NBA\n3. NFL  4. MLB")
        return

    # -- MY command ------------------------------------------------------------
    if tl == "my":
        favs     = favorites.get(user_id, {})
        set_favs = [(lg, favs[lg]) for lg in ("nhl", "nba", "nfl", "mlb") if favs.get(lg)]
        if not set_favs:
            reply(user_id, "No favorites set yet.\nText FAV to set them.")
            return
        lines = ["Your favorites:"]
        for i, (lg, team) in enumerate(set_favs, 1):
            lines.append(str(i) + ". " + lg.upper() + " - " + team["name"])
        lines.append("Pick one.")
        s         = session(user_id)
        s["step"]    = "MY_PICK"
        s["my_favs"] = set_favs
        reply(user_id, "\n".join(lines))
        return

    s    = session(user_id)
    step = s.get("step", "LEAGUE")

    # STEP FAV_LEAGUE ----------------------------------------------------------
    if step == "FAV_LEAGUE":
        league = LEAGUES.get(tl)
        if not league:
            reply(user_id, "Pick a league:\n1. NHL  2. NBA\n3. NFL  4. MLB")
            return
        teams = espn.get_teams(league)
        if not teams:
            reply(user_id, "Couldn't load teams. Try again.")
            return
        s["fav_league"] = league
        s["teams"]      = teams
        s["step"]       = "FAV_TEAM"
        reply(user_id, league.upper() + " - Pick your favorite:\n" + team_list_text(teams) + "\n\nReply with number or name.")
        return

    # STEP FAV_TEAM ------------------------------------------------------------
    if step == "FAV_TEAM":
        teams  = s.get("teams", [])
        team   = pick_team(text, teams)
        league = s.get("fav_league")
        if not team:
            reply(user_id, "Not found. Reply 1-" + str(len(teams)) + " or team name.")
            return
        if user_id not in favorites:
            favorites[user_id] = {}
        favorites[user_id][league] = {"id": team["id"], "name": team["name"]}
        s["step"] = "LEAGUE"
        reply(user_id, team["name"] + " saved as your " + league.upper() + " favorite!")
        return

    # STEP MY_PICK -------------------------------------------------------------
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

    # STEP 1: Choose League ----------------------------------------------------
    if step == "LEAGUE":
        league = LEAGUES.get(tl)
        if not league:
            reply(user_id, '"' + text + '" not recognized.\n\n' + WELCOME)
            return
        s["league"] = league
        teams = espn.get_teams(league)
        if not teams:
            reply(user_id, "Couldn't load teams. Try again.\nText MENU to restart.")
            reset(user_id)
            return
        s["teams"] = teams
        s["step"]  = "TEAM"
        reply(user_id, league.upper() + " - Choose a team:\n" + team_list_text(teams) + "\n\nReply with number or team name.")

    # STEP 2: Choose Team ------------------------------------------------------
    elif step == "TEAM":
        teams = s.get("teams", [])
        team  = pick_team(text, teams)
        if not team:
            reply(user_id, '"' + text + '" not found.\nReply 1-' + str(len(teams)) + ' or type team name.\nText MENU to restart.')
            return
        s["team_id"]   = team["id"]
        s["team_name"] = team["name"]
        s["step"]      = "CATEGORY"
        reply(user_id, team["name"] + "\n" + CATEGORY_MENU)

    # STEP 3: Choose Category --------------------------------------------------
    elif step == "CATEGORY":
        cat = CATEGORIES.get(tl)
        if not cat:
            reply(user_id, '"' + text + '" not recognized.\n\n' + CATEGORY_MENU)
            return
        league    = s["league"]
        team_id   = s["team_id"]
        team_name = s["team_name"]

        result_holder = [None]
        def fetch():
            result_holder[0] = espn.get_data(league, team_id, team_name, cat)
        t = threading.Thread(target=fetch)
        t.start()
        t.join(timeout=10)
        if t.is_alive():
            reply(user_id, "Still loading...")
            t.join(timeout=15)
        result = result_holder[0] or "Could not load data. Try again."
        s["step"] = "AGAIN"
        uname     = s.get("name", "Someone")
        tag       = "[" + uname + "]"
        if isinstance(result, list):
            for i, msg in enumerate(result):
                if i > 0:
                    time.sleep(1)
                prefix = tag + "\n" if i == 0 else tag + " (cont.)\n"
                reply(user_id, prefix + msg)
            time.sleep(1)
            reply(user_id, AFTER_MENU)
        else:
            reply(user_id, tag + "\n" + result + "\n\n" + AFTER_MENU)

    # STEP 4: After results ----------------------------------------------------
    elif step == "AGAIN":
        if tl in ("1", "same", "same team", "more"):
            s["step"] = "CATEGORY"
            reply(user_id, s["team_name"] + "\n" + CATEGORY_MENU)
        elif tl in ("2", "new team", "team"):
            league = s["league"]
            teams  = s.get("teams", espn.get_teams(league))
            s["teams"] = teams
            s["step"]  = "TEAM"
            reply(user_id, league.upper() + " - Pick a team:\n" + team_list_text(teams) + "\n\nReply with number or team name.")
        elif tl in ("3", "new league", "league"):
            reset(user_id)
            reply(user_id, WELCOME)
        else:
            reply(user_id, "Reply 1 (same team), 2 (new team),\n3 (new league) or text MENU.")
    else:
        reset(user_id)
        reply(user_id, WELCOME)

def health():
    return "Sports Bot is running!", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
