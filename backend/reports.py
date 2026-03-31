from __future__ import annotations
from typing import Dict
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from .models import TelemetryRecord, Equipment, AlertRecord, PredictionRecord

def summary_report(db: Session) -> Dict:
    total_predictions = db.query(func.count(PredictionRecord.id)).scalar() or 0
    high_risk_count = db.query(func.count(PredictionRecord.id)).filter(PredictionRecord.predicted_risk >= 71).scalar() or 0
    average_risk = db.query(func.avg(PredictionRecord.predicted_risk)).scalar() or 0.0
    alerts_today = db.query(func.count(AlertRecord.id)).scalar() or 0

    top_equipment = []
    equipment_rows = (
        db.query(Equipment.name, func.avg(TelemetryRecord.predicted_risk).label("avg_risk"))
        .join(TelemetryRecord, TelemetryRecord.equipment_id == Equipment.id)
        .group_by(Equipment.name)
        .order_by(desc("avg_risk"))
        .limit(5)
        .all()
    )
    for name, avg_risk in equipment_rows:
        top_equipment.append({"name": name, "risk": round(float(avg_risk), 2)})

    top_regions = []
    region_rows = (
        db.query(TelemetryRecord.region, func.avg(TelemetryRecord.predicted_risk).label("avg_risk"))
        .group_by(TelemetryRecord.region)
        .order_by(desc("avg_risk"))
        .limit(5)
        .all()
    )
    for region, avg_risk in region_rows:
        top_regions.append({"region": region, "risk": round(float(avg_risk), 2)})

    trend_rows = (
        db.query(func.date(TelemetryRecord.timestamp).label("day"), func.avg(TelemetryRecord.predicted_risk).label("avg_risk"))
        .group_by("day")
        .order_by("day")
        .limit(30)
        .all()
    )
    risk_trend = [{"day": str(day), "risk": round(float(avg_risk), 2)} for day, avg_risk in trend_rows]

    return {
        "total_predictions": int(total_predictions),
        "high_risk_count": int(high_risk_count),
        "average_risk": round(float(average_risk), 2),
        "alerts_today": int(alerts_today),
        "top_equipment": top_equipment,
        "top_regions": top_regions,
        "risk_trend": risk_trend,
    }
