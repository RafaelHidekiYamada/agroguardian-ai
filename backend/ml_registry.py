from __future__ import annotations

import json
from pathlib import Path

import joblib

from .risk_model import FEATURES, train_or_load_model


ROOT_DIR = Path(__file__).resolve().parent.parent
ML_DIR = ROOT_DIR / "ml"
ML_MODELS_DIR = ML_DIR / "saved_models"

METRICS_PATH = ML_DIR / "model_metrics.json"
BEST_MODEL_PATH = ML_MODELS_DIR / "best_risk_model.joblib"
TREE_MODEL_PATH = ML_MODELS_DIR / "tree_risk_model.joblib"
NEURAL_MODEL_PATH = ML_MODELS_DIR / "mlp_regressor.joblib"


def _bundle_from_path(model_path: Path, runtime_source: str) -> dict:
    bundle = joblib.load(model_path)

    if isinstance(bundle, dict):
        bundle["runtime_source"] = runtime_source
        return bundle

    return {
        "model": bundle,
        "model_name": model_path.stem,
        "feature_names": FEATURES,
        "runtime_source": runtime_source,
    }


def load_runtime_model():
    """
    Load the strongest saved model available.

    Priority:
    1. best model produced by tree/ensemble search
    2. tree model artifact
    3. neural model artifact
    4. default backend artifact
    """
    candidates = (
        (BEST_MODEL_PATH, "best_saved_model"),
        (TREE_MODEL_PATH, "tree_saved_model"),
        (NEURAL_MODEL_PATH, "ml_saved_model"),
    )

    for model_path, runtime_source in candidates:
        if model_path.exists():
            return _bundle_from_path(model_path, runtime_source)

    bundle = train_or_load_model()
    bundle["runtime_source"] = "backend_artifact"
    return bundle


def get_ml_status():
    return {
        "best_model_exists": BEST_MODEL_PATH.exists(),
        "tree_model_exists": TREE_MODEL_PATH.exists(),
        "neural_model_exists": NEURAL_MODEL_PATH.exists(),
        "metrics_file_exists": METRICS_PATH.exists(),
        "best_model_path": str(BEST_MODEL_PATH),
        "tree_model_path": str(TREE_MODEL_PATH),
        "neural_model_path": str(NEURAL_MODEL_PATH),
        "metrics_path": str(METRICS_PATH),
    }


def get_ml_metrics():
    if METRICS_PATH.exists():
        with open(METRICS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    return {
        "message": "Arquivo de metricas ainda nao encontrado.",
        "expected_path": str(METRICS_PATH),
    }
