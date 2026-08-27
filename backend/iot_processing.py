"""Validation, freshness and risk context helpers for physical ESP32 telemetry."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .config import settings
from .feature_engineering import STANDARD_GRAVITY_M_S2, build_mpu6050_features
from .schemas import IotTelemetryInput, TelemetryInput


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_timestamp(timestamp: datetime | None) -> datetime:
    """Treat naive device timestamps as UTC and retain an aware UTC value."""
    if timestamp is None:
        return utcnow()
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def telemetry_age_seconds(timestamp: datetime, *, now: datetime | None = None) -> float:
    return max(0.0, ((now or utcnow()) - normalize_timestamp(timestamp)).total_seconds())


def telemetry_status(age_seconds: float) -> str:
    if age_seconds <= settings.iot_live_seconds:
        return "LIVE"
    stale_limit = max(settings.iot_live_seconds, settings.iot_stale_seconds)
    offline_limit = max(stale_limit, settings.iot_offline_threshold_seconds)
    if age_seconds <= offline_limit:
        return "STALE"
    return "OFFLINE"


def current_telemetry_status(timestamp: datetime | None) -> tuple[str, float]:
    if timestamp is None:
        return "OFFLINE", float("inf")
    age = telemetry_age_seconds(timestamp)
    return telemetry_status(age), round(age, 2)


def current_device_status(device: Any) -> str:
    if not getattr(device, "is_active", True):
        return "DISABLED"
    configured = str(getattr(device, "status", "") or "").upper()
    if configured in {"DISABLED", "MAINTENANCE"}:
        return configured
    freshness, _age = current_telemetry_status(getattr(device, "last_seen_at", None))
    if freshness == "LIVE":
        return "ONLINE"
    return freshness


@dataclass(frozen=True)
class RiskContext:
    """Immutable evidence used to compose a risk decision and audit snapshot."""

    equipment_id: int
    farm_id: int
    device_id: str | None
    telemetry_id: int | None
    operation: str
    recorded_at: datetime | None
    received_at: datetime | None
    data_quality_status: str
    telemetry_status: str
    telemetry_age_seconds: float
    confidence_score: float | None
    iot: dict[str, Any] = field(default_factory=dict)
    weather: dict[str, Any] = field(default_factory=dict)
    soil: dict[str, Any] = field(default_factory=dict)
    terrain: dict[str, Any] = field(default_factory=dict)
    history: dict[str, Any] = field(default_factory=dict)

    @property
    def is_usable(self) -> bool:
        return self.data_quality_status in {"VALID", "PARTIAL"} and self.telemetry_status == "LIVE"

    def snapshot(self) -> dict[str, Any]:
        return {
            "telemetry_id": self.telemetry_id,
            "device_id": self.device_id,
            "recorded_at": self.recorded_at.isoformat() if self.recorded_at else None,
            "received_at": self.received_at.isoformat() if self.received_at else None,
            "data_quality_status": self.data_quality_status,
            "telemetry_status": self.telemetry_status,
            "telemetry_age_seconds": self.telemetry_age_seconds,
            "confidence_score": self.confidence_score,
            "iot": self.iot,
            "weather": self.weather,
            "soil": self.soil,
            "terrain": self.terrain,
            "history": self.history,
        }


def _sensor_missing(sensor: Any, fields: tuple[str, ...]) -> bool:
    if sensor is None:
        return True
    return all(getattr(sensor, field, None) is None for field in fields)


def _jsn_sensor(payload: IotTelemetryInput):
    return payload.jsn_sr04t or payload.obstacle


def _infer_climate(payload: IotTelemetryInput) -> str:
    humidity = payload.bme280.humidity_pct if payload.bme280 else None
    pressure = payload.bme280.pressure_hpa if payload.bme280 else None
    rain = float(payload.rain_mm or 0)
    if rain >= 20:
        return "tempestade"
    if rain >= 5:
        return "chuva"
    if rain > 0:
        return "garoa"
    if humidity is not None and float(humidity) >= 88:
        return "nublado"
    if pressure is not None and float(pressure) <= 960:
        return "nublado"
    return "sol"


def evaluate_iot_quality(
    payload: IotTelemetryInput,
    timestamp: datetime,
    derived: dict[str, Any],
) -> dict[str, Any]:
    missing_sensors: list[str] = []
    issues: list[str] = []
    jsn = _jsn_sensor(payload)

    if _sensor_missing(payload.bme280, ("temperature_c", "humidity_pct", "pressure_hpa")):
        missing_sensors.append("BME280")
    if _sensor_missing(payload.mpu6050, ("accel_x", "accel_y", "accel_z", "inclination_deg", "pitch", "roll")):
        missing_sensors.append("MPU6050")
    if _sensor_missing(jsn, ("distance_cm",)):
        missing_sensors.append("JSN_SR04T")
    if jsn is not None and bool(getattr(jsn, "timeout", False)):
        issues.append("JSN-SR04T sem leitura por timeout")
    if jsn is not None and bool(getattr(jsn, "out_of_range", False)):
        issues.append("JSN-SR04T fora de alcance")

    age = telemetry_age_seconds(timestamp)
    freshness = telemetry_status(age)
    if freshness != "LIVE":
        issues.append(f"telemetria {freshness.lower()} ({int(age)} segundos)")

    future_delta = (normalize_timestamp(timestamp) - utcnow()).total_seconds()
    if future_delta > settings.iot_future_timestamp_tolerance_seconds:
        return {
            "data_quality_status": "INVALID",
            "telemetry_status": "SUSPECT",
            "telemetry_age_seconds": 0.0,
            "missing_sensors": missing_sensors,
            "data_quality_issues": issues + ["timestamp acima da tolerancia futura"],
            "confidence_score": 0.0,
        }

    accel = derived.get("acceleration_magnitude")
    if accel is not None and float(accel) > settings.iot_acceleration_suspect_m_s2:
        issues.append("aceleracao fora do padrao esperado do MPU6050")

    if len(missing_sensors) == 3:
        status = "INVALID"
        issues.append("nenhum sensor utilizavel enviado")
    elif issues:
        status = "SUSPECT"
    elif missing_sensors:
        status = "PARTIAL"
    else:
        status = "VALID"

    confidence_penalty = min(65.0, len(missing_sensors) * 12.0 + len(issues) * 10.0)
    confidence_score = 0.0 if status == "INVALID" else max(30.0, 96.0 - confidence_penalty)
    return {
        "data_quality_status": status,
        "telemetry_status": freshness,
        "telemetry_age_seconds": round(age, 2),
        "missing_sensors": missing_sensors,
        "data_quality_issues": issues,
        "confidence_score": round(confidence_score, 2),
    }


def build_iot_context(payload: IotTelemetryInput, equipment: Any, farm: Any) -> dict[str, Any]:
    timestamp = normalize_timestamp(payload.timestamp)
    bme = payload.bme280
    mpu = payload.mpu6050
    jsn = _jsn_sensor(payload)
    gps = payload.gps

    mpu_features = build_mpu6050_features(
        accel_x=mpu.accel_x if mpu else None,
        accel_y=mpu.accel_y if mpu else None,
        accel_z=mpu.accel_z if mpu else None,
        inclination_deg=mpu.inclination_deg if mpu else None,
        gyro_x=mpu.gyro_x if mpu else None,
        gyro_y=mpu.gyro_y if mpu else None,
        gyro_z=mpu.gyro_z if mpu else None,
        pitch=mpu.pitch if mpu else None,
        roll=mpu.roll if mpu else None,
        acceleration_impact_g=settings.acceleration_impact_g,
        gyro_abnormal_dps=settings.gyro_abnormal_dps,
        tilt_high_deg=settings.iot_inclination_high_deg,
    )
    quality = evaluate_iot_quality(payload, timestamp, mpu_features)

    distance_cm = jsn.distance_cm if jsn else None
    obstacle_detected = getattr(jsn, "detected", None) if jsn else None
    if obstacle_detected is None and distance_cm is not None:
        obstacle_detected = float(distance_cm) <= settings.iot_distance_attention_cm

    latitude = gps.latitude if gps and gps.latitude is not None else getattr(farm, "latitude", None)
    longitude = gps.longitude if gps and gps.longitude is not None else getattr(farm, "longitude", None)
    # Canonical inclination wins when sent; legacy pitch/roll are reduced to
    # the same absolute maximum for compatibility with older devices.
    inclination_deg = mpu_features.get("max_tilt_angle")
    rain_mm = float(payload.rain_mm or 0)
    # Air humidity is not treated as soil moisture. This is a neutral fallback
    # until a real soil source is integrated with the decision.
    soil_proxy = min(100.0, max(0.0, 50.0 + min(rain_mm * 2.0, 35.0)))
    solo_instavel = int(rain_mm >= 10 and inclination_deg is not None and inclination_deg >= settings.iot_inclination_attention_deg)

    iot_snapshot = {
        "temperature_c": bme.temperature_c if bme else None,
        "humidity_pct": bme.humidity_pct if bme else None,
        "pressure_hpa": bme.pressure_hpa if bme else None,
        "distance_cm": distance_cm,
        "accel_x": mpu.accel_x if mpu else None,
        "accel_y": mpu.accel_y if mpu else None,
        "accel_z": mpu.accel_z if mpu else None,
        "gyro_x": mpu.gyro_x if mpu else None,
        "gyro_y": mpu.gyro_y if mpu else None,
        "gyro_z": mpu.gyro_z if mpu else None,
        "acceleration_magnitude": mpu_features.get("acceleration_magnitude"),
        "gyro_magnitude": mpu_features.get("gyro_magnitude"),
        "pitch": mpu_features.get("absolute_pitch"),
        "roll": mpu_features.get("absolute_roll"),
        "inclination_deg": inclination_deg,
        "movement_anomaly_score": mpu_features.get("movement_anomaly_score"),
        "possible_impact": mpu_features.get("possible_impact"),
        "obstacle_detected": obstacle_detected,
        "data_quality_status": quality["data_quality_status"],
        "telemetry_status": quality["telemetry_status"],
    }
    risk_context = RiskContext(
        equipment_id=int(equipment.id),
        farm_id=int(equipment.farm_id),
        device_id=payload.device_id,
        telemetry_id=None,
        operation=payload.operation_type or "campo",
        recorded_at=timestamp,
        received_at=None,
        data_quality_status=quality["data_quality_status"],
        telemetry_status=quality["telemetry_status"],
        telemetry_age_seconds=quality["telemetry_age_seconds"],
        confidence_score=quality["confidence_score"],
        iot=iot_snapshot,
        soil={"source": "fallback", "moisture_proxy_pct": soil_proxy},
        terrain={"latitude": latitude, "longitude": longitude},
    )

    telemetry_input = TelemetryInput(
        equipment_id=int(equipment.id),
        farm_id=int(equipment.farm_id),
        region=getattr(farm, "region", settings.default_region),
        operation_type=payload.operation_type or "campo",
        clima=_infer_climate(payload),
        umidade_solo=soil_proxy,
        inclinacao=float(inclination_deg or 0.0),
        distancia_agua=999.0,
        velocidade=float(payload.speed_kmh or 0.0),
        historico_sinistros=0.0,
        chuva_mm=rain_mm,
        solo_instavel=solo_instavel,
        latitude=float(latitude if latitude is not None else settings.openweather_lat),
        longitude=float(longitude if longitude is not None else settings.openweather_lon),
        device_id=payload.device_id,
        temperatura_c=bme.temperature_c if bme else None,
        umidade_ar=bme.humidity_pct if bme else None,
        pressao_hpa=bme.pressure_hpa if bme else None,
        distancia_obstaculo=float(distance_cm) / 100.0 if distance_cm is not None else None,
        acceleration_magnitude=mpu_features.get("acceleration_magnitude"),
        gyro_magnitude=mpu_features.get("gyro_magnitude"),
        absolute_pitch=mpu_features.get("absolute_pitch"),
        absolute_roll=mpu_features.get("absolute_roll"),
        max_tilt_angle=inclination_deg,
        movement_anomaly_score=mpu_features.get("movement_anomaly_score"),
        possible_impact=mpu_features.get("possible_impact"),
        obstacle_detected=obstacle_detected,
        obstacle_distance_cm=distance_cm,
        telemetry_age_seconds=quality["telemetry_age_seconds"],
        telemetry_status=quality["telemetry_status"],
        data_quality_status=quality["data_quality_status"],
        data_quality_issues=quality["data_quality_issues"],
        missing_sensors=quality["missing_sensors"],
        confidence_score=quality["confidence_score"],
        iot_used=True,
        iot_snapshot=risk_context.snapshot(),
    )
    raw_values = {
        "timestamp": timestamp,
        "temperature_c": bme.temperature_c if bme else None,
        "humidity_pct": bme.humidity_pct if bme else None,
        "pressure_hpa": bme.pressure_hpa if bme else None,
        "altitude_m": bme.altitude_m if bme else None,
        "accel_x": mpu.accel_x if mpu else None,
        "accel_y": mpu.accel_y if mpu else None,
        "accel_z": mpu.accel_z if mpu else None,
        "gyro_x": mpu.gyro_x if mpu else None,
        "gyro_y": mpu.gyro_y if mpu else None,
        "gyro_z": mpu.gyro_z if mpu else None,
        "pitch": mpu.pitch if mpu else None,
        "roll": mpu.roll if mpu else None,
        "obstacle_detected": obstacle_detected,
        "obstacle_distance_cm": distance_cm,
        "distance_cm": distance_cm,
        "inclination_deg": inclination_deg,
        "latitude": latitude,
        "longitude": longitude,
    }
    return {
        "telemetry_input": telemetry_input,
        "raw_values": raw_values,
        "derived": mpu_features,
        "quality": quality,
        "risk_context": risk_context,
    }


def risk_context_from_telemetry(row: Any, equipment: Any, farm: Any) -> RiskContext:
    recorded_at = getattr(row, "recorded_at", None) or getattr(row, "timestamp", None)
    status, age = current_telemetry_status(recorded_at)
    quality = str(getattr(row, "data_quality_status", "VALID") or "VALID").upper()
    distance_cm = getattr(row, "distance_cm", None)
    if distance_cm is None:
        distance_cm = getattr(row, "obstacle_distance_cm", None)
    inclination_deg = getattr(row, "inclination_deg", None)
    if inclination_deg is None:
        inclination_deg = getattr(row, "max_tilt_angle", None)
    return RiskContext(
        equipment_id=int(equipment.id),
        farm_id=int(equipment.farm_id),
        device_id=getattr(row, "device_id", None),
        telemetry_id=getattr(row, "id", None),
        operation="campo",
        recorded_at=recorded_at,
        received_at=getattr(row, "received_at", None),
        data_quality_status=quality,
        telemetry_status=status,
        telemetry_age_seconds=age,
        confidence_score=getattr(row, "confidence_score", None),
        iot={
            "temperature_c": getattr(row, "temperature_c", None),
            "humidity_pct": getattr(row, "humidity_pct", None),
            "pressure_hpa": getattr(row, "pressure_hpa", None),
            "distance_cm": distance_cm,
            "accel_x": getattr(row, "accel_x", None),
            "accel_y": getattr(row, "accel_y", None),
            "accel_z": getattr(row, "accel_z", None),
            "acceleration_magnitude": getattr(row, "acceleration_magnitude", None),
            "gyro_magnitude": getattr(row, "gyro_magnitude", None),
            "pitch": getattr(row, "pitch", None),
            "roll": getattr(row, "roll", None),
            "inclination_deg": inclination_deg,
            "movement_anomaly_score": getattr(row, "movement_anomaly_score", None),
            "possible_impact": bool(getattr(row, "possible_impact", False)),
            "obstacle_detected": getattr(row, "obstacle_detected", None),
        },
        terrain={"latitude": getattr(row, "latitude", None), "longitude": getattr(row, "longitude", None)},
    )


def apply_risk_context(payload: dict[str, Any], context: RiskContext) -> dict[str, Any]:
    """Give valid recent physical readings priority over simulated equivalents."""
    if not context.is_usable:
        return payload
    data = dict(payload)
    iot = context.iot
    replacements = {
        "temperatura_c": iot.get("temperature_c"),
        "umidade_ar": iot.get("humidity_pct"),
        "pressao_hpa": iot.get("pressure_hpa"),
        "distancia_obstaculo": (float(iot["distance_cm"]) / 100.0) if iot.get("distance_cm") is not None else None,
        "inclinacao": iot.get("inclination_deg"),
        "acceleration_magnitude": iot.get("acceleration_magnitude"),
        "movement_anomaly_score": iot.get("movement_anomaly_score"),
        "possible_impact": iot.get("possible_impact"),
        "obstacle_detected": iot.get("obstacle_detected"),
    }
    for key, value in replacements.items():
        if value is not None:
            data[key] = value
    data.update(
        {
            "iot_used": True,
            "telemetry_id": context.telemetry_id,
            "iot_snapshot": context.snapshot(),
            "telemetry_status": context.telemetry_status,
            "telemetry_age_seconds": context.telemetry_age_seconds,
            "data_quality_status": context.data_quality_status,
            "confidence_score": context.confidence_score,
            "obstacle_distance_cm": iot.get("distance_cm"),
            "max_tilt_angle": iot.get("inclination_deg"),
            "absolute_pitch": iot.get("pitch"),
            "absolute_roll": iot.get("roll"),
        }
    )
    return data


def build_iot_events(context: RiskContext) -> list[dict[str, Any]]:
    """Return only sensor events actually supported by the current readings."""
    iot = context.iot
    events: list[dict[str, Any]] = []
    distance = iot.get("distance_cm")
    if distance is not None:
        if float(distance) <= settings.iot_distance_critical_cm:
            events.append(("OBSTACLE_CRITICAL", "CRITICAL", distance, "cm", "Obstaculo em distancia critica detectado pelo JSN-SR04T."))
        elif float(distance) <= settings.iot_distance_attention_cm:
            events.append(("OBSTACLE_NEAR", "MEDIUM", distance, "cm", "Obstaculo proximo detectado pelo JSN-SR04T."))

    inclination = iot.get("inclination_deg")
    if inclination is not None:
        if float(inclination) >= settings.iot_inclination_critical_deg:
            events.append(("CRITICAL_INCLINATION", "CRITICAL", inclination, "deg", "Inclinacao critica detectada pelo MPU-6050."))
        elif float(inclination) >= settings.iot_inclination_high_deg:
            events.append(("HIGH_INCLINATION", "MEDIUM", inclination, "deg", "Inclinacao elevada detectada pelo MPU-6050."))

    acceleration = iot.get("acceleration_magnitude")
    if acceleration is not None and float(acceleration) >= STANDARD_GRAVITY_M_S2 * settings.acceleration_impact_g:
        events.append(("ABNORMAL_ACCELERATION", "CRITICAL", acceleration, "m/s2", "Aceleracao anormal detectada pelo MPU-6050."))

    temperature = iot.get("temperature_c")
    if temperature is not None and float(temperature) >= settings.high_temperature_c:
        events.append(("HIGH_TEMPERATURE", "MEDIUM", temperature, "C", "Temperatura elevada detectada pelo BME280."))
    humidity = iot.get("humidity_pct")
    if humidity is not None and float(humidity) >= settings.high_humidity_pct:
        events.append(("HIGH_HUMIDITY", "MEDIUM", humidity, "%", "Umidade elevada detectada pelo BME280."))

    if context.data_quality_status == "PARTIAL":
        events.append(("SENSOR_PARTIAL", "MEDIUM", None, None, "Telemetria parcial: um ou mais sensores estao ausentes."))
    elif context.data_quality_status == "INVALID":
        events.append(("SENSOR_INVALID", "CRITICAL", None, None, "Telemetria invalida e nao utilizada pela IA."))

    return [
        {
            "event_type": event_type,
            "severity": severity,
            "value": value,
            "unit": unit,
            "description": description,
        }
        for event_type, severity, value, unit, description in events
    ]
