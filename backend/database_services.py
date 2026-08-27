"""Transactional write services for normalized database workflows."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.orm import Session

from . import models
from .database_schemas import AlertCreate, RecommendationCreate, RiskPredictionCreate


def create_risk_prediction_bundle(
    db: Session,
    *,
    prediction_data: RiskPredictionCreate,
    alerts: Sequence[AlertCreate] = (),
    recommendations: Sequence[RecommendationCreate] = (),
    actor_user_id: int | None = None,
    request_id: str | None = None,
    commit: bool = True,
    audit: bool = True,
) -> models.RiskPrediction:
    """Persist a prediction and all dependent records atomically.

    The operation deliberately commits only after factors, alerts,
    recommendations and the audit record have all been flushed successfully.
    Any exception rolls back the complete bundle.
    """
    try:
        prediction_payload = prediction_data.model_dump(exclude={"factors"})
        prediction = models.RiskPrediction(**prediction_payload)
        db.add(prediction)
        db.flush()

        for factor_data in prediction_data.factors:
            db.add(
                models.RiskPredictionFactor(
                    risk_prediction_id=prediction.id,
                    **factor_data.model_dump(),
                )
            )
        for alert_data in alerts:
            alert_payload = alert_data.model_dump()
            alert_payload["risk_prediction_id"] = prediction.id
            db.add(models.Alert(**alert_payload))
        for recommendation_data in recommendations:
            recommendation_payload = recommendation_data.model_dump()
            recommendation_payload["risk_prediction_id"] = prediction.id
            db.add(models.Recommendation(**recommendation_payload))

        if audit:
            db.add(
                models.AuditLog(
                    actor="user" if actor_user_id else "system",
                    action="RISK_PREDICTED",
                    payload={"risk_prediction_id": prediction.id},
                    user_id=actor_user_id,
                    entity_type="risk_prediction",
                    entity_id=str(prediction.id),
                    request_id=request_id,
                    new_values_json={
                        "risk_score": prediction.risk_score,
                        "risk_level": prediction.risk_level.value
                        if hasattr(prediction.risk_level, "value")
                        else prediction.risk_level,
                    },
                )
            )
        if commit:
            db.commit()
            db.refresh(prediction)
        else:
            db.flush()
        return prediction
    except Exception:
        db.rollback()
        raise
