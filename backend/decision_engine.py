from __future__ import annotations

from typing import Any, Dict, List


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _risk_band(score: float) -> str:
    if score >= 85:
        return "critico"
    if score >= 71:
        return "alto"
    if score >= 41:
        return "medio"
    return "baixo"


def _confidence_label(confidence: float) -> str:
    if confidence >= 0.78:
        return "alta"
    if confidence >= 0.60:
        return "media"
    return "baixa"


def _add_if(condition: bool, items: List[str], text: str) -> None:
    if condition:
        items.append(text)


def _interaction_risk_points(payload: Dict[str, Any], geo_context: Dict[str, Any]) -> Dict[str, Any]:
    points = 0.0
    reasons: List[str] = []

    velocidade = float(payload.get("velocidade", 0) or 0)
    inclinacao = float(payload.get("inclinacao", 0) or 0)
    chuva_mm = float(payload.get("chuva_mm", 0) or 0)
    umidade_solo = float(payload.get("umidade_solo", 0) or 0)
    distancia_agua = float(payload.get("distancia_agua", 999999) or 999999)
    historico_sinistros = float(payload.get("historico_sinistros", 0) or 0)
    solo_instavel = int(payload.get("solo_instavel", 0) or 0)
    operation_type = str(payload.get("operation_type", "campo")).lower()
    clima = str(payload.get("clima", "")).lower()

    geo_risk = geo_context.get("geo_risk", {})
    water_zone = str(geo_risk.get("water_zone", "seguro")).lower()

    if velocidade > 18 and inclinacao >= 12:
        points += 7.0
        reasons.append("velocidade alta combinada com inclinacao elevada")

    if chuva_mm >= 20 and umidade_solo >= 75:
        points += 8.0
        reasons.append("chuva relevante sobre solo muito umido")
    elif chuva_mm >= 10 and umidade_solo >= 65:
        points += 4.0
        reasons.append("chuva moderada com solo ja umido")

    if solo_instavel == 1 and inclinacao >= 10:
        points += 6.0
        reasons.append("solo instavel em terreno inclinado")

    if distancia_agua < 80 and operation_type == "proximidade_agua":
        points += 6.0
        reasons.append("operacao declarada perto de agua")

    if water_zone in {"alto_risco", "atencao"} and chuva_mm >= 8:
        points += 5.0
        reasons.append("zona hidrica sensivel com chuva")

    if historico_sinistros >= 6 and velocidade > 14:
        points += 4.0
        reasons.append("historico de sinistros com velocidade operacional relevante")

    if clima in {"tempestade", "thunderstorm"}:
        points += 5.0
        reasons.append("condicao de tempestade")

    return {
        "points": round(_clamp(points, 0.0, 25.0), 2),
        "reasons": reasons,
    }


def _data_quality(payload: Dict[str, Any], weather: Dict[str, Any], geo_context: Dict[str, Any]) -> Dict[str, Any]:
    issues: List[str] = []

    if weather.get("error") or weather.get("source") == "fallback":
        issues.append("clima externo indisponivel; fallback aplicado")

    if not payload.get("latitude") or not payload.get("longitude"):
        issues.append("coordenadas ausentes ou zeradas")

    manual_distance = payload.get("distancia_agua_manual")
    geo_distance = geo_context.get("nearest_water", {}).get("distance_m")
    if manual_distance is not None and geo_distance is not None:
        try:
            if abs(float(manual_distance) - float(geo_distance)) > 500:
                issues.append("distancia manual da agua diverge bastante da geointeligencia")
        except (TypeError, ValueError):
            issues.append("distancia manual da agua nao numerica")

    confidence_penalty = min(0.25, len(issues) * 0.07)
    return {
        "issues": issues,
        "confidence_penalty": round(confidence_penalty, 2),
    }


def calculate_contextual_risk(
    model_risk_score: float,
    payload: Dict[str, Any],
    geo_context: Dict[str, Any],
    weather: Dict[str, Any],
) -> Dict[str, Any]:
    geo_risk_points = float(geo_context.get("geo_risk", {}).get("geo_risk_points", 0) or 0)
    interaction = _interaction_risk_points(payload, geo_context)
    data_quality = _data_quality(payload, weather, geo_context)

    geo_adjustment = geo_risk_points * 0.55
    interaction_points = float(interaction["points"])
    uncapped_final_score = float(model_risk_score) + geo_adjustment + interaction_points
    final_risk_score = _clamp(uncapped_final_score, 0.0, 100.0)

    threshold_penalty = 0.06 if 37 <= final_risk_score <= 44 or 67 <= final_risk_score <= 74 else 0.0
    weather_bonus = 0.07 if weather.get("source") not in {"fallback", None, ""} and not weather.get("error") else 0.0
    geo_bonus = 0.05 if geo_context.get("nearest_water", {}).get("distance_m") is not None else 0.0
    confidence = 0.74 + weather_bonus + geo_bonus - threshold_penalty - data_quality["confidence_penalty"]
    confidence = _clamp(confidence, 0.45, 0.94)

    return {
        "model_risk_score": round(float(model_risk_score), 2),
        "geo_risk_points": round(geo_risk_points, 2),
        "geo_adjustment_points": round(geo_adjustment, 2),
        "interaction_risk_points": round(interaction_points, 2),
        "interaction_reasons": interaction["reasons"],
        "uncapped_final_score": round(uncapped_final_score, 2),
        "final_risk_score": round(final_risk_score, 2),
        "risk_band": _risk_band(final_risk_score),
        "confidence": round(confidence, 2),
        "confidence_label": _confidence_label(confidence),
        "data_quality": data_quality,
    }


def build_decision_support(
    risk_score: float,
    risk_label: str,
    alert_level: str,
    payload: Dict[str, Any],
    risk_components: Dict[str, Any],
    alerts: List[Dict[str, Any]],
    recommendation: str,
    route: Dict[str, Any],
    explanation: Dict[str, float],
    geo_context: Dict[str, Any],
) -> Dict[str, Any]:
    score = float(risk_score)
    alert_types = {str(alert.get("type", "")) for alert in alerts}
    is_policy_block = "policy_block" in alert_types or "bloqueada" in str(alert_level).lower()

    if is_policy_block or score >= 85:
        decision = "bloquear"
        decision_label = "Bloquear ou pausar a operacao"
        priority = "critica"
    elif score >= 71:
        decision = "replanejar"
        decision_label = "Pausar e replanejar antes de continuar"
        priority = "alta"
    elif score >= 41:
        decision = "operar_com_restricao"
        decision_label = "Operar com restricoes e monitoramento"
        priority = "media"
    else:
        decision = "liberar_monitorado"
        decision_label = "Liberar com monitoramento padrao"
        priority = "baixa"

    top_factors = [
        {"name": name, "impact": impact}
        for name, impact in list(explanation.items())[:4]
    ]

    geo_risk = geo_context.get("geo_risk", {})
    nearest_water = geo_context.get("nearest_water", {})
    actions: List[str] = []
    monitoring: List[str] = []
    escalation: List[str] = []

    _add_if(score >= 71, actions, "interromper a frente de trabalho e validar nova rota antes de retomar")
    _add_if(score >= 41, actions, "reduzir velocidade e manter operador dentro dos limites da politica ativa")
    _add_if(float(payload.get("chuva_mm", 0) or 0) >= 10, actions, "aguardar janela de menor chuva ou dividir a operacao em trechos menores")
    _add_if(float(payload.get("inclinacao", 0) or 0) >= 12, actions, "evitar manobras laterais em declive e priorizar trajetos com menor inclinacao")
    _add_if(float(payload.get("distancia_agua", 999999) or 999999) < 80, actions, "aumentar afastamento de rios, canais e areas alagaveis")
    _add_if(int(payload.get("solo_instavel", 0) or 0) == 1, actions, "validar solo em campo antes de entrada de equipamento pesado")

    if not actions:
        actions.append("manter operacao planejada e registrar nova leitura se o clima mudar")

    monitoring.append("recalcular risco se chuva, velocidade, inclinacao ou coordenadas mudarem")
    monitoring.append("registrar nova telemetria a cada mudanca de talhao ou rota")
    _add_if(
        risk_components.get("confidence_label") != "alta",
        monitoring,
        "confirmar dados de clima e distancia da agua antes de decisao definitiva",
    )

    _add_if(score >= 71, escalation, "acionar gestor da fazenda")
    _add_if(is_policy_block, escalation, "registrar justificativa de bloqueio na auditoria")
    _add_if(score >= 85, escalation, "exigir aprovacao gerencial para qualquer retomada")
    if not escalation:
        escalation.append("sem escalonamento obrigatorio no momento")

    why = (
        f"Score {round(score, 2)} ({risk_label.lower()}) com prioridade {priority}. "
        f"A rota sugerida e {route.get('recommended_route', '-')}, "
        f"score de rota {route.get('route_score', '-')}. "
        f"Zona geografica: {geo_risk.get('geo_zone', '-')}; "
        f"agua mais proxima: {nearest_water.get('distance_m', '-')} m."
    )

    return {
        "decision": decision,
        "decision_label": decision_label,
        "priority": priority,
        "confidence": risk_components.get("confidence"),
        "confidence_label": risk_components.get("confidence_label"),
        "why": why,
        "critical_factors": top_factors,
        "operational_actions": actions,
        "monitoring_plan": monitoring,
        "escalation": escalation,
        "route_decision": {
            "recommended_route": route.get("recommended_route"),
            "route_score": route.get("route_score"),
            "safety_margin": route.get("route_explanation", {}).get("safety_margin"),
            "operator_steps": route.get("route_explanation", {}).get("operator_steps", []),
        },
        "data_quality": risk_components.get("data_quality", {}),
        "recommendation_text": recommendation,
    }
