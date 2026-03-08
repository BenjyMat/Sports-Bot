"""
sports_bot.py -- GroupMe Sports Bot
Receives messages from a group, replies via PRIVATE DM to each user.
Nobody sees anyone else's conversation!
"""

from flask import Flask, request, jsonify
import os
import requests
import espn

app = Flask(__name__)

BOT_ID       = os.environ.get("GROUPME_BOT_ID",       "YOUR_BOT_ID_HERE")
ACCESS_TOKEN = os.environ.get("GROUPME_ACCESS_TOKEN", "YOUR_TOKEN_HERE")

# In-memory sessions: { user_id: { step, league, team_id, team_name, teams } }
sessions = {}

LEAGUES    = {"1": "nhl", "2": "nba", "3": "nfl", "4": "mlb",
              "nhl": "nhl", "nba": "nba", "nfl": "nfl", "mlb": "mlb"}
CATEGORIES = {"1": "scores", "2": "schedule", "3": "roster", "4": "news", "5": "standings",
              "scores": "scores", "schedule": "schedule", "roster": "roster",
              "news": "news", "standings": "standings"}

LEAGUE_EMOJI = {"nhl": "Hockey", "nba": "Basketball", "nfl": "Football", "mlb": "Baseball"}

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
    """Send a private DM to a specific user. Only they can see it."""
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


def send_group(text):
    """Fallback: post to group (only used if DM fails)."""
    try:
        requests.post(
            "https://api.groupme.com/v3/bots/post",
            json={"bot_id": BOT_ID, "text": text},
            timeout=5,
        )
    except Exception:
        pass


def reply(user_id, text):
    """Try DM first, fall back to group post."""
    if ACCESS_TOKEN and ACCESS_TOKEN != "YOUR_TOKEN_HERE":
        send_dm(user_id, text)
    else:
        send_group(text)


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

    # Ignore bot's own messages and empty messages
    if sender_type == "bot" or not text:
        return jsonify({}), 200

    tl = text.lower()

    # Global commands
    if tl in ("menu", "restart", "reset", "start", "hi", "hello"):
        reset(user_id)
        reply(user_id, WELCOME)
        return jsonify({}), 200

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
        return jsonify({}), 200

    s    = session(user_id)
    step = s.get("step", "LEAGUE")

    # STEP 1: Choose League
    if step == "LEAGUE":
        league = LEAGUES.get(tl)
        if not league:
            reply(user_id, f'"{text}" not recognized.\n\n{WELCOME}')
            return jsonify({}), 200

        s["league"] = league
        teams = espn.get_teams(league)
        if not teams:
            reply(user_id, "Couldn't load teams. Try again.\nText MENU to restart.")
            reset(user_id)
            return jsonify({}), 200

        s["teams"] = teams
        s["step"]  = "TEAM"
        reply(user_id, (
            f"{league.upper()} -- Choose a team:\n"
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
            return jsonify({}), 200

        s["team_id"]   = team["id"]
        s["team_name"] = team["name"]
        s["step"]      = "CATEGORY"
        reply(user_id, f'{team["name"]} selected!\n------------------\n{CATEGORY_MENU}')

    # STEP 3: Choose Category
    elif step == "CATEGORY":
        cat = CATEGORIES.get(tl)
        if not cat:
            reply(user_id, f'"{text}" not recognized.\n\n{CATEGORY_MENU}')
            return jsonify({}), 200

        league    = s["league"]
        team_id   = s["team_id"]
        team_name = s["team_name"]

        reply(user_id, f"Fetching {cat} for {team_name}...")
        result    = espn.get_data(league, team_id, team_name, cat)
        s["step"] = "AGAIN"
        reply(user_id, result)
        reply(user_id, AFTER_MENU)

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
                f"{league.upper()} -- Pick a team:\n"
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

    return jsonify({}), 200


# -- Health check --------------------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return "Sports Bot is running!", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
