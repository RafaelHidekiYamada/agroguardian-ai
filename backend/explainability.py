from __future__ import annotations
from typing import Dict, Any, List
import numpy as np

FEATURE_ORDER = [
    "umidade_solo",
    "inclinacao",
    "distancia_agua",
    "velocidade",
    "historico_sinistros",
    "chuva_mm",
    "solo_instavel",
    "clima_code",
    "operation_code",
]

def heuristic_explanation(payload: Dict, risk_score: float) -> Dict[str, float]:
    raw = {
        "Solo úmido": payload["umidade_solo"] * 0.30,
        "Inclinação": payload["inclinacao"] * 0.18,
        "Proximidade de água": max(0, 100 - payload["distancia_agua"]) * 0.25,
        "Velocidade": payload["velocidade"] * 0.14,
        "Histórico de sinistros": payload["historico_sinistros"] * 0.22,
        "Chuva": payload["chuva_mm"] * 0.10,
        "Solo instável": payload["solo_instavel"] * 18.0,
    }
    total = sum(raw.values()) or 1.0
    return {k: round((v / total) * 100, 1) for k, v in sorted(raw.items(), key=lambda item: item[1], reverse=True)}

def shap_explanation(model, background_features: np.ndarray, one_row: np.ndarray, feature_names: List[str]) -> Dict[str, float]:
    try:
        import shap  # type: ignore
        explainer = shap.Explainer(model, background_features, feature_names=feature_names)
        shap_values = explainer(one_row)
        vals = np.abs(shap_values.values[0])
        total = float(vals.sum()) or 1.0
        return {
            feature_names[i]: round(float(vals[i] / total) * 100, 1)
            for i in range(len(feature_names))
        }
    except Exception:
        return {}
