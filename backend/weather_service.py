from __future__ import annotations
from typing import Dict
import requests
from .config import settings

def get_weather(latitude: float, longitude: float) -> Dict:
    if settings.openweather_api_key:
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            "lat": latitude,
            "lon": longitude,
            "appid": settings.openweather_api_key,
            "units": "metric",
            "lang": "pt_br",
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        return {
            "source": "openweather",
            "weather_main": data["weather"][0]["main"],
            "description": data["weather"][0]["description"],
            "temperature": data["main"]["temp"],
            "humidity": data["main"]["humidity"],
            "wind_speed": data.get("wind", {}).get("speed", 0),
            "rain_mm_1h": data.get("rain", {}).get("1h", 0),
        }

    return {
        "source": "fallback",
        "weather_main": "Chuva",
        "description": "Fallback de demonstração (sem chave OpenWeather)",
        "temperature": 22.5,
        "humidity": 87,
        "wind_speed": 6.2,
        "rain_mm_1h": 12.0,
    }
