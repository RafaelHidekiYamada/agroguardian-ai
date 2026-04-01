from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from .models import Equipment, Farm, PredictionRecord, AlertRecord, AuditLog


def _safe(value: Any, default: Any = None) -> Any:
    return value if value is not None else default


def _get_time(obj: Any):
    return getattr(obj, "created_at", None) or getattr(obj, "timestamp", None)


def build_summary(db: Session) -> dict:
    predictions = db.query(PredictionRecord).all()
    equipment = db.query(Equipment).all()
    farms = db.query(Farm).all()

    total_predictions = len(predictions)
    total_equipment = len(equipment)
    total_farms = len(farms)

    if total_predictions == 0:
        return {
            "total_predictions": 0,
            "avg_risk_score": 0,
            "high_risk_predictions": 0,
            "medium_risk_predictions": 0,
            "low_risk_predictions": 0,
            "total_equipment": total_equipment,
            "total_farms": total_farms,
            "most_common_operation_type": None,
            "top_region": None,
        }

    risk_scores = [float(_safe(getattr(p, "predicted_risk", 0), 0)) for p in predictions]
    avg_risk_score = round(sum(risk_scores) / len(risk_scores), 2)

    high_risk = sum(1 for p in predictions if str(_safe(getattr(p, "risk_label", ""))).lower() == "alto")
    medium_risk = sum(1 for p in predictions if str(_safe(getattr(p, "risk_label", ""))).lower() == "médio")
    low_risk = sum(1 for p in predictions if str(_safe(getattr(p, "risk_label", ""))).lower() == "baixo")

    operation_counter = Counter()
    region_counter = Counter()

    for p in predictions:
        payload = _safe(getattr(p, "input_payload", {}), {})
        if isinstance(payload, dict):
            operation = payload.get("operation_type")
            region = payload.get("region")
            if operation:
                operation_counter[str(operation)] += 1
            if region:
                region_counter[str(region)] += 1

    return {
        "total_predictions": total_predictions,
        "avg_risk_score": avg_risk_score,
        "high_risk_predictions": high_risk,
        "medium_risk_predictions": medium_risk,
        "low_risk_predictions": low_risk,
        "total_equipment": total_equipment,
        "total_farms": total_farms,
        "most_common_operation_type": operation_counter.most_common(1)[0][0] if operation_counter else None,
        "top_region": region_counter.most_common(1)[0][0] if region_counter else None,
    }


def build_ranking(db: Session) -> list[dict]:
    predictions = db.query(PredictionRecord).all()
    equipment_map = {getattr(e, "id", None): e for e in db.query(Equipment).all()}

    grouped: dict[int, list[PredictionRecord]] = defaultdict(list)

    for p in predictions:
        payload = _safe(getattr(p, "input_payload", {}), {})
        if isinstance(payload, dict):
            equipment_id = payload.get("equipment_id")
            if equipment_id is not None:
                grouped[int(equipment_id)].append(p)

    ranking = []
    for equipment_id, rows in grouped.items():
        scores = [float(_safe(getattr(r, "predicted_risk", 0), 0)) for r in rows]
        avg_score = round(sum(scores) / len(scores), 2) if scores else 0

        equip = equipment_map.get(equipment_id)
        equipment_name = getattr(equip, "name", None) or f"Equipamento {equipment_id}"
        equipment_type = getattr(equip, "equipment_type", None) or getattr(equip, "type", None)

        ranking.append(
            {
                "equipment_id": equipment_id,
                "equipment_name": equipment_name,
                "equipment_type": equipment_type,
                "avg_risk_score": avg_score,
                "total_predictions": len(rows),
                "latest_risk_label": getattr(rows[-1], "risk_label", None),
            }
        )

    ranking.sort(key=lambda x: x["avg_risk_score"], reverse=True)
    return ranking


def build_trends(db: Session) -> list[dict]:
    predictions = db.query(PredictionRecord).all()

    by_day: dict[str, list[float]] = defaultdict(list)
    for p in predictions:
        ts = _get_time(p)
        if isinstance(ts, datetime):
            day = ts.strftime("%Y-%m-%d")
        else:
            day = "sem_data"

        by_day[day].append(float(_safe(getattr(p, "predicted_risk", 0), 0)))

    trend_rows = []
    for day, values in sorted(by_day.items()):
        avg_value = round(sum(values) / len(values), 2) if values else 0
        trend_rows.append(
            {
                "date": day,
                "avg_risk": avg_value,
                "total_predictions": len(values),
            }
        )

    return trend_rows


def build_alerts(db: Session) -> list[dict]:
    alerts = db.query(AlertRecord).all()

    rows = []
    for a in alerts:
        rows.append(
            {
                "alert_id": getattr(a, "id", None),
                "timestamp": _get_time(a),
                "type": getattr(a, "alert_type", None),
                "severity": getattr(a, "severity", None),
                "message": getattr(a, "message", None),
                "context": getattr(a, "context", None),
            }
        )

    rows.sort(key=lambda x: x["timestamp"] or datetime.min, reverse=True)
    return rows[:20]


def build_audit(db: Session) -> list[dict]:
    logs = db.query(AuditLog).all()

    rows = []
    for log in logs:
        rows.append(
            {
                "audit_id": getattr(log, "id", None),
                "timestamp": _get_time(log),
                "actor": getattr(log, "actor", None),
                "action": getattr(log, "action", None),
                "payload": getattr(log, "payload", None),
            }
        )

    rows.sort(key=lambda x: x["timestamp"] or datetime.min, reverse=True)
    return rows[:50]


def list_farms_data(db: Session) -> list[dict]:
    farms = db.query(Farm).all()
    rows = []

    for farm in farms:
        rows.append(
            {
                "farm_id": getattr(farm, "id", None),
                "farm_name": getattr(farm, "name", None),
                "region": getattr(farm, "region", None),
                "latitude": getattr(farm, "latitude", None),
                "longitude": getattr(farm, "longitude", None),
            }
        )

    return rows


def list_equipment_data(db: Session) -> list[dict]:
    equipment = db.query(Equipment).all()
    rows = []

    for eq in equipment:
        rows.append(
            {
                "equipment_id": getattr(eq, "id", None),
                "equipment_name": getattr(eq, "name", None),
                "equipment_type": getattr(eq, "equipment_type", None) or getattr(eq, "type", None),
                "client_name": getattr(eq, "client_name", None),
                "farm_id": getattr(eq, "farm_id", None),
            }
        )

    return rows