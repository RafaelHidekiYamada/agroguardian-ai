from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from .models import Equipment, Farm, PredictionRecord, AlertRecord, AuditLog, TelemetryRecord, SensorReading


def _safe(value: Any, default: Any = None) -> Any:
    return value if value is not None else default


def _get_time(obj: Any):
    return getattr(obj, "created_at", None) or getattr(obj, "timestamp", None)


def _normalize_label(value: Any) -> str:
    label = str(_safe(value, "")).lower()
    if label.startswith("m"):
        return "medio"
    return label


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

    high_risk = sum(1 for p in predictions if _normalize_label(getattr(p, "risk_label", "")) == "alto")
    medium_risk = sum(1 for p in predictions if _normalize_label(getattr(p, "risk_label", "")) == "medio")
    low_risk = sum(1 for p in predictions if _normalize_label(getattr(p, "risk_label", "")) == "baixo")

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
                "model": getattr(eq, "model", None),
                "year": getattr(eq, "year", None),
                "status": getattr(eq, "status", None),
                "iot_devices": [
                    {
                        "device_id": getattr(device, "device_id", None),
                        "status": getattr(device, "status", None),
                        "last_seen_at": device.last_seen_at.isoformat() if getattr(device, "last_seen_at", None) else None,
                    }
                    for device in getattr(eq, "iot_devices", [])
                ],
            }
        )

    return rows


def _risk_label(score: float) -> str:
    if score <= 40:
        return "Baixo"
    if score <= 70:
        return "Medio"
    return "Alto"


def _history_trend(sorted_scores: list[float]) -> float:
    if len(sorted_scores) < 4:
        return 0.0
    midpoint = len(sorted_scores) // 2
    older = sorted_scores[:midpoint]
    newer = sorted_scores[midpoint:]
    older_avg = sum(older) / len(older)
    newer_avg = sum(newer) / len(newer)
    return round(newer_avg - older_avg, 2)


def _aggregate_score(rows: list[TelemetryRecord]) -> dict:
    if not rows:
        return {
            "risk_score": 0.0,
            "avg_risk_score": 0.0,
            "recent_avg_risk_score": 0.0,
            "max_risk_score": 0.0,
            "high_risk_rate": 0.0,
            "trend_delta": 0.0,
            "risk_label": "Baixo",
        }

    ordered = sorted(rows, key=lambda item: item.timestamp or datetime.min)
    scores = [float(_safe(getattr(row, "predicted_risk", 0), 0)) for row in ordered]
    recent = scores[-10:]
    avg_score = sum(scores) / len(scores)
    recent_avg = sum(recent) / len(recent)
    max_score = max(scores)
    high_rate = sum(1 for score in scores if score >= 70) / len(scores) * 100
    trend_delta = _history_trend(scores)

    risk_score = (
        recent_avg * 0.45
        + avg_score * 0.25
        + high_rate * 0.20
        + max_score * 0.10
        + max(0.0, trend_delta) * 0.10
    )
    risk_score = max(0.0, min(100.0, risk_score))

    return {
        "risk_score": round(risk_score, 2),
        "avg_risk_score": round(avg_score, 2),
        "recent_avg_risk_score": round(recent_avg, 2),
        "max_risk_score": round(max_score, 2),
        "high_risk_rate": round(high_rate, 2),
        "trend_delta": trend_delta,
        "risk_label": _risk_label(risk_score),
    }


def build_region_risk_scores(db: Session) -> list[dict]:
    telemetry = db.query(TelemetryRecord).all()
    farms = db.query(Farm).all()

    by_region: dict[str, list[TelemetryRecord]] = defaultdict(list)
    for row in telemetry:
        by_region[str(getattr(row, "region", "Sem regiao") or "Sem regiao")].append(row)

    farm_by_region: dict[str, list[Farm]] = defaultdict(list)
    for farm in farms:
        farm_by_region[str(getattr(farm, "region", "Sem regiao") or "Sem regiao")].append(farm)

    rows = []
    for region, records in by_region.items():
        aggregate = _aggregate_score(records)
        region_farms = farm_by_region.get(region, [])
        lat_values = [float(f.latitude) for f in region_farms if getattr(f, "latitude", None) is not None]
        lon_values = [float(f.longitude) for f in region_farms if getattr(f, "longitude", None) is not None]

        if not lat_values:
            lat_values = [float(record.latitude) for record in records]
        if not lon_values:
            lon_values = [float(record.longitude) for record in records]

        equipment_ids = {int(record.equipment_id) for record in records if getattr(record, "equipment_id", None) is not None}
        latest = max(records, key=lambda item: item.timestamp or datetime.min)

        rows.append({
            "region": region,
            "risk_score": aggregate["risk_score"],
            "risk_label": aggregate["risk_label"],
            "avg_risk_score": aggregate["avg_risk_score"],
            "recent_avg_risk_score": aggregate["recent_avg_risk_score"],
            "max_risk_score": aggregate["max_risk_score"],
            "high_risk_rate": aggregate["high_risk_rate"],
            "trend_delta": aggregate["trend_delta"],
            "total_records": len(records),
            "equipment_count": len(equipment_ids),
            "farm_count": len(region_farms),
            "latitude": round(sum(lat_values) / len(lat_values), 7) if lat_values else None,
            "longitude": round(sum(lon_values) / len(lon_values), 7) if lon_values else None,
            "latest_timestamp": latest.timestamp.isoformat() if latest.timestamp else None,
        })

    rows.sort(key=lambda item: item["risk_score"], reverse=True)
    return rows


def build_equipment_risk_scores(db: Session) -> list[dict]:
    telemetry = db.query(TelemetryRecord).all()
    equipment_map = {getattr(e, "id", None): e for e in db.query(Equipment).all()}
    farm_map = {getattr(f, "id", None): f for f in db.query(Farm).all()}

    by_equipment: dict[int, list[TelemetryRecord]] = defaultdict(list)
    for row in telemetry:
        if getattr(row, "equipment_id", None) is not None:
            by_equipment[int(row.equipment_id)].append(row)

    rows = []
    for equipment_id, records in by_equipment.items():
        aggregate = _aggregate_score(records)
        latest = max(records, key=lambda item: item.timestamp or datetime.min)
        equip = equipment_map.get(equipment_id)
        farm = farm_map.get(getattr(latest, "farm_id", None))

        rows.append({
            "equipment_id": equipment_id,
            "equipment_name": getattr(equip, "name", None) or f"Equipamento {equipment_id}",
            "equipment_type": getattr(equip, "equipment_type", None),
            "client_name": getattr(equip, "client_name", None),
            "farm_id": getattr(latest, "farm_id", None),
            "farm_name": getattr(farm, "name", None),
            "region": getattr(latest, "region", None),
            "risk_score": aggregate["risk_score"],
            "risk_label": aggregate["risk_label"],
            "avg_risk_score": aggregate["avg_risk_score"],
            "recent_avg_risk_score": aggregate["recent_avg_risk_score"],
            "max_risk_score": aggregate["max_risk_score"],
            "high_risk_rate": aggregate["high_risk_rate"],
            "trend_delta": aggregate["trend_delta"],
            "total_records": len(records),
            "latest_timestamp": latest.timestamp.isoformat() if latest.timestamp else None,
            "latest_latitude": getattr(latest, "latitude", None),
            "latest_longitude": getattr(latest, "longitude", None),
        })

    rows.sort(key=lambda item: item["risk_score"], reverse=True)
    return rows


def build_equipment_risk_history(db: Session, equipment_id: int, limit: int = 100) -> dict:
    records = (
        db.query(TelemetryRecord)
        .filter(TelemetryRecord.equipment_id == equipment_id)
        .order_by(TelemetryRecord.timestamp.desc())
        .limit(limit)
        .all()
    )
    ordered = list(reversed(records))
    aggregate = _aggregate_score(ordered)

    return {
        "equipment_id": equipment_id,
        "score": aggregate,
        "history": [
            {
                "id": row.id,
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                "risk_score": row.predicted_risk,
                "risk_label": row.risk_label,
                "region": row.region,
                "operation_type": row.operation_type,
                "latitude": row.latitude,
                "longitude": row.longitude,
                "clima": row.clima,
                "umidade_solo": row.umidade_solo,
                "inclinacao": row.inclinacao,
                "distancia_agua": row.distancia_agua,
                "velocidade": row.velocidade,
                "chuva_mm": row.chuva_mm,
            }
            for row in ordered
        ],
    }


def list_sensor_readings_data(db: Session, limit: int = 50) -> list[dict]:
    readings = (
        db.query(SensorReading)
        .order_by(SensorReading.timestamp.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": row.id,
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            "device_id": row.device_id,
            "equipment_id": row.equipment_id,
            "farm_id": row.farm_id,
            "latitude": row.latitude,
            "longitude": row.longitude,
            "gps_accuracy_m": row.gps_accuracy_m,
            "gps_satellites": row.gps_satellites,
            "temperatura_c": row.temperatura_c,
            "umidade_ar": row.umidade_ar,
            "pressao_hpa": row.pressao_hpa,
            "umidade_solo": row.umidade_solo,
            "inclinacao": row.inclinacao,
            "distancia_obstaculo": row.distancia_obstaculo,
            "predicted_risk": row.predicted_risk,
            "risk_label": row.risk_label,
        }
        for row in readings
    ]
