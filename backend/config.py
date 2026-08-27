from __future__ import annotations
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "sim"}


def _normalize_database_url(value: str | None) -> str:
    """Use psycopg explicitly while accepting common PostgreSQL URL aliases."""
    database_url = (value or "sqlite:///./agroguardian.db").strip()
    if database_url.startswith("postgres://"):
        return "postgresql+psycopg://" + database_url.removeprefix("postgres://")
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url.removeprefix("postgresql://")
    return database_url


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "AgroGuardian AI")
    model_version: str = os.getenv("MODEL_VERSION", "1.0.0")
    database_url: str = _normalize_database_url(os.getenv("DATABASE_URL"))
    auto_seed_demo: bool = _as_bool(os.getenv("AUTO_SEED_DEMO"), default=False)
    initial_admin_username: str = os.getenv("INITIAL_ADMIN_USERNAME", "")
    initial_admin_email: str = os.getenv("INITIAL_ADMIN_EMAIL", "")
    initial_admin_password: str = os.getenv("INITIAL_ADMIN_PASSWORD", "")
    api_base_url: str = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
    openweather_api_key: str = os.getenv("OPENWEATHER_API_KEY", "")
    openweather_lat: float = float(os.getenv("OPENWEATHER_LAT", "-23.455"))
    openweather_lon: float = float(os.getenv("OPENWEATHER_LON", "-46.533"))
    overpass_api_url: str = os.getenv("OVERPASS_API_URL", "https://overpass-api.de/api/interpreter")
    geo_search_radius_m: int = int(os.getenv("GEO_SEARCH_RADIUS_M", "3000"))
    enable_overpass_geo: bool = _as_bool(os.getenv("ENABLE_OVERPASS_GEO"), default=True)
    default_farm_name: str = os.getenv("DEFAULT_FARM_NAME", "Fazenda Modelo")
    default_region: str = os.getenv("DEFAULT_REGION", "Guarulhos - SP")
    default_client: str = os.getenv("DEFAULT_CLIENT", "Cliente Demo")
    default_equipment: str = os.getenv("DEFAULT_EQUIPMENT", "Trator A")
    default_device_api_key: str = os.getenv("DEFAULT_DEVICE_API_KEY", "")
    environment: str = os.getenv("ENVIRONMENT", "development").strip().lower()
    iot_auth_enabled: bool = _as_bool(os.getenv("IOT_AUTH_ENABLED"), default=True)
    iot_live_seconds: int = int(os.getenv("IOT_LIVE_SECONDS", "30"))
    iot_stale_seconds: int = int(
        os.getenv(
            "IOT_STALE_SECONDS",
            os.getenv("IOT_OFFLINE_THRESHOLD_SECONDS", os.getenv("IOT_OFFLINE_SECONDS", "300")),
        )
    )
    iot_offline_threshold_seconds: int = int(
        os.getenv("IOT_OFFLINE_THRESHOLD_SECONDS", os.getenv("IOT_STALE_SECONDS", os.getenv("IOT_OFFLINE_SECONDS", "300")))
    )
    # Compatibility alias used by older callers.
    iot_offline_seconds: int = int(
        os.getenv("IOT_OFFLINE_THRESHOLD_SECONDS", os.getenv("IOT_STALE_SECONDS", os.getenv("IOT_OFFLINE_SECONDS", "300")))
    )
    iot_rate_limit_per_minute: int = int(os.getenv("IOT_RATE_LIMIT_PER_MINUTE", "120"))
    iot_max_payload_bytes: int = int(os.getenv("IOT_MAX_PAYLOAD_BYTES", "32768"))
    iot_min_prediction_interval_seconds: int = int(os.getenv("IOT_MIN_PREDICTION_INTERVAL_SECONDS", "0"))
    iot_distance_safe_cm: float = float(os.getenv("IOT_DISTANCE_SAFE_CM", "180"))
    iot_distance_attention_cm: float = float(
        os.getenv("IOT_DISTANCE_ATTENTION_CM", os.getenv("OBSTACLE_ATTENTION_CM", "180"))
    )
    iot_distance_critical_cm: float = float(
        os.getenv("IOT_DISTANCE_CRITICAL_CM", os.getenv("OBSTACLE_CRITICAL_CM", "45"))
    )
    obstacle_attention_cm: float = float(
        os.getenv("IOT_DISTANCE_ATTENTION_CM", os.getenv("OBSTACLE_ATTENTION_CM", "180"))
    )
    obstacle_near_cm: float = float(os.getenv("OBSTACLE_NEAR_CM", "80"))
    obstacle_critical_cm: float = float(
        os.getenv("IOT_DISTANCE_CRITICAL_CM", os.getenv("OBSTACLE_CRITICAL_CM", "45"))
    )
    iot_inclination_attention_deg: float = float(
        os.getenv("IOT_INCLINATION_ATTENTION_DEG", os.getenv("TILT_MODERATE_DEG", "10"))
    )
    iot_inclination_high_deg: float = float(
        os.getenv("IOT_INCLINATION_HIGH_DEG", os.getenv("TILT_HIGH_DEG", "15"))
    )
    iot_inclination_critical_deg: float = float(
        os.getenv("IOT_INCLINATION_CRITICAL_DEG", os.getenv("TILT_EXTREME_DEG", "22"))
    )
    tilt_moderate_deg: float = float(
        os.getenv("IOT_INCLINATION_ATTENTION_DEG", os.getenv("TILT_MODERATE_DEG", "10"))
    )
    tilt_high_deg: float = float(
        os.getenv("IOT_INCLINATION_HIGH_DEG", os.getenv("TILT_HIGH_DEG", "15"))
    )
    tilt_extreme_deg: float = float(
        os.getenv("IOT_INCLINATION_CRITICAL_DEG", os.getenv("TILT_EXTREME_DEG", "22"))
    )
    acceleration_impact_g: float = float(os.getenv("ACCELERATION_IMPACT_G", "1.8"))
    iot_acceleration_max_m_s2: float = float(os.getenv("IOT_ACCELERATION_MAX_M_S2", "78.5"))
    iot_acceleration_suspect_m_s2: float = float(os.getenv("IOT_ACCELERATION_SUSPECT_M_S2", "70"))
    gyro_abnormal_dps: float = float(os.getenv("GYRO_ABNORMAL_DPS", "220"))
    high_temperature_c: float = float(os.getenv("HIGH_TEMPERATURE_C", "38"))
    high_humidity_pct: float = float(os.getenv("HIGH_HUMIDITY_PCT", "88"))
    iot_temperature_min_c: float = float(os.getenv("IOT_TEMPERATURE_MIN_C", "-40"))
    iot_temperature_max_c: float = float(os.getenv("IOT_TEMPERATURE_MAX_C", "85"))
    iot_pressure_min_hpa: float = float(os.getenv("IOT_PRESSURE_MIN_HPA", "300"))
    iot_pressure_max_hpa: float = float(os.getenv("IOT_PRESSURE_MAX_HPA", "1100"))
    iot_future_timestamp_tolerance_seconds: int = int(
        os.getenv("IOT_FUTURE_TIMESTAMP_TOLERANCE_SECONDS", "60")
    )

settings = Settings()
