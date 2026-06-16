from __future__ import annotations

from typing import Any, Dict


def _normalize_weights(raw: Dict[str, float]) -> Dict[str, float]:
    total = sum(abs(v) for v in raw.values())
    if total == 0:
        return {k: 0.0 for k in raw}
    return {k: round((abs(v) / total) * 100, 2) for k, v in raw.items()}


def heuristic_explanation(payload: Dict[str, Any], risk_score: float) -> Dict[str, float]:
    distancia_agua = float(payload.get("distancia_agua", 1000) or 1000)
    chuva_mm = float(payload.get("chuva_mm", 0) or 0)
    velocidade = float(payload.get("velocidade", 0) or 0)
    inclinacao = float(payload.get("inclinacao", 0) or 0)
    umidade = float(payload.get("umidade_solo", 0) or 0)
    historico = float(payload.get("historico_sinistros", 0) or 0)
    solo_instavel = int(payload.get("solo_instavel", 0) or 0)
    clima = str(payload.get("clima", "")).lower()
    operation_type = str(payload.get("operation_type", "")).lower()

    fatores = {
        "Umidade do solo": max(0.0, umidade - 35) * 0.52,
        "Inclinacao": inclinacao * 1.35,
        "Proximidade da agua": max(0.0, 150.0 - distancia_agua) * 0.36,
        "Velocidade": max(0.0, velocidade - 8.0) * 1.22,
        "Historico de sinistros": historico * 2.2,
        "Chuva acumulada": chuva_mm * 1.45,
    }

    if clima in {"chuva", "garoa"}:
        fatores["Clima adverso"] = 20.0 + chuva_mm * 0.5
    elif clima in {"tempestade", "thunderstorm"}:
        fatores["Clima adverso"] = 36.0 + chuva_mm * 0.7

    if solo_instavel == 1:
        fatores["Solo instavel"] = 28.0

    if operation_type == "proximidade_agua":
        fatores["Tipo de operacao"] = 18.0
    elif operation_type == "transporte" and velocidade > 14:
        fatores["Tipo de operacao"] = 12.0

    if risk_score >= 71:
        fatores["Pressao operacional total"] = risk_score * 0.16

    explicacao = _normalize_weights(fatores)
    return dict(sorted(explicacao.items(), key=lambda item: item[1], reverse=True))


def shap_explanation(model, X_background, X_current, feature_names):
    """
    Compatibility hook.
    If SHAP is installed in the future, this function can return SHAP values.
    The project currently uses deterministic heuristic explanations.
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
    decision_support: Dict[str, Any] | None = None,
    safe_route: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    top_factors = list(explanation.items())[:3]
    factor_text = ", ".join([f"{name} ({value}%)" for name, value in top_factors]) or "sem fator dominante"

    if decision_support:
        decision = decision_support.get("decision_label", "Decisao operacional pendente")
        confidence_label = decision_support.get("confidence_label", "-")
        priority = decision_support.get("priority", "-")
    else:
        decision = "Operar conforme recomendacao"
        confidence_label = "-"
        priority = "media" if risk_score >= 41 else "baixa"

    route_name = "-"
    route_reason = ""
    if safe_route:
        route_name = safe_route.get("recommended_route", "-")
        route_reason = safe_route.get("route_explanation", {}).get("why_selected", "")

    summary = (
        f"Decisao: {decision}. Score {round(risk_score, 2)} ({risk_label.lower()}), "
        f"prioridade {priority}, confianca {confidence_label}. "
        f"Fatores principais: {factor_text}. Rota sugerida: {route_name}."
    )

    next_actions = []
    if decision_support:
        next_actions = decision_support.get("operational_actions", [])[:4]
    if not next_actions:
        next_actions = [recommendation]

    return {
        "summary": summary,
        "decision": decision,
        "confidence_label": confidence_label,
        "priority": priority,
        "top_factors": [{"name": name, "impact": value} for name, value in top_factors],
        "route_summary": route_reason,
        "next_actions": next_actions,
        "recommendation": recommendation,
    }
