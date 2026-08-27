from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

from backend.feature_engineering import normalize_climate, normalize_operation
from backend.risk_model import FEATURES, _synth_dataset


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "ml" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

REAL_DATA_PATH = DATA_DIR / "nasa_power_agroguardian_training.csv"
REAL_METADATA_PATH = DATA_DIR / "nasa_power_agroguardian_training.metadata.json"
NASA_POWER_DAILY_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
NASA_PARAMETERS = ["T2M", "RH2M", "PS", "PRECTOTCORR", "WS10M"]

DEFAULT_START = "20240101"
DEFAULT_END = "20251231"

AGRO_REGIONS = [
    {
        "region": "Guarulhos - SP",
        "latitude": -23.4550,
        "longitude": -46.5330,
        "slope_mean": 8.0,
        "water_distance_mean": 120.0,
        "incident_bias": 2.5,
    },
    {
        "region": "Ribeirao Preto - SP",
        "latitude": -21.1775,
        "longitude": -47.8103,
        "slope_mean": 5.5,
        "water_distance_mean": 210.0,
        "incident_bias": 1.8,
    },
    {
        "region": "Rio Verde - GO",
        "latitude": -17.7923,
        "longitude": -50.9192,
        "slope_mean": 4.5,
        "water_distance_mean": 260.0,
        "incident_bias": 1.4,
    },
    {
        "region": "Sorriso - MT",
        "latitude": -12.5425,
        "longitude": -55.7211,
        "slope_mean": 3.5,
        "water_distance_mean": 340.0,
        "incident_bias": 1.1,
    },
    {
        "region": "Londrina - PR",
        "latitude": -23.3045,
        "longitude": -51.1696,
        "slope_mean": 7.0,
        "water_distance_mean": 180.0,
        "incident_bias": 1.9,
    },
    {
        "region": "Luis Eduardo Magalhaes - BA",
        "latitude": -12.0956,
        "longitude": -45.7866,
        "slope_mean": 4.0,
        "water_distance_mean": 300.0,
        "incident_bias": 1.2,
    },
    {
        "region": "Petrolina - PE",
        "latitude": -9.3891,
        "longitude": -40.5030,
        "slope_mean": 3.0,
        "water_distance_mean": 230.0,
        "incident_bias": 1.6,
    },
]


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def fetch_nasa_power_daily(region: dict[str, Any], start: str, end: str) -> pd.DataFrame:
    params = {
        "parameters": ",".join(NASA_PARAMETERS),
        "community": "AG",
        "longitude": region["longitude"],
        "latitude": region["latitude"],
        "start": start,
        "end": end,
        "format": "JSON",
    }
    response = requests.get(NASA_POWER_DAILY_URL, params=params, timeout=45)
    response.raise_for_status()
    payload = response.json()
    parameter_data = payload.get("properties", {}).get("parameter", {})

    dates = sorted(parameter_data.get("T2M", {}).keys())
    rows = []
    for date_key in dates:
        values = {name: parameter_data.get(name, {}).get(date_key) for name in NASA_PARAMETERS}
        if any(value is None or float(value) <= -900 for value in values.values()):
            continue

        rows.append(
            {
                "date": date_key,
                "region": region["region"],
                "latitude": region["latitude"],
                "longitude": region["longitude"],
                "temperature_c": float(values["T2M"]),
                "air_humidity_pct": float(values["RH2M"]),
                "surface_pressure_kpa": float(values["PS"]),
                "precipitation_mm_day": float(values["PRECTOTCORR"]),
                "wind_speed_m_s": float(values["WS10M"]),
                "source": "NASA POWER Daily API",
            }
        )

    return pd.DataFrame(rows)


def _climate_from_weather(precipitation_mm: float, humidity_pct: float) -> str:
    if precipitation_mm >= 25:
        return "tempestade"
    if precipitation_mm >= 5:
        return "chuva"
    if precipitation_mm > 0:
        return "garoa"
    if humidity_pct >= 82:
        return "nublado"
    return "sol"


def _operation_for_weather(rng: np.random.Generator, precipitation_mm: float) -> str:
    if precipitation_mm >= 15:
        return rng.choice(["campo", "transporte", "proximidade_agua"], p=[0.42, 0.23, 0.35])
    return rng.choice(["campo", "transporte", "proximidade_agua", "manutencao"], p=[0.56, 0.26, 0.12, 0.06])


def _risk_target(row: dict[str, Any]) -> float:
    climate_code = float(row["clima_code"])
    operation_code = float(row["operation_code"])
    pressure = float(row["pressao_hpa"])
    obstacle = float(row["distancia_obstaculo"])

    risk = (
        0.30 * float(row["umidade_solo"])
        + 1.05 * float(row["inclinacao"])
        + 0.30 * max(0.0, 90.0 - float(row["distancia_agua"]))
        + 1.25 * float(row["velocidade"])
        + 2.15 * float(row["historico_sinistros"])
        + 0.95 * float(row["chuva_mm"])
        + 16.0 * float(row["solo_instavel"])
        + 4.5 * (climate_code == 2)
        + 8.0 * (climate_code == 3)
        + 4.0 * (operation_code == 2)
        + 0.70 * max(0.0, float(row["temperatura_c"]) - 32.0)
        + 0.22 * max(0.0, float(row["umidade_ar"]) - 85.0)
        + 0.07 * max(0.0, 960.0 - pressure)
        + (12.0 if obstacle < 1.5 else 6.0 if obstacle < 3.0 else 0.0)
        + 0.08 * max(0.0, float(row["gps_accuracy_m"]) - 15.0)
    )
    return round(_clamp(risk, 0.0, 100.0), 2)


def build_real_weather_training_dataset(
    start: str = DEFAULT_START,
    end: str = DEFAULT_END,
    force: bool = False,
    seed: int = 42,
) -> pd.DataFrame:
    if REAL_DATA_PATH.exists() and not force:
        return pd.read_csv(REAL_DATA_PATH)

    rng = np.random.default_rng(seed)
    training_rows: list[dict[str, Any]] = []

    for region in AGRO_REGIONS:
        weather_df = fetch_nasa_power_daily(region, start=start, end=end)
        if weather_df.empty:
            continue

        weather_df["rolling_precip_7d"] = (
            weather_df["precipitation_mm_day"].rolling(window=7, min_periods=1).sum()
        )

        for _, weather in weather_df.iterrows():
            precipitation = float(weather["precipitation_mm_day"])
            humidity = float(weather["air_humidity_pct"])
            temperature = float(weather["temperature_c"])
            operation_type = _operation_for_weather(rng, precipitation)
            clima = _climate_from_weather(precipitation, humidity)

            umidade_solo = _clamp(
                0.42 * humidity
                + 1.55 * float(weather["rolling_precip_7d"])
                + 0.95 * precipitation
                - 0.85 * max(0.0, temperature - 30.0)
                + rng.normal(0, 5),
                5.0,
                100.0,
            )
            inclinacao = _clamp(float(region["slope_mean"]) + rng.normal(0, 3.2), 0.0, 28.0)
            distancia_agua = _clamp(float(region["water_distance_mean"]) + rng.normal(0, 85), 5.0, 650.0)
            velocidade_base = 12.0 if operation_type == "campo" else 19.0 if operation_type == "transporte" else 8.0
            velocidade = _clamp(velocidade_base + rng.normal(0, 4.5) - min(5.0, precipitation * 0.12), 0.0, 35.0)
            historico = _clamp(float(region["incident_bias"]) + rng.poisson(1.1 if precipitation >= 10 else 0.45), 0.0, 18.0)
            solo_instavel = int(umidade_solo >= 78 and (precipitation >= 5 or inclinacao >= 12))
            distancia_obstaculo = _clamp(rng.lognormal(mean=2.0, sigma=0.95), 0.35, 80.0)
            gps_accuracy_m = _clamp(rng.lognormal(mean=1.6, sigma=0.55), 0.6, 35.0)

            row = {
                "date": weather["date"],
                "region": weather["region"],
                "latitude": weather["latitude"],
                "longitude": weather["longitude"],
                "operation_type": operation_type,
                "clima": clima,
                "umidade_solo": round(float(umidade_solo), 2),
                "inclinacao": round(float(inclinacao), 2),
                "distancia_agua": round(float(distancia_agua), 2),
                "velocidade": round(float(velocidade), 2),
                "historico_sinistros": round(float(historico), 2),
                "chuva_mm": round(precipitation, 2),
                "solo_instavel": solo_instavel,
                "clima_code": float(normalize_climate(clima)),
                "operation_code": float(normalize_operation(operation_type)),
                "temperatura_c": round(temperature, 2),
                "umidade_ar": round(humidity, 2),
                "pressao_hpa": round(float(weather["surface_pressure_kpa"]) * 10.0, 2),
                "distancia_obstaculo": round(float(distancia_obstaculo), 2),
                "gps_accuracy_m": round(float(gps_accuracy_m), 2),
                "wind_speed_m_s": round(float(weather["wind_speed_m_s"]), 2),
                "source": weather["source"],
            }
            row["risk_score"] = _risk_target(row)
            training_rows.append(row)

    df = pd.DataFrame(training_rows)
    if df.empty:
        raise RuntimeError("Nenhum dado retornado pela NASA POWER para o intervalo solicitado.")

    df.to_csv(REAL_DATA_PATH, index=False, encoding="utf-8")
    REAL_METADATA_PATH.write_text(
        json.dumps(
            {
                "dataset": REAL_DATA_PATH.name,
                "created_at_utc": datetime.utcnow().isoformat(),
                "source": "NASA POWER Daily API",
                "source_url": NASA_POWER_DAILY_URL,
                "parameters": NASA_PARAMETERS,
                "start": start,
                "end": end,
                "regions": AGRO_REGIONS,
                "rows": int(len(df)),
                "features": FEATURES,
                "target": "risk_score",
                "labeling_note": (
                    "Meteorologia historica real da NASA POWER. O target de risco e "
                    "heuristico-operacional ate haver base real de sinistros/equipamentos."
                ),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return df


def load_training_data(prefer_real: bool = True, n_synthetic: int = 4000, seed: int = 42) -> tuple[pd.DataFrame, pd.Series, dict[str, Any]]:
    if prefer_real:
        try:
            df = build_real_weather_training_dataset(force=False, seed=seed)
            missing = [feature for feature in FEATURES if feature not in df.columns]
            if not missing and "risk_score" in df.columns:
                X = df[FEATURES].copy()
                y = df["risk_score"].copy()
                metadata = {
                    "dataset": "nasa_power_agroguardian_training",
                    "source": "NASA POWER Daily API",
                    "rows": int(len(df)),
                    "path": str(REAL_DATA_PATH),
                    "features": FEATURES,
                    "target": "risk_score",
                }
                return X, y, metadata
        except Exception as exc:
            fallback_reason = str(exc)
        else:
            fallback_reason = "dataset real incompleto"
    else:
        fallback_reason = "prefer_real=False"

    X, y = _synth_dataset(n=n_synthetic, seed=seed)
    metadata = {
        "dataset": "synthetic_operational_risk",
        "source": "fallback_synthetic",
        "rows": int(len(X)),
        "features": FEATURES,
        "target": "risk_score",
        "fallback_reason": fallback_reason,
    }
    return X, y, metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Baixa dados reais da NASA POWER para treino do AgroGuardian.")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    df = build_real_weather_training_dataset(start=args.start, end=args.end, force=args.force)
    print(f"Dataset salvo em: {REAL_DATA_PATH}")
    print(f"Linhas: {len(df)}")
    print(f"Periodo: {args.start} a {args.end}")


if __name__ == "__main__":
    main()
