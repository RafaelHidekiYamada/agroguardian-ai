from __future__ import annotations
from typing import Dict
import requests
from .config import settings


def get_weather(latitude: float, longitude: float) -> Dict:
    """
    Busca clima no OpenWeather.
    Se falhar por qualquer motivo, retorna fallback sem quebrar a API.
    """
    if not settings.openweather_api_key:
        return {
            "source": "fallback",
            "weather_main": "Clear",
            "description": "Fallback sem chave OpenWeather",
            "temperature": 22.5,
            "humidity": 70,
            "wind_speed": 4.0,
            "rain_mm_1h": 0.0,
            "error": None,
        }

    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "lat": latitude,
        "lon": longitude,
        "appid": settings.openweather_api_key,
        "units": "metric",
        "lang": "pt_br",
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        return {
            "source": "openweather",
            "weather_main": data.get("weather", [{}])[0].get("main", "Clear"),
            "description": data.get("weather", [{}])[0].get("description", "Sem descrição"),
            "temperature": data.get("main", {}).get("temp", 22.5),
            "humidity": data.get("main", {}).get("humidity", 70),
            "wind_speed": data.get("wind", {}).get("speed", 4.0),
            "rain_mm_1h": data.get("rain", {}).get("1h", 0.0),
            "error": None,
        }

    except Exception as e:
        return {
            "source": "fallback",
            "weather_main": "Clear",
            "description": "Fallback por falha na consulta do clima",
            "temperature": 22.5,
            "humidity": 70,
            "wind_speed": 4.0,
            "rain_mm_1h": 0.0,
            "error": str(e),
        }