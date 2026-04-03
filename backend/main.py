from __future__ import annotations
from datetime import datetime
from typing import Dict, Any
import numpy as np

from fastapi import FastAPI, Depends, Query, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import desc

from .config import settings
from .database import Base, engine, get_db
from . import models
from .schemas import (
    TelemetryInput,
    ScenarioInput,
    PredictionResponse,
    SafeRouteRequest,
    SafeRouteResponse,
    SummaryResponse,
    LoginRequest,
    TokenResponse,
    MeResponse,
    AlertPolicyCreate,
    AlertPolicyUpdate,
    AlertPolicyResponse,
)
from .feature_engineering import build_features, FEATURE_ORDER
from .risk_model import predict_risk
from .ml_registry import load_runtime_model, get_ml_status, get_ml_metrics
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
from .security import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    require_roles,
)

app = FastAPI(title=settings.app_name, version=settings.model_version)
MODEL_BUNDLE = None


@app.on_event("startup")
def startup_event():
    global MODEL_BUNDLE
    Base.metadata.create_all(bind=engine)
    MODEL_BUNDLE = load_runtime_model()
    _seed_if_needed()
    _seed_users_if_needed()


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
        db.add_all([
            models.AlertPolicy(
                name="Política Campo",
                operation_type="campo",
                min_risk_alert=40,
                min_risk_block=70,
                max_speed=20,
                max_slope=12,
                min_distance_water=25,
                max_rain_mm=15,
                block_on_water=False,
                block_on_unstable_soil=True,
                is_active=True,
            ),
            models.AlertPolicy(
                name="Política Transporte",
                operation_type="transporte",
                min_risk_alert=35,
                min_risk_block=65,
                max_speed=30,
                max_slope=10,
                min_distance_water=20,
                max_rain_mm=10,
                block_on_water=False,
                block_on_unstable_soil=False,
                is_active=True,
            ),
            models.AlertPolicy(
                name="Política Água",
                operation_type="proximidade_agua",
                min_risk_alert=30,
                min_risk_block=55,
                max_speed=15,
                max_slope=8,
                min_distance_water=40,
                max_rain_mm=8,
                block_on_water=True,
                block_on_unstable_soil=True,
                is_active=True,
            ),
        ])
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

def _seed_users_if_needed():
    db = next(get_db())
    try:
        if db.query(models.UserAccount).count() > 0:
            return

        users = [
            models.UserAccount(
                username="admin",
                full_name="Administrador AgroGuardian",
                email="admin@agroguardian.ai",
                hashed_password=hash_password("admin123"),
                role="admin",
                is_active=True,
            ),
            models.UserAccount(
                username="sompo",
                full_name="Analista Sompo",
                email="sompo@agroguardian.ai",
                hashed_password=hash_password("sompo123"),
                role="sompo",
                is_active=True,
            ),
            models.UserAccount(
                username="gestor",
                full_name="Gestor de Fazenda",
                email="gestor@agroguardian.ai",
                hashed_password=hash_password("gestor123"),
                role="gestor",
                is_active=True,
            ),
            models.UserAccount(
                username="operador",
                full_name="Operador de Campo",
                email="operador@agroguardian.ai",
                hashed_password=hash_password("operador123"),
                role="operador",
                is_active=True,
            ),
        ]

        db.add_all(users)
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

def _get_active_policy(db: Session, operation_type: str):
    policy = (
        db.query(models.AlertPolicy)
        .filter(
            models.AlertPolicy.operation_type == operation_type,
            models.AlertPolicy.is_active == True,
        )
        .first()
    )

    if policy:
        return policy

    fallback = (
        db.query(models.AlertPolicy)
        .filter(
            models.AlertPolicy.operation_type == "all",
            models.AlertPolicy.is_active == True,
        )
        .first()
    )
    return fallback


def _apply_alert_policy(
    risk_score: float,
    payload: Dict[str, Any],
    policy,
    current_alert_level: str,
    current_recommendation: str,
):
    if not policy:
        return current_alert_level, current_recommendation, []

    policy_alerts = []
    block_reasons = []

    velocidade = float(payload.get("velocidade", 0))
    inclinacao = float(payload.get("inclinacao", 0))
    distancia_agua = float(payload.get("distancia_agua", 9999))
    chuva_mm = float(payload.get("chuva_mm", 0))
    solo_instavel = int(payload.get("solo_instavel", 0))

    if risk_score >= policy.min_risk_alert:
        policy_alerts.append({
            "type": "policy_risk_alert",
            "severity": "medium",
            "message": f"Score acima do limite de alerta da política ({policy.min_risk_alert}).",
        })

    if risk_score >= policy.min_risk_block:
        block_reasons.append(f"Score acima do limite de bloqueio ({policy.min_risk_block})")

    if velocidade > policy.max_speed:
        block_reasons.append(f"Velocidade acima do limite ({policy.max_speed})")

    if inclinacao > policy.max_slope:
        block_reasons.append(f"Inclinação acima do limite ({policy.max_slope})")

    if distancia_agua < policy.min_distance_water:
        policy_alerts.append({
            "type": "policy_water_distance",
            "severity": "medium",
            "message": f"Distância da água abaixo do mínimo da política ({policy.min_distance_water} m).",
        })
        if policy.block_on_water:
            block_reasons.append("Operação próxima à água com bloqueio habilitado")

    if chuva_mm > policy.max_rain_mm:
        block_reasons.append(f"Chuva acima do limite ({policy.max_rain_mm} mm)")

    if solo_instavel == 1 and policy.block_on_unstable_soil:
        block_reasons.append("Solo instável com bloqueio habilitado")

    if block_reasons:
        alert_level = "⛔ Operação bloqueada por política"
        recommendation = (
            "Operação bloqueada pela política configurada. Motivos: "
            + "; ".join(block_reasons)
            + ". Revise velocidade, clima, inclinação e proximidade da água."
        )
        policy_alerts.append({
            "type": "policy_block",
            "severity": "high",
            "message": recommendation,
        })
        return alert_level, recommendation, policy_alerts

    return current_alert_level, current_recommendation, policy_alerts

@app.post("/api/v1/auth/login", response_model=TokenResponse)
def auth_login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = (
        db.query(models.UserAccount)
        .filter(models.UserAccount.username == payload.username)
        .first()
    )

    if not user or not verify_password(payload.password, user.hashed_password):
        db.add(
            models.AccessEvent(
                username=payload.username,
                role="unknown",
                action="login",
                endpoint=str(request.url.path),
                success=False,
                detail={"reason": "invalid_credentials"},
            )
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha inválidos",
        )

    if not user.is_active:
        db.add(
            models.AccessEvent(
                username=user.username,
                role=user.role,
                action="login",
                endpoint=str(request.url.path),
                success=False,
                detail={"reason": "inactive_user"},
            )
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário inativo",
        )

    access_token = create_access_token(
        {"sub": user.username, "role": user.role}
    )

    user.last_login_at = datetime.utcnow()
    db.add(
        models.AccessEvent(
            username=user.username,
            role=user.role,
            action="login",
            endpoint=str(request.url.path),
            success=True,
            detail={"message": "login_realizado"},
        )
    )
    db.commit()

    return TokenResponse(
        access_token=access_token,
        username=user.username,
        role=user.role,
    )

@app.post("/api/v1/auth/token", response_model=TokenResponse)
def auth_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = (
        db.query(models.UserAccount)
        .filter(models.UserAccount.username == form_data.username)
        .first()
    )

    if not user or not verify_password(form_data.password, user.hashed_password):
        db.add(
            models.AccessEvent(
                username=form_data.username,
                role="unknown",
                action="login_oauth2",
                endpoint=str(request.url.path),
                success=False,
                detail={"reason": "invalid_credentials"},
            )
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha inválidos",
        )

    if not user.is_active:
        db.add(
            models.AccessEvent(
                username=user.username,
                role=user.role,
                action="login_oauth2",
                endpoint=str(request.url.path),
                success=False,
                detail={"reason": "inactive_user"},
            )
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário inativo",
        )

    access_token = create_access_token(
        {"sub": user.username, "role": user.role}
    )

    user.last_login_at = datetime.utcnow()
    db.add(
        models.AccessEvent(
            username=user.username,
            role=user.role,
            action="login_oauth2",
            endpoint=str(request.url.path),
            success=True,
            detail={"message": "login_realizado_oauth2"},
        )
    )
    db.commit()

    return TokenResponse(
        access_token=access_token,
        username=user.username,
        role=user.role,
    )


@app.get("/api/v1/auth/me", response_model=MeResponse)
def auth_me(current_user=Depends(get_current_user)):
    return MeResponse(
        username=current_user.username,
        full_name=current_user.full_name,
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active,
        last_login_at=current_user.last_login_at,
    )


@app.get("/api/v1/auth/access-events")
def auth_access_events(
    current_user=Depends(require_roles("admin", "sompo")),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(models.AccessEvent)
        .order_by(desc(models.AccessEvent.timestamp))
        .limit(50)
        .all()
    )

    return {
        "events": [
            {
                "id": row.id,
                "username": row.username,
                "role": row.role,
                "action": row.action,
                "endpoint": row.endpoint,
                "success": row.success,
                "detail": row.detail,
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            }
            for row in rows
        ]
    }


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

    policy = _get_active_policy(db, full_payload["operation_type"])
    policy_alert_level, policy_recommendation, policy_alerts = _apply_alert_policy(
        risk_score=risk_score,
        payload=full_payload,
        policy=policy,
        current_alert_level=alert_level,
        current_recommendation=recommendation,
    )

    alerts.extend(policy_alerts)
    alert_level = policy_alert_level
    recommendation = policy_recommendation
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

@app.get("/api/v1/policies/alerts", response_model=list[AlertPolicyResponse])
def list_alert_policies(db: Session = Depends(get_db)):
    return db.query(models.AlertPolicy).order_by(models.AlertPolicy.id.asc()).all()


@app.post("/api/v1/policies/alerts", response_model=AlertPolicyResponse)
def create_alert_policy(payload: AlertPolicyCreate, db: Session = Depends(get_db)):
    policy = models.AlertPolicy(**payload.model_dump())
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy


@app.put("/api/v1/policies/alerts/{policy_id}", response_model=AlertPolicyResponse)
def update_alert_policy(policy_id: int, payload: AlertPolicyUpdate, db: Session = Depends(get_db)):
    policy = db.query(models.AlertPolicy).filter(models.AlertPolicy.id == policy_id).first()
    if not policy:
        raise ValueError("Política não encontrada")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(policy, key, value)

    db.commit()
    db.refresh(policy)
    return policy

@app.get("/api/v1/ml/status")
def ml_status():
    global MODEL_BUNDLE

    return {
        "loaded_model_name": MODEL_BUNDLE.get("model_name") if MODEL_BUNDLE else None,
        "runtime_source": MODEL_BUNDLE.get("runtime_source") if MODEL_BUNDLE else None,
        "feature_names": MODEL_BUNDLE.get("feature_names") if MODEL_BUNDLE else None,
        "registry": get_ml_status(),
    }


@app.get("/api/v1/ml/metrics")
def ml_metrics():
    return get_ml_metrics()