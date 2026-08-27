from __future__ import annotations
import math
from typing import Any, Dict

STANDARD_GRAVITY_M_S2 = 9.80665

FEATURE_ORDER = [
    "umidade_solo",
    "inclinacao",
    "distancia_agua",
    "velocidade",
    "historico_sinistros",
    "chuva_mm",
    "solo_instavel",
    "clima_code",
    "operation_code",
    "temperatura_c",
    "umidade_ar",
    "pressao_hpa",
    "distancia_obstaculo",
    "gps_accuracy_m",
]

CLIMATE_MAP = {
    "sol": 0,
    "nublado": 1,
    "chuva": 2,
    "tempestade": 3,
    "garoa": 4,
}

OPERATION_MAP = {
    "campo": 0,
    "transporte": 1,
    "proximidade_agua": 2,
    "manutencao": 3,
}

def normalize_climate(clima: str) -> int:
    return CLIMATE_MAP.get(clima.lower().strip(), 1)

def normalize_operation(operation_type: str) -> int:
    return OPERATION_MAP.get(operation_type.lower().strip(), 0)


def _first_number(data: Dict[str, Any], keys: list[str], default: float) -> float:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return float(default)


def calculate_magnitude(x: float | None, y: float | None, z: float | None) -> float | None:
    if x is None or y is None or z is None:
        return None
    return math.sqrt(float(x) ** 2 + float(y) ** 2 + float(z) ** 2)


def build_mpu6050_features(
    accel_x: float | None = None,
    accel_y: float | None = None,
    accel_z: float | None = None,
    inclination_deg: float | None = None,
    gyro_x: float | None = None,
    gyro_y: float | None = None,
    gyro_z: float | None = None,
    pitch: float | None = None,
    roll: float | None = None,
    acceleration_impact_g: float = 1.8,
    gyro_abnormal_dps: float = 220.0,
    tilt_high_deg: float = 15.0,
) -> Dict[str, Any]:
    acceleration_magnitude = calculate_magnitude(accel_x, accel_y, accel_z)
    gyro_magnitude = calculate_magnitude(gyro_x, gyro_y, gyro_z)

    absolute_pitch = abs(float(pitch)) if pitch is not None else None
    absolute_roll = abs(float(roll)) if roll is not None else None
    absolute_inclination = abs(float(inclination_deg)) if inclination_deg is not None else None
    tilt_values = [value for value in (absolute_inclination, absolute_pitch, absolute_roll) if value is not None]
    max_tilt_angle = max(tilt_values) if tilt_values else None

    movement_anomaly_score = 0.0
    if acceleration_magnitude is not None:
        # MPU6050 axes are canonical m/s2 values. Resting gravity must not be
        # treated as an impact or anomalous motion.
        delta_g = abs(float(acceleration_magnitude) - STANDARD_GRAVITY_M_S2) / STANDARD_GRAVITY_M_S2
        movement_anomaly_score += min(60.0, delta_g * 100.0)
    if gyro_magnitude is not None:
        movement_anomaly_score += min(40.0, (float(gyro_magnitude) / max(gyro_abnormal_dps, 1.0)) * 40.0)
    if max_tilt_angle is not None and max_tilt_angle >= tilt_high_deg:
        movement_anomaly_score += min(20.0, (max_tilt_angle - tilt_high_deg) * 1.5)
    movement_anomaly_score = round(min(100.0, movement_anomaly_score), 2)

    possible_impact = False
    if acceleration_magnitude is not None:
        possible_impact = acceleration_magnitude >= (STANDARD_GRAVITY_M_S2 * acceleration_impact_g)
    if gyro_magnitude is not None and gyro_magnitude >= gyro_abnormal_dps * 1.6:
        possible_impact = True

    return {
        "acceleration_magnitude": round(acceleration_magnitude, 4) if acceleration_magnitude is not None else None,
        "gyro_magnitude": round(gyro_magnitude, 4) if gyro_magnitude is not None else None,
        "absolute_pitch": round(absolute_pitch, 4) if absolute_pitch is not None else None,
        "absolute_roll": round(absolute_roll, 4) if absolute_roll is not None else None,
        "inclination_deg": round(absolute_inclination, 4) if absolute_inclination is not None else None,
        "max_tilt_angle": round(max_tilt_angle, 4) if max_tilt_angle is not None else None,
        "movement_anomaly_score": movement_anomaly_score,
        "possible_impact": possible_impact,
    }


def build_features(data: Dict) -> Dict[str, float]:
    clima_code = normalize_climate(str(data.get("clima", "nublado")))
    operation_code = normalize_operation(str(data.get("operation_type", "campo")))

    features = {
        "umidade_solo": float(data["umidade_solo"]),
        "inclinacao": float(data["inclinacao"]),
        "distancia_agua": float(data["distancia_agua"]),
        "velocidade": float(data["velocidade"]),
        "historico_sinistros": float(data["historico_sinistros"]),
        "chuva_mm": float(data["chuva_mm"]),
        "solo_instavel": float(data["solo_instavel"]),
        "clima_code": float(clima_code),
        "operation_code": float(operation_code),
        "temperatura_c": _first_number(
            data,
            ["temperatura_c", "temperature_c", "temp_c", "weather_temperature"],
            24.0,
        ),
        "umidade_ar": _first_number(
            data,
            ["umidade_ar", "air_humidity_pct", "humidity_pct", "weather_humidity"],
            70.0,
        ),
        "pressao_hpa": _first_number(
            data,
            ["pressao_hpa", "pressure_hpa", "barometric_pressure_hpa"],
            1013.25,
        ),
        "distancia_obstaculo": _first_number(
            data,
            ["distancia_obstaculo", "obstacle_distance_m", "distance_obstacle_m"],
            99.0,
        ),
        "gps_accuracy_m": _first_number(
            data,
            ["gps_accuracy_m", "gps_hdop_m", "location_accuracy_m"],
            10.0,
        ),
    }
    return features
