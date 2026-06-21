import os
import requests
import smtplib

from email.mime.text import MIMEText
from dotenv import load_dotenv
from datetime import datetime
from openai import OpenAI

load_dotenv()

CITY = os.getenv("CITY")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
TO_EMAIL = os.getenv("TO_EMAIL")

client = OpenAI(api_key=OPENAI_API_KEY)


def log(message):
    with open("weather_log.txt", "a") as f:
        f.write(f"{datetime.now()} - {message}\n")


def get_weather():
    url = (
        "https://api.openweathermap.org/data/2.5/weather"
        f"?q={CITY}&appid={WEATHER_API_KEY}&units=metric"
    )

    response = requests.get(url)
    data = response.json()

    print("Weather API status:", response.status_code)
    print("Weather API response:", data)

    if response.status_code != 200:
        raise Exception(f"Weather API failed: {data}")

    return {
        "temp": data["main"]["temp"],
        "description": data["weather"][0]["description"],
        "humidity": data["main"]["humidity"],
        "wind": data["wind"]["speed"],
    }


def get_forecast():
    url = (
        "https://api.openweathermap.org/data/2.5/forecast"
        f"?q={CITY}&appid={WEATHER_API_KEY}&units=metric"
    )

    response = requests.get(url)
    data = response.json()

    print("Forecast API status:", response.status_code)

    if response.status_code != 200:
        raise Exception(f"Forecast API failed: {data}")

    forecast_items = data["list"]

    next_24_hours = forecast_items[:8]

    hourly_summary = []

    for item in next_24_hours:
        hourly_summary.append({
            "time": item["dt_txt"],
            "temp": item["main"]["temp"],
            "description": item["weather"][0]["description"],
            "rain_probability": round(item.get("pop", 0) * 100),
            "wind": item["wind"]["speed"],
        })

    tomorrow_date = forecast_items[8]["dt_txt"].split(" ")[0]

    tomorrow_items = [
        item for item in forecast_items
        if item["dt_txt"].startswith(tomorrow_date)
    ]

    tomorrow_temps = [item["main"]["temp"] for item in tomorrow_items]
    tomorrow_rain_probs = [item.get("pop", 0) for item in tomorrow_items]

    tomorrow_summary = {
        "date": tomorrow_date,
        "min_temp": round(min(tomorrow_temps)),
        "max_temp": round(max(tomorrow_temps)),
        "max_rain_probability": round(max(tomorrow_rain_probs) * 100),
        "conditions": tomorrow_items[0]["weather"][0]["description"],
    }

    return {
        "next_24_hours": hourly_summary,
        "tomorrow": tomorrow_summary,
    }


def analyze_forecast(forecast):
    next_24_hours = forecast["next_24_hours"]

    highest_rain = max(
        next_24_hours,
        key=lambda item: item["rain_probability"]
    )

    hottest_period = max(
        next_24_hours,
        key=lambda item: item["temp"]
    )

    coldest_period = min(
        next_24_hours,
        key=lambda item: item["temp"]
    )

    strongest_wind = max(
        next_24_hours,
        key=lambda item: item["wind"]
    )

    max_rain_probability = highest_rain["rain_probability"]
    max_wind_speed = strongest_wind["wind"]

    if max_rain_probability >= 70 or max_wind_speed >= 12:
        commute_risk_score = "High"
    elif max_rain_probability >= 40 or max_wind_speed >= 8:
        commute_risk_score = "Medium"
    else:
        commute_risk_score = "Low"

    return {
        "highest_rain_probability": {
            "time": highest_rain["time"],
            "value": highest_rain["rain_probability"],
            "conditions": highest_rain["description"],
        },
        "hottest_period": {
            "time": hottest_period["time"],
            "temp": round(hottest_period["temp"]),
            "conditions": hottest_period["description"],
        },
        "coldest_period": {
            "time": coldest_period["time"],
            "temp": round(coldest_period["temp"]),
            "conditions": coldest_period["description"],
        },
        "strongest_wind": {
            "time": strongest_wind["time"],
            "speed": strongest_wind["wind"],
            "conditions": strongest_wind["description"],
        },
        "commute_risk_score": commute_risk_score,
    }


def get_commute():
    url = "https://api.tfl.gov.uk/Journey/JourneyResults/1000151/to/1000266"

    params = {
        "mode": "tube",
    }

    response = requests.get(url, params=params)
    data = response.json()

    print("TfL Journey status:", response.status_code)
    print("TfL Journey response:", data)

    if response.status_code != 200:
        raise Exception(f"TfL Journey API failed: {data}")

    if "journeys" not in data or len(data["journeys"]) == 0:
        raise Exception(f"No TfL journey found: {data}")

    journey = data["journeys"][0]

    return {
        "route": "Morden to Westminster",
        "duration": f"{journey['duration']} mins",
        "start_time": journey.get("startDateTime"),
        "arrival_time": journey.get("arrivalDateTime"),
    }


def get_tube_status():
    url = "https://api.tfl.gov.uk/Line/Mode/tube/Status"

    response = requests.get(url)
    data = response.json()

    print("TfL Tube status:", response.status_code)
    print("TfL Tube response:", data)

    if response.status_code != 200:
        raise Exception(f"TfL Line Status API failed: {data}")

    relevant_lines = [
        "northern",
        "jubilee",
        "district",
        "circle",
    ]

    statuses = []

    for line in data:
        line_id = line["id"]

        if line_id in relevant_lines:
            line_statuses = [
                status["statusSeverityDescription"]
                for status in line["lineStatuses"]
            ]

            statuses.append({
                "line": line["name"],
                "status": ", ".join(line_statuses),
            })

    return statuses

try:
    commute = get_commute()
except Exception as e:
    log(f"TfL commute failed: {e}")
    commute = {
        "route": "Morden to Westminster",
        "duration": "Unavailable",
        "start_time": "Unavailable",
        "arrival_time": "Unavailable",
    }

try:
    tube_status = get_tube_status()
except Exception as e:
    log(f"Tube status failed: {e}")
    tube_status = [{"line": "TfL", "status": "Unavailable"}]


def generate_summary(weather, forecast, analysis, commute, tube_status):
    prompt = f"""
    You are a concise and useful London weather and Tube commute assistant.

    Write a short morning briefing for today's weather, tomorrow's weather, and the commute.

    Requirements:
    - Start email with "Hello lovely people."
    - End email with "Take care everyone!"
    - Each new sentence should be a new paragraph.
    - Keep it under 200 words.
    - Include temperature, rounded to the nearest degree.
    - Use adjectives to describe the temperature, for example "brisk" for 9°C and "sweltering" for 25°C.
    - Include conditions.
    - Include clothing recommendation.
    - Include TfL Tube commute duration.
    - Mention relevant Tube disruption status.
    - If Tube lines look normal, say the commute appears straightforward.
    - Mention whether the commute looks weather-affected based on rain and wind.
    - Include advice on what to see that is appropriate for the weather and within a 45 minute commute of Morden, south-west London.
    - *Do Not* recommend the same destination more than twice in one week. 
    - Check out websites such as Time Out London for appropriate recommendations. 
    - Use separate paragraphs for today and tomorrow's weather. Highlight if the weather is going to change.
    - Use the structured analysis below as the main source of reasoning.

    Current weather:
    Temperature: {round(weather['temp'])}°C
    Conditions: {weather['description']}
    Humidity: {weather['humidity']}%
    Wind Speed: {weather['wind']} m/s

    Structured forecast analysis:
    Highest rain probability: {analysis['highest_rain_probability']['value']}% at {analysis['highest_rain_probability']['time']} with {analysis['highest_rain_probability']['conditions']}
    Hottest period: {analysis['hottest_period']['temp']}°C at {analysis['hottest_period']['time']} with {analysis['hottest_period']['conditions']}
    Coldest period: {analysis['coldest_period']['temp']}°C at {analysis['coldest_period']['time']} with {analysis['coldest_period']['conditions']}
    Strongest wind: {analysis['strongest_wind']['speed']} m/s at {analysis['strongest_wind']['time']} with {analysis['strongest_wind']['conditions']}
    Weather-based commute risk score: {analysis['commute_risk_score']}

    Tomorrow:
    Date: {forecast['tomorrow']['date']}
    Min temp: {forecast['tomorrow']['min_temp']}°C
    Max temp: {forecast['tomorrow']['max_temp']}°C
    Max rain probability: {forecast['tomorrow']['max_rain_probability']}%
    Conditions: {forecast['tomorrow']['conditions']}

    TfL Tube commute:
    Route: {commute['route']}
    Estimated duration: {commute['duration']}
    Start time: {commute['start_time']}
    Arrival time: {commute['arrival_time']}

    Relevant Tube line status:
    {tube_status}
    """

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )

    return response.choices[0].message.content


def send_email(body):
    recipients = [
        email.strip()
        for email in TO_EMAIL.split(",")
        if email.strip()
    ]

    html_body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #222;">
        <div style="max-width: 600px; margin: auto; padding: 20px;">
          <h2 style="color: #2563eb;">Weather & Tube Commute Briefing — {CITY}</h2>

          <div style="background: #f3f4f6; padding: 16px; border-radius: 10px;">
            {body.replace(chr(10), "<br>")}
          </div>

          <p style="font-size: 12px; color: #666; margin-top: 20px;">
            Sent automatically by your AI weather agent.
          </p>
        </div>
      </body>
    </html>
    """

    msg = MIMEText(html_body, "html")

    msg["Subject"] = f"Weather & Tube Commute Update — {CITY}"
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = ", ".join(recipients)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.sendmail(
            EMAIL_ADDRESS,
            recipients,
            msg.as_string()
        )

    print("HTML email sent successfully")


if __name__ == "__main__":
    try:
        log("Script started")

        weather = get_weather()
        log(f"Weather data: {weather}")

        forecast = get_forecast()
        log("Forecast data fetched")

        analysis = analyze_forecast(forecast)
        log(f"Forecast analysis: {analysis}")

        commute = get_commute()
        log(f"TfL commute data: {commute}")

        tube_status = get_tube_status()
        log(f"Tube status: {tube_status}")

        summary = generate_summary(
            weather,
            forecast,
            analysis,
            commute,
            tube_status
        )
        log("Summary generated")

        send_email(summary)
        log("Email sent successfully")

        print(summary)

    except Exception as e:
        log(f"ERROR: {e}")
        print("ERROR:", e)
        raise
