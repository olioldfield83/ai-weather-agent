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
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
TO_EMAIL = os.getenv("TO_EMAIL")
OPENROUTESERVICE_API_KEY = os.getenv("OPENROUTESERVICE_API_KEY")
COMMUTE_ORIGIN = os.getenv("COMMUTE_ORIGIN")
COMMUTE_DESTINATION = os.getenv("COMMUTE_DESTINATION")

def log(message):
    with open("weather_log.txt", "a") as f:
        f.write(f"{datetime.now()} - {message}\n")


def get_weather():
    url = (
        "https://api.openweathermap.org/data/2.5/weather"
        f"?q={CITY}&appid={WEATHER_API_KEY}&units=metric"
    )

    print("Request URL:", url)

    response = requests.get(url)

    print("Status code:", response.status_code)

    data = response.json()

print("OpenRouteService response:", data)

if response.status_code != 200:
    raise Exception(f"OpenRouteService failed: {data}")

if "routes" not in data:
    raise Exception(f"No route found: {data}")

summary = data["routes"][0]["summary"])

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

    print("Forecast API response status:", response.status_code)

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
        "min_temp": min(tomorrow_temps),
        "max_temp": max(tomorrow_temps),
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
            "temp": hottest_period["temp"],
            "conditions": hottest_period["description"],
        },
        "coldest_period": {
            "time": coldest_period["time"],
            "temp": coldest_period["temp"],
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
    url = "https://api.openrouteservice.org/v2/directions/driving-car"

    headers = {
        "Authorization": OPENROUTESERVICE_API_KEY,
        "Content-Type": "application/json",
    }

    body = {
    "coordinates": [
        [-0.1945, 51.4022],  # Morden
        [-0.1246, 51.4975],  # Westminster
    ]
}

    response = requests.post(url, json=body, headers=headers)

    data = response.json()

    print("OpenRouteService response:", data)

    summary = data["routes"][0]["summary"]

    distance_km = round(summary["distance"] / 1000, 1)
    duration_minutes = round(summary["duration"] / 60)

    return {
        "distance": f"{distance_km} km",
        "duration": f"{duration_minutes} mins",
    }

def generate_summary(weather, forecast, analysis, commute):
    prompt = f"""
    You are a concise and useful London weather assistant.

    Write a short morning weather briefing for today and tomorrow's weather. 

    Requirements:
    - Start email with "Hello lovely people."
    - End email with "Take care everyone!"
    - Each new sentence should be a new paragraph.
    - Keep it under 120 words.
    - Include temperature, rounded to the nearest degree.
    - Use adjectives to describe the temperature, for example "brisk" for 9°C and "sweltering" for 25°C.
    - Include conditions.
    - Include clothing recommendation.
    - Include commute time and traffic impact.
    - Mention whether the commute looks normal, delayed, or easy.
    - Include advice on what to see that is appropriate for the weather.
    - Use separate paragraphs for today and tomorrow's weather. Highlight if the weather is going to change.
    - Use the structured analysis below as the main source of reasoning.

    Current weather:
    Temperature: {weather['temp']}°C
    Conditions: {weather['description']}
    Humidity: {weather['humidity']}%
    Wind Speed: {weather['wind']} m/s

    Structured forecast analysis:
    Highest rain probability: {analysis['highest_rain_probability']['value']}% at {analysis['highest_rain_probability']['time']} with {analysis['highest_rain_probability']['conditions']}
    Hottest period: {analysis['hottest_period']['temp']}°C at {analysis['hottest_period']['time']} with {analysis['hottest_period']['conditions']}
    Coldest period: {analysis['coldest_period']['temp']}°C at {analysis['coldest_period']['time']} with {analysis['coldest_period']['conditions']}
    Strongest wind: {analysis['strongest_wind']['speed']} m/s at {analysis['strongest_wind']['time']} with {analysis['strongest_wind']['conditions']}
    Commute risk score: {analysis['commute_risk_score']}

    Tomorrow:
    Date: {forecast['tomorrow']['date']}
    Min temp: {forecast['tomorrow']['min_temp']}°C
    Max temp: {forecast['tomorrow']['max_temp']}°C
    Max rain probability: {forecast['tomorrow']['max_rain_probability']}%
    Conditions: {forecast['tomorrow']['conditions']}

    Commute:
Distance: {commute['distance']}
Estimated duration: {commute['duration']}
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
    recipients = TO_EMAIL.split(",")

    html_body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #222;">
        <div style="max-width: 600px; margin: auto; padding: 20px;">
          <h2 style="color: #2563eb;">Weather & Commute Briefing — {CITY}</h2>

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

    msg["Subject"] = f"Weather & Commute Update — {CITY}"
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

        analysis = analyze_forecast(forecast)

        commute = get_commute()

        summary = generate_summary(weather, forecast, analysis, commute)

        log("Summary generated")

        send_email(summary)

        log("Email sent successfully")

        print(summary)

    except Exception as e:
        log(f"ERROR: {e}")

        print("ERROR:", e)
