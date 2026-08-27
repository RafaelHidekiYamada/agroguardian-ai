from __future__ import annotations

from typing import Any, Dict, List

from .config import settings


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


def _sensor_risk_points(payload: Dict[str, Any]) -> Dict[str, Any]:
    points = 0.0
    reasons: List[str] = []

    temperatura_c = payload.get("temperatura_c")
    umidade_ar = payload.get("umidade_ar")
    pressao_hpa = payload.get("pressao_hpa")
    distancia_obstaculo = payload.get("distancia_obstaculo")
    obstacle_detected = payload.get("obstacle_detected")
    obstacle_distance_cm = payload.get("obstacle_distance_cm")
    gps_accuracy_m = payload.get("gps_accuracy_m")
    max_tilt_angle = payload.get("max_tilt_angle", payload.get("inclinacao"))
    movement_anomaly_score = payload.get("movement_anomaly_score")
    possible_impact = bool(payload.get("possible_impact", False))
    telemetry_status = str(payload.get("telemetry_status", "LIVE")).upper()
    chuva_mm = float(payload.get("chuva_mm", 0) or 0)

    try:
        if temperatura_c is not None and float(temperatura_c) >= settings.high_temperature_c:
            points += 6.0
            reasons.append("temperatura elevada no entorno do equipamento")
    except (TypeError, ValueError):
        pass

    try:
        if umidade_ar is not None and float(umidade_ar) >= settings.high_humidity_pct:
            points += 5.0
            reasons.append("umidade do ar muito alta")
    except (TypeError, ValueError):
        pass

    try:
        if pressao_hpa is not None and float(pressao_hpa) <= 960 and chuva_mm >= 5:
            points += 4.0
            reasons.append("baixa pressao com chuva registrada")
    except (TypeError, ValueError):
        pass

    obstacle_cm = None
    try:
        if obstacle_distance_cm is not None:
            obstacle_cm = float(obstacle_distance_cm)
        elif distancia_obstaculo is not None:
            obstacle_cm = float(distancia_obstaculo) * 100.0
    except (TypeError, ValueError):
        obstacle_cm = None

    if obstacle_cm is not None:
        if obstacle_cm <= settings.obstacle_critical_cm:
            points += 18.0
            reasons.append("obstaculo em distancia critica")
        elif obstacle_cm <= settings.obstacle_near_cm:
            points += 12.0
            reasons.append("obstaculo proximo do equipamento")
        elif obstacle_cm <= settings.obstacle_attention_cm:
            points += 5.0
            reasons.append("obstaculo na faixa de atencao")
    elif obstacle_detected is True:
        points += 8.0
        reasons.append("sensor indicou obstaculo sem distancia medida")

    try:
        if max_tilt_angle is not None:
            tilt = abs(float(max_tilt_angle))
            if tilt >= settings.tilt_extreme_deg:
                points += 22.0
                reasons.append("inclinacao extrema detectada pelo MPU6050")
            elif tilt >= settings.tilt_high_deg:
                points += 15.0
                reasons.append("inclinacao elevada detectada pelo MPU6050")
            elif tilt >= settings.tilt_moderate_deg:
                points += 7.0
                reasons.append("inclinacao moderada detectada pelo MPU6050")
    except (TypeError, ValueError):
        pass

    try:
        if movement_anomaly_score is not None and float(movement_anomaly_score) >= 65:
            points += 12.0
            reasons.append("movimento anormal relevante detectado pelo MPU6050")
        elif movement_anomaly_score is not None and float(movement_anomaly_score) >= 35:
            points += 6.0
            reasons.append("movimento acima do comportamento operacional esperado")
    except (TypeError, ValueError):
        pass

    if possible_impact:
        points += 16.0
        reasons.append("possivel impacto detectado por aceleracao ou giro")

    if telemetry_status == "STALE":
        reasons.append("telemetria do equipamento esta desatualizada")
    elif telemetry_status == "OFFLINE":
        points += 4.0
        reasons.append("equipamento sem telemetria recente")

    try:
        if gps_accuracy_m is not None and float(gps_accuracy_m) > 20:
            points += 2.0
            reasons.append("precisao GPS baixa para decisao fina de rota")
    except (TypeError, ValueError):
        pass

    return {
        "points": round(_clamp(points, 0.0, 38.0), 2),
        "reasons": reasons,
    }


def _data_quality(payload: Dict[str, Any], weather: Dict[str, Any], geo_context: Dict[str, Any]) -> Dict[str, Any]:
    issues: List[str] = []

    if weather.get("error") or weather.get("source") == "fallback":
        issues.append("clima externo indisponivel; fallback aplicado")

    telemetry_status = str(payload.get("telemetry_status", "LIVE")).upper()
    if telemetry_status == "STALE":
        issues.append("telemetria do equipamento esta desatualizada")
    elif telemetry_status == "OFFLINE":
        issues.append("telemetria do equipamento esta offline")

    data_quality_status = str(payload.get("data_quality_status", "VALID")).upper()
    if data_quality_status in {"PARTIAL", "SUSPECT", "INVALID"}:
        issues.append(f"qualidade da telemetria {data_quality_status.lower()}")

    missing_sensors = payload.get("missing_sensors") or []
    for sensor_name in missing_sensors:
        issues.append(f"sensor ausente: {sensor_name}")

    if not payload.get("latitude") or not payload.get("longitude"):
        issues.append("coordenadas ausentes ou zeradas")

    try:
        gps_accuracy = payload.get("gps_accuracy_m")
        if gps_accuracy is not None and float(gps_accuracy) > 15:
            issues.append("precisao GPS acima de 15 m")
    except (TypeError, ValueError):
        issues.append("precisao GPS nao numerica")

    if geo_context.get("nearest_water", {}).get("source") == "fallback_static_water_points":
        issues.append("geointeligencia usando fallback local; OSM indisponivel")

    manual_distance = payload.get("distancia_agua_manual")
    geo_distance = geo_context.get("nearest_water", {}).get("distance_m")
    if manual_distance is not None and geo_distance is not None:
        try:
            if abs(float(manual_distance) - float(geo_distance)) > 500:
                issues.append("distancia manual da agua diverge bastante da geointeligencia")
        except (TypeError, ValueError):
            issues.append("distancia manual da agua nao numerica")

    confidence_penalty = min(0.45, len(issues) * 0.07)
    return {
        "issues": issues,
        "status": data_quality_status,
        "telemetry_status": telemetry_status,
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
    sensor = _sensor_risk_points(payload)
    data_quality = _data_quality(payload, weather, geo_context)

    geo_adjustment = geo_risk_points * 0.55
    interaction_points = float(interaction["points"])
    sensor_points = float(sensor["points"])
    uncapped_final_score = float(model_risk_score) + geo_adjustment + interaction_points + sensor_points
    final_risk_score = _clamp(uncapped_final_score, 0.0, 100.0)

    threshold_penalty = 0.06 if 37 <= final_risk_score <= 44 or 67 <= final_risk_score <= 74 else 0.0
    weather_bonus = 0.07 if weather.get("source") not in {"fallback", None, ""} and not weather.get("error") else 0.0
    geo_bonus = 0.05 if geo_context.get("nearest_water", {}).get("distance_m") is not None else 0.0
    confidence = 0.74 + weather_bonus + geo_bonus - threshold_penalty - data_quality["confidence_penalty"]
    if payload.get("confidence_score") is not None:
        try:
            confidence = min(confidence, float(payload["confidence_score"]) / 100.0)
        except (TypeError, ValueError):
            pass
    confidence = _clamp(confidence, 0.45, 0.94)

    return {
        "model_risk_score": round(float(model_risk_score), 2),
        "geo_risk_points": round(geo_risk_points, 2),
        "geo_adjustment_points": round(geo_adjustment, 2),
        "interaction_risk_points": round(interaction_points, 2),
        "interaction_reasons": interaction["reasons"],
        "sensor_risk_points": round(sensor_points, 2),
        "sensor_reasons": sensor["reasons"],
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
    _add_if(float(payload.get("distancia_obstaculo", 999999) or 999999) < 3, actions, "parar e liberar faixa de deslocamento antes de seguir")
    _add_if(float(payload.get("gps_accuracy_m", 0) or 0) > 15, actions, "aguardar melhor fix GPS ou confirmar posicao manualmente")

    if not actions:
        actions.append("manter operacao planejada e registrar nova leitura se o clima mudar")

    monitoring.append("recalcular risco se chuva, velocidade, inclinacao ou coordenadas mudarem")
    monitoring.append("registrar nova telemetria a cada mudanca de talhao ou rota")
    monitoring.append("acompanhar obstaculo, temperatura, umidade, pressao e precisao GPS do ESP")
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
