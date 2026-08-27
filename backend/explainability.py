from __future__ import annotations

from typing import Any, Dict

from .config import settings


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
    temperatura_c = float(payload.get("temperatura_c", 24) or 24)
    umidade_ar = float(payload.get("umidade_ar", 70) or 70)
    distancia_obstaculo = float(payload.get("distancia_obstaculo", 99) or 99)
    gps_accuracy_m = float(payload.get("gps_accuracy_m", 0) or 0)

    fatores = {
        "Umidade do solo": max(0.0, umidade - 35) * 0.52,
        "Inclinacao": inclinacao * 1.35,
        "Proximidade da agua": max(0.0, 150.0 - distancia_agua) * 0.36,
        "Velocidade": max(0.0, velocidade - 8.0) * 1.22,
        "Historico de sinistros": historico * 2.2,
        "Chuva acumulada": chuva_mm * 1.45,
        "Temperatura ambiente": max(0.0, temperatura_c - 32) * 2.0,
        "Umidade do ar": max(0.0, umidade_ar - 85) * 1.25,
    }

    if clima in {"chuva", "garoa"}:
        fatores["Clima adverso"] = 20.0 + chuva_mm * 0.5
    elif clima in {"tempestade", "thunderstorm"}:
        fatores["Clima adverso"] = 36.0 + chuva_mm * 0.7

    if solo_instavel == 1:
        fatores["Solo instavel"] = 28.0

    if distancia_obstaculo < 3:
        fatores["Obstaculo proximo"] = 30.0 if distancia_obstaculo < 1.5 else 15.0

    if gps_accuracy_m > 15:
        fatores["Precisao GPS"] = min(20.0, gps_accuracy_m * 0.75)

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


def _risk_level_slug(risk_label: str) -> str:
    value = str(risk_label or "").lower()
    if value.startswith("crit"):
        return "critico"
    if value.startswith("alto"):
        return "alto"
    if value.startswith("medio") or value.startswith("m"):
        return "medio"
    return "baixo"


def _add_factor(
    factors: list[dict[str, Any]],
    *,
    factor: str,
    value: Any,
    unit: str,
    impact_points: float,
    explanation: str,
    source: str = "context",
) -> None:
    if value is None or impact_points <= 0:
        return
    factors.append(
        {
            "factor": factor,
            "value": value,
            "unit": unit,
            "impact_points": round(float(impact_points), 2),
            "importance_pct": 0,
            "explanation": explanation,
            "source": source,
        }
    )


def build_structured_explanation(
    *,
    payload: Dict[str, Any],
    risk_score: float,
    risk_label: str,
    recommendation: str,
    risk_components: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    factors: list[dict[str, Any]] = []
    risk_components = risk_components or {}

    humidity_soil = payload.get("umidade_solo")
    rain_mm = payload.get("chuva_mm")
    if humidity_soil is not None:
        _add_factor(
            factors,
            factor="soil_condition",
            value=round(float(humidity_soil), 2),
            unit="%",
            impact_points=max(0.0, (float(humidity_soil) - 60.0) * 0.38 + float(rain_mm or 0) * 0.45),
            explanation="Solo/umidade elevaram o risco porque reduzem aderencia e aumentam chance de atolamento.",
        )

    max_tilt = payload.get("max_tilt_angle", payload.get("inclinacao"))
    if max_tilt is not None:
        tilt = abs(float(max_tilt))
        if tilt >= settings.tilt_extreme_deg:
            tilt_points = 22.0
        elif tilt >= settings.tilt_high_deg:
            tilt_points = 15.0
        elif tilt >= settings.tilt_moderate_deg:
            tilt_points = 7.0
        else:
            tilt_points = 0.0
        _add_factor(
            factors,
            factor="tilt",
            value=round(tilt, 2),
            unit="deg",
            impact_points=tilt_points,
            explanation="Pitch/roll do MPU6050 indicam inclinacao que pode afetar estabilidade do equipamento.",
            source="MPU6050",
        )

    obstacle_cm = payload.get("obstacle_distance_cm")
    if obstacle_cm is None and payload.get("distancia_obstaculo") is not None:
        obstacle_cm = float(payload["distancia_obstaculo"]) * 100.0
    if obstacle_cm is not None:
        distance = float(obstacle_cm)
        if distance <= settings.obstacle_critical_cm:
            impact = 21.0
        elif distance <= settings.obstacle_near_cm:
            impact = 14.0
        elif distance <= settings.obstacle_attention_cm:
            impact = 6.0
        else:
            impact = 0.0
        _add_factor(
            factors,
            factor="obstacle",
            value=round(distance, 2),
            unit="cm",
            impact_points=impact,
            explanation="Sensor de obstaculo indicou distancia que aumenta risco de colisao.",
            source="JSN-SR04T",
        )
    elif payload.get("obstacle_detected") is True:
        _add_factor(
            factors,
            factor="obstacle",
            value=True,
            unit="binary",
            impact_points=8.0,
            explanation="Sensor de obstaculo indicou presenca, mas sem distancia para calibrar severidade.",
            source="JSN-SR04T",
        )

    movement = payload.get("movement_anomaly_score")
    if movement is not None:
        if float(movement) >= 65:
            movement_points = 12.0
        elif float(movement) >= 35:
            movement_points = 6.0
        else:
            movement_points = 0.0
        _add_factor(
            factors,
            factor="movement_anomaly",
            value=round(float(movement), 2),
            unit="score",
            impact_points=movement_points,
            explanation="Magnitude de aceleracao e giroscopio indicam movimento fora do padrao esperado.",
            source="MPU6050",
        )

    if payload.get("possible_impact"):
        _add_factor(
            factors,
            factor="possible_impact",
            value=True,
            unit="boolean",
            impact_points=16.0,
            explanation="A aceleracao ou giro passou do threshold configurado para possivel impacto.",
            source="MPU6050",
        )

    humidity_air = payload.get("umidade_ar")
    if humidity_air is not None:
        _add_factor(
            factors,
            factor="humidity",
            value=round(float(humidity_air), 2),
            unit="%",
            impact_points=5.0 if float(humidity_air) >= settings.high_humidity_pct else 0.0,
            explanation="Umidade alta do BME280 reforca condicao de baixa aderencia e solo saturado.",
            source="BME280",
        )

    temperature = payload.get("temperatura_c")
    if temperature is not None:
        _add_factor(
            factors,
            factor="temperature",
            value=round(float(temperature), 2),
            unit="C",
            impact_points=6.0 if float(temperature) >= settings.high_temperature_c else 0.0,
            explanation="Temperatura elevada aumenta desgaste operacional e reduz margem de seguranca.",
            source="BME280",
        )

    pressure = payload.get("pressao_hpa")
    if pressure is not None and float(pressure) <= 960 and float(payload.get("chuva_mm", 0) or 0) >= 5:
        _add_factor(
            factors,
            factor="pressure",
            value=round(float(pressure), 2),
            unit="hPa",
            impact_points=4.0,
            explanation="Pressao baixa medida pelo BME280 junto com chuva reforca a condicao adversa.",
            source="BME280",
        )

    water_distance = payload.get("distancia_agua")
    if water_distance is not None:
        _add_factor(
            factors,
            factor="water_proximity",
            value=round(float(water_distance), 2),
            unit="m",
            impact_points=max(0.0, (120.0 - float(water_distance)) * 0.14),
            explanation="Proximidade de agua aumenta severidade operacional em caso de perda de controle.",
        )

    speed = payload.get("velocidade")
    if speed is not None:
        _add_factor(
            factors,
            factor="speed",
            value=round(float(speed), 2),
            unit="km/h",
            impact_points=max(0.0, (float(speed) - 12.0) * 0.9),
            explanation="Velocidade acima da faixa conservadora reduz tempo de reacao.",
        )

    freshness = str(payload.get("telemetry_status", "LIVE")).upper()
    if freshness in {"STALE", "OFFLINE"}:
        _add_factor(
            factors,
            factor="telemetry_freshness",
            value=round(float(payload.get("telemetry_age_seconds", 0) or 0), 2),
            unit="s",
            impact_points=5.0 if freshness == "OFFLINE" else 2.0,
            explanation="Telemetria antiga reduz a confianca da decisao em tempo real.",
            source="telemetry",
        )

    factors.sort(key=lambda item: item["impact_points"], reverse=True)
    total_impact = sum(item["impact_points"] for item in factors)
    for item in factors:
        item["importance_pct"] = round((item["impact_points"] / total_impact) * 100, 2) if total_impact else 0

    main_factor = factors[0]["factor"] if factors else None
    if factors:
        summary = (
            f"Risco {_risk_level_slug(risk_label)} porque {factors[0]['factor']} "
            f"e outros sinais operacionais adicionaram pressao ao score."
        )
    else:
        summary = "Risco calculado sem fator dominante entre os dados disponiveis."

    confidence = risk_components.get("confidence")
    confidence_score = round(float(confidence) * 100, 2) if confidence is not None else payload.get("confidence_score")
    expected_after = max(0.0, float(risk_score) - min(35.0, sum(item["impact_points"] for item in factors[:3]) * 0.55))

    return {
        "risk_score": round(float(risk_score), 2),
        "risk_level": _risk_level_slug(risk_label),
        "summary": summary,
        "main_factor": main_factor,
        "factors": factors[:8],
        "recommendation": recommendation,
        "expected_risk_after_action": round(expected_after, 2),
        "confidence_score": confidence_score,
        "telemetry_status": payload.get("telemetry_status"),
        "data_quality_status": payload.get("data_quality_status"),
        "data_quality_issues": payload.get("data_quality_issues", []),
        "missing_sensors": payload.get("missing_sensors", []),
    }
