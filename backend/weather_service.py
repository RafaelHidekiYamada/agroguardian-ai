from __future__ import annotations
from typing import Dict, Tuple
import time
import requests
from .config import settings

_WEATHER_CACHE: dict[Tuple[float, float], Dict] = {}
CACHE_TTL_SECONDS = 600


def _cache_key(latitude: float, longitude: float) -> Tuple[float, float]:
    return (round(latitude, 3), round(longitude, 3))


def _get_cached_weather(latitude: float, longitude: float) -> Dict | None:
    key = _cache_key(latitude, longitude)
    entry = _WEATHER_CACHE.get(key)

    if not entry:
        return None

    if time.time() > entry["expires_at"]:
        return None

    return entry["data"]


def _set_cached_weather(latitude: float, longitude: float, data: Dict) -> None:
    key = _cache_key(latitude, longitude)
    _WEATHER_CACHE[key] = {
        "data": data,
        "expires_at": time.time() + CACHE_TTL_SECONDS,
    }


def _fallback_weather(reason: str) -> Dict:
    return {
        "source": "fallback",
        "weather_main": "Clear",
        "description": "Fallback por indisponibilidade do clima externo",
        "temperature": 22.5,
        "humidity": 70,
        "wind_speed": 4.0,
        "rain_mm_1h": 0.0,
        "error": reason,
    }


def get_weather(latitude: float, longitude: float) -> Dict:
    if not settings.openweather_api_key:
        return _fallback_weather("Sem OPENWEATHER_API_KEY configurada")

    cached = _get_cached_weather(latitude, longitude)
    if cached:
        return cached

    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "lat": latitude,
        "lon": longitude,
        "appid": settings.openweather_api_key,
        "units": "metric",
        "lang": "pt_br",
    }

    last_error = "Erro desconhecido"

    for attempt in range(3):
        try:
            response = requests.get(url, params=params, timeout=8)
            response.raise_for_status()
            data = response.json()

            weather = {
                "source": "openweather",
                "weather_main": data.get("weather", [{}])[0].get("main", "Clear"),
                "description": data.get("weather", [{}])[0].get("description", "Sem descrição"),
                "temperature": data.get("main", {}).get("temp", 22.5),
                "humidity": data.get("main", {}).get("humidity", 70),
                "wind_speed": data.get("wind", {}).get("speed", 4.0),
                "rain_mm_1h": data.get("rain", {}).get("1h", 0.0),
                "error": None,
            }

            _set_cached_weather(latitude, longitude, weather)
            return weather

        except Exception as e:
            last_error = str(e)
            time.sleep(1.2 * (attempt + 1))

    key = _cache_key(latitude, longitude)
    stale = _WEATHER_CACHE.get(key)
    if stale:
        stale_data = dict(stale["data"])
        stale_data["source"] = "stale-cache"
        stale_data["error"] = f"OpenWeather indisponível. Usando cache antigo. Motivo: {last_error}"
        return stale_data

    return _fallback_weather(last_error)