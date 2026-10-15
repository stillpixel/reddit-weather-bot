# Reddit Weather Bot

A small Python bot that posts a **daily weather update** for a location (US zip code)
to a Reddit subreddit.

- **Zip code → coordinates:** [zippopotam.us](https://api.zippopotam.us) (free, no API key)
- **Forecast:** [Open-Meteo](https://open-meteo.com) (free, no API key)
- **Posting:** [PRAW](https://praw.readthedocs.io/) (Reddit API)

## What the post looks like

> **Title:** Daily weather — Beverly Hills, CA (90210) · October 15, 2026
>
> ## Weather in Beverly Hills, CA (90210)
>
> - **Now:** 72°F — Partly cloudy
> - **Feels like:** 74°F
> - **High / Low:** 78°F / 58°F
> - **Wind:** 8 mph NW
> - **Humidity:** 45%
> - **Chance of precipitation:** 20%
> - **Sunrise / Sunset:** 6:58 AM / 6:02 PM
> - **UV index:** 6

## Setup

1. **Install Python 3.10+**, then:
   ```
   pip install -r requirements.txt
   ```

2. **Create a Reddit API app** at [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps):
   - Click **create another app**
   - Name: anything (e.g. `weatherbot`)
   - Type: **script**
   - Redirect uri: `http://localhost:8080` (not used, but required)
   - Copy the **client id** (under the app name) and **client secret**.

3. **Fill in credentials** — copy `.env.example` to `.env` and add your values:
   ```
   REDDIT_CLIENT_ID=...
   REDDIT_CLIENT_SECRET=...
   REDDIT_USERNAME=your_reddit_account
   REDDIT_PASSWORD=your_reddit_password
   ```

4. **Configure the bot** in `config.json`:
   ```json
   {
     "subreddit": "your_subreddit",   // where to post (no leading r/)
     "zip_code": "90210",             // location
     "post_hour": 8                   // hour of day (24h, local time)
   }
   ```

## Usage

```
python bot.py test        # fetch weather and print the post — no Reddit needed
python bot.py post        # post to the subreddit right now
python bot.py schedule    # run forever; posts once per day at "post_hour"
```

`test` and `post` are safe to run any number of times. The `schedule` loop keeps a
`.state.json` so it only posts once per day, even if the machine restarts.

## Daily posting — pick one

### Option A: keep the scheduler running

Run `python bot.py schedule` and leave it running (e.g. start it with Windows at
login via Task Scheduler: *"At log on"* → action `python C:\path\to\bot.py schedule`).

### Option B: let Windows Task Scheduler do the timing

Create a task that runs once a day:

1. Open **Task Scheduler** → *Create Basic Task*
2. Trigger: daily, pick the time you want (e.g. 08:00)
3. Action: **Start a program**
   - Program: `python`
   - Arguments: `C:\path\to\reddit-weather-bot\bot.py post`
   - Start in: `C:\path\to\reddit-weather-bot`

The bot only needs to run for a few seconds, so this is the lightest option.

## Notes

- Check your subreddit's rules — some communities disallow automated posting.
- Reddit's API requires the bot account to already be a member of the subreddit
  (or you can't post there).
- No rate-limit worries: this is one post per day.
- Want multiple locations? Change `zip_code` to a list and loop in `cmd_post` —
  or ask and I'll add it.
