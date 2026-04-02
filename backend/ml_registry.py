from __future__ import annotations
from pathlib import Path
import json
import joblib

from .risk_model import train_or_load_model

ROOT_DIR = Path(__file__).resolve().parent.parent
ML_DIR = ROOT_DIR / "ml"
ML_MODELS_DIR = ML_DIR / "saved_models"

METRICS_PATH = ML_DIR / "model_metrics.json"
NEURAL_MODEL_PATH = ML_MODELS_DIR / "mlp_regressor.joblib"


def load_runtime_model():
    """
    Carrega o melhor modelo disponível.
    Prioridade:
    1. rede neural salva em ml/saved_models
    2. modelo padrão do sistema em backend/artifacts
    """
    if NEURAL_MODEL_PATH.exists():
        bundle = joblib.load(NEURAL_MODEL_PATH)

        if isinstance(bundle, dict):
            bundle["runtime_source"] = "ml_saved_model"
            return bundle

        return {
            "model": bundle,
            "model_name": "mlp_regressor",
            "feature_names": [
                "umidade_solo",
                "inclinacao",
                "distancia_agua",
                "velocidade",
                "historico_sinistros",
                "chuva_mm",
                "solo_instavel",
                "clima_code",
                "operation_code",
            ],
            "runtime_source": "ml_saved_model",
        }

    bundle = train_or_load_model()
    bundle["runtime_source"] = "backend_artifact"
    return bundle


def get_ml_status():
    return {
        "neural_model_exists": NEURAL_MODEL_PATH.exists(),
        "metrics_file_exists": METRICS_PATH.exists(),
        "neural_model_path": str(NEURAL_MODEL_PATH),
        "metrics_path": str(METRICS_PATH),
    }


def get_ml_metrics():
    if METRICS_PATH.exists():
        with open(METRICS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    return {
        "message": "Arquivo de métricas ainda não encontrado.",
        "expected_path": str(METRICS_PATH),
    }