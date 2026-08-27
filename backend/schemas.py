from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import settings


_SENSITIVE_FIELD_NAMES = frozenset(
    {
        "api_key",
        "api_key_hash",
        "apikey",
        "authorization",
        "access_token",
        "refresh_token",
        "password",
        "secret",
        "token",
        "x_api_key",
    }
)


def sensitive_field_path(value: Any, path: str = "") -> str | None:
    """Find credentials before they can reach raw telemetry or metadata JSON."""
    if isinstance(value, dict):
        for key, nested_value in value.items():
            field_name = str(key).strip().lower().replace("-", "_")
            field_path = f"{path}.{key}" if path else str(key)
            if field_name in _SENSITIVE_FIELD_NAMES:
                return field_path
            nested_path = sensitive_field_path(nested_value, field_path)
            if nested_path:
                return nested_path
    elif isinstance(value, list):
        for index, nested_value in enumerate(value):
            nested_path = sensitive_field_path(nested_value, f"{path}[{index}]")
            if nested_path:
                return nested_path
    return None


def redact_sensitive_fields(value: Any) -> Any:
    """Defensively redact legacy data when it is returned or persisted."""
    if isinstance(value, dict):
        return {
            key: "[redacted]"
            if str(key).strip().lower().replace("-", "_") in _SENSITIVE_FIELD_NAMES
            else redact_sensitive_fields(nested_value)
            for key, nested_value in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive_fields(nested_value) for nested_value in value]
    return value

class TelemetryInput(BaseModel):
    equipment_id: int = Field(default=1)
    farm_id: int = Field(default=1)
    region: str = Field(default="Guarulhos - SP")
    operation_type: str = Field(default="campo")
    clima: str = Field(default="chuva")
    umidade_solo: float = Field(ge=0, le=100)
    inclinacao: float = Field(ge=0, le=90)
    distancia_agua: float = Field(ge=0, le=10000)
    velocidade: float = Field(ge=0, le=200)
    historico_sinistros: float = Field(ge=0, le=100)
    chuva_mm: float = Field(ge=0, le=500)
    solo_instavel: int = Field(default=0, ge=0, le=1)
    latitude: float = Field(default=-23.455, ge=-90, le=90)
    longitude: float = Field(default=-46.533, ge=-180, le=180)
    device_id: str | None = Field(default=None)
    temperatura_c: float | None = Field(default=None, ge=-40, le=90)
    umidade_ar: float | None = Field(default=None, ge=0, le=100)
    pressao_hpa: float | None = Field(default=None, ge=300, le=1100)
    distancia_obstaculo: float | None = Field(default=None, ge=0, le=10000)
    gps_accuracy_m: float | None = Field(default=None, ge=0, le=1000)
    gps_satellites: int | None = Field(default=None, ge=0, le=64)
    battery_voltage: float | None = Field(default=None, ge=0, le=30)
    acceleration_magnitude: float | None = None
    gyro_magnitude: float | None = None
    absolute_pitch: float | None = None
    absolute_roll: float | None = None
    max_tilt_angle: float | None = None
    movement_anomaly_score: float | None = Field(default=None, ge=0, le=100)
    possible_impact: bool | None = None
    obstacle_detected: bool | None = None
    obstacle_distance_cm: float | None = Field(default=None, ge=0, le=100000)
    telemetry_age_seconds: float | None = Field(default=None, ge=0)
    telemetry_status: str | None = None
    data_quality_status: str | None = None
    data_quality_issues: list[str] = Field(default_factory=list)
    missing_sensors: list[str] = Field(default_factory=list)
    confidence_score: float | None = Field(default=None, ge=0, le=100)
    iot_used: bool = False
    telemetry_id: int | None = None
    iot_snapshot: dict[str, Any] | None = None


class ESPTelemetryInput(BaseModel):
    device_id: str = Field(default="esp32-demo")
    equipment_id: int = Field(default=1)
    farm_id: int = Field(default=1)
    region: str = Field(default="Guarulhos - SP")
    operation_type: str = Field(default="campo")
    latitude: float = Field(default=-23.455, ge=-90, le=90)
    longitude: float = Field(default=-46.533, ge=-180, le=180)
    gps_accuracy_m: float | None = Field(default=None, ge=0, le=1000)
    gps_satellites: int | None = Field(default=None, ge=0, le=64)

    temperatura_c: float | None = Field(default=None, ge=-40, le=90)
    umidade_ar: float | None = Field(default=None, ge=0, le=100)
    pressao_hpa: float | None = Field(default=None, ge=300, le=1100)
    umidade_solo: float | None = Field(default=None, ge=0, le=100)
    inclinacao: float | None = Field(default=None, ge=0, le=90)
    pitch_deg: float | None = Field(default=None, ge=-90, le=90)
    roll_deg: float | None = Field(default=None, ge=-90, le=90)
    distancia_obstaculo: float | None = Field(default=None, ge=0, le=10000)
    distancia_agua: float | None = Field(default=None, ge=0, le=10000)
    velocidade: float | None = Field(default=None, ge=0, le=200)
    chuva_mm: float | None = Field(default=None, ge=0, le=500)
    solo_instavel: int | None = Field(default=None, ge=0, le=1)
    historico_sinistros: float | None = Field(default=None, ge=0, le=100)
    battery_voltage: float | None = Field(default=None, ge=0, le=30)

    @model_validator(mode="before")
    @classmethod
    def normalize_sensor_aliases(cls, data):
        if not isinstance(data, dict):
            return data

        aliases = {
            "gps_latitude": "latitude",
            "lat": "latitude",
            "gps_longitude": "longitude",
            "lon": "longitude",
            "lng": "longitude",
            "temperature_c": "temperatura_c",
            "temp_c": "temperatura_c",
            "air_humidity_pct": "umidade_ar",
            "humidity_pct": "umidade_ar",
            "pressure_hpa": "pressao_hpa",
            "barometric_pressure_hpa": "pressao_hpa",
            "soil_moisture_pct": "umidade_solo",
            "soil_humidity_pct": "umidade_solo",
            "inclination_deg": "inclinacao",
            "tilt_deg": "inclinacao",
            "obstacle_distance_m": "distancia_obstaculo",
            "distance_obstacle_m": "distancia_obstaculo",
            "water_distance_m": "distancia_agua",
            "speed_kmh": "velocidade",
            "rainfall_mm_h": "chuva_mm",
            "rain_mm": "chuva_mm",
            "unstable_soil": "solo_instavel",
            "battery_v": "battery_voltage",
        }
        normalized = dict(data)
        for source, target in aliases.items():
            if source in normalized and target not in normalized:
                normalized[target] = normalized[source]
        return normalized

class ScenarioInput(TelemetryInput):
    scenario_name: str = Field(default="Chuva amanhã")

class PredictionResponse(BaseModel):
    timestamp: datetime
    model_version: str
    risk_score: float
    risk_label: str
    alert_level: str
    alerts: List[Dict[str, Any]]
    recommendation: str
    safe_route: Dict[str, Any]
    explanation: Dict[str, float]
    weather: Dict[str, Any]
    audit_id: int
    executive_explanation: dict | None = None
    geo_context: dict | None = None
    risk_components: dict | None = None
    decision_support: dict | None = None
    explainable_ai: dict | None = None
    confidence_score: float | None = None
    telemetry_status: str | None = None
    data_quality_status: str | None = None
    equipment_id: int | None = None
    iot_used: bool = False
    telemetry_id: int | None = None
    normalized_prediction_id: int | None = None
    main_factor: str | None = None
    factors: List[Dict[str, Any]] = Field(default_factory=list)
    summary: str | None = None

class SafeRouteRequest(BaseModel):
    origin_name: str = "Ponto atual"
    destination_name: str = "Armazém / Oficina"
    latitude: float = -23.455
    longitude: float = -46.533

class SafeRouteResponse(BaseModel):
    recommended_route: str
    route_score: float
    alternatives: List[Dict[str, Any]]
    rationale: str
    route_explanation: Dict[str, Any] | None = None

class SummaryResponse(BaseModel):
    total_predictions: int
    high_risk_count: int
    average_risk: float
    alerts_today: int
    top_equipment: List[Dict[str, Any]]
    top_regions: List[Dict[str, Any]]
    risk_trend: List[Dict[str, Any]]

class AuditResponse(BaseModel):
    id: int
    timestamp: datetime
    actor: str
    action: str
    payload: Dict[str, Any]

from pydantic import BaseModel


class AlertPolicyBase(BaseModel):
    name: str
    operation_type: str

    min_risk_alert: float = 40.0
    min_risk_block: float = 70.0

    max_speed: float = 25.0
    max_slope: float = 15.0
    min_distance_water: float = 30.0
    max_rain_mm: float = 20.0

    block_on_water: bool = False
    block_on_unstable_soil: bool = False

    is_active: bool = True


class AlertPolicyCreate(AlertPolicyBase):
    pass


class AlertPolicyUpdate(BaseModel):
    name: str | None = None
    operation_type: str | None = None

    min_risk_alert: float | None = None
    min_risk_block: float | None = None

    max_speed: float | None = None
    max_slope: float | None = None
    min_distance_water: float | None = None
    max_rain_mm: float | None = None

    block_on_water: bool | None = None
    block_on_unstable_soil: bool | None = None

    is_active: bool | None = None


class AlertPolicyResponse(AlertPolicyBase):
    id: int

    model_config = ConfigDict(from_attributes=True)

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str
    permissions: list[str] = []


class MeResponse(BaseModel):
    id: int | None = None
    username: str
    full_name: str
    email: str | None = None
    role: str
    roles: list[str] = []
    permissions: list[str] = []
    is_active: bool
    status: str | None = None
    last_login_at: datetime | None = None
    created_at: datetime | None = None


class AccessEventResponse(BaseModel):
    id: int
    username: str
    role: str
    action: str
    endpoint: str
    success: bool
    detail: dict | None = None
    timestamp: datetime


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class PermissionResponse(BaseModel):
    id: int
    code: str
    description: str | None = None

    model_config = ConfigDict(from_attributes=True)


class RoleResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    permissions: list[str] = []

    model_config = ConfigDict(from_attributes=True)


class UserAccessScopeInput(BaseModel):
    client_id: int | None = None
    client_name: str | None = None
    farm_id: int | None = None
    equipment_id: int | None = None


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    email: str = Field(min_length=5, max_length=160)
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=8)
    roles: list[str] = Field(default_factory=lambda: ["LEITURA"])
    permissions_add: list[str] = []
    permissions_remove: list[str] = []
    is_active: bool = True
    status: str = "active"
    access_scopes: list[UserAccessScopeInput] = []


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    email: str | None = Field(default=None, min_length=5, max_length=160)
    username: str | None = Field(default=None, min_length=3, max_length=80)
    password: str | None = Field(default=None, min_length=8)
    roles: list[str] | None = None
    permissions_add: list[str] | None = None
    permissions_remove: list[str] | None = None
    is_active: bool | None = None
    status: str | None = None
    access_scopes: list[UserAccessScopeInput] | None = None


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8)


class UserPermissionUpdate(BaseModel):
    permissions_add: list[str] = []
    permissions_remove: list[str] = []


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    username: str
    status: str
    is_active: bool
    roles: list[str]
    permissions: list[str]
    explicit_permissions_add: list[str] = []
    explicit_permissions_remove: list[str] = []
    access_scopes: list[dict[str, Any]] = []
    last_login_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class BME280Payload(BaseModel):
    temperature_c: float | None = None
    humidity_pct: float | None = Field(default=None, ge=0, le=100)
    pressure_hpa: float | None = None
    altitude_m: float | None = Field(default=None, ge=-500, le=9000)

    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_plausible_bme280_ranges(self):
        if self.temperature_c is not None and not (
            settings.iot_temperature_min_c <= self.temperature_c <= settings.iot_temperature_max_c
        ):
            raise ValueError("temperature_c fora da faixa plausivel configurada")
        if self.pressure_hpa is not None and not (
            settings.iot_pressure_min_hpa <= self.pressure_hpa <= settings.iot_pressure_max_hpa
        ):
            raise ValueError("pressure_hpa fora da faixa plausivel configurada")
        return self


class MPU6050Payload(BaseModel):
    accel_x: float | None = None
    accel_y: float | None = None
    accel_z: float | None = None
    gyro_x: float | None = Field(default=None, ge=-5000, le=5000)
    gyro_y: float | None = Field(default=None, ge=-5000, le=5000)
    gyro_z: float | None = Field(default=None, ge=-5000, le=5000)
    pitch: float | None = Field(default=None, ge=-180, le=180)
    roll: float | None = Field(default=None, ge=-180, le=180)
    inclination_deg: float | None = Field(default=None, ge=0, le=180)

    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_acceleration_units_and_range(self):
        for axis in ("accel_x", "accel_y", "accel_z"):
            value = getattr(self, axis)
            if value is not None and abs(value) > settings.iot_acceleration_max_m_s2:
                raise ValueError(f"{axis} fora da faixa m/s2 configurada para o MPU6050")
        return self


class ObstaclePayload(BaseModel):
    detected: bool | None = None
    distance_cm: float | None = Field(default=None, ge=0, le=100000)

    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)


class JSNSR04TPayload(BaseModel):
    distance_cm: float | None = Field(default=None, ge=0, le=100000)
    detected: bool | None = None
    timeout: bool = False
    out_of_range: bool = False

    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)


class GPSPayload(BaseModel):
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)


class IotTelemetryInput(BaseModel):
    device_id: str = Field(min_length=1, max_length=120)
    timestamp: datetime | None = None
    sequence_number: int | None = Field(default=None, ge=0)
    bme280: BME280Payload | None = None
    mpu6050: MPU6050Payload | None = None
    jsn_sr04t: JSNSR04TPayload | None = None
    # Kept as a compatibility adapter for older simulator and dashboard payloads.
    obstacle: ObstaclePayload | None = None
    gps: GPSPayload | None = None
    operation_type: str = "campo"
    speed_kmh: float | None = Field(default=None, ge=0, le=200)
    rain_mm: float | None = Field(default=None, ge=0, le=500)
    firmware_version: str | None = None

    model_config = ConfigDict(extra="allow", allow_inf_nan=False)

    @model_validator(mode="before")
    @classmethod
    def accept_flat_payload(cls, data):
        if not isinstance(data, dict):
            return data
        secret_path = sensitive_field_path(data)
        if secret_path:
            raise ValueError(f"Credenciais nao podem ser enviadas no payload ({secret_path}).")
        normalized = dict(data)

        if "bme280" not in normalized:
            bme_keys = {
                "temperature_c": "temperature_c",
                "temperatura_c": "temperature_c",
                "humidity_pct": "humidity_pct",
                "air_humidity_pct": "humidity_pct",
                "umidade_ar": "humidity_pct",
                "pressure_hpa": "pressure_hpa",
                "pressao_hpa": "pressure_hpa",
                "pressure_pa": "pressure_pa",
                "altitude_m": "altitude_m",
            }
            bme = {target: normalized[source] for source, target in bme_keys.items() if source in normalized}
            if bme:
                normalized["bme280"] = bme

        bme_payload = normalized.get("bme280")
        if isinstance(bme_payload, dict) and "pressure_hpa" not in bme_payload and "pressure_pa" in bme_payload:
            bme_payload = dict(bme_payload)
            bme_payload["pressure_hpa"] = float(bme_payload["pressure_pa"]) / 100.0
            normalized["bme280"] = bme_payload

        if "mpu6050" not in normalized:
            mpu_keys = {
                "accel_x": "accel_x",
                "accel_y": "accel_y",
                "accel_z": "accel_z",
                "gyro_x": "gyro_x",
                "gyro_y": "gyro_y",
                "gyro_z": "gyro_z",
                "pitch": "pitch",
                "pitch_deg": "pitch",
                "roll": "roll",
                "roll_deg": "roll",
                "inclination_deg": "inclination_deg",
                "inclinacao": "inclination_deg",
                "tilt_deg": "inclination_deg",
            }
            mpu = {target: normalized[source] for source, target in mpu_keys.items() if source in normalized}
            if mpu:
                normalized["mpu6050"] = mpu

        if "jsn_sr04t" not in normalized and "obstacle" in normalized:
            normalized["jsn_sr04t"] = normalized["obstacle"]

        if "jsn_sr04t" not in normalized:
            obstacle = {}
            if "obstacle_detected" in normalized:
                obstacle["detected"] = normalized["obstacle_detected"]
            if "detected" in normalized:
                obstacle["detected"] = normalized["detected"]
            if "obstacle_distance_cm" in normalized:
                obstacle["distance_cm"] = normalized["obstacle_distance_cm"]
            if "distance_cm" in normalized:
                obstacle["distance_cm"] = normalized["distance_cm"]
            if "distancia_obstaculo" in normalized:
                obstacle["distance_cm"] = float(normalized["distancia_obstaculo"]) * 100.0
            if "obstacle_distance_m" in normalized:
                obstacle["distance_cm"] = float(normalized["obstacle_distance_m"]) * 100.0
            if obstacle:
                normalized["jsn_sr04t"] = obstacle

        if "gps" not in normalized:
            gps = {}
            if "latitude" in normalized:
                gps["latitude"] = normalized["latitude"]
            if "gps_latitude" in normalized:
                gps["latitude"] = normalized["gps_latitude"]
            if "longitude" in normalized:
                gps["longitude"] = normalized["longitude"]
            if "gps_longitude" in normalized:
                gps["longitude"] = normalized["gps_longitude"]
            if gps:
                normalized["gps"] = gps

        if "rain_mm" not in normalized and "chuva_mm" in normalized:
            normalized["rain_mm"] = normalized["chuva_mm"]
        if "rain_mm" not in normalized and "rainfall_mm_h" in normalized:
            normalized["rain_mm"] = normalized["rainfall_mm_h"]
        if "speed_kmh" not in normalized and "velocidade" in normalized:
            normalized["speed_kmh"] = normalized["velocidade"]

        return normalized


class IotTelemetryResponse(BaseModel):
    status: str
    telemetry_id: int
    equipment_id: int
    risk_updated: bool
    risk_score: float | None = None
    risk_level: str | None = None
    telemetry_status: str | None = None
    data_quality_status: str | None = None
    confidence_score: float | None = None
    iot_used: bool = True
    recorded_at: datetime | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    message: str | None = None


class IotDeviceCreate(BaseModel):
    device_id: str | None = Field(default=None, min_length=3, max_length=120)
    device_identifier: str | None = Field(default=None, min_length=3, max_length=120)
    equipment_id: int
    name: str = Field(min_length=2, max_length=160)
    device_type: str = "ESP32"
    firmware_version: str | None = None
    status: str = "OFFLINE"
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_identifier(self):
        identifier = (self.device_identifier or self.device_id or "").strip()
        if not identifier:
            raise ValueError("device_identifier ou device_id e obrigatorio")
        self.device_id = identifier
        self.device_identifier = identifier
        secret_path = sensitive_field_path(self.metadata_json)
        if secret_path:
            raise ValueError(f"Credenciais nao podem ser salvas em metadata_json ({secret_path}).")
        return self


class IotDeviceUpdate(BaseModel):
    equipment_id: int | None = None
    name: str | None = Field(default=None, min_length=2, max_length=160)
    device_type: str | None = None
    firmware_version: str | None = None
    status: str | None = None
    metadata_json: dict[str, Any] | None = None
    is_active: bool | None = None
    rotate_api_key: bool = False
    revoke_api_key: bool = False

    @model_validator(mode="after")
    def reject_conflicting_key_actions(self):
        if self.rotate_api_key and self.revoke_api_key:
            raise ValueError("rotate_api_key e revoke_api_key nao podem ser usados juntos")
        secret_path = sensitive_field_path(self.metadata_json)
        if secret_path:
            raise ValueError(f"Credenciais nao podem ser salvas em metadata_json ({secret_path}).")
        return self


class IotDeviceResponse(BaseModel):
    id: int
    device_id: str
    device_identifier: str | None = None
    equipment_id: int
    name: str
    device_type: str
    firmware_version: str | None = None
    status: str
    last_seen_at: datetime | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
    api_key: str | None = None
    equipment_name: str | None = None
    farm_id: int | None = None
    farm_name: str | None = None
    telemetry_count: int | None = None
    latest_telemetry: dict[str, Any] | None = None


class EquipmentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    equipment_type: str = Field(min_length=2, max_length=60)
    client_name: str = Field(min_length=2, max_length=120)
    farm_id: int
    model: str | None = None
    year: int | None = Field(default=None, ge=1900, le=2100)
    status: str = "active"


class EquipmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    equipment_type: str | None = Field(default=None, min_length=2, max_length=60)
    client_name: str | None = Field(default=None, min_length=2, max_length=120)
    farm_id: int | None = None
    model: str | None = None
    year: int | None = Field(default=None, ge=1900, le=2100)
    status: str | None = None
