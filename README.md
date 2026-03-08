# 🏟 Sports SMS Bot — Complete Setup Guide

Works 100% by text message. No app or internet required for users.
Everything is FREE with no trial limits.

---

## What You Need (all free, takes ~15 minutes)

| Service | What it does | Cost |
|---------|-------------|------|
| GroupMe | The texting platform | FREE forever |
| Render.com | Hosts your bot 24/7 | FREE forever |
| ESPN API | Live sports data | FREE, no key needed |
| GitHub | Stores your code | FREE forever |

---

## STEP 1 — Create Your GroupMe Bot (5 min)

1. Go to **https://dev.groupme.com** and sign in (or create a free account)
2. Click **"Create Bot"**
3. Fill in:
   - **Name:** Sports Bot (or whatever you want)
   - **Group:** Create a new group OR pick an existing one
   - **Callback URL:** Leave blank for now — you'll fill this in after Step 3
   - **Avatar URL:** (optional) any image URL
4. Click **Submit**
5. You'll see your **Bot ID** — copy it, you'll need it soon

### How SMS users join your group (no app needed):
- In GroupMe, go to your group → click the group name → **"Share"**
- GroupMe gives a phone number people can TEXT to join and participate
- Members on basic phones can text that number just like any regular SMS
- They never need to download anything

---

## STEP 2 — Put Your Code on GitHub (3 min)

1. Go to **https://github.com** and create a free account
2. Click **"New repository"**, name it `sports-bot`, make it **Public**
3. Upload all these files to the repo:
   - `sports_bot.py`
   - `espn.py`
   - `requirements.txt`
   - `Procfile`
   - `README.md`
4. Click **"Commit changes"**

---

## STEP 3 — Deploy to Render.com (5 min)

1. Go to **https://render.com** and sign up free (use your GitHub account)
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repo (`sports-bot`)
4. Fill in:
   - **Name:** sports-bot
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn sports_bot:app`
5. Under **Environment Variables**, click **"Add Environment Variable"**:
   - Key: `GROUPME_BOT_ID`
   - Value: (paste your Bot ID from Step 1)
6. Click **"Create Web Service"**
7. Wait ~2 minutes for it to deploy
8. Copy your Render URL — it looks like: `https://sports-bot-xxxx.onrender.com`

---

## STEP 4 — Connect GroupMe to Your Bot (1 min)

1. Go back to **https://dev.groupme.com**
2. Find your bot and click **Edit**
3. Set **Callback URL** to:
   ```
   https://sports-bot-xxxx.onrender.com/groupme
   ```
   (use your actual Render URL)
4. Click **Save**

---

## STEP 5 — Test It!

In your GroupMe group, type:
```
MENU
```
The bot should respond with the league menu. 

---

## How the Conversation Works

```
User:  MENU
Bot:   🏟 SPORTS BOT
       Pick a league:
       1. NHL 🏒
       2. NBA 🏀
       3. NFL 🏈
       4. MLB ⚾

User:  2
Bot:   NBA 🏀 — Choose a team:
       1. Atlanta Hawks
       2. Boston Celtics
       3. Brooklyn Nets
       ...

User:  6
Bot:   Golden State Warriors ✅
       What do you want?
       1. Scores
       2. Schedule
       3. Roster
       4. News

User:  1
Bot:   ⏳ Fetching scores for Golden State Warriors...
       📊 GOLDEN STATE WARRIORS SCORES
       ━━━━━━━━━━━━━━━━━━
       ✅ W 112-98 vs Lakers
       ❌ L 101-115 @ Celtics
       ...

Bot:   Want more?
       1. Same team
       2. New team
       3. New league
       Or text MENU to restart.
```

---

## Commands That Always Work

| Text | Does |
|------|------|
| `MENU` | Restart from beginning |
| `HELP` | Show instructions |
| `1`, `2`, `3`, `4` | Pick from numbered list |
| Team name | Type any part of the team name |

---

## Troubleshooting

**Bot not responding?**
- Check Render dashboard — is the service running?
- Make sure the Callback URL in GroupMe matches your Render URL exactly
- Check Render logs for errors

**"Couldn't load teams" error?**
- ESPN API is temporarily down — try again in a minute

**Render goes to sleep?**
- Free Render services sleep after 15 min of inactivity
- First message after idle takes ~30 seconds to wake up
- To prevent this: use https://uptimerobot.com (free) to ping your URL every 10 min

---

## Completely Free — No Hidden Costs

- ✅ GroupMe: Free forever
- ✅ Render.com free tier: 750 hours/month (enough for 24/7)
- ✅ ESPN API: Free, public, no key needed
- ✅ GitHub: Free forever
- ✅ Standard SMS rates apply for users on basic phones (same as any text)
