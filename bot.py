#!/usr/bin/env python3
"""Reddit Weather Bot — posts a daily weather update to a subreddit for a US zip code.

Usage:
    python bot.py test        # fetch weather and print the post (does not touch Reddit)
    python bot.py post        # fetch weather and post to the subreddit now
    python bot.py schedule    # run forever; posts once per day at the configured hour

Weather sources (no API keys needed):
    * zip -> coordinates : https://api.zippopotam.us
    * forecast           : https://open-meteo.com

Reddit credentials come from environment variables or a local `.env` file —
see `.env.example`.
"""
from __future__ import annotations

import argparse
import calendar
import json
import logging
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
STATE_PATH = BASE_DIR / ".state.json"
ENV_PATH = BASE_DIR / ".env"

log = logging.getLogger("weatherbot")

# WMO weather interpretation codes used by Open-Meteo.
WMO_WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Freezing drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Freezing rain",
    71: "Light snowfall",
    73: "Snowfall",
    75: "Heavy snowfall",
    77: "Snow grains",
    80: "Light rain showers",
    81: "Rain showers",
    82: "Violent rain showers",
    85: "Light snow showers",
    86: "Snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with light hail",
    99: "Thunderstorm with heavy hail",
}


# --------------------------------------------------------------------------- setup

def load_dotenv(path: Path = ENV_PATH) -> None:
    """Tiny .env loader so python-dotenv isn't required."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        sys.exit(f"Missing {CONFIG_PATH} — create it as described in README.md.")
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if not cfg.get("subreddit"):
        sys.exit('config.json: "subreddit" is required.')
    if not cfg.get("zip_code"):
        sys.exit('config.json: "zip_code" is required.')
    return cfg


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- weather

def fetch_location(zip_code: str) -> dict:
    """Resolve a US zip code to coordinates and a place name."""
    url = f"https://api.zippopotam.us/us/{zip_code.strip()}"
    resp = requests.get(url, timeout=15)
    if resp.status_code == 404:
        sys.exit(f"Zip code {zip_code!r} not found in the US zip database.")
    resp.raise_for_status()
    place = resp.json()["places"][0]
    return {
        "zip": zip_code.strip(),
        "name": place.get("place name", "Unknown"),
        "state": place.get("state abbreviation", ""),
        "lat": float(place["latitude"]),
        "lon": float(place["longitude"]),
    }


def fetch_weather(lat: float, lon: float) -> dict:
    """Fetch current + daily weather from Open-Meteo (imperial units)."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "current": ",".join([
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "weather_code",
            "wind_speed_10m",
            "wind_direction_10m",
        ]),
        "daily": ",".join([
            "weather_code",
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_probability_max",
            "sunrise",
            "sunset",
            "uv_index_max",
        ]),
        "timezone": "auto",
        "forecast_days": 1,
    }
    resp = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _weather_name(code: object) -> str:
    try:
        return WMO_WEATHER_CODES.get(int(code), "Unknown conditions")
    except (TypeError, ValueError):
        return "Unknown conditions"


def _compass(degrees: float) -> str:
    points = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
              "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")
    return points[int((degrees / 22.5) + 0.5) % 16]


def _fmt_time(iso: str) -> str:
    t = datetime.fromisoformat(iso)
    hour = t.strftime("%I").lstrip("0") or "12"
    return f"{hour}:{t.strftime('%M')} {t.strftime('%p')}"


def build_post(cfg: dict, loc: dict, weather: dict) -> tuple[str, str]:
    """Return (title, body) for the Reddit post."""
    now = weather["current"]
    daily = weather["daily"]
    today = date.today()
    date_label = f"{calendar.month_name[today.month]} {today.day}, {today.year}"
    location = f"{loc['name']}, {loc['state']}".strip(", ")

    title = f"Daily weather — {location} ({loc['zip']}) · {date_label}"

    precip = (daily.get("precipitation_probability_max") or [None])[0]
    lines = [
        f"## Weather in {location} ({loc['zip']})",
        "",
        f"- **Now:** {now['temperature_2m']}°F — {_weather_name(now['weather_code'])}",
        f"- **Feels like:** {now['apparent_temperature']}°F",
        f"- **High / Low:** {daily['temperature_2m_max'][0]}°F / {daily['temperature_2m_min'][0]}°F",
        f"- **Wind:** {now['wind_speed_10m']} mph {_compass(now['wind_direction_10m'])}",
        f"- **Humidity:** {now['relative_humidity_2m']}%",
    ]
    if precip is not None:
        lines.append(f"- **Chance of precipitation:** {precip}%")
    lines += [
        f"- **Sunrise / Sunset:** {_fmt_time(daily['sunrise'][0])} / {_fmt_time(daily['sunset'][0])}",
        f"- **UV index:** {int(daily['uv_index_max'][0])}",
        "",
        "---",
        "_Auto-posted by a weather bot. Forecast data from [Open-Meteo](https://open-meteo.com)._",
    ]
    return title, "\n".join(lines)


# --------------------------------------------------------------------------- reddit

def make_reddit_client():
    try:
        import praw
    except ImportError:
        sys.exit("praw is not installed. Run: pip install -r requirements.txt")

    user_agent = os.environ.get(
        "REDDIT_USER_AGENT",
        "reddit-weather-bot/1.0 (daily weather poster)",
    )
    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    username = os.environ.get("REDDIT_USERNAME")
    password = os.environ.get("REDDIT_PASSWORD")

    if client_id and client_secret:
        kwargs = dict(client_id=client_id, client_secret=client_secret, user_agent=user_agent)
        if username and password:
            kwargs.update(username=username, password=password)
    elif username and password:
        kwargs = dict(rusername=username, rpassword=password, user_agent=user_agent)
    else:
        sys.exit(
            "Missing Reddit credentials. Set REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, "
            "REDDIT_USERNAME and REDDIT_PASSWORD in .env (see .env.example)."
        )
    return praw.Reddit(**kwargs)


def cmd_post(cfg: dict) -> None:
    loc = fetch_location(cfg["zip_code"])
    weather = fetch_weather(loc["lat"], loc["lon"])
    title, body = build_post(cfg, loc, weather)

    client = make_reddit_client()
    submission = client.subreddit(cfg["subreddit"]).submit(title=title, text=body)
    log.info("Posted to r/%s: %s", cfg["subreddit"], submission.url)
    save_state({**load_state(), "last_posted": date.today().isoformat()})


def cmd_test(cfg: dict) -> None:
    loc = fetch_location(cfg["zip_code"])
    weather = fetch_weather(loc["lat"], loc["lon"])
    title, body = build_post(cfg, loc, weather)
    print("=" * 60)
    print("TITLE:", title)
    print("=" * 60)
    print(body)


def cmd_schedule(cfg: dict) -> None:
    hour = int(cfg.get("post_hour", 8))
    log.info(
        "Scheduler running: will post once per day around %02d:00 local time. Ctrl+C to stop.",
        hour,
    )
    while True:
        now = datetime.now()
        today = date.today().isoformat()
        if now.hour == hour and load_state().get("last_posted") != today:
            try:
                cmd_post(cfg)
            except Exception:
                log.exception("Scheduled post failed; will retry on the next loop.")
        time.sleep(30)


# --------------------------------------------------------------------------- main

def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = argparse.ArgumentParser(
        description="Post a daily weather update for a US zip code to a Reddit subreddit."
    )
    parser.add_argument(
        "command",
        choices=["test", "post", "schedule"],
        help="test = print the post, post = post now, schedule = run daily at the configured hour",
    )
    args = parser.parse_args()
    cfg = load_config()
    {"test": cmd_test, "post": cmd_post, "schedule": cmd_schedule}[args.command](cfg)


if __name__ == "__main__":
    main()
