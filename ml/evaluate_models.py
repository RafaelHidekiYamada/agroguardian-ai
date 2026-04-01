from __future__ import annotations

import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

from backend.risk_model import FEATURES, _synth_dataset, train_or_load_model
from ml.train_neural_network import train_neural_network, MODEL_PATH as NN_MODEL_PATH

BASE_DIR = Path(__file__).resolve().parent
METRICS_PATH = BASE_DIR / "model_metrics.json"


def evaluate_bundle(bundle: dict, X_test: pd.DataFrame, y_test: pd.Series) -> dict:
    model = bundle["model"]
    preds = model.predict(X_test[FEATURES])
    return {
        "model_name": bundle.get("model_name", "unknown"),
        "mae": round(float(mean_absolute_error(y_test, preds)), 4),
        "rmse": round(float(mean_squared_error(y_test, preds) ** 0.5), 4),
        "r2": round(float(r2_score(y_test, preds)), 4),
    }


def main() -> None:
    X, y = _synth_dataset(n=4000, seed=123)
    _, X_test, _, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    base_bundle = train_or_load_model()
    base_metrics = evaluate_bundle(base_bundle, X_test, y_test)

    if not NN_MODEL_PATH.exists():
        train_neural_network()
    nn_bundle = joblib.load(NN_MODEL_PATH)
    nn_metrics = evaluate_bundle(nn_bundle, X_test, y_test)

    output = {
        "baseline": base_metrics,
        "neural_network": nn_metrics,
        "recommended_model": (
            nn_metrics["model_name"] if nn_metrics["rmse"] <= base_metrics["rmse"] else base_metrics["model_name"]
        ),
    }

    METRICS_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
