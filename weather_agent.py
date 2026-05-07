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

    response = requests.get(url)

    data = response.json()

    temp = data["main"]["temp"]
    description = data["weather"][0]["description"]
    humidity = data["main"]["humidity"]
    wind = data["wind"]["speed"]

    return {
        "temp": temp,
        "description": description,
        "humidity": humidity,
        "wind": wind,
    }


def generate_summary(weather):
    prompt = f"""
    You are a concise and useful London weather assistant.

    Write a short morning weather briefing.

    Include:
    - temperature
    - conditions
    - clothing recommendation
    - commute advice if relevant
    - advice on what to see that is appropriate for the weather

    Start email with "Hello lovely people"
    End email with "Lots of love from Oli's AI agent"
    Each new sentence should be a new paragraph.

    Keep it under 120 words.

    Weather data:
    Temperature: {weather['temp']}°C
    Conditions: {weather['description']}
    Humidity: {weather['humidity']}%
    Wind Speed: {weather['wind']} m/s
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
