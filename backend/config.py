from __future__ import annotations
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "AgroGuardian AI")
    model_version: str = os.getenv("MODEL_VERSION", "1.0.0")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./agroguardian.db")
    api_base_url: str = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
    openweather_api_key: str = os.getenv("OPENWEATHER_API_KEY", "")
    openweather_lat: float = float(os.getenv("OPENWEATHER_LAT", "-23.455"))
    openweather_lon: float = float(os.getenv("OPENWEATHER_LON", "-46.533"))
    default_farm_name: str = os.getenv("DEFAULT_FARM_NAME", "Fazenda Modelo")
    default_region: str = os.getenv("DEFAULT_REGION", "Guarulhos - SP")
    default_client: str = os.getenv("DEFAULT_CLIENT", "Cliente Demo")
    default_equipment: str = os.getenv("DEFAULT_EQUIPMENT", "Trator A")

settings = Settings()
