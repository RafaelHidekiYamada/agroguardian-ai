from __future__ import annotations
from datetime import datetime
from typing import Dict, Any
import numpy as np

from fastapi import FastAPI, Depends, Query
from sqlalchemy.orm import Session

from .config import settings
from .database import Base, engine, get_db
from . import models
from .schemas import (
    TelemetryInput,
    ScenarioInput,
    PredictionResponse,
    SafeRouteRequest,
    SafeRouteResponse,
)
from .feature_engineering import build_features, FEATURE_ORDER
from .risk_model import train_or_load_model, predict_risk
from .alerts import build_alerts, alert_summary
from .weather_service import get_weather
from .route_ai import recommend_route
from .explainability import heuristic_explanation, shap_explanation
from .map_service import build_risk_map
from .audit import write_audit
from .reports import (
    build_summary,
    build_ranking,
    build_trends,
    build_alerts as build_alerts_report,
    build_audit,
    list_farms_data,
    list_equipment_data,
)

app = FastAPI(title=settings.app_name, version=settings.model_version)
MODEL_BUNDLE = None


@app.on_event("startup")
def startup_event():
    global MODEL_BUNDLE
    Base.metadata.create_all(bind=engine)
    MODEL_BUNDLE = train_or_load_model()
    _seed_if_needed()


def _seed_if_needed():
    db = next(get_db())
    try:
        if db.query(models.Farm).count() > 0:
            return

        farm = models.Farm(
            name=settings.default_farm_name,
            region=settings.default_region,
            latitude=-23.455,
            longitude=-46.533,
        )
        farm2 = models.Farm(
            name="Fazenda Vista Verde",
            region="Mogi das Cruzes - SP",
            latitude=-23.520,
            longitude=-46.187,
        )
        db.add_all([farm, farm2])
        db.flush()

        equipments = [
            models.Equipment(
                name="Trator A",
                equipment_type="Trator",
                client_name=settings.default_client,
                farm_id=farm.id,
            ),
            models.Equipment(
                name="Colheitadeira B",
                equipment_type="Colheitadeira",
                client_name=settings.default_client,
                farm_id=farm.id,
            ),
            models.Equipment(
                name="Pulverizador C",
                equipment_type="Pulverizador",
                client_name=settings.default_client,
                farm_id=farm2.id,
            ),
        ]
        db.add_all(equipments)
        db.commit()

        sample_records = [
            dict(
                equipment_id=1,
                farm_id=1,
                region=farm.region,
                operation_type="campo",
                clima="chuva",
                umidade_solo=84,
                inclinacao=13,
                distancia_agua=18,
                velocidade=16,
                historico_sinistros=6,
                chuva_mm=18,
                solo_instavel=1,
                latitude=farm.latitude,
                longitude=farm.longitude,
            ),
            dict(
                equipment_id=2,
                farm_id=1,
                region=farm.region,
                operation_type="transporte",
                clima="nublado",
                umidade_solo=55,
                inclinacao=7,
                distancia_agua=60,
                velocidade=12,
                historico_sinistros=2,
                chuva_mm=3,
                solo_instavel=0,
                latitude=farm.latitude,
                longitude=farm.longitude,
            ),
            dict(
                equipment_id=3,
                farm_id=2,
                region=farm2.region,
                operation_type="proximidade_agua",
                clima="tempestade",
                umidade_solo=91,
                inclinacao=18,
                distancia_agua=8,
                velocidade=9,
                historico_sinistros=8,
                chuva_mm=24,
                solo_instavel=1,
                latitude=farm2.latitude,
                longitude=farm2.longitude,
            ),
        ]

        for payload in sample_records:
            features = build_features(payload)
            risk_score = predict_risk(MODEL_BUNDLE, features)
            explanation = heuristic_explanation(payload, risk_score)
            alerts = build_alerts(risk_score, payload)
            route = recommend_route(payload)

            db.add(
                models.TelemetryRecord(
                    **payload,
                    predicted_risk=risk_score,
                    risk_label=_risk_label(risk_score),
                    alert_level=alert_summary(alerts),
                    recommendation=_recommendation_text(risk_score, payload),
                    safe_route=route["recommended_route"],
                    explanation=explanation,
                )
            )
            db.add(
                models.PredictionRecord(
                    model_version=settings.model_version,
                    source="seed",
                    input_payload=payload,
                    predicted_risk=risk_score,
                    risk_label=_risk_label(risk_score),
                    alert_level=alert_summary(alerts),
                    explanation=explanation,
                    recommendation=_recommendation_text(risk_score, payload),
                    safe_route=route["recommended_route"],
                    weather_payload={"source": "seed"},
                )
            )

            for a in alerts:
                db.add(
                    models.AlertRecord(
                        alert_type=a["type"],
                        severity=a["severity"],
                        message=a["message"],
                        context=payload,
                    )
                )

        db.commit()

        db.add(
            models.RouteRecommendation(
                origin_name="Fazenda Modelo",
                destination_name="Armazém / Oficina",
                recommended_route="Rota C - via alternativa mais longa",
                route_score=28.5,
                alternatives=[
                    {"name": "Rota A - estrada principal", "route_score": 41.2},
                    {"name": "Rota B - estrada rural curta", "route_score": 39.8},
                    {"name": "Rota C - via alternativa mais longa", "route_score": 28.5},
                ],
                context={"seed": True},
            )
        )
        db.add(models.AuditLog(actor="system", action="seed_database", payload={"status": "ok"}))
        db.commit()

    finally:
        db.close()


def _risk_label(score: float) -> str:
    if score <= 40:
        return "Baixo"
    if score <= 70:
        return "Médio"
    return "Alto"


def _recommendation_text(risk_score: float, payload: Dict[str, Any]) -> str:
    if risk_score >= 71:
        return (
            "Interromper ou replanejar a operação; reduzir velocidade; "
            "evitar bordas próximas à água; aguardar melhora do clima."
        )
    if risk_score >= 41:
        return "Operar com cautela; reduzir velocidade; revisar rota; monitorar terreno e umidade."
    return "Operação liberada com monitoramento padrão e atenção a mudanças de clima."


def _prepare_prediction(payload: TelemetryInput, weather: Dict[str, Any]) -> Dict[str, Any]:
    data = payload.model_dump()

    rain_mm = float(weather.get("rain_mm_1h", 0) or 0)
    weather_main = str(weather.get("weather_main", "")).lower()

    data["chuva_mm"] = max(float(data["chuva_mm"]), rain_mm * 3.0)

    if weather_main in {"rain", "drizzle", "thunderstorm", "chuva"}:
        data["clima"] = "chuva"
    elif weather_main in {"clouds", "mist", "fog", "nublado"}:
        data["clima"] = "nublado"
    elif weather_main in {"clear", "sun", "sol"}:
        data["clima"] = "sol"

    data["solo_instavel"] = int(data["solo_instavel"])
    return data


@app.get("/")
def root():
    return {
        "app": settings.app_name,
        "version": settings.model_version,
        "status": "running",
        "docs": "/docs",
        "dashboard_hint": "Use a interface Streamlit para visualizar risco, alertas e relatórios.",
    }


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


@app.post("/api/v1/risk/predict", response_model=PredictionResponse)
def predict(payload: TelemetryInput, db: Session = Depends(get_db)):
    weather = get_weather(payload.latitude, payload.longitude)
    full_payload = _prepare_prediction(payload, weather)
    features = build_features(full_payload)
    risk_score = predict_risk(MODEL_BUNDLE, features)
    risk_label = _risk_label(risk_score)
    alerts = build_alerts(risk_score, full_payload)
    alert_level = alert_summary(alerts)
    recommendation = _recommendation_text(risk_score, full_payload)
    route = recommend_route(full_payload)

    explanation = shap_explanation(
        MODEL_BUNDLE["model"],
        np.array([list(features.values())]),
        np.array([list(features.values())]),
        FEATURE_ORDER,
    )
    if not explanation:
        explanation = heuristic_explanation(full_payload, risk_score)

    audit_id = write_audit(
        db,
        actor="api",
        action="risk_predict",
        payload={
            "input": payload.model_dump(),
            "weather": weather,
            "risk_score": risk_score,
            "risk_label": risk_label,
            "alert_level": alert_level,
        },
    )

    db.add(
        models.PredictionRecord(
            model_version=settings.model_version,
            source="api",
            input_payload=payload.model_dump(),
            predicted_risk=risk_score,
            risk_label=risk_label,
            alert_level=alert_level,
            explanation=explanation,
            recommendation=recommendation,
            safe_route=route["recommended_route"],
            weather_payload=weather,
        )
    )

    db.add(
        models.TelemetryRecord(
            equipment_id=payload.equipment_id,
            farm_id=payload.farm_id,
            region=payload.region,
            operation_type=payload.operation_type,
            clima=full_payload["clima"],
            umidade_solo=full_payload["umidade_solo"],
            inclinacao=full_payload["inclinacao"],
            distancia_agua=full_payload["distancia_agua"],
            velocidade=full_payload["velocidade"],
            historico_sinistros=full_payload["historico_sinistros"],
            chuva_mm=full_payload["chuva_mm"],
            solo_instavel=full_payload["solo_instavel"],
            latitude=full_payload["latitude"],
            longitude=full_payload["longitude"],
            predicted_risk=risk_score,
            risk_label=risk_label,
            alert_level=alert_level,
            recommendation=recommendation,
            safe_route=route["recommended_route"],
            explanation=explanation,
        )
    )

    for a in alerts:
        db.add(
            models.AlertRecord(
                alert_type=a["type"],
                severity=a["severity"],
                message=a["message"],
                context=payload.model_dump(),
            )
        )

    db.commit()

    return PredictionResponse(
        timestamp=datetime.utcnow(),
        model_version=settings.model_version,
        risk_score=round(risk_score, 2),
        risk_label=risk_label,
        alert_level=alert_level,
        alerts=alerts,
        recommendation=recommendation,
        safe_route=route,
        explanation=explanation,
        weather=weather,
        audit_id=audit_id,
    )


@app.post("/api/v1/simulate", response_model=PredictionResponse)
def simulate(payload: ScenarioInput, db: Session = Depends(get_db)):
    weather = get_weather(payload.latitude, payload.longitude)
    simulated = payload.model_dump()
    simulated["clima"] = "chuva" if payload.scenario_name else payload.clima
    simulated["chuva_mm"] = max(payload.chuva_mm, weather.get("rain_mm_1h", 0) * 4 + 10)
    simulated["velocidade"] = max(0, payload.velocidade - 2)
    simulated["umidade_solo"] = min(100, payload.umidade_solo + 8)

    sim_input = TelemetryInput(**simulated)
    return predict(sim_input, db=db)


@app.get("/api/v1/risk-map")
def risk_map(
    latitude: float = Query(-23.455),
    longitude: float = Query(-46.533),
    risk_score: float = Query(68.0),
):
    zones = [
        {
            "name": "Zona segura",
            "lat": latitude + 0.004,
            "lon": longitude + 0.002,
            "radius_m": 250,
            "color": "green",
        },
        {
            "name": "Zona de atenção",
            "lat": latitude - 0.003,
            "lon": longitude + 0.004,
            "radius_m": 300,
            "color": "orange",
        },
        {
            "name": "Zona crítica",
            "lat": latitude - 0.005,
            "lon": longitude - 0.003,
            "radius_m": 320,
            "color": "red",
        },
    ]
    html = build_risk_map(latitude, longitude, risk_score, zones)
    return {"html": html}


@app.post("/api/v1/routes/safe", response_model=SafeRouteResponse)
def safe_route(payload: SafeRouteRequest, db: Session = Depends(get_db)):
    route = recommend_route(
        {
            "chuva_mm": 18,
            "inclinacao": 10,
            "historico_sinistros": 4,
            "distancia_agua": 35,
            "clima": "chuva",
        },
        payload.origin_name,
        payload.destination_name,
    )

    db.add(
        models.RouteRecommendation(
            origin_name=payload.origin_name,
            destination_name=payload.destination_name,
            recommended_route=route["recommended_route"],
            route_score=route["route_score"],
            alternatives=route["alternatives"],
            context=payload.model_dump(),
        )
    )
    db.add(models.AuditLog(actor="api", action="safe_route", payload=payload.model_dump()))
    db.commit()

    return SafeRouteResponse(
        recommended_route=route["recommended_route"],
        route_score=route["route_score"],
        alternatives=route["alternatives"],
        rationale=route["rationale"],
    )


@app.get("/api/v1/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db)):
    return build_summary(db)


@app.get("/api/v1/dashboard/ranking")
def dashboard_ranking(db: Session = Depends(get_db)):
    return build_ranking(db)


@app.get("/api/v1/dashboard/trends")
def dashboard_trends(db: Session = Depends(get_db)):
    return build_trends(db)


@app.get("/api/v1/dashboard/alerts")
def dashboard_alerts(db: Session = Depends(get_db)):
    return build_alerts_report(db)


@app.get("/api/v1/dashboard/audit")
def dashboard_audit(db: Session = Depends(get_db)):
    return build_audit(db)


@app.get("/api/v1/farms")
def list_farms(db: Session = Depends(get_db)):
    return list_farms_data(db)


@app.get("/api/v1/equipment")
def list_equipment(db: Session = Depends(get_db)):
    return list_equipment_data(db)