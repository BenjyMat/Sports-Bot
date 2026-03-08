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
bans = {}  # { user_id: ban_expiry_timestamp }

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
    for chunk in chunk_message(text):
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
def groupme_webhook():
    data        = request.get_json(force=True)
    user_id     = data.get("user_id", "")
    text        = data.get("text", "").strip()
    sender_type = data.get("sender_type", "")

    if sender_type == "bot" or not text:
        return jsonify({}), 200

    # Respond to GroupMe instantly so it never retries/duplicates
    # Process everything in background thread
    def process():
        handle_message(user_id, data)
    threading.Thread(target=process, daemon=True).start()
    return jsonify({}), 200


def handle_message(user_id, data):
    text = data.get("text", "").strip()
    tl   = text.lower()
    name = data.get("name", "Someone")



    # Store name in session for use in replies
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
            del bans[user_id]  # ban expired

    # -- Prank for Shimshy -----------------------------------------------------
    phone = data.get("sender_id", data.get("user_id", ""))
    normalized = phone.replace("+", "").replace("-", "").replace(" ", "")
    if PRANK_USER in normalized or normalized in PRANK_USER:
        if user_id not in PRANK_ASKED:
            PRANK_ASKED.add(user_id)
            reply(user_id, "Before you can use Sports Bot\nyou must answer one question:\n\nWho is better,\nthe Lakers or the Knicks?")
            return
        elif user_id in PRANK_ASKED and tl not in ("lakers", "la lakers", "los angeles lakers"):
            if any(x in tl for x in ("knicks", "new york", "ny")):
                bans[user_id] = time.time() + 3600  # 1 hour ban
                PRANK_ASKED.discard(user_id)
                reply(user_id, "WRONG.\n\nYou have been banned\nfor 1 hour.\n\nShame on you.")
                return
            elif any(x in tl for x in ("lakers", "la lakers", "los angeles lakers")):
                PRANK_ASKED.discard(user_id)
                reply(user_id, "Correct! Good taste.\nWelcome to Sports Bot!\n\n" + WELCOME)
                return
            else:
                reply(user_id, "Just answer the question:\nLakers or Knicks?")
                return
        elif any(x in tl for x in ("lakers", "la lakers", "los angeles lakers")):
            PRANK_ASKED.discard(user_id)
            reply(user_id, "Correct! Good taste.\nWelcome to Sports Bot!\n\n" + WELCOME)
            return

    if tl in ("menu", "restart", "reset", "start", "hi", "hello"):
        reset(user_id)
        reply(user_id, WELCOME)
        return

    if tl == "help":
        reply(user_id, (
            "SPORTS BOT HELP\n"
            "---------------\n"
            "Text MENU to start.\n"
            "Pick league, team,\n"
            "then what you want.\n"
            "Replies are private -\n"
            "only YOU see them!"
        ))
        return

    s    = session(user_id)
    step = s.get("step", "LEAGUE")

    # STEP 1: Choose League
    if step == "LEAGUE":
        league = LEAGUES.get(tl)
        if not league:
            reply(user_id, f'"{text}" not recognized.\n\n{WELCOME}')
            return

        s["league"] = league
        teams = espn.get_teams(league)
        if not teams:
            reply(user_id, "Couldn't load teams. Try again.\nText MENU to restart.")
            reset(user_id)
            return

        s["teams"] = teams
        s["step"]  = "TEAM"
        reply(user_id, (
            f"{league.upper()} - Choose a team:\n"
            f"------------------\n"
            f"{team_list_text(teams)}\n\n"
            f"Reply with number or team name."
        ))

    # STEP 2: Choose Team
    elif step == "TEAM":
        teams = s.get("teams", [])
        team  = pick_team(text, teams)
        if not team:
            reply(user_id, f'"{text}" not found.\nReply 1-{len(teams)} or type team name.\nText MENU to restart.')
            return

        s["team_id"]   = team["id"]
        s["team_name"] = team["name"]
        s["step"]      = "CATEGORY"
        reply(user_id, f'{team["name"]} selected!\n------------------\n{CATEGORY_MENU}')

    # STEP 3: Choose Category
    elif step == "CATEGORY":
        cat = CATEGORIES.get(tl)
        if not cat:
            reply(user_id, f'"{text}" not recognized.\n\n{CATEGORY_MENU}')
            return

        league    = s["league"]
        team_id   = s["team_id"]
        team_name = s["team_name"]

        # ESPN can be slow -- send a reminder if it takes over 10 seconds
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
        tag       = f"[{uname}]"
        # Roster returns a list of messages; everything else returns a string
        if isinstance(result, list):
            for i, msg in enumerate(result):
                prefix = tag + "\n" if i == 0 else tag + " (cont.)\n"
                reply(user_id, prefix + msg)
            reply(user_id, AFTER_MENU)
        else:
            reply(user_id, tag + "\n" + result + "\n\n" + AFTER_MENU)

    # STEP 4: After results
    elif step == "AGAIN":
        if tl in ("1", "same", "same team", "more"):
            s["step"] = "CATEGORY"
            reply(user_id, f'{s["team_name"]}\n------------------\n{CATEGORY_MENU}')

        elif tl in ("2", "new team", "team"):
            league = s["league"]
            teams  = s.get("teams", espn.get_teams(league))
            s["teams"] = teams
            s["step"]  = "TEAM"
            reply(user_id, (
                f"{league.upper()} - Pick a team:\n"
                f"------------------\n"
                f"{team_list_text(teams)}\n\n"
                f"Reply with number or team name."
            ))

        elif tl in ("3", "new league", "league"):
            reset(user_id)
            reply(user_id, WELCOME)

        else:
            reply(user_id, "Reply 1 (same team), 2 (new team),\n3 (new league) or text MENU.")

    else:
        reset(user_id)
        reply(user_id, WELCOME)



# -- Health check --------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return "Sports Bot is running!", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
