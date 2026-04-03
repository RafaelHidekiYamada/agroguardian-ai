from __future__ import annotations
from typing import Dict, Any


def _normalize_weights(raw: Dict[str, float]) -> Dict[str, float]:
    total = sum(abs(v) for v in raw.values())
    if total == 0:
        return {k: 0.0 for k in raw}
    return {k: round((abs(v) / total) * 100, 2) for k, v in raw.items()}


def heuristic_explanation(payload: Dict[str, Any], risk_score: float) -> Dict[str, float]:
    fatores = {
        "Umidade do solo": float(payload.get("umidade_solo", 0)) * 0.30,
        "Inclinação": float(payload.get("inclinacao", 0)) * 0.20,
        "Proximidade da água": max(0.0, 100.0 - float(payload.get("distancia_agua", 100))) * 0.25,
        "Velocidade": float(payload.get("velocidade", 0)) * 0.15,
        "Histórico de sinistros": float(payload.get("historico_sinistros", 0)) * 0.10,
    }

    if str(payload.get("clima", "")).lower() in {"chuva", "tempestade"}:
        fatores["Clima"] = 30.0

    if int(payload.get("solo_instavel", 0)) == 1:
        fatores["Solo instável"] = 25.0

    explicacao = _normalize_weights(fatores)
    explicacao_ordenada = dict(
        sorted(explicacao.items(), key=lambda item: item[1], reverse=True)
    )
    return explicacao_ordenada


def shap_explanation(model, X_background, X_current, feature_names):
    """
    Mantém compatibilidade com o projeto.
    Se SHAP real não estiver configurado, retorna dicionário vazio
    e o sistema usa a explicação heurística.
    """
    try:
        return {}
    except Exception:
        return {}


def build_executive_explanation(
    risk_score: float,
    risk_label: str,
    explanation: Dict[str, float],
    recommendation: str,
) -> Dict[str, Any]:
    top_factors = list(explanation.items())[:3]

    if risk_score >= 71:
        summary = (
            f"O equipamento está em nível de risco {risk_label.lower()}, "
            f"com score {round(risk_score, 2)}. "
            f"Os fatores mais relevantes foram: "
            + ", ".join([f"{name} ({value}%)" for name, value in top_factors])
            + "."
        )
    elif risk_score >= 41:
        summary = (
            f"O equipamento está em nível de risco {risk_label.lower()}, "
            f"com atenção preventiva recomendada. "
            f"Os fatores principais foram: "
            + ", ".join([f"{name} ({value}%)" for name, value in top_factors])
            + "."
        )
    else:
        summary = (
            f"O equipamento está em nível de risco {risk_label.lower()}, "
            f"com operação liberada sob monitoramento. "
            f"Os fatores mais perceptíveis foram: "
            + ", ".join([f"{name} ({value}%)" for name, value in top_factors])
            + "."
        )

    return {
        "summary": summary,
        "top_factors": [{"name": name, "impact": value} for name, value in top_factors],
        "recommendation": recommendation,
    }