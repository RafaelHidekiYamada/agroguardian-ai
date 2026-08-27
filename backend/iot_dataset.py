"""Safe telemetry exports for future supervised-model training."""

from __future__ import annotations

import csv
from pathlib import Path

from sqlalchemy.orm import Session

from . import models


def export_equipment_telemetry_dataset(
    db: Session,
    equipment_id: int,
    output_path: str | Path | None = None,
) -> Path:
    """Export physical features and labels without raw payloads or API secrets."""
    destination = Path(output_path or f"data_science_r/data/equipment_{equipment_id}_telemetry.csv")
    destination.parent.mkdir(parents=True, exist_ok=True)
    rows = (
        db.query(models.IotTelemetry)
        .filter(models.IotTelemetry.equipment_id == equipment_id)
        .order_by(models.IotTelemetry.recorded_at, models.IotTelemetry.id)
        .all()
    )
    fieldnames = [
        "telemetry_id",
        "equipment_id",
        "recorded_at",
        "temperature_c",
        "humidity_pct",
        "pressure_hpa",
        "distance_cm",
        "accel_x",
        "accel_y",
        "accel_z",
        "acceleration_magnitude",
        "inclination_deg",
        "movement_anomaly_score",
        "possible_impact",
        "telemetry_status",
        "data_quality_status",
        "confidence_score",
        "risk_score",
        "risk_level",
    ]
    with destination.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "telemetry_id": row.id,
                    "equipment_id": row.equipment_id,
                    "recorded_at": (row.recorded_at or row.timestamp).isoformat()
                    if (row.recorded_at or row.timestamp)
                    else None,
                    "temperature_c": row.temperature_c,
                    "humidity_pct": row.humidity_pct,
                    "pressure_hpa": row.pressure_hpa,
                    "distance_cm": row.distance_cm if row.distance_cm is not None else row.obstacle_distance_cm,
                    "accel_x": row.accel_x,
                    "accel_y": row.accel_y,
                    "accel_z": row.accel_z,
                    "acceleration_magnitude": row.acceleration_magnitude,
                    "inclination_deg": row.inclination_deg if row.inclination_deg is not None else row.max_tilt_angle,
                    "movement_anomaly_score": row.movement_anomaly_score,
                    "possible_impact": row.possible_impact,
                    "telemetry_status": row.telemetry_status,
                    "data_quality_status": row.data_quality_status,
                    "confidence_score": row.confidence_score,
                    "risk_score": row.risk_score,
                    "risk_level": row.risk_level,
                }
            )
    return destination
