from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import (
    ExtraTreesRegressor,
    GradientBoostingRegressor,
    HistGradientBoostingRegressor,
    RandomForestRegressor,
)
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
from sklearn.model_selection import GridSearchCV, train_test_split
from sklearn.inspection import permutation_importance
from sklearn.tree import DecisionTreeRegressor

from backend.risk_model import FEATURES, _synth_dataset


BASE_DIR = Path(__file__).resolve().parent
ARTIFACTS_DIR = BASE_DIR / "saved_models"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

TREE_MODEL_PATH = ARTIFACTS_DIR / "tree_risk_model.joblib"
BEST_MODEL_PATH = ARTIFACTS_DIR / "best_risk_model.joblib"
TREE_METRICS_PATH = ARTIFACTS_DIR / "tree_metrics.json"
PROJECT_METRICS_PATH = BASE_DIR / "model_metrics.json"

HIGH_RISK_THRESHOLD = 70.0


def _classifier_metrics(y_true: pd.Series, y_pred_score: np.ndarray, threshold: float) -> Dict[str, float]:
    y_true_high = (y_true >= HIGH_RISK_THRESHOLD).astype(int)
    y_pred_high = (y_pred_score >= threshold).astype(int)

    metrics = {
        "threshold": round(float(threshold), 2),
        "accuracy": round(float(accuracy_score(y_true_high, y_pred_high)), 4),
        "balanced_accuracy": round(float(balanced_accuracy_score(y_true_high, y_pred_high)), 4),
        "precision": round(float(precision_score(y_true_high, y_pred_high, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true_high, y_pred_high, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true_high, y_pred_high, zero_division=0)), 4),
    }

    try:
        metrics["roc_auc"] = round(float(roc_auc_score(y_true_high, y_pred_score)), 4)
    except ValueError:
        metrics["roc_auc"] = 0.0

    return metrics


def _threshold_curve(y_true: pd.Series, y_pred_score: np.ndarray) -> Tuple[List[Dict[str, float]], Dict[str, float]]:
    curve = []
    for threshold in np.arange(35.0, 86.0, 2.5):
        metrics = _classifier_metrics(y_true, y_pred_score, float(threshold))
        curve.append(metrics)

    best = max(curve, key=lambda row: (row["f1"], row["balanced_accuracy"], row["accuracy"]))
    return curve, best


def _regression_metrics(y_true: pd.Series, y_pred_score: np.ndarray) -> Dict[str, float]:
    return {
        "mae": round(float(mean_absolute_error(y_true, y_pred_score)), 4),
        "rmse": round(float(mean_squared_error(y_true, y_pred_score) ** 0.5), 4),
        "r2": round(float(r2_score(y_true, y_pred_score)), 4),
    }


def _feature_weights(
    model: Any,
    feature_names: List[str],
    X_test: pd.DataFrame,
    y_test: pd.Series,
) -> Dict[str, float]:
    raw_importances = None

    if hasattr(model, "best_estimator_"):
        model = model.best_estimator_

    if hasattr(model, "feature_importances_"):
        raw_importances = getattr(model, "feature_importances_")

    if raw_importances is None:
        permutation = permutation_importance(
            model,
            X_test[feature_names],
            y_test,
            scoring="neg_root_mean_squared_error",
            n_repeats=8,
            random_state=42,
            n_jobs=-1,
        )
        raw_importances = np.maximum(permutation.importances_mean, 0)

    total = float(np.sum(np.abs(raw_importances)))
    if total == 0:
        return {feature: 0.0 for feature in feature_names}

    weights = {
        feature: round(float(abs(value) / total * 100), 2)
        for feature, value in zip(feature_names, raw_importances)
    }
    return dict(sorted(weights.items(), key=lambda item: item[1], reverse=True))


def _candidate_models() -> Dict[str, Tuple[Any, Dict[str, List[Any]]]]:
    return {
        "decision_tree": (
            DecisionTreeRegressor(random_state=42),
            {
                "max_depth": [5, 8, 12, None],
                "min_samples_leaf": [4, 10, 20],
                "min_samples_split": [8, 16],
            },
        ),
        "random_forest": (
            RandomForestRegressor(random_state=42, n_jobs=-1),
            {
                "n_estimators": [180, 320],
                "max_depth": [10, 16, None],
                "min_samples_leaf": [2, 6],
            },
        ),
        "extra_trees": (
            ExtraTreesRegressor(random_state=42, n_jobs=-1),
            {
                "n_estimators": [180, 320],
                "max_depth": [10, 16, None],
                "min_samples_leaf": [2, 6],
            },
        ),
        "gradient_boosting": (
            GradientBoostingRegressor(random_state=42),
            {
                "n_estimators": [160, 260],
                "learning_rate": [0.04, 0.07],
                "max_depth": [3, 4],
                "subsample": [0.85, 1.0],
            },
        ),
        "hist_gradient_boosting": (
            HistGradientBoostingRegressor(random_state=42),
            {
                "max_iter": [180, 260],
                "learning_rate": [0.04, 0.07],
                "max_leaf_nodes": [15, 31],
                "l2_regularization": [0.0, 0.05],
            },
        ),
    }


def train_decision_tree_models(n: int = 7000, seed: int = 42) -> Dict[str, Any]:
    X, y = _synth_dataset(n=n, seed=seed)
    X_train, X_test, y_train, y_test = train_test_split(
        X[FEATURES],
        y,
        test_size=0.22,
        random_state=42,
        stratify=(y >= HIGH_RISK_THRESHOLD).astype(int),
    )

    evaluations = []
    best_bundle = None

    for model_name, (estimator, param_grid) in _candidate_models().items():
        search = GridSearchCV(
            estimator=estimator,
            param_grid=param_grid,
            scoring="neg_root_mean_squared_error",
            cv=3,
            n_jobs=-1,
            refit=True,
        )
        search.fit(X_train, y_train)

        preds = np.clip(search.predict(X_test), 0, 100)
        regression = _regression_metrics(y_test, preds)
        curve, best_curve_point = _threshold_curve(y_test, preds)
        classification = _classifier_metrics(y_test, preds, HIGH_RISK_THRESHOLD)
        weights = _feature_weights(search.best_estimator_, FEATURES, X_test, y_test)

        evaluation = {
            "model_name": model_name,
            "best_params": search.best_params_,
            "regression": regression,
            "classification_at_70": classification,
            "best_curve_point": best_curve_point,
            "feature_weights": weights,
        }
        evaluations.append(evaluation)

        candidate_bundle = {
            "model": search.best_estimator_,
            "model_name": model_name,
            "feature_names": FEATURES,
            "metrics": evaluation,
            "threshold_curve": curve,
            "feature_weights": weights,
            "high_risk_threshold": HIGH_RISK_THRESHOLD,
        }

        if best_bundle is None:
            best_bundle = candidate_bundle
        else:
            current = candidate_bundle["metrics"]
            best = best_bundle["metrics"]
            current_key = (
                current["regression"]["rmse"],
                -current["best_curve_point"]["f1"],
                -current["best_curve_point"]["balanced_accuracy"],
            )
            best_key = (
                best["regression"]["rmse"],
                -best["best_curve_point"]["f1"],
                -best["best_curve_point"]["balanced_accuracy"],
            )
            if current_key < best_key:
                best_bundle = candidate_bundle

    assert best_bundle is not None

    best_model_name = best_bundle["model_name"]
    output = {
        "training": {
            "dataset": "synthetic_operational_risk",
            "n_samples": n,
            "n_train": int(len(X_train)),
            "n_test": int(len(X_test)),
            "high_risk_threshold": HIGH_RISK_THRESHOLD,
            "selection_rule": "menor RMSE, desempate por F1 e balanced accuracy",
        },
        "tree_models": evaluations,
        "recommended_model": best_model_name,
        "best_model": {
            "model_name": best_model_name,
            "best_params": best_bundle["metrics"]["best_params"],
            "regression": best_bundle["metrics"]["regression"],
            "classification_at_70": best_bundle["metrics"]["classification_at_70"],
            "best_curve_point": best_bundle["metrics"]["best_curve_point"],
            "feature_weights": best_bundle["metrics"]["feature_weights"],
            "threshold_curve": best_bundle["threshold_curve"],
        },
    }

    joblib.dump(best_bundle, TREE_MODEL_PATH)
    joblib.dump(best_bundle, BEST_MODEL_PATH)
    TREE_METRICS_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    PROJECT_METRICS_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


if __name__ == "__main__":
    metrics = train_decision_tree_models()
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
