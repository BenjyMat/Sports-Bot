"""
espn.py -- ESPN Public API (100% free, no key needed)
All data comes from ESPN's public API endpoints.
"""

import requests
from datetime import datetime

BASE    = "https://site.api.espn.com/apis/site/v2/sports"
CDNBASE = "https://site.web.api.espn.com/apis/site/v2/sports"
TIMEOUT = 8

SPORT_MAP = {
    "nhl": ("hockey",     "nhl"),
    "nba": ("basketball", "nba"),
    "nfl": ("football",   "nfl"),
    "mlb": ("baseball",   "mlb"),
}


def url(league, path=""):
    sport, lg = SPORT_MAP[league]
    return f"{BASE}/{sport}/{lg}{path}"


def safe_get(endpoint, params=None):
    try:
        r = requests.get(endpoint, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


# -- Teams ---------------------------------------------------------------------
def get_teams(league):
    data = safe_get(url(league, "/teams"), {"limit": 50})
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
    data = safe_get(url(league, "/scoreboard"))
    if not data:
        return f"Couldn't fetch scores for {team_name}."

    lines = [f"SCORES: {team_name.upper()}", "------------------"]
    found = 0

    for event in data.get("events", []):
        comps = event.get("competitions", [])
        if not comps:
            continue
        comp       = comps[0]
        teams_data = comp.get("competitors", [])

        our_team   = None
        other_team = None
        for t in teams_data:
            if t.get("team", {}).get("id") == team_id:
                our_team = t
            else:
                other_team = t

        if not our_team or not other_team:
            continue

        found      += 1
        our_score   = our_team.get("score", "?")
        other_score = other_team.get("score", "?")
        other_name  = other_team.get("team", {}).get("shortDisplayName", "Opponent")
        home_away   = "vs" if our_team.get("homeAway") == "home" else "@"

        status = event.get("status", {})
        state  = status.get("type", {}).get("state", "pre")
        detail = status.get("type", {}).get("shortDetail", "")

        if state == "in":
            line = f"LIVE {detail}\n  {team_name} {our_score} {home_away} {other_name} {other_score}"
        elif state == "post":
            won  = int(our_score or 0) > int(other_score or 0)
            icon = "W" if won else "L"
            line = f"{icon} {our_score}-{other_score} {home_away} {other_name}"
        else:
            game_date = event.get("date", "")
            try:
                dt       = datetime.fromisoformat(game_date.replace("Z", "+00:00"))
                date_str = dt.strftime("%a %b %-d")
            except Exception:
                date_str = game_date[:10]
            line = f"Upcoming: {date_str} {home_away} {other_name}"

        lines.append(line)

    if found == 0:
        lines.append("No recent games found.")

    return "\n".join(lines)


# -- Schedule ------------------------------------------------------------------
def get_schedule(league, team_id, team_name):
    data = safe_get(url(league, f"/teams/{team_id}/schedule"))
    if not data:
        return f"Couldn't fetch schedule for {team_name}."

    lines  = [f"SCHEDULE: {team_name.upper()}", "------------------"]
    events = data.get("events", [])

    upcoming = []
    for event in events:
        status = event.get("competitions", [{}])[0].get("status", {})
        state  = status.get("type", {}).get("state", "pre")
        if state == "pre":
            upcoming.append(event)

    if not upcoming:
        lines.append("No upcoming games found.")
        return "\n".join(lines)

    for event in upcoming[:6]:
        comp      = event.get("competitions", [{}])[0]
        game_date = event.get("date", "")
        opponents = comp.get("competitors", [])

        home_away = "vs"
        opp_name  = "TBD"
        for t in opponents:
            if t.get("team", {}).get("id") != team_id:
                opp_name  = t.get("team", {}).get("shortDisplayName", "Opponent")
                home_away = "vs" if t.get("homeAway") == "away" else "@"

        try:
            dt       = datetime.fromisoformat(game_date.replace("Z", "+00:00"))
            date_str = dt.strftime("%a %b %-d %-I:%M%p")
        except Exception:
            date_str = game_date[:10]

        lines.append(f"{date_str}\n  {home_away} {opp_name}")

    return "\n".join(lines)


# -- Roster --------------------------------------------------------------------
def get_roster(league, team_id, team_name):
    data = safe_get(url(league, f"/teams/{team_id}/roster"))
    if not data:
        return f"Couldn't fetch roster for {team_name}."

    lines    = [f"ROSTER: {team_name.upper()}", "------------------"]
    athletes = data.get("athletes", [])

    players = []
    if athletes and isinstance(athletes[0], dict) and "items" in athletes[0]:
        for group in athletes:
            pos_label = group.get("position", "")
            for p in group.get("items", []):
                players.append((p, pos_label))
    else:
        for p in athletes:
            players.append((p, ""))

    if not players:
        lines.append("No roster data available.")
        return "\n".join(lines)

    for player, group_pos in players[:25]:
        name    = player.get("displayName", player.get("fullName", "?"))
        pos     = player.get("position", {}).get("abbreviation", group_pos) if isinstance(player.get("position"), dict) else group_pos
        jersey  = player.get("jersey", "")
        num_str = f"#{jersey} " if jersey else ""
        pos_str = f" ({pos})" if pos else ""
        lines.append(f"{num_str}{name}{pos_str}")

    if len(players) > 25:
        lines.append(f"...+{len(players)-25} more")

    return "\n".join(lines)


# -- News ----------------------------------------------------------------------
def get_news(league, team_id, team_name):
    sport, lg = SPORT_MAP[league]

    # Try every known ESPN news endpoint format
    # Different leagues use different endpoints so we try all of them
    attempts = [
        (url(league, f"/teams/{team_id}/news"),                          None),
        (url(league, "/news"),                                           {"team": team_id}),
        (f"{CDNBASE}/{sport}/{lg}/teams/{team_id}/news",                 None),
        ("https://site.api.espn.com/apis/site/v2/sports/news",          {"team": team_id}),
        (f"https://site.api.espn.com/apis/v2/sports/{sport}/{lg}/news", {"team": team_id}),
        (url(league, "/news"),                                           None),
    ]

    articles = []
    for endpoint, params in attempts:
        data = safe_get(endpoint, params)
        if data:
            articles = data.get("articles", [])
            if articles:
                break

    lines = [f"NEWS: {team_name.upper()}", "------------------"]

    if not articles:
        lines.append("No news found right now. Try again later.")
        return "\n".join(lines)

    for article in articles[:5]:
        headline = article.get("headline", "No headline")
        desc     = article.get("description", "")
        pub      = article.get("published", "")

        try:
            dt      = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            pub_str = dt.strftime("%b %-d")
        except Exception:
            pub_str = ""

        date_tag = f" [{pub_str}]" if pub_str else ""
        lines.append(f"* {headline}{date_tag}")
        if desc:
            short_desc = desc[:120] + ("..." if len(desc) > 120 else "")
            lines.append(f"  {short_desc}")
        lines.append("")

    return "\n".join(lines).strip()


# -- Standings -----------------------------------------------------------------
def get_standings(league, team_id, team_name):
    data = safe_get(url(league, "/standings"))
    if not data:
        return f"Couldn't fetch standings for {league.upper()}."

    lines = [f"STANDINGS: {league.upper()}", "------------------"]

    for group in data.get("children", []):
        conf = group.get("name", "")
        if conf:
            lines.append(f"\n{conf}")
        entries = group.get("standings", {}).get("entries", [])
        for entry in entries[:8]:
            team   = entry.get("team", {}).get("displayName", "?")
            stats  = {s["name"]: s["displayValue"] for s in entry.get("stats", [])}
            wins   = stats.get("wins",   stats.get("W", "?"))
            losses = stats.get("losses", stats.get("L", "?"))
            pct    = stats.get("winPercent", stats.get("PCT", ""))
            pct_str = f" ({pct})" if pct else ""
            marker  = " <--YOU" if team_name.lower() in team.lower() else ""
            lines.append(f"  {team}: {wins}-{losses}{pct_str}{marker}")

    return "\n".join(lines)


# -- Dispatcher ----------------------------------------------------------------
def get_data(league, team_id, team_name, category):
    if category == "scores":
        return get_scores(league, team_id, team_name)
    elif category == "schedule":
        return get_schedule(league, team_id, team_name)
    elif category == "roster":
        return get_roster(league, team_id, team_name)
    elif category == "news":
        return get_news(league, team_id, team_name)
    elif category == "standings":
        return get_standings(league, team_id, team_name)
    return "Unknown category."
