from __future__ import annotations
from typing import Dict, List

def build_alerts(risk_score: float, payload: Dict) -> List[Dict]:
    alerts = []

    if risk_score >= 71:
        alerts.append({
            "type": "alto_risco",
            "severity": "high",
            "message": "Alto risco operacional. Considere interromper a operação.",
        })

    if payload["distancia_agua"] < 30:
        alerts.append({
            "type": "proximidade_agua",
            "severity": "high" if payload["distancia_agua"] < 15 else "medium",
            "message": "Operação próxima de água. Reavaliar rota e bordas da área.",
        })

    if payload["umidade_solo"] >= 75:
        alerts.append({
            "type": "atolamento",
            "severity": "high",
            "message": "Solo úmido aumenta a chance de atolamento.",
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
            "message": "Inclinação elevada. Reduzir velocidade e revisar trajeto.",
        })

    if payload["clima"].lower() in {"chuva", "tempestade", "garoa"}:
        alerts.append({
            "type": "clima_adverso",
            "severity": "medium",
            "message": "Condição climática adversa. Recomendado adiar ou revisar operação.",
        })

    if not alerts:
        alerts.append({
            "type": "operacao_segura",
            "severity": "low",
            "message": "Condição operacional aceitável no momento.",
        })

    return alerts

def alert_summary(alerts: List[Dict]) -> str:
    strongest = "low"
    if any(a["severity"] == "high" for a in alerts):
        strongest = "high"
    elif any(a["severity"] == "medium" for a in alerts):
        strongest = "medium"

    if strongest == "high":
        return "🔴 Alto risco"
    if strongest == "medium":
        return "🟡 Atenção"
    return "🟢 Baixo risco"
