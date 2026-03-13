"""
sports_bot.py -- GroupMe Sports Bot
SMS optimized. No emojis. Works on any basic phone.
"""

from flask import Flask, request, jsonify
import os
import requests
import espn
import threading
import time

app = Flask(__name__)

BOT_ID       = os.environ.get("GROUPME_BOT_ID",       "YOUR_BOT_ID_HERE")
ACCESS_TOKEN = os.environ.get("GROUPME_ACCESS_TOKEN", "YOUR_TOKEN_HERE")

sessions  = {}
bans      = {}
favorites = {}

PRANK_USER  = "18483671827"
PRANK_ASKED = set()

LEAGUES = {
    "1": "nhl", "2": "nba", "3": "nfl", "4": "mlb",
    "nhl": "nhl", "nba": "nba", "nfl": "nfl", "mlb": "mlb"
}
CATEGORIES = {
    "1": "scores", "2": "schedule", "3": "roster", "4": "news", "5": "standings",
    "scores": "scores", "schedule": "schedule", "roster": "roster",
    "news": "news", "standings": "standings"
}
LEAGUE_CATS = {
    "1": "league_scores", "2": "league_schedule", "3": "league_news",
    "scores": "league_scores", "schedule": "league_schedule", "news": "league_news"
}

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
    "1. Scores  2. Schedule\n"
    "3. Roster  4. News\n"
    "5. Standings"
)

LEAGUE_CAT_MENU = (
    "WHOLE LEAGUE:\n"
    "1. Scores\n"
    "2. Schedule\n"
    "3. News"
)

AFTER_MENU = (
    "1. Same team\n"
    "2. New team\n"
    "3. New league"
)

MSG_LIMIT = 155


def send_group(text):
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
    chunks = chunk_message(text)
    for i, chunk in enumerate(chunks):
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
    time.sleep(3)
    # Only send AFTER_MENU once per result batch
    s["after_sent"] = _time_now()
    reply(user_id, AFTER_MENU)

def _time_now():
    return time.time()


def session(uid):
    if uid not in sessions:
        sessions[uid] = {"step": "LEAGUE"}
    return sessions[uid]

def reset(uid):
    sessions[uid] = {"step": "LEAGUE"}


def team_list_text(teams):
    # Compact: number+abbrev per line to keep SMS short
    lines = [str(i+1) + "." + t.get("abbrev", t["name"][:3].upper()) + " " + t["name"] for i, t in enumerate(teams)]
    if len(lines) > 16:
        mid = len(lines) // 2
        return "\n".join(lines[:mid]) + "\n---\n" + "\n".join(lines[mid:])
    return "\n".join(lines)

def team_abbrev_list(teams):
    """Ultra-compact: just numbers and abbreviations, fits in 1-2 SMS"""
    chunks = []
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
    # Exact abbrev match first
    for team in teams:
        if t == team.get("abbrev", "").lower():
            return team
    # Partial name match
    for team in teams:
        if t in team["name"].lower():
            return team
    return None


def run_fetch(fn, timeout=10):
    holder = [None]
    def go():
        holder[0] = fn()
    t = threading.Thread(target=go)
    t.start()
    t.join(timeout=timeout)
    if t.is_alive():
        reply(None, "Still loading...")
        t.join(timeout=15)
    return holder[0]


def parse_quick_command(text, all_teams_cache):
    """
    Parse a full one-line command like:
    "nba lakers scores"
    "nhl kings standings"
    "mlb dodgers scores info"
    Returns dict with keys: league, team, category, info
    or None if not a quick command.
    """
    words = text.lower().split()
    if len(words) < 2:
        return None

    result = {"league": None, "team": None, "category": None, "info": False}

    # Check for "info" at the end
    if words[-1] in ("info", "details", "more"):
        result["info"] = True
        words = words[:-1]

    # Find league word
    league_words = {"nhl": "nhl", "nba": "nba", "nfl": "nfl", "mlb": "mlb",
                    "hockey": "nhl", "basketball": "nba", "football": "nfl", "baseball": "mlb"}
    cat_words = {"scores": "scores", "score": "scores", "schedule": "schedule",
                 "roster": "roster", "news": "news", "standings": "standings",
                 "standing": "standings"}

    for w in words:
        if w in league_words:
            result["league"] = league_words[w]
        elif w in cat_words:
            result["category"] = cat_words[w]

    if not result["league"]:
        return None

    # Find team - remaining words after removing league/cat words
    team_words = [w for w in words if w not in league_words and w not in cat_words]
    if not team_words:
        return None

    # Look up team in that league
    teams = all_teams_cache.get(result["league"]) or espn.get_teams(result["league"])
    if teams:
        all_teams_cache[result["league"]] = teams
        team_query = " ".join(team_words)
        team = None
        # Try exact abbrev
        for t in teams:
            if team_query == t.get("abbrev", "").lower():
                team = t
                break
        # Try partial name
        if not team:
            for t in teams:
                if team_query in t["name"].lower():
                    team = t
                    break
        # Try each word individually
        if not team:
            for word in team_words:
                for t in teams:
                    if word in t["name"].lower() or word == t.get("abbrev", "").lower():
                        team = t
                        break
                if team:
                    break
        if team:
            result["team"] = team

    if not result["team"]:
        return None

    return result


_teams_cache = {}


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


def handle_message(user_id, data):
    text = data.get("text", "").strip()
    tl   = text.lower()
    name = data.get("name", "Someone")

    if user_id:
        s = session(user_id)
        s["name"] = name

    # Ban check
    if user_id in bans:
        if time.time() < bans[user_id]:
            mins_left = int((bans[user_id] - time.time()) / 60) + 1
            reply(user_id, "Banned " + str(mins_left) + " more min.\nKnicks fan.")
            return
        else:
            del bans[user_id]

    # Prank
    phone      = data.get("sender_id", data.get("user_id", ""))
    normalized = phone.replace("+", "").replace("-", "").replace(" ", "")
    if PRANK_USER in normalized or normalized in PRANK_USER:
        if user_id not in PRANK_ASKED:
            PRANK_ASKED.add(user_id)
            reply(user_id, "Answer one question:\nLakers or Knicks?")
            return
        elif any(x in tl for x in ("knicks", "new york", "ny")):
            bans[user_id] = time.time() + 3600
            PRANK_ASKED.discard(user_id)
            reply(user_id, "WRONG. Banned 1 hour.\nShame on you.")
            return
        elif any(x in tl for x in ("lakers", "la lakers", "los angeles lakers")):
            PRANK_ASKED.discard(user_id)
            reply(user_id, "Correct!\n\n" + WELCOME)
            return
        elif user_id in PRANK_ASKED:
            reply(user_id, "Lakers or Knicks?")
            return

    # Global commands
    if tl in ("menu", "restart", "reset", "start", "hi", "hello"):
        reset(user_id)
        reply(user_id, WELCOME)
        return

    if tl == "help":
        reply(user_id,
            "SPORTS BOT HELP\n"
            "---------------\n"
            "MENU - start over\n"
            "FAV  - save fav teams\n"
            "MY   - jump to fav team\n"
            "\n"
            "HOW TO USE:\n"
            "1. Pick league (1-4)\n"
            "2. Pick team (or 0 for\n"
            "   whole league view)\n"
            "3. Pick category 1-5\n"
            "\n"
            "After scores text INFO\n"
            "for scorer details.\n"
            "\n"
            "After results:\n"
            "1=same 2=new team\n"
            "3=new league"
        )
        return

    # -- Quick command parser: "nba lakers scores" or "nhl kings standings info" --
    if len(tl.split()) >= 2 and tl.split()[0] in ("nhl","nba","nfl","mlb","hockey","basketball","football","baseball"):
        qc = parse_quick_command(tl, _teams_cache)
        if qc and qc["team"]:
            league    = qc["league"]
            team      = qc["team"]
            category  = qc["category"]
            do_info   = qc["info"]
            # Store in session
            s["league"]    = league
            s["team_id"]   = team["id"]
            s["team_name"] = team["name"]
            s["step"]      = "AGAIN"
            if not category:
                # No category given - just set team and ask
                reply(user_id, team["name"] + "\n" + CATEGORY_MENU)
                s["step"] = "CATEGORY"
                return
            # Fetch the data
            result = run_fetch(lambda: espn.get_data(league, team["id"], team["name"], category))
            result = result or ["Could not load data."]
            send_results(user_id, result, s)
            # If they also want info, fetch that too
            if do_info and category == "scores":
                time.sleep(2)
                info = run_fetch(lambda: espn.get_score_details(league, team["id"], team["name"]))
                info = info or ["No detail available."]
                uname = s.get("name", "Someone")
                tag   = "[" + uname + "]"
                for i, msg in enumerate(info):
                    if i > 0:
                        time.sleep(2)
                    reply(user_id, tag + " " + msg if i == 0 else msg)
            return

    # FAV command
    if tl == "fav":
        favs     = favorites.get(user_id, {})
        nhl_name = favs.get("nhl", {}).get("name", "not set")
        nba_name = favs.get("nba", {}).get("name", "not set")
        nfl_name = favs.get("nfl", {}).get("name", "not set")
        mlb_name = favs.get("mlb", {}).get("name", "not set")
        s        = session(user_id)
        s["step"] = "FAV_LEAGUE"
        reply(user_id,
            "Your favorites:\n"
            "NHL: " + nhl_name + "\n"
            "NBA: " + nba_name + "\n"
            "NFL: " + nfl_name + "\n"
            "MLB: " + mlb_name + "\n"
            "\nSet one:\n"
            "1.NHL 2.NBA 3.NFL 4.MLB"
        )
        return

    # MY command
    if tl == "my":
        favs     = favorites.get(user_id, {})
        set_favs = [(lg, favs[lg]) for lg in ("nhl", "nba", "nfl", "mlb") if favs.get(lg)]
        if not set_favs:
            reply(user_id, "No favorites set.\nText FAV to set them.")
            return
        lines = ["Your favorites:"]
        for i, (lg, team) in enumerate(set_favs, 1):
            lines.append(str(i) + ". " + lg.upper() + " - " + team["name"])
        lines.append("Pick one.")
        s            = session(user_id)
        s["step"]    = "MY_PICK"
        s["my_favs"] = set_favs
        reply(user_id, "\n".join(lines))
        return

    s    = session(user_id)
    step = s.get("step", "LEAGUE")

    # FAV_LEAGUE
    if step == "FAV_LEAGUE":
        league = LEAGUES.get(tl)
        if not league:
            reply(user_id, "Pick:\n1.NHL 2.NBA 3.NFL 4.MLB")
            return
        teams = espn.get_teams(league)
        if not teams:
            reply(user_id, "Couldn't load teams.")
            return
        s["fav_league"] = league
        s["teams"]      = teams
        s["step"]       = "FAV_TEAM"
        reply(user_id, league.upper() + " - Pick favorite:\n" + team_list_text(teams))
        return

    # FAV_TEAM
    if step == "FAV_TEAM":
        teams  = s.get("teams", [])
        team   = pick_team(text, teams)
        league = s.get("fav_league")
        if not team:
            reply(user_id, "Not found. Try again.")
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

    # LEAGUE_CAT: whole league category
    if step == "LEAGUE_CAT":
        cat = LEAGUE_CATS.get(tl)
        if not cat:
            reply(user_id, LEAGUE_CAT_MENU)
            return
        league         = s.get("league")
        s["step"]      = "AGAIN"
        s["team_name"] = league.upper() + " (All)"
        s["last_cat"]  = cat
        result = run_fetch(lambda: espn.get_league_data(league, cat))
        result = result or ["Could not load data."]
        send_results(user_id, result, s)
        return

    # STEP 1: League
    if step == "LEAGUE":
        league = LEAGUES.get(tl)
        if not league:
            reply(user_id, '"' + text + '" not recognized.\n\n' + WELCOME)
            return
        s["league"] = league
        teams = espn.get_teams(league)
        if not teams:
            reply(user_id, "Couldn't load teams.\nText MENU to restart.")
            reset(user_id)
            return
        s["teams"] = teams
        s["step"]  = "TEAM"
        # Send compact abbrev list first (fits in 1-2 SMS), then full names
        abbrev_chunks = team_abbrev_list(teams)
        for i, chunk in enumerate(abbrev_chunks):
            if i > 0:
                time.sleep(2)
            reply(user_id, league.upper() + " teams:\n" + chunk if i == 0 else chunk)
        time.sleep(2)
        reply(user_id, "Type name, abbrev, or\nnumber. 0=league view.")

    # STEP 2: Team
    elif step == "TEAM":
        if tl == "0":
            s["step"] = "LEAGUE_CAT"
            reply(user_id, LEAGUE_CAT_MENU)
            return
        teams = s.get("teams", [])
        team  = pick_team(text, teams)
        if not team:
            reply(user_id, '"' + text + '" not found.\nPick number or name.\nMENU to restart.')
            return
        s["team_id"]   = team["id"]
        s["team_name"] = team["name"]
        s["step"]      = "CATEGORY"
        reply(user_id, team["name"] + "\n" + CATEGORY_MENU)

    # STEP 3: Category
    elif step == "CATEGORY":
        try:
            if int(tl) > 5:
                reply(user_id, "Pick 1-5:\n" + CATEGORY_MENU)
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
        if tl in ("info", "more info", "details", "who scored", "scorers"):
            league    = s.get("league")
            team_id   = s.get("team_id")
            team_name = s.get("team_name", "")
            if league and team_id:
                result = run_fetch(lambda: espn.get_score_details(league, team_id, team_name))
                result = result or ["No detail available."]
                send_results(user_id, result, s)
            else:
                reply(user_id, "No score loaded yet.")
            return
        if tl in ("1", "same", "same team"):
            s["step"] = "CATEGORY"
            reply(user_id, s["team_name"] + "\n" + CATEGORY_MENU)
        elif tl in ("2", "new team", "team"):
            league = s["league"]
            teams  = s.get("teams", espn.get_teams(league))
            s["teams"] = teams
            s["step"]  = "TEAM"
            abbrev_chunks = team_abbrev_list(teams)
            for i, chunk in enumerate(abbrev_chunks):
                if i > 0:
                    time.sleep(2)
                reply(user_id, league.upper() + " teams:\n" + chunk if i == 0 else chunk)
            time.sleep(2)
            reply(user_id, "Type name, abbrev, or\nnumber. 0=league view.")
        elif tl in ("3", "new league", "league"):
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
