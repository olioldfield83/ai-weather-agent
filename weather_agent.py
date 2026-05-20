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

    print("Full API response:", data)

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

def generate_summary(weather, forecast):
    prompt = f"""
   You are a concise and useful London weather assistant.

    Write a short morning weather briefing.

    Include:
    - temperature, rounded to the nearest degree
    - adjectives to describe the temperature, for example "brisk" for 9°C and "sweltering" for 25°C
    - conditions
    - clothing recommendation
    - commute advice if relevant
    - advice on what to see that is appropriate for the weather

    Start email with "Hello lovely people"
    End email with "Take care everyone!"
    Each new sentence should be a new paragraph.

    Keep it under 120 words.
    Current weather:
    Temperature: {weather['temp']}°C
    Conditions: {weather['description']}
    Humidity: {weather['humidity']}%
    Wind Speed: {weather['wind']} m/s

    Next 24 hours forecast:
    {forecast['next_24_hours']}

    Tomorrow:
    Date: {forecast['tomorrow']['date']}
    Min temp: {forecast['tomorrow']['min_temp']}°C
    Max temp: {forecast['tomorrow']['max_temp']}°C
    Max rain probability: {forecast['tomorrow']['max_rain_probability']}%
    Conditions: {forecast['tomorrow']['conditions']}
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

    msg = MIMEText(body)

    msg["Subject"] = f"Weather Update — {CITY}"
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = ", ".join(recipients)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)

        server.sendmail(
            EMAIL_ADDRESS,
            recipients,
            msg.as_string()
        )

    print("Email sent successfully")


if __name__ == "__main__":
    try:
        log("Script started")

        weather = get_weather()

        log(f"Weather data: {weather}")

        summary = generate_summary(weather)

        log("Summary generated")

        send_email(summary)

        log("Email sent successfully")

        print(summary)

    except Exception as e:
        log(f"ERROR: {e}")

        print("ERROR:", e)
