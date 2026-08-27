from __future__ import annotations

from typing import Dict, List

from .config import settings


def build_alerts(risk_score: float, payload: Dict) -> List[Dict]:
    alerts = []

    if risk_score >= 71:
        alerts.append({
            "type": "alto_risco",
            "severity": "high",
            "message": "Alto risco operacional. Considere interromper a operacao.",
        })

    if payload["distancia_agua"] < 30:
        alerts.append({
            "type": "proximidade_agua",
            "severity": "high" if payload["distancia_agua"] < 15 else "medium",
            "message": "Operacao proxima de agua. Reavaliar rota e bordas da area.",
        })

    if payload["umidade_solo"] >= 75:
        alerts.append({
            "type": "atolamento",
            "severity": "high",
            "message": "Solo umido aumenta a chance de atolamento.",
        })

    if payload["velocidade"] > 18:
        alerts.append({
            "type": "velocidade_insegura",
            "severity": "medium",
            "message": "Velocidade acima do recomendado para este contexto.",
        })

    if payload["inclinacao"] >= 12:
        alerts.append({
            "type": "terreno_inclinado",
            "severity": "medium",
            "message": "Inclinacao elevada. Reduzir velocidade e revisar trajeto.",
        })

    if payload["clima"].lower() in {"chuva", "tempestade", "garoa"}:
        alerts.append({
            "type": "clima_adverso",
            "severity": "medium",
            "message": "Condicao climatica adversa. Recomendado adiar ou revisar operacao.",
        })

    distancia_obstaculo = payload.get("distancia_obstaculo")
    obstacle_distance_cm = payload.get("obstacle_distance_cm")
    obstacle_detected = payload.get("obstacle_detected")
    obstacle_cm = None
    try:
        if obstacle_distance_cm is not None:
            obstacle_cm = float(obstacle_distance_cm)
        elif distancia_obstaculo is not None:
            obstacle_cm = float(distancia_obstaculo) * 100.0
    except (TypeError, ValueError):
        obstacle_cm = None

    if obstacle_cm is not None and obstacle_cm <= settings.obstacle_critical_cm:
        alerts.append({
            "type": "OBSTACLE_CRITICAL",
            "severity": "high",
            "message": "Obstaculo em distancia critica. Pare o equipamento e libere a faixa.",
        })
    elif obstacle_cm is not None and obstacle_cm <= settings.obstacle_attention_cm:
        alerts.append({
            "type": "obstaculo_proximo",
            "severity": "high" if obstacle_cm <= settings.obstacle_near_cm else "medium",
            "message": "Obstaculo proximo detectado pelo ESP. Pare e confirme a faixa de deslocamento.",
        })
    elif obstacle_detected is True:
        alerts.append({
            "type": "OBSTACLE_CRITICAL",
            "severity": "medium",
            "message": "Sensor indicou obstaculo, mas nao enviou distancia. Verificar faixa antes de seguir.",
        })

    try:
        max_tilt = float(payload.get("max_tilt_angle", payload.get("inclinacao", 0)) or 0)
        if max_tilt >= settings.tilt_extreme_deg:
            alerts.append({
                "type": "EXCESSIVE_TILT",
                "severity": "high",
                "message": "Inclinacao extrema detectada pelo MPU6050. Risco de instabilidade ou tombamento.",
            })
        elif max_tilt >= settings.tilt_high_deg:
            alerts.append({
                "type": "EXCESSIVE_TILT",
                "severity": "medium",
                "message": "Inclinacao elevada detectada pelo MPU6050. Reduzir velocidade e reposicionar.",
            })
    except (TypeError, ValueError):
        pass

    try:
        movement = float(payload.get("movement_anomaly_score") or 0)
        if movement >= 65:
            alerts.append({
                "type": "ABNORMAL_MOVEMENT",
                "severity": "high",
                "message": "Movimento anormal relevante detectado pelo MPU6050.",
            })
        elif movement >= 35:
            alerts.append({
                "type": "ABNORMAL_MOVEMENT",
                "severity": "medium",
                "message": "Movimento acima do padrao operacional esperado.",
            })
    except (TypeError, ValueError):
        pass

    if bool(payload.get("possible_impact", False)):
        alerts.append({
            "type": "POSSIBLE_IMPACT",
            "severity": "high",
            "message": "Possivel impacto detectado por aceleracao ou giro anormal.",
        })

    try:
        temperature = payload.get("temperatura_c")
        if temperature is not None and float(temperature) >= settings.high_temperature_c:
            alerts.append({
                "type": "HIGH_TEMPERATURE",
                "severity": "medium",
                "message": "Temperatura ambiente elevada no entorno do equipamento.",
            })
    except (TypeError, ValueError):
        pass

    try:
        humidity = payload.get("umidade_ar")
        if humidity is not None and float(humidity) >= settings.high_humidity_pct:
            alerts.append({
                "type": "HIGH_HUMIDITY",
                "severity": "medium",
                "message": "Umidade do ar elevada, com potencial de baixa aderencia e solo saturado.",
            })
    except (TypeError, ValueError):
        pass

    telemetry_status = str(payload.get("telemetry_status", "LIVE")).upper()
    if telemetry_status == "OFFLINE":
        alerts.append({
            "type": "DEVICE_OFFLINE",
            "severity": "high",
            "message": "Dispositivo sem telemetria recente.",
        })
    elif telemetry_status == "STALE":
        alerts.append({
            "type": "DEVICE_OFFLINE",
            "severity": "medium",
            "message": "Telemetria do equipamento esta desatualizada.",
        })

    data_quality_status = str(payload.get("data_quality_status", "VALID")).upper()
    if data_quality_status in {"PARTIAL", "SUSPECT", "INVALID"}:
        alerts.append({
            "type": "SENSOR_FAILURE",
            "severity": "high" if data_quality_status == "INVALID" else "medium",
            "message": f"Qualidade da telemetria {data_quality_status.lower()}. Verificar sensores antes de decisao critica.",
        })

    gps_accuracy_m = payload.get("gps_accuracy_m")
    if gps_accuracy_m is not None and float(gps_accuracy_m) > 15:
        alerts.append({
            "type": "gps_baixa_precisao",
            "severity": "medium",
            "message": "Precisao GPS insuficiente para decisao fina de borda, agua ou rota.",
        })

    if not alerts:
        alerts.append({
            "type": "operacao_segura",
            "severity": "low",
            "message": "Condicao operacional aceitavel no momento.",
        })

    return alerts


def alert_summary(alerts: List[Dict]) -> str:
    strongest = "low"
    if any(a["severity"] == "high" for a in alerts):
        strongest = "high"
    elif any(a["severity"] == "medium" for a in alerts):
        strongest = "medium"

    if strongest == "high":
        return "Alto risco"
    if strongest == "medium":
        return "Atencao"
    return "Baixo risco"
