"""
Real-time weather (Open-Meteo, no API key) and datetime helpers
used as Claude tool implementations.
"""

import datetime

import requests

_WMO = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "freezing fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    71: "light snow", 73: "snow", 75: "heavy snow",
    80: "showers", 81: "heavy showers", 82: "violent showers",
    95: "thunderstorm", 96: "thunderstorm with hail",
}


def get_location() -> tuple[float | None, float | None, str]:
    try:
        r = requests.get("http://ip-api.com/json/", timeout=5)
        d = r.json()
        return d.get("lat"), d.get("lon"), d.get("city", "your location")
    except Exception:
        return None, None, "unknown"


def get_weather(lat: float, lon: float, city: str) -> str:
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
                "timezone": "auto",
            },
            timeout=10,
        )
        c = r.json()["current"]
        conditions = _WMO.get(c.get("weather_code", 0), "unknown conditions")
        return (
            f"Current weather in {city}: {conditions}, "
            f"{round(c['temperature_2m'])}°F, "
            f"humidity {c['relative_humidity_2m']}%, "
            f"wind {round(c['wind_speed_10m'])} mph."
        )
    except Exception as exc:
        return f"Could not fetch weather: {exc}"


def get_datetime() -> str:
    now = datetime.datetime.now()
    return now.strftime("%A, %B %-d %Y, %-I:%M %p")
