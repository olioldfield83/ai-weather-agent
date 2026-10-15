
import os
import csv
import random
import requests
import smtplib
import html

from pathlib import Path
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from email.mime.text import MIMEText
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# ============================================================
# CONFIGURATION
# ============================================================

CITY = os.getenv("CITY", "London")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
TO_EMAIL = os.getenv("TO_EMAIL")

LONDON_TZ = ZoneInfo("Europe/London")

PLACES_FILE = Path("places.csv")
RECOMMENDATION_HISTORY_FILE = Path("recommendation_history.csv")
LOG_FILE = Path("weather_log.txt")

# TfL station identifiers
MORDEN_STATION = "1000151"
CANARY_WHARF_STATION = "940GZZLUCYF"

COMMUTE_ROUTE = "Morden to Canary Wharf"

TFL_LINES = [
    "northern",
    "jubilee",
    "dlr",
    "elizabeth",
]

REQUEST_TIMEOUT = 20

client = OpenAI(api_key=OPENAI_API_KEY)


# ============================================================
# LOGGING
# ============================================================

def log(message):
    timestamp = datetime.now(LONDON_TZ).isoformat(
        timespec="seconds"
    )

    with open(LOG_FILE, "a", encoding="utf-8") as file:
        file.write(f"{timestamp} - {message}\n")

    print(f"{timestamp} - {message}")


# ============================================================
# API HELPERS
# ============================================================

def get_json(url, params=None):
    response = requests.get(
        url,
        params=params,
        timeout=REQUEST_TIMEOUT,
    )

    response.raise_for_status()
    return response.json()


# ============================================================
# CURRENT WEATHER
# ============================================================

def get_weather():
    data = get_json(
        "https://api.openweathermap.org/data/2.5/weather",
        params={
            "q": CITY,
            "appid": WEATHER_API_KEY,
            "units": "metric",
        },
    )

    return {
        "temp": data["main"]["temp"],
        "description": data["weather"][0]["description"],
        "humidity": data["main"]["humidity"],
        "wind": data["wind"]["speed"],
    }


# ============================================================
# WEATHER FORECAST
# ============================================================

def get_forecast():
    data = get_json(
        "https://api.openweathermap.org/data/2.5/forecast",
        params={
            "q": CITY,
            "appid": WEATHER_API_KEY,
            "units": "metric",
        },
    )

    forecast_items = data["list"]

    now_london = datetime.now(LONDON_TZ)
    tomorrow_date = (
        now_london.date() + timedelta(days=1)
    )

    next_24_hours = []
    tomorrow_items = []

    for item in forecast_items:
        forecast_time = datetime.fromtimestamp(
            item["dt"],
            tz=timezone.utc,
        ).astimezone(LONDON_TZ)

        forecast_entry = {
            "time": forecast_time.strftime(
                "%Y-%m-%d %H:%M"
            ),
            "temp": item["main"]["temp"],
            "description": item["weather"][0]["description"],
            "rain_probability": round(
                item.get("pop", 0) * 100
            ),
            "wind": item["wind"]["speed"],
        }

        if (
            now_london
            <= forecast_time
            <= now_london + timedelta(hours=24)
        ):
            next_24_hours.append(forecast_entry)

        if forecast_time.date() == tomorrow_date:
            tomorrow_items.append(forecast_entry)

    if not next_24_hours:
        raise ValueError(
            "No forecast periods found for the next 24 hours"
        )

    if not tomorrow_items:
        raise ValueError(
            "No forecast periods found for tomorrow"
        )

    tomorrow_temps = [
        item["temp"] for item in tomorrow_items
    ]

    tomorrow_rain = [
        item["rain_probability"]
        for item in tomorrow_items
    ]

    # Prefer a daytime forecast for tomorrow's description.
    daytime_items = [
        item for item in tomorrow_items
        if 11 <= int(item["time"][11:13]) <= 16
    ]

    representative = (
        daytime_items[len(daytime_items) // 2]
        if daytime_items
        else tomorrow_items[len(tomorrow_items) // 2]
    )

    return {
        "next_24_hours": next_24_hours,
        "tomorrow": {
            "date": tomorrow_date.isoformat(),
            "min_temp": round(min(tomorrow_temps)),
            "max_temp": round(max(tomorrow_temps)),
            "max_rain_probability": max(tomorrow_rain),
            "conditions": representative["description"],
        },
    }


# ============================================================
# FORECAST ANALYSIS
# ============================================================

def analyze_forecast(forecast):
    periods = forecast["next_24_hours"]

    highest_rain = max(
        periods,
        key=lambda item: item["rain_probability"],
    )

    hottest = max(
        periods,
        key=lambda item: item["temp"],
    )

    coldest = min(
        periods,
        key=lambda item: item["temp"],
    )

    strongest_wind = max(
        periods,
        key=lambda item: item["wind"],
    )

    rain = highest_rain["rain_probability"]
    wind = strongest_wind["wind"]

    if rain >= 70 or wind >= 12:
        commute_risk = "High"
    elif rain >= 40 or wind >= 8:
        commute_risk = "Medium"
    else:
        commute_risk = "Low"

    return {
        "highest_rain_probability": {
            "time": highest_rain["time"],
            "value": rain,
            "conditions": highest_rain["description"],
        },
        "hottest_period": {
            "time": hottest["time"],
            "temp": round(hottest["temp"]),
            "conditions": hottest["description"],
        },
        "coldest_period": {
            "time": coldest["time"],
            "temp": round(coldest["temp"]),
            "conditions": coldest["description"],
        },
        "strongest_wind": {
            "time": strongest_wind["time"],
            "speed": wind,
            "conditions": strongest_wind["description"],
        },
        "commute_risk_score": commute_risk,
    }


# ============================================================
# TFL COMMUTE: MORDEN TO CANARY WHARF
# ============================================================

def get_commute():
    url = (
        "https://api.tfl.gov.uk/Journey/JourneyResults/"
        f"{MORDEN_STATION}/to/{CANARY_WHARF_STATION}"
    )

    data = get_json(
        url,
        params={
            "mode": "tube",
            "journeyPreference": "leasttime",
        },
    )

    journeys = data.get("journeys", [])

    if not journeys:
        raise ValueError(
            f"No TfL journeys returned for {COMMUTE_ROUTE}"
        )

    journey = journeys[0]

    # Extract actual transport lines from journey legs.
    lines_used = []

    for leg in journey.get("legs", []):
        route_options = leg.get("routeOptions", [])

        for option in route_options:
            line_name = option.get("name")

            if line_name and line_name not in lines_used:
                lines_used.append(line_name)

    return {
        "route": COMMUTE_ROUTE,
        "duration": f"{journey['duration']} mins",
        "start_time": journey.get("startDateTime"),
        "arrival_time": journey.get("arrivalDateTime"),
        "lines_used": lines_used,
    }


# ============================================================
# TFL SERVICE STATUS
# ============================================================

def get_tube_status():
    line_ids = ",".join(TFL_LINES)

    url = (
        "https://api.tfl.gov.uk/Line/"
        f"{line_ids}/Status"
    )

    data = get_json(url)

    statuses = []

    for line in data:
        line_statuses = line.get("lineStatuses", [])

        descriptions = []

        for status in line_statuses:
            description = status.get(
                "statusSeverityDescription",
                "Unknown",
            )

            reason = status.get("reason", "")

            if reason and description != "Good Service":
                descriptions.append(
                    f"{description}: {reason}"
                )
            else:
                descriptions.append(description)

        statuses.append({
            "line": line.get("name", "Unknown"),
            "status": "; ".join(descriptions)
            or "Unavailable",
        })

    return statuses


# ============================================================
# LOAD LONDON PLACES
# ============================================================

def load_places():
    if not PLACES_FILE.exists():
        raise FileNotFoundError(
            "places.csv was not found. "
            "Add it to the same folder as weather_agent.py."
        )

    with open(
        PLACES_FILE,
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        places = list(csv.DictReader(file))

    if not places:
        raise ValueError("places.csv contains no places")

    required_columns = {
        "name",
        "category",
        "area",
        "indoor",
        "outdoor",
        "rain_good",
        "cold_good",
        "hot_good",
        "dry_good",
        "wind_good",
        "max_commute_mins",
        "description",
    }

    missing = required_columns - set(places[0].keys())

    if missing:
        raise ValueError(
            "places.csv is missing columns: "
            + ", ".join(sorted(missing))
        )

    return [
        place for place in places
        if place.get("name", "").strip()
    ]


# ============================================================
# RECOMMENDATION HISTORY
# ============================================================

def load_used_recommendations():
    if not RECOMMENDATION_HISTORY_FILE.exists():
        return set()

    with open(
        RECOMMENDATION_HISTORY_FILE,
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        rows = list(csv.DictReader(file))

    return {
        row["name"].strip().casefold()
        for row in rows
        if row.get("name")
    }


def save_recommendation(place):
    file_exists = (
        RECOMMENDATION_HISTORY_FILE.exists()
        and RECOMMENDATION_HISTORY_FILE.stat().st_size > 0
    )

    with open(
        RECOMMENDATION_HISTORY_FILE,
        "a",
        newline="",
        encoding="utf-8",
    ) as file:
        fieldnames = [
            "timestamp",
            "name",
            "category",
            "area",
        ]

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        if not file_exists:
            writer.writeheader()

        writer.writerow({
            "timestamp": datetime.now(
                LONDON_TZ
            ).isoformat(),
            "name": place["name"],
            "category": place["category"],
            "area": place["area"],
        })


# ============================================================
# WEATHER SUITABILITY SCORING
# ============================================================

def is_yes(place, field):
    return (
        place.get(field, "")
        .strip()
        .casefold() == "yes"
    )


def score_place(place, weather, analysis):
    score = 0

    rain = analysis[
        "highest_rain_probability"
    ]["value"]

    wind = analysis[
        "strongest_wind"
    ]["speed"]

    temp = weather["temp"]

    if rain >= 50 and is_yes(place, "rain_good"):
        score += 5

    if rain < 30 and is_yes(place, "dry_good"):
        score += 4

    if temp <= 10 and is_yes(place, "cold_good"):
        score += 3

    if temp >= 20 and is_yes(place, "hot_good"):
        score += 3

    if wind >= 8 and is_yes(place, "wind_good"):
        score += 2

    if is_yes(place, "indoor") and (
        rain >= 50 or temp <= 10
    ):
        score += 2

    if (
        is_yes(place, "outdoor")
        and rain < 30
        and wind < 8
    ):
        score += 2

    try:
        if int(place["max_commute_mins"]) <= 45:
            score += 2
    except (ValueError, TypeError, KeyError):
        pass

    return score


# ============================================================
# CHOOSE AN UNUSED RECOMMENDATION
# ============================================================

def choose_recommendation(weather, analysis):
    places = load_places()

    # Avoid duplicate place names in the CSV.
    unique_places = {}

    for place in places:
        key = place["name"].strip().casefold()
        unique_places.setdefault(key, place)

    places = list(unique_places.values())

    used_places = load_used_recommendations()

    unused_places = [
        place for place in places
        if place["name"].strip().casefold()
        not in used_places
    ]

    if not unused_places:
        log(
            "All places have been recommended. "
            "Starting a new recommendation cycle."
        )

        # Start a new cycle. The existing history is
        # archived rather than deleted.
        if RECOMMENDATION_HISTORY_FILE.exists():
            archive_name = (
                "recommendation_history_"
                + datetime.now(LONDON_TZ).strftime(
                    "%Y%m%d_%H%M%S"
                )
                + ".csv"
            )

            RECOMMENDATION_HISTORY_FILE.rename(
                RECOMMENDATION_HISTORY_FILE.with_name(
                    archive_name
                )
            )

        unused_places = places

    ranked = [
        {
            "place": place,
            "score": score_place(
                place,
                weather,
                analysis,
            ),
        }
        for place in unused_places
    ]

    ranked.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    top_choices = ranked[:10]

    if not top_choices:
        raise ValueError(
            "No places are available for recommendation"
        )

    selected = random.choice(top_choices)

    log(
        f"Selected {selected['place']['name']} "
        f"(weather suitability score: "
        f"{selected['score']})"
    )

    log(
        f"Places remaining in cycle: "
        f"{len(unused_places) - 1}"
    )

    return selected["place"]


# ============================================================
# AI-GENERATED EMAIL
# ============================================================

def generate_summary(
    weather,
    forecast,
    analysis,
    commute,
    tube_status,
    recommendation,
):
    now = datetime.now(LONDON_TZ)

    greeting_period = (
        "morning" if now.hour < 12
        else "afternoon" if now.hour < 18
        else "evening"
    )

    prompt = f"""
You are a friendly, accurate London weather and
public transport briefing assistant.

Write a short {greeting_period} email.

REQUIREMENTS:
- Start exactly with "Hello everyone"
- End exactly with "Take care everyone!"
- Keep the email under 200 words.
- Put each new sentence in a separate paragraph.
- Use natural British English.
- Include today's weather and temperature.
- Include tomorrow's forecast.
- Recommend suitable clothing.
- Highlight significant changes in the weather.
- Include the Morden to Canary Wharf commute.
- Include the estimated journey duration.
- Identify relevant transport disruptions.
- Prioritise Northern and Jubilee line disruptions.
- Mention DLR or Elizabeth line disruption when useful.
- If transport information is unavailable, say so.
- Do not claim the commute is disruption-free if
  live TfL information is unavailable.
- Explain whether rain or wind could affect
  the walking portions of the commute.
- Recommend ONLY the selected London attraction.
- Explain why it suits the weather.
- Do not suggest a different attraction.
- Do not invent opening hours, prices, or events.

CURRENT WEATHER:
Temperature: {round(weather['temp'])}°C
Conditions: {weather['description']}
Humidity: {weather['humidity']}%
Wind: {weather['wind']} m/s

FORECAST ANALYSIS:
Highest rain probability:
{analysis['highest_rain_probability']}

Hottest period:
{analysis['hottest_period']}

Coldest period:
{analysis['coldest_period']}

Strongest wind:
{analysis['strongest_wind']}

Weather-based commute risk:
{analysis['commute_risk_score']}

TOMORROW:
Date: {forecast['tomorrow']['date']}
Minimum temperature:
{forecast['tomorrow']['min_temp']}°C
Maximum temperature:
{forecast['tomorrow']['max_temp']}°C
Maximum rain probability:
{forecast['tomorrow']['max_rain_probability']}%
Conditions:
{forecast['tomorrow']['conditions']}

TFL COMMUTE:
Route: {commute['route']}
Duration: {commute['duration']}
Departure: {commute['start_time']}
Arrival: {commute['arrival_time']}
Lines in selected journey:
{commute.get('lines_used', [])}

LIVE TRANSPORT STATUS:
{tube_status}

SELECTED LONDON ATTRACTION:
Name: {recommendation['name']}
Category: {recommendation['category']}
Area: {recommendation['area']}
Description: {recommendation['description']}
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You write concise, accurate London "
                    "weather and transport email briefings. "
                    "Use only the supplied information."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.5,
    )

    summary = response.choices[0].message.content

    if not summary:
        raise ValueError(
            "OpenAI returned an empty email summary"
        )

    return summary.strip()


# ============================================================
# SEND HTML EMAIL
# ============================================================

def send_email(body):
    if not TO_EMAIL:
        raise ValueError(
            "TO_EMAIL environment variable is missing"
        )

    recipients = [
        address.strip()
        for address in TO_EMAIL.split(",")
        if address.strip()
    ]

    if not recipients:
        raise ValueError(
            "No valid email recipients configured"
        )

    safe_body = html.escape(body).replace(
        "\n",
        "<br>"
    )

    safe_city = html.escape(CITY)

    html_body = f"""
    <html>
      <body style="
        font-family: Arial, sans-serif;
        line-height: 1.6;
        color: #222;
      ">
        <div style="
          max-width: 600px;
          margin: auto;
          padding: 20px;
        ">
          <h2 style="color: #2563eb;">
            Weather &amp; Canary Wharf
            Commute Briefing — {safe_city}
          </h2>

          <div style="
            background: #f3f4f6;
            padding: 16px;
            border-radius: 10px;
          ">
            {safe_body}
          </div>

          <p style="
            font-size: 12px;
            color: #666;
            margin-top: 20px;
          ">
            Sent automatically by your AI weather agent.
          </p>
        </div>
      </body>
    </html>
    """

    msg = MIMEText(
        html_body,
        "html",
        "utf-8",
    )

    msg["Subject"] = (
        f"Weather & Canary Wharf Commute Update — {CITY}"
    )

    msg["From"] = EMAIL_ADDRESS
    msg["To"] = ", ".join(recipients)

    with smtplib.SMTP_SSL(
        "smtp.gmail.com",
        465,
        timeout=30,
    ) as server:
        server.login(
            EMAIL_ADDRESS,
            EMAIL_PASSWORD,
        )

        server.sendmail(
            EMAIL_ADDRESS,
            recipients,
            msg.as_string(),
        )

    log("HTML email sent successfully")


# ============================================================
# MAIN EXECUTION
# ============================================================

def main():
    log("Weather agent started")

    # 1. Get current weather.
    weather = get_weather()
    log("Current weather retrieved")

    # 2. Get forecast.
    forecast = get_forecast()
    analysis = analyze_forecast(forecast)
    log("Weather forecast analysed")

    # 3. Get Canary Wharf commute.
    try:
        commute = get_commute()
        log(
            f"TfL commute retrieved: "
            f"{commute['duration']}"
        )

    except Exception as error:
        log(f"TfL commute failed: {error}")

        commute = {
            "route": COMMUTE_ROUTE,
            "duration": "Unavailable",
            "start_time": "Unavailable",
            "arrival_time": "Unavailable",
            "lines_used": [],
        }

    # 4. Get relevant transport line statuses.
    try:
        tube_status = get_tube_status()
        log("TfL service status retrieved")

    except Exception as error:
        log(f"TfL line status failed: {error}")

        tube_status = [
            {
                "line": "TfL",
                "status": "Unavailable",
            }
        ]

    # 5. Select an unused, weather-suitable place.
    recommendation = choose_recommendation(
        weather,
        analysis,
    )

    log(
        "Recommendation chosen: "
        + recommendation["name"]
    )

    # 6. Generate the AI email.
    summary = generate_summary(
        weather,
        forecast,
        analysis,
        commute,
        tube_status,
        recommendation,
    )

    log("AI email summary generated")

    # 7. Send the email.
    send_email(summary)

    # 8. Save recommendation only after email succeeds.
    save_recommendation(recommendation)

    log(
        "Recommendation saved: "
        + recommendation["name"]
    )

    log("Weather agent completed successfully")

    print("\n" + summary)


if __name__ == "__main__":
    try:
        main()

    except Exception as error:
        log(f"ERROR: {error}")
        raise
