from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

from backend.risk_model import FEATURES, _synth_dataset, train_or_load_model
from ml.train_decision_trees import (
    BEST_MODEL_PATH,
    HIGH_RISK_THRESHOLD,
    train_decision_tree_models,
)
from ml.train_neural_network import MODEL_PATH as NN_MODEL_PATH
from ml.train_neural_network import train_neural_network


BASE_DIR = Path(__file__).resolve().parent
METRICS_PATH = BASE_DIR / "model_metrics.json"


def _classification_metrics(y_test: pd.Series, preds: np.ndarray, threshold: float) -> Dict[str, float]:
    y_true_high = (y_test >= HIGH_RISK_THRESHOLD).astype(int)
    y_pred_high = (preds >= threshold).astype(int)
    metrics = {
        "threshold": round(float(threshold), 2),
        "accuracy": round(float(accuracy_score(y_true_high, y_pred_high)), 4),
        "balanced_accuracy": round(float(balanced_accuracy_score(y_true_high, y_pred_high)), 4),
        "precision": round(float(precision_score(y_true_high, y_pred_high, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true_high, y_pred_high, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true_high, y_pred_high, zero_division=0)), 4),
    }
    try:
        metrics["roc_auc"] = round(float(roc_auc_score(y_true_high, preds)), 4)
    except ValueError:
        metrics["roc_auc"] = 0.0
    return metrics


def evaluate_bundle(bundle: dict, X_test: pd.DataFrame, y_test: pd.Series) -> Dict[str, Any]:
    model = bundle["model"]
    preds = np.clip(model.predict(X_test[FEATURES]), 0, 100)
    return {
        "model_name": bundle.get("model_name", "unknown"),
        "runtime_source": bundle.get("runtime_source", "evaluation"),
        "regression": {
            "mae": round(float(mean_absolute_error(y_test, preds)), 4),
            "rmse": round(float(mean_squared_error(y_test, preds) ** 0.5), 4),
            "r2": round(float(r2_score(y_test, preds)), 4),
        },
        "classification_at_70": _classification_metrics(y_test, preds, HIGH_RISK_THRESHOLD),
        "feature_weights": bundle.get("feature_weights")
        or bundle.get("metrics", {}).get("feature_weights")
        or {},
    }


def main() -> None:
    X, y = _synth_dataset(n=4500, seed=123)
    _, X_test, _, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42,
        stratify=(y >= HIGH_RISK_THRESHOLD).astype(int),
    )

    base_bundle = train_or_load_model()
    base_bundle["runtime_source"] = "backend_artifact"
    base_metrics = evaluate_bundle(base_bundle, X_test, y_test)

    if not NN_MODEL_PATH.exists():
        train_neural_network()
    nn_bundle = joblib.load(NN_MODEL_PATH)
    nn_metrics = evaluate_bundle(nn_bundle, X_test, y_test)

    if not BEST_MODEL_PATH.exists():
        tree_output = train_decision_tree_models(n=5000, seed=42)
    else:
        tree_output = {}
    tree_bundle = joblib.load(BEST_MODEL_PATH)
    tree_metrics = evaluate_bundle(tree_bundle, X_test, y_test)
    tree_saved_metrics = tree_bundle.get("metrics", {}) if isinstance(tree_bundle, dict) else {}
    tree_search_report = tree_output.get(
        "best_model",
        {
            "model_name": tree_metrics["model_name"],
            "best_params": tree_saved_metrics.get("best_params", {}),
            "regression": tree_metrics["regression"],
            "classification_at_70": tree_metrics["classification_at_70"],
            "best_curve_point": tree_saved_metrics.get(
                "best_curve_point",
                tree_metrics["classification_at_70"],
            ),
            "feature_weights": tree_metrics.get("feature_weights", {}),
            "threshold_curve": tree_bundle.get("threshold_curve", [])
            if isinstance(tree_bundle, dict)
            else [],
        },
    )

    candidates = [base_metrics, nn_metrics, tree_metrics]
    recommended = min(
        candidates,
        key=lambda item: (
            item["regression"]["rmse"],
            -item["classification_at_70"]["f1"],
            -item["classification_at_70"]["accuracy"],
        ),
    )

    output = {
        "baseline": base_metrics,
        "neural_network": nn_metrics,
        "tree_search": tree_search_report,
        "recommended_model": recommended["model_name"],
        "selection_rule": "menor RMSE, desempate por F1 e accuracy para alto risco",
    }

    METRICS_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
