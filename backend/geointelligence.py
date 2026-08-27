from __future__ import annotations

from math import atan2, cos, radians, sin, sqrt
import time
from typing import Any, Dict

import requests

from .config import settings


# Fallback local usado apenas se a consulta OSM/Overpass estiver indisponivel.
WATER_POINTS = [
    {"name": "Rio Tiete - trecho 1", "lat": -23.4800, "lon": -46.5200},
    {"name": "Rio Tiete - trecho 2", "lat": -23.4700, "lon": -46.5400},
    {"name": "Area alagavel Norte", "lat": -23.4500, "lon": -46.5000},
    {"name": "Canal agricola", "lat": -23.4300, "lon": -46.5600},
]

_OVERPASS_CACHE: dict[tuple[float, float, int], dict] = {}
_CACHE_TTL_SECONDS = 60 * 60 * 6
_EARTH_RADIUS_M = 6371000.0


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return _EARTH_RADIUS_M * c


def _project_to_meters(lat: float, lon: float, origin_lat: float, origin_lon: float) -> tuple[float, float]:
    x = radians(lon - origin_lon) * _EARTH_RADIUS_M * cos(radians(origin_lat))
    y = radians(lat - origin_lat) * _EARTH_RADIUS_M
    return x, y


def _unproject_from_meters(x: float, y: float, origin_lat: float, origin_lon: float) -> tuple[float, float]:
    lat = origin_lat + (y / _EARTH_RADIUS_M) * (180.0 / 3.141592653589793)
    lon = origin_lon + (x / (_EARTH_RADIUS_M * cos(radians(origin_lat)))) * (180.0 / 3.141592653589793)
    return lat, lon


def _closest_geometry_point(
    latitude: float,
    longitude: float,
    geometry: list[dict[str, float]],
) -> tuple[float, float, float]:
    projected = [
        _project_to_meters(float(point["lat"]), float(point["lon"]), latitude, longitude)
        for point in geometry
        if point.get("lat") is not None and point.get("lon") is not None
    ]

    if not projected:
        return 0.0, latitude, longitude

    if len(projected) == 1:
        x, y = projected[0]
        lat, lon = _unproject_from_meters(x, y, latitude, longitude)
        return sqrt(x * x + y * y), lat, lon

    best_distance = None
    best_xy = (0.0, 0.0)

    for start, end in zip(projected, projected[1:]):
        ax, ay = start
        bx, by = end
        dx = bx - ax
        dy = by - ay
        denominator = dx * dx + dy * dy
        t = 0.0 if denominator == 0 else (-(ax * dx + ay * dy) / denominator)
        t = max(0.0, min(1.0, t))
        cx = ax + t * dx
        cy = ay + t * dy
        distance = sqrt(cx * cx + cy * cy)
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_xy = (cx, cy)

    closest_lat, closest_lon = _unproject_from_meters(best_xy[0], best_xy[1], latitude, longitude)
    return float(best_distance or 0.0), closest_lat, closest_lon


def _water_label(element: dict[str, Any]) -> str:
    tags = element.get("tags", {}) if isinstance(element.get("tags"), dict) else {}
    return (
        tags.get("name")
        or tags.get("waterway")
        or tags.get("natural")
        or tags.get("water")
        or f"osm_{element.get('type')}_{element.get('id')}"
    )


def _build_overpass_query(latitude: float, longitude: float, search_radius_m: int) -> str:
    return f"""
    [out:json][timeout:12];
    (
      node["waterway"](around:{search_radius_m},{latitude},{longitude});
      way["waterway"](around:{search_radius_m},{latitude},{longitude});
      relation["waterway"](around:{search_radius_m},{latitude},{longitude});
      node["natural"="water"](around:{search_radius_m},{latitude},{longitude});
      way["natural"="water"](around:{search_radius_m},{latitude},{longitude});
      relation["natural"="water"](around:{search_radius_m},{latitude},{longitude});
      way["water"](around:{search_radius_m},{latitude},{longitude});
      relation["water"](around:{search_radius_m},{latitude},{longitude});
    );
    out center geom;
    """


def _query_overpass_water(latitude: float, longitude: float, search_radius_m: int) -> Dict[str, Any]:
    key = (round(latitude, 5), round(longitude, 5), int(search_radius_m))
    cached = _OVERPASS_CACHE.get(key)
    if cached and time.time() < cached["expires_at"]:
        return cached["data"]

    response = requests.post(
        settings.overpass_api_url,
        data={"data": _build_overpass_query(latitude, longitude, search_radius_m)},
        headers={"User-Agent": "AgroGuardianAI/1.0 geointelligence"},
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    elements = data.get("elements", []) if isinstance(data, dict) else []

    best = None
    for element in elements:
        geometry = element.get("geometry")
        if isinstance(geometry, list) and geometry:
            distance_m, nearest_lat, nearest_lon = _closest_geometry_point(latitude, longitude, geometry)
        elif element.get("lat") is not None and element.get("lon") is not None:
            nearest_lat = float(element["lat"])
            nearest_lon = float(element["lon"])
            distance_m = haversine_distance_m(latitude, longitude, nearest_lat, nearest_lon)
        elif isinstance(element.get("center"), dict):
            center = element["center"]
            nearest_lat = float(center["lat"])
            nearest_lon = float(center["lon"])
            distance_m = haversine_distance_m(latitude, longitude, nearest_lat, nearest_lon)
        else:
            continue

        candidate = {
            "nearest_name": _water_label(element),
            "distance_m": round(float(distance_m), 2),
            "distance_km": round(float(distance_m) / 1000, 3),
            "nearest_lat": round(float(nearest_lat), 7),
            "nearest_lon": round(float(nearest_lon), 7),
            "source": "openstreetmap_overpass",
            "osm_type": element.get("type"),
            "osm_id": element.get("id"),
            "feature_count": len(elements),
            "search_radius_m": search_radius_m,
            "error": None,
        }
        if best is None or candidate["distance_m"] < best["distance_m"]:
            best = candidate

    if best is None:
        best = {
            "nearest_name": None,
            "distance_m": float(search_radius_m + 1),
            "distance_km": round((search_radius_m + 1) / 1000, 3),
            "nearest_lat": None,
            "nearest_lon": None,
            "source": "openstreetmap_overpass",
            "osm_type": None,
            "osm_id": None,
            "feature_count": 0,
            "search_radius_m": search_radius_m,
            "error": "Nenhum curso ou corpo de agua encontrado no raio consultado.",
        }

    _OVERPASS_CACHE[key] = {
        "data": best,
        "expires_at": time.time() + _CACHE_TTL_SECONDS,
    }
    return best


def _nearest_static_water_point(latitude: float, longitude: float, reason: str) -> Dict[str, Any]:
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
        "source": "fallback_static_water_points",
        "osm_type": None,
        "osm_id": None,
        "feature_count": len(WATER_POINTS),
        "search_radius_m": None,
        "error": reason,
    }


def nearest_water_point(
    latitude: float,
    longitude: float,
    search_radius_m: int | None = None,
) -> Dict[str, Any]:
    radius = int(search_radius_m or settings.geo_search_radius_m)

    if settings.enable_overpass_geo:
        try:
            return _query_overpass_water(latitude, longitude, radius)
        except Exception as exc:
            return _nearest_static_water_point(latitude, longitude, str(exc))

    return _nearest_static_water_point(latitude, longitude, "ENABLE_OVERPASS_GEO desabilitado")


def classify_geo_risk(distance_m: float, solo_instavel: int, inclinacao: float) -> Dict[str, Any]:
    terrain_points = 0
    terrain_reasons = []

    if distance_m <= 50:
        water_zone = "alto_risco"
        water_points = 40
        water_reason = "Equipamento em zona critica muito proxima de agua."
    elif distance_m <= 150:
        water_zone = "atencao"
        water_points = 25
        water_reason = "Equipamento em area de atencao proxima de agua."
    elif distance_m <= 300:
        water_zone = "moderado"
        water_points = 12
        water_reason = "Equipamento em area moderadamente proxima de agua."
    else:
        water_zone = "seguro"
        water_points = 0
        water_reason = "Equipamento fora de zona critica de agua."

    if int(solo_instavel) == 1:
        terrain_points += 15
        terrain_reasons.append("solo instavel")

    if float(inclinacao) >= 15:
        terrain_points += 10
        terrain_reasons.append("inclinacao elevada")

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
    gps_accuracy_m: float | None = None,
    search_radius_m: int | None = None,
) -> Dict[str, Any]:
    water_info = nearest_water_point(latitude, longitude, search_radius_m=search_radius_m)
    risk_info = classify_geo_risk(
        distance_m=float(water_info["distance_m"]),
        solo_instavel=int(solo_instavel),
        inclinacao=float(inclinacao),
    )

    return {
        "latitude": latitude,
        "longitude": longitude,
        "gps_accuracy_m": gps_accuracy_m,
        "nearest_water": water_info,
        "geo_risk": risk_info,
        "precision": {
            "coordinate_rounding_degrees": 5,
            "estimated_gps_accuracy_m": gps_accuracy_m,
            "water_source": water_info.get("source"),
            "water_feature_count": water_info.get("feature_count"),
            "search_radius_m": water_info.get("search_radius_m"),
        },
    }
