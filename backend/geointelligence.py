from __future__ import annotations

from math import radians, sin, cos, sqrt, atan2
from typing import Dict, Any


# Pontos simulados de água/rios/zona alagável
WATER_POINTS = [
    {"name": "Rio Tietê - trecho 1", "lat": -23.4800, "lon": -46.5200},
    {"name": "Rio Tietê - trecho 2", "lat": -23.4700, "lon": -46.5400},
    {"name": "Área alagável Norte", "lat": -23.4500, "lon": -46.5000},
    {"name": "Canal agrícola", "lat": -23.4300, "lon": -46.5600},
]


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000  # metros

    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return r * c


def nearest_water_point(latitude: float, longitude: float) -> Dict[str, Any]:
    nearest = None
    min_distance = None

    for point in WATER_POINTS:
        dist = haversine_distance_m(
            latitude,
            longitude,
            float(point["lat"]),
            float(point["lon"]),
        )
        if min_distance is None or dist < min_distance:
            min_distance = dist
            nearest = point

    return {
        "nearest_name": nearest["name"] if nearest else None,
        "distance_m": round(min_distance or 0, 2),
        "distance_km": round((min_distance or 0) / 1000, 3),
        "nearest_lat": nearest["lat"] if nearest else None,
        "nearest_lon": nearest["lon"] if nearest else None,
    }


def classify_geo_risk(distance_m: float, solo_instavel: int, inclinacao: float) -> Dict[str, Any]:
    terrain_points = 0
    terrain_reasons = []

    if distance_m <= 50:
        water_zone = "alto_risco"
        water_points = 40
        water_reason = "Equipamento em zona crítica muito próxima de água."
    elif distance_m <= 150:
        water_zone = "atencao"
        water_points = 25
        water_reason = "Equipamento em área de atenção próxima de água."
    elif distance_m <= 300:
        water_zone = "moderado"
        water_points = 12
        water_reason = "Equipamento em área moderadamente próxima de água."
    else:
        water_zone = "seguro"
        water_points = 0
        water_reason = "Equipamento fora de zona crítica de água."

    if int(solo_instavel) == 1:
        terrain_points += 15
        terrain_reasons.append("solo instável")

    if float(inclinacao) >= 15:
        terrain_points += 10
        terrain_reasons.append("inclinação elevada")

    geo_risk_points = min(100, water_points + terrain_points)

    if water_zone in {"alto_risco", "atencao"}:
        geo_zone = water_zone
    elif terrain_points > 0:
        geo_zone = "seguro_com_agravantes"
    else:
        geo_zone = "seguro"

    reason = water_reason
    if terrain_reasons:
        reason += " Agravantes de terreno: " + ", ".join(terrain_reasons) + "."

    return {
        "geo_zone": geo_zone,
        "water_zone": water_zone,
        "water_risk_points": water_points,
        "terrain_aggravation_points": terrain_points,
        "geo_risk_points": geo_risk_points,
        "geo_reason": reason,
    }


def build_geo_context(
    latitude: float,
    longitude: float,
    solo_instavel: int,
    inclinacao: float,
) -> Dict[str, Any]:
    water_info = nearest_water_point(latitude, longitude)
    risk_info = classify_geo_risk(
        distance_m=float(water_info["distance_m"]),
        solo_instavel=int(solo_instavel),
        inclinacao=float(inclinacao),
    )

    return {
        "latitude": latitude,
        "longitude": longitude,
        "nearest_water": water_info,
        "geo_risk": risk_info,
    }