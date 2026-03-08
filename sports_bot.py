"""
sports_bot.py — GroupMe Sports Bot
====================================
Handles the full conversation flow over GroupMe / SMS:
  League → Team → Category → Live ESPN Data

Run locally:  python sports_bot.py
Deploy free:  Render.com (see README.md)
"""

from flask import Flask, request, jsonify
import os
import requests
import espn

app = Flask(__name__)

BOT_ID = os.environ.get("GROUPME_BOT_ID", "YOUR_BOT_ID_HERE")

# ── In-memory sessions: { user_id: { step, league, team_id, team_name, teams } }
sessions = {}

# ── League/Category constants ──────────────────────────────────────────────────
LEAGUES      = {"1": "nhl", "2": "nba", "3": "nfl", "4": "mlb",
                "nhl": "nhl", "nba": "nba", "nfl": "nfl", "mlb": "mlb"}
CATEGORIES   = {"1": "scores", "2": "schedule", "3": "roster", "4": "news", "5": "standings",
                "scores": "scores", "schedule": "schedule",
                "roster": "roster", "news": "news", "standings": "standings"}
LEAGUE_EMOJI = {"nhl": "🏒", "nba": "🏀", "nfl": "🏈", "mlb": "⚾"}

WELCOME = (
    "🏟 SPORTS BOT\n"
    "━━━━━━━━━━━━━\n"
    "Pick a league:\n"
    "1. NHL 🏒\n"
    "2. NBA 🏀\n"
    "3. NFL 🏈\n"
    "4. MLB ⚾\n"
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


# ── GroupMe sender ─────────────────────────────────────────────────────────────
def send(text):
    """Post a message to the GroupMe group via bot."""
    requests.post(
        "https://api.groupme.com/v3/bots/post",
        json={"bot_id": BOT_ID, "text": text},
        timeout=5,
    )


# ── Session helpers ────────────────────────────────────────────────────────────
def session(uid):
    if uid not in sessions:
        sessions[uid] = {"step": "LEAGUE"}
    return sessions[uid]

def reset(uid):
    sessions[uid] = {"step": "LEAGUE"}


# ── Team list formatter ────────────────────────────────────────────────────────
def team_list_text(teams):
    lines = [f"{i+1}. {t['name']}" for i, t in enumerate(teams)]
    # GroupMe/SMS works fine with long messages — split if >30 teams
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


# ── Main webhook ───────────────────────────────────────────────────────────────
@app.route("/groupme", methods=["POST"])
def groupme_webhook():
    data    = request.get_json(force=True)
    user_id = data.get("user_id", "")
    name    = data.get("name", "")
    text    = data.get("text", "").strip()
    sender  = data.get("sender_type", "")

    # Ignore bot's own messages
    if sender == "bot":
        return jsonify({}), 200

    # Ignore empty
    if not text:
        return jsonify({}), 200

    tl = text.lower()

    # ── Global commands ────────────────────────────────────────────────────────
    if tl in ("menu", "restart", "reset", "start", "hi", "hello"):
        reset(user_id)
        send(WELCOME)
        return jsonify({}), 200

    if tl == "help":
        send(
            "SPORTS BOT HELP\n"
            "━━━━━━━━━━━━━━━\n"
            "• MENU — restart\n"
            "• HELP — this message\n"
            "Works 100% by text.\n"
            "No app or internet needed!"
        )
        return jsonify({}), 200

    s    = session(user_id)
    step = s.get("step", "LEAGUE")

    # ── STEP 1: Choose League ──────────────────────────────────────────────────
    if step == "LEAGUE":
        league = LEAGUES.get(tl)
        if not league:
            send(f'"{text}" not recognized.\n\n{WELCOME}')
            return jsonify({}), 200

        s["league"] = league
        teams = espn.get_teams(league)
        if not teams:
            send("Couldn't load teams right now. Try again.\nText MENU to restart.")
            reset(user_id)
            return jsonify({}), 200

        s["teams"] = teams
        s["step"]  = "TEAM"
        emoji = LEAGUE_EMOJI.get(league, "")
        send(
            f"{league.upper()} {emoji} — Choose a team:\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{team_list_text(teams)}\n\n"
            f"Reply with number or team name."
        )

    # ── STEP 2: Choose Team ────────────────────────────────────────────────────
    elif step == "TEAM":
        teams = s.get("teams", [])
        team  = pick_team(text, teams)
        if not team:
            send(f'"{text}" not found.\nReply 1–{len(teams)} or type team name.\nText MENU to restart.')
            return jsonify({}), 200

        s["team_id"]   = team["id"]
        s["team_name"] = team["name"]
        s["step"]      = "CATEGORY"
        send(f'{team["name"]} ✅\n━━━━━━━━━━━━━━━━━━\n{CATEGORY_MENU}')

    # ── STEP 3: Choose Category ────────────────────────────────────────────────
    elif step == "CATEGORY":
        cat = CATEGORIES.get(tl)
        if not cat:
            send(f'"{text}" not recognized.\n\n{CATEGORY_MENU}')
            return jsonify({}), 200

        league    = s["league"]
        team_id   = s["team_id"]
        team_name = s["team_name"]

        send(f"⏳ Fetching {cat} for {team_name}...")

        result = espn.get_data(league, team_id, team_name, cat)
        s["step"] = "AGAIN"
        send(result)
        send(AFTER_MENU)

    # ── STEP 4: After results ──────────────────────────────────────────────────
    elif step == "AGAIN":
        if tl in ("1", "same", "same team", "more"):
            s["step"] = "CATEGORY"
            send(f'{s["team_name"]}\n━━━━━━━━━━━━━━━━━━\n{CATEGORY_MENU}')

        elif tl in ("2", "new team", "team"):
            league = s["league"]
            teams  = s.get("teams", espn.get_teams(league))
            s["teams"] = teams
            s["step"]  = "TEAM"
            emoji = LEAGUE_EMOJI.get(league, "")
            send(
                f"{league.upper()} {emoji} — Pick a team:\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{team_list_text(teams)}\n\n"
                f"Reply with number or team name."
            )

        elif tl in ("3", "new league", "league"):
            reset(user_id)
            send(WELCOME)

        else:
            send(f'Reply 1 (same team), 2 (new team), 3 (new league)\nor text MENU.')

    else:
        reset(user_id)
        send(WELCOME)

    return jsonify({}), 200


# ── Health check for Render ────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def health():
    return "Sports Bot is running! 🏟", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
