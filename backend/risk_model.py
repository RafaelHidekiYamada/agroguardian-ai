from __future__ import annotations
from pathlib import Path
from typing import Dict, Tuple
import numpy as np
import pandas as pd
import joblib

MODEL_DIR = Path(__file__).resolve().parent.parent / "artifacts"
MODEL_DIR.mkdir(parents=True, exist_ok=True)
MODEL_PATH = MODEL_DIR / "risk_model.joblib"

FEATURES = [
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

def _synth_dataset(n: int = 2500, seed: int = 42) -> Tuple[pd.DataFrame, pd.Series]:
    rng = np.random.default_rng(seed)
    umidade_solo = rng.uniform(10, 100, n)
    inclinacao = rng.uniform(0, 25, n)
    distancia_agua = rng.uniform(0, 250, n)
    velocidade = rng.uniform(0, 30, n)
    historico_sinistros = rng.uniform(0, 12, n)
    chuva_mm = rng.uniform(0, 45, n)
    solo_instavel = rng.integers(0, 2, n)
    clima_code = rng.integers(0, 5, n)
    operation_code = rng.integers(0, 4, n)
    temperatura_c = rng.uniform(12, 39, n)
    umidade_ar = rng.uniform(35, 100, n)
    pressao_hpa = rng.uniform(900, 1025, n)
    distancia_obstaculo = rng.uniform(0.4, 60, n)
    gps_accuracy_m = rng.uniform(0.8, 35, n)

    risco = (
        0.32 * umidade_solo +
        1.10 * inclinacao +
        0.28 * np.maximum(0, 80 - distancia_agua) +
        1.45 * velocidade +
        2.10 * historico_sinistros +
        0.85 * chuva_mm +
        17.0 * solo_instavel +
        5.0 * (clima_code == 2).astype(float) +
        7.0 * (clima_code == 3).astype(float) +
        4.0 * (operation_code == 2).astype(float) +
        0.75 * np.maximum(0, temperatura_c - 32) +
        0.22 * np.maximum(0, umidade_ar - 85) +
        0.06 * np.maximum(0, 960 - pressao_hpa) +
        13.0 * (distancia_obstaculo < 1.5).astype(float) +
        6.0 * ((distancia_obstaculo >= 1.5) & (distancia_obstaculo < 3.0)).astype(float) +
        0.12 * np.maximum(0, gps_accuracy_m - 15) +
        rng.normal(0, 7, n)
    )
    risco = np.clip(risco, 0, 100)

    X = pd.DataFrame({
        "umidade_solo": umidade_solo,
        "inclinacao": inclinacao,
        "distancia_agua": distancia_agua,
        "velocidade": velocidade,
        "historico_sinistros": historico_sinistros,
        "chuva_mm": chuva_mm,
        "solo_instavel": solo_instavel,
        "clima_code": clima_code,
        "operation_code": operation_code,
        "temperatura_c": temperatura_c,
        "umidade_ar": umidade_ar,
        "pressao_hpa": pressao_hpa,
        "distancia_obstaculo": distancia_obstaculo,
        "gps_accuracy_m": gps_accuracy_m,
    })
    y = pd.Series(risco, name="risk_score")
    return X, y

def train_or_load_model():
    if MODEL_PATH.exists():
        return joblib.load(MODEL_PATH)

    X, y = _synth_dataset()

    model = None
    model_name = "random_forest"

    try:
        import xgboost as xgb  # type: ignore
        model = xgb.XGBRegressor(
            n_estimators=250,
            max_depth=5,
            learning_rate=0.07,
            subsample=0.9,
            colsample_bytree=0.9,
            objective="reg:squarederror",
            random_state=42,
            n_jobs=4,
        )
        model_name = "xgboost"
    except Exception:
        from sklearn.ensemble import RandomForestRegressor
        model = RandomForestRegressor(
            n_estimators=250,
            random_state=42,
            max_depth=14,
            n_jobs=4,
        )

    model.fit(X, y)

    bundle = {
        "model": model,
        "model_name": model_name,
        "feature_names": FEATURES,
    }
    joblib.dump(bundle, MODEL_PATH)
    return bundle

def predict_risk(bundle: Dict, features: Dict[str, float]) -> float:
    model = bundle["model"]
    feature_names = bundle.get("feature_names") or FEATURES
    row = {name: float(features.get(name, 0.0)) for name in feature_names}
    df = pd.DataFrame([row], columns=feature_names)
    pred = float(model.predict(df)[0])
    return float(np.clip(pred, 0, 100))
