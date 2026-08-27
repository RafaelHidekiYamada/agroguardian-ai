from __future__ import annotations

import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from backend.risk_model import FEATURES
from ml.training_data import load_training_data as load_tabular_training_data

BASE_DIR = Path(__file__).resolve().parent
ARTIFACTS_DIR = BASE_DIR / "saved_models"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
MODEL_PATH = ARTIFACTS_DIR / "mlp_regressor.joblib"
METRICS_PATH = ARTIFACTS_DIR / "neural_metrics.json"


def load_training_data() -> tuple[pd.DataFrame, pd.Series, dict]:
    return load_tabular_training_data(prefer_real=True, n_synthetic=4000, seed=42)


def train_neural_network() -> dict:
    X, y, training_metadata = load_training_data()

    X_train, X_test, y_train, y_test = train_test_split(
        X[FEATURES], y, test_size=0.2, random_state=42
    )

    pipeline = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "mlp",
                MLPRegressor(
                    hidden_layer_sizes=(64, 32),
                    activation="relu",
                    solver="adam",
                    max_iter=500,
                    random_state=42,
                    early_stopping=True,
                ),
            ),
        ]
    )

    pipeline.fit(X_train, y_train)
    preds = pipeline.predict(X_test)

    metrics = {
        "model_name": "mlp_regressor",
        "mae": round(float(mean_absolute_error(y_test, preds)), 4),
        "rmse": round(float(mean_squared_error(y_test, preds) ** 0.5), 4),
        "r2": round(float(r2_score(y_test, preds)), 4),
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "features": FEATURES,
        "training_dataset": training_metadata.get("dataset", "unknown"),
        "training_source": training_metadata.get("source", "unknown"),
        "training_path": training_metadata.get("path"),
    }

    bundle = {
        "model": pipeline,
        "model_name": "mlp_regressor",
        "feature_names": FEATURES,
        "metrics": metrics,
    }

    joblib.dump(bundle, MODEL_PATH)
    METRICS_PATH.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    return metrics


if __name__ == "__main__":
    metrics = train_neural_network()
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
