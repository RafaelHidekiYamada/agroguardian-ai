from __future__ import annotations
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
import numpy as np

from fastapi import FastAPI, Depends, Header, Query, HTTPException, status, Request, Response
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_

from .geointelligence import build_geo_context
from .config import settings
from .database import get_db
from .database_seed import seed_database_from_environment
from .database_schemas import (
    AlertCreate as DatabaseAlertCreate,
    RecommendationCreate,
    RiskPredictionCreate,
    RiskPredictionFactorCreate,
)
from .database_services import create_risk_prediction_bundle
from . import models
from .schemas import (
    TelemetryInput,
    ESPTelemetryInput,
    IotTelemetryInput,
    IotTelemetryResponse,
    IotDeviceCreate,
    IotDeviceUpdate,
    IotDeviceResponse,
    EquipmentCreate,
    EquipmentUpdate,
    ScenarioInput,
    PredictionResponse,
    SafeRouteRequest,
    SafeRouteResponse,
    SummaryResponse,
    LoginRequest,
    TokenResponse,
    MeResponse,
    ChangePasswordRequest,
    UserCreate,
    UserUpdate,
    UserResponse,
    UserPermissionUpdate,
    ResetPasswordRequest,
    AlertPolicyCreate,
    AlertPolicyUpdate,
    AlertPolicyResponse,
    redact_sensitive_fields,
)
from .feature_engineering import build_features, FEATURE_ORDER
from .risk_model import predict_risk
from .ml_registry import load_runtime_model, get_ml_status, get_ml_metrics
from .alerts import build_alerts, alert_summary
from .weather_service import get_weather
from .route_ai import recommend_route
from .decision_engine import calculate_contextual_risk, build_decision_support
from .explainability import (
    heuristic_explanation,
    shap_explanation,
    build_executive_explanation,
    build_structured_explanation,
)
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
    build_region_risk_scores,
    build_equipment_risk_scores,
    build_equipment_risk_history,
    list_sensor_readings_data,
)
from .security import (
    ALL_PERMISSIONS,
    DEFAULT_ROLE_PERMISSIONS,
    authenticate_user,
    generate_api_key,
    get_primary_role,
    get_user_permissions,
    get_user_roles,
    hash_password,
    verify_password,
    hash_api_key,
    verify_api_key,
    create_access_token,
    get_current_user,
    normalize_role,
    require_permission,
    require_roles,
)
from .iot_processing import (
    apply_risk_context,
    build_iot_context,
    build_iot_events,
    current_device_status,
    current_telemetry_status,
    normalize_timestamp,
    risk_context_from_telemetry,
)
from .integration_hub import (
    build_operational_context,
    build_prediction_trace,
    build_system_architecture,
    build_system_status,
)

app = FastAPI(title=settings.app_name, version=settings.model_version)
MODEL_BUNDLE = None
DEVICE_RATE_LIMIT: dict[str, list[float]] = {}


class _PayloadTooLargeError(Exception):
    pass


class IoTPayloadSizeMiddleware:
    """Validate ESP32 content type and body size before FastAPI parses JSON."""

    _paths = {"/api/v1/telemetry/esp", "/api/v1/iot/telemetry"}

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] not in self._paths:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_type = headers.get(b"content-type", b"").split(b";", 1)[0].strip().lower()
        if content_type != b"application/json":
            await JSONResponse(
                status_code=415,
                content={"detail": "Content-Type deve ser application/json."},
            )(scope, receive, send)
            return

        max_bytes = settings.iot_max_payload_bytes
        try:
            content_length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            content_length = max_bytes + 1
        if content_length > max_bytes:
            await JSONResponse(
                status_code=413,
                content={"detail": "Payload de telemetria muito grande."},
            )(scope, receive, send)
            return

        received_bytes = 0

        async def limited_receive():
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > max_bytes:
                    raise _PayloadTooLargeError
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _PayloadTooLargeError:
            await JSONResponse(
                status_code=413,
                content={"detail": "Payload de telemetria muito grande."},
            )(scope, receive, send)


app.add_middleware(IoTPayloadSizeMiddleware)


@app.on_event("startup")
def startup_event():
    global MODEL_BUNDLE
    MODEL_BUNDLE = load_runtime_model()
    if settings.auto_seed_demo:
        seed_database_from_environment()


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
        permission_by_code = {}
        for code in ALL_PERMISSIONS:
            permission = db.query(models.Permission).filter(models.Permission.code == code).first()
            if not permission:
                permission = models.Permission(code=code, description=code.replace(".", " "))
                db.add(permission)
                db.flush()
            permission_by_code[code] = permission

        role_by_name = {}
        for role_name, permission_codes in DEFAULT_ROLE_PERMISSIONS.items():
            role = db.query(models.Role).filter(models.Role.name == role_name).first()
            if not role:
                role = models.Role(name=role_name, description=f"Perfil {role_name}")
                db.add(role)
                db.flush()
            role.permissions = [permission_by_code[code] for code in sorted(permission_codes)]
            role_by_name[role_name] = role

        # Development identities are created exclusively by database_seed.py,
        # which requires credentials from INITIAL_ADMIN_* environment variables.
        seed_users: list[tuple[str, str, str, str, list[str]]] = []

        for username, name, email, password, roles in seed_users:
            user = db.query(models.User).filter(models.User.username == username).first()
            if not user:
                user = models.User(
                    username=username,
                    name=name,
                    email=email,
                    password_hash=hash_password(password),
                    status="active",
                    is_active=True,
                )
                db.add(user)
                db.flush()
            user.roles = [role_by_name[normalize_role(role)] for role in roles]

        db.commit()

        if settings.default_device_api_key:
            device = (
                db.query(models.IotDevice)
                .filter(models.IotDevice.device_id == "ESP32-TRATOR-001")
                .first()
            )
            equipment = db.query(models.Equipment).filter(models.Equipment.id == 1).first()
            if equipment and not device:
                db.add(
                    models.IotDevice(
                        device_id="ESP32-TRATOR-001",
                        equipment_id=equipment.id,
                        name="ESP32 Trator A",
                        device_type="ESP32",
                        firmware_version="dev",
                        api_key_hash=hash_api_key(settings.default_device_api_key),
                        status="offline",
                    )
                )
                db.add(
                    models.AuditLog(
                        actor="system",
                        action="iot_device_seeded",
                        payload={"device_id": "ESP32-TRATOR-001", "api_key": "configured"},
                    )
                )
                db.commit()
    finally:
        db.close()


def _role_lookup(db: Session) -> dict[str, models.Role]:
    return {role.name: role for role in db.query(models.Role).all()}


def _permission_lookup(db: Session) -> dict[str, models.Permission]:
    return {permission.code: permission for permission in db.query(models.Permission).all()}


def _sync_user_roles(db: Session, user: models.User, role_names: list[str]) -> None:
    roles = _role_lookup(db)
    normalized_roles = [normalize_role(role) for role in role_names] or ["LEITURA"]
    user.roles = [roles[role] for role in normalized_roles if role in roles]


def _sync_user_permission_overrides(
    db: Session,
    user: models.User,
    permissions_add: list[str] | None,
    permissions_remove: list[str] | None,
) -> None:
    permission_by_code = _permission_lookup(db)
    requested: dict[str, bool] = {}
    for code in permissions_add or []:
        if code in permission_by_code:
            requested[code] = True
    for code in permissions_remove or []:
        if code in permission_by_code:
            requested[code] = False

    current = {
        override.permission.code: override
        for override in user.permission_overrides
        if override.permission is not None
    }
    for code, allowed in requested.items():
        override = current.get(code)
        if override:
            override.allowed = allowed
        else:
            db.add(
                models.UserPermission(
                    user_id=user.id,
                    permission_id=permission_by_code[code].id,
                    allowed=allowed,
                )
            )


def _replace_access_scopes(
    db: Session,
    user: models.User,
    scopes: list[Any] | None,
) -> None:
    if scopes is None:
        return
    for scope in list(user.access_scopes):
        db.delete(scope)
    db.flush()
    for scope in scopes:
        data = scope.model_dump() if hasattr(scope, "model_dump") else dict(scope)
        db.add(
            models.UserAccessScope(
                user_id=user.id,
                client_id=data.get("client_id"),
                client_name=data.get("client_name"),
                farm_id=data.get("farm_id"),
                equipment_id=data.get("equipment_id"),
            )
        )


def _serialize_user(user: models.User) -> dict[str, Any]:
    explicit_add = []
    explicit_remove = []
    for override in user.permission_overrides:
        if override.permission is None:
            continue
        if override.allowed:
            explicit_add.append(override.permission.code)
        else:
            explicit_remove.append(override.permission.code)

    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "username": user.username,
        "status": user.status,
        "is_active": user.is_active,
        "roles": get_user_roles(user),
        "permissions": sorted(get_user_permissions(user)),
        "explicit_permissions_add": sorted(explicit_add),
        "explicit_permissions_remove": sorted(explicit_remove),
        "access_scopes": [
            {
                "id": scope.id,
                "client_id": scope.client_id,
                "client_name": scope.client_name,
                "farm_id": scope.farm_id,
                "equipment_id": scope.equipment_id,
            }
            for scope in user.access_scopes
        ],
        "last_login_at": user.last_login_at,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


def _is_global_scope_user(user: Any) -> bool:
    return bool(getattr(user, "is_superuser", False)) or "ADMIN" in set(get_user_roles(user))


def _assert_equipment_scope(current_user: Any, equipment: models.Equipment) -> None:
    """Apply explicit client/farm/equipment grants without changing legacy broad roles."""
    if _is_global_scope_user(current_user):
        return
    scopes = list(getattr(current_user, "access_scopes", []) or [])
    if not scopes:
        return
    farm = getattr(equipment, "farm", None)
    client = getattr(farm, "client", None) if farm else None
    for scope in scopes:
        if scope.equipment_id is not None and scope.equipment_id == equipment.id:
            return
        if scope.farm_id is not None and scope.farm_id == equipment.farm_id:
            return
        if client is not None and scope.client_id is not None and scope.client_id == client.id:
            return
        if scope.client_name and scope.client_name == getattr(client, "name", equipment.client_name):
            return
    raise HTTPException(status_code=403, detail="Seu escopo de acesso nao inclui este equipamento.")


def _scoped_equipment(current_user: Any, equipment: list[models.Equipment]) -> list[models.Equipment]:
    if _is_global_scope_user(current_user) or not getattr(current_user, "access_scopes", None):
        return equipment
    visible: list[models.Equipment] = []
    for item in equipment:
        try:
            _assert_equipment_scope(current_user, item)
        except HTTPException:
            continue
        visible.append(item)
    return visible


def _serialize_role(role: models.Role) -> dict[str, Any]:
    return {
        "id": role.id,
        "name": role.name,
        "description": role.description,
        "permissions": sorted(permission.code for permission in role.permissions),
    }


def _serialize_iot_device(device: models.IotDevice, api_key: str | None = None) -> dict[str, Any]:
    equipment = getattr(device, "equipment", None)
    telemetry = list(getattr(device, "telemetry_by_id", []) or getattr(device, "telemetry", []) or [])
    latest = max(
        telemetry,
        key=lambda row: normalize_timestamp(
            getattr(row, "recorded_at", None) or getattr(row, "timestamp", None)
        ).timestamp()
        if (getattr(row, "recorded_at", None) or getattr(row, "timestamp", None))
        else float("-inf"),
        default=None,
    )
    data = {
        "id": device.id,
        "device_id": device.device_id,
        "device_identifier": device.device_identifier,
        "equipment_id": device.equipment_id,
        "name": device.name,
        "device_type": device.device_type,
        "firmware_version": device.firmware_version,
        "status": current_device_status(device),
        "last_seen_at": device.last_seen_at,
        "metadata_json": redact_sensitive_fields(device.metadata_json or {}),
        "is_active": device.is_active,
        "created_at": device.created_at,
        "updated_at": device.updated_at,
        "api_key": api_key,
        "equipment_name": getattr(equipment, "name", None),
        "farm_id": getattr(equipment, "farm_id", None),
        "farm_name": getattr(getattr(equipment, "farm", None), "name", None),
        "telemetry_count": len(telemetry),
        "latest_telemetry": _serialize_iot_telemetry(latest) if latest else None,
    }
    return data


def _iot_device_by_reference(db: Session, reference: str) -> models.IotDevice | None:
    if reference.isdigit():
        by_id = db.query(models.IotDevice).filter(models.IotDevice.id == int(reference)).first()
        if by_id is not None:
            return by_id
    return db.query(models.IotDevice).filter(models.IotDevice.device_id == reference).first()


def _serialize_equipment(equipment: models.Equipment) -> dict[str, Any]:
    farm = getattr(equipment, "farm", None)
    return {
        "equipment_id": equipment.id,
        "id": equipment.id,
        "equipment_name": equipment.name,
        "name": equipment.name,
        "equipment_type": equipment.equipment_type,
        "client_name": equipment.client_name,
        "farm_id": equipment.farm_id,
        "farm_name": getattr(farm, "name", None),
        "model": getattr(equipment, "model", None),
        "year": getattr(equipment, "year", None),
        "status": getattr(equipment, "status", None),
        "iot_devices": [
            {
                "device_id": device.device_id,
                "status": current_device_status(device),
                "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
            }
            for device in getattr(equipment, "iot_devices", [])
        ],
    }


def _serialize_iot_telemetry(row: models.IotTelemetry) -> dict[str, Any]:
    recorded_at = row.recorded_at or row.timestamp
    status, age_seconds = current_telemetry_status(recorded_at)
    return {
        "id": row.id,
        "device_id": row.device_id,
        "iot_device_id": row.iot_device_id,
        "equipment_id": row.equipment_id,
        "sequence_number": row.sequence_number,
        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        "recorded_at": recorded_at.isoformat() if recorded_at else None,
        "received_at": row.received_at.isoformat() if row.received_at else None,
        "temperature_c": row.temperature_c,
        "humidity_pct": row.humidity_pct,
        "pressure_hpa": row.pressure_hpa,
        "altitude_m": row.altitude_m,
        "accel_x": row.accel_x,
        "accel_y": row.accel_y,
        "accel_z": row.accel_z,
        "gyro_x": row.gyro_x,
        "gyro_y": row.gyro_y,
        "gyro_z": row.gyro_z,
        "pitch": row.pitch,
        "roll": row.roll,
        "acceleration_magnitude": row.acceleration_magnitude,
        "gyro_magnitude": row.gyro_magnitude,
        "max_tilt_angle": row.max_tilt_angle,
        "movement_anomaly_score": row.movement_anomaly_score,
        "possible_impact": row.possible_impact,
        "obstacle_detected": row.obstacle_detected,
        "obstacle_distance_cm": row.obstacle_distance_cm,
        "distance_cm": row.distance_cm if row.distance_cm is not None else row.obstacle_distance_cm,
        "inclination_deg": row.inclination_deg if row.inclination_deg is not None else row.max_tilt_angle,
        "latitude": row.latitude,
        "longitude": row.longitude,
        "telemetry_age_seconds": age_seconds,
        "telemetry_status": status,
        "data_quality_status": row.data_quality_status,
        "data_quality_issues": row.data_quality_issues,
        "missing_sensors": row.missing_sensors,
        "confidence_score": row.confidence_score,
        "risk_score": row.risk_score,
        "risk_level": row.risk_level,
        "explanation": row.explanation,
        "bme280": {
            "temperature_c": row.temperature_c,
            "humidity_pct": row.humidity_pct,
            "pressure_hpa": row.pressure_hpa,
        },
        "jsn_sr04t": {
            "distance_cm": row.distance_cm if row.distance_cm is not None else row.obstacle_distance_cm,
        },
        "mpu6050": {
            "accel_x": row.accel_x,
            "accel_y": row.accel_y,
            "accel_z": row.accel_z,
            "inclination_deg": row.inclination_deg if row.inclination_deg is not None else row.max_tilt_angle,
            "acceleration_magnitude": row.acceleration_magnitude,
        },
    }


def _risk_label(score: float) -> str:
    if score >= 85:
        return "Critico"
    if score >= 71:
        return "Alto"
    if score >= 41:
        return "Medio"
    return "Baixo"


def _recommendation_text(risk_score: float, payload: Dict[str, Any]) -> str:
    distance_cm = payload.get("obstacle_distance_cm")
    inclination = payload.get("max_tilt_angle", payload.get("inclinacao"))
    if distance_cm is not None and float(distance_cm) <= settings.iot_distance_critical_cm:
        return "Parar o equipamento, isolar o obstaculo detectado pelo JSN-SR04T e liberar a faixa antes de retomar."
    if inclination is not None and abs(float(inclination)) >= settings.iot_inclination_critical_deg:
        return "Pausar a operacao, reduzir carga e reposicionar o equipamento antes de retomar em terreno inclinado."
    if bool(payload.get("possible_impact")):
        return "Parar em local seguro e inspecionar implementos, pneus e estrutura apos o possivel impacto detectado."
    if payload.get("temperatura_c") is not None and float(payload["temperatura_c"]) >= settings.high_temperature_c:
        return "Reduzir a carga operacional, monitorar o equipamento e programar uma pausa por temperatura elevada."
    if risk_score >= 71:
        return (
            "Interromper ou replanejar a operação; reduzir velocidade; "
            "evitar bordas próximas à água; aguardar melhora do clima."
        )
    if risk_score >= 41:
        return "Operar com cautela; reduzir velocidade; revisar rota; monitorar terreno e umidade."
    return "Operação liberada com monitoramento padrão e atenção a mudanças de clima."


def _latest_usable_iot_context(
    db: Session,
    equipment_id: int,
):
    """Return a recent valid physical reading without trusting request-side sensor fields."""
    equipment = db.query(models.Equipment).filter(models.Equipment.id == equipment_id).first()
    if not equipment:
        return None
    farm = db.query(models.Farm).filter(models.Farm.id == equipment.farm_id).first()
    if not farm:
        return None
    rows = (
        db.query(models.IotTelemetry)
        .filter(
            models.IotTelemetry.equipment_id == equipment_id,
            models.IotTelemetry.data_quality_status.in_(("VALID", "PARTIAL")),
        )
        .order_by(desc(models.IotTelemetry.received_at), desc(models.IotTelemetry.id))
        .all()
    )
    for row in rows:
        context = risk_context_from_telemetry(row, equipment, farm)
        if context.is_usable:
            return context
    return None


def _with_latest_iot_context(payload: TelemetryInput, db: Session) -> TelemetryInput:
    if payload.iot_used:
        return payload
    context = _latest_usable_iot_context(db, payload.equipment_id)
    if context is None:
        return payload
    return TelemetryInput(**apply_risk_context(payload.model_dump(), context))


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

    if data.get("temperatura_c") is None and weather.get("temperature") is not None:
        data["temperatura_c"] = weather.get("temperature")
    if data.get("umidade_ar") is None and weather.get("humidity") is not None:
        data["umidade_ar"] = weather.get("humidity")
    if data.get("pressao_hpa") is None and weather.get("pressure_hpa") is not None:
        data["pressao_hpa"] = weather.get("pressure_hpa")

    data["solo_instavel"] = int(data["solo_instavel"])
    return data


def _model_feature_names() -> list[str]:
    if MODEL_BUNDLE and MODEL_BUNDLE.get("feature_names"):
        return list(MODEL_BUNDLE["feature_names"])
    return list(FEATURE_ORDER)


def _feature_vector(features: Dict[str, float]) -> np.ndarray:
    names = _model_feature_names()
    return np.array([[float(features.get(name, 0.0)) for name in names]])


def _equipment_history_signal(db: Session, equipment_id: int) -> float:
    rows = (
        db.query(models.TelemetryRecord)
        .filter(models.TelemetryRecord.equipment_id == equipment_id)
        .order_by(desc(models.TelemetryRecord.timestamp))
        .limit(80)
        .all()
    )
    if not rows:
        return 0.0

    scores = [float(row.predicted_risk or 0) for row in rows]
    high_count = sum(1 for score in scores if score >= 70)
    avg_recent = sum(scores[:10]) / min(len(scores), 10)
    history_score = high_count * 0.9 + max(0.0, avg_recent - 55) * 0.08
    return round(min(100.0, history_score), 2)


def _ensure_farm_and_equipment(
    db: Session,
    payload: Dict[str, Any],
) -> tuple[models.Client, models.Farm, models.Equipment]:
    farm_id = int(payload.get("farm_id") or 1)
    equipment_id = int(payload.get("equipment_id") or 1)
    region = str(payload.get("region") or settings.default_region)
    latitude = float(payload.get("latitude") or settings.openweather_lat)
    longitude = float(payload.get("longitude") or settings.openweather_lon)
    device_id = payload.get("device_id")

    farm = db.query(models.Farm).filter(models.Farm.id == farm_id).first()
    client = farm.client if farm and farm.client else None
    if client is None:
        client_name = str(payload.get("client_name") or settings.default_client).strip()
        client = db.query(models.Client).filter(models.Client.name == client_name).order_by(models.Client.id).first()
        if client is None:
            client = models.Client(
                name=client_name,
                region=region,
                client_type=models.ClientType.COMPANY,
                status=models.ClientStatus.ACTIVE,
            )
            db.add(client)
            db.flush()

    if not farm:
        farm = models.Farm(
            id=farm_id,
            client_id=client.id,
            name=f"Fazenda {farm_id}",
            region=region,
            latitude=latitude,
            longitude=longitude,
        )
        db.add(farm)
        db.flush()
    else:
        farm.client_id = client.id
        farm.region = region or farm.region
        farm.latitude = latitude
        farm.longitude = longitude

    equipment = db.query(models.Equipment).filter(models.Equipment.id == equipment_id).first()
    if not equipment:
        equipment = models.Equipment(
            id=equipment_id,
            name=str(device_id or f"Equipamento {equipment_id}"),
            equipment_type="ESP32" if device_id else "Equipamento",
            client_name=client.name,
            farm_id=farm_id,
        )
        db.add(equipment)
        db.flush()

    return client, farm, equipment


def _risk_level_for_score(risk_score: float) -> models.RiskLevel:
    if risk_score >= 85:
        return models.RiskLevel.CRITICAL
    if risk_score >= 71:
        return models.RiskLevel.HIGH
    if risk_score >= 41:
        return models.RiskLevel.MEDIUM
    return models.RiskLevel.LOW


def _recommendation_priority_for_score(risk_score: float) -> models.RecommendationPriority:
    if risk_score >= 85:
        return models.RecommendationPriority.CRITICAL
    if risk_score >= 71:
        return models.RecommendationPriority.HIGH
    if risk_score >= 41:
        return models.RecommendationPriority.MEDIUM
    return models.RecommendationPriority.LOW


def _alert_severity(value: Any) -> models.AlertSeverity:
    try:
        return models.AlertSeverity(str(value).upper())
    except ValueError:
        return models.AlertSeverity.INFO


def _persist_normalized_prediction(
    db: Session,
    *,
    client: models.Client,
    farm: models.Farm,
    equipment: models.Equipment,
    full_payload: dict[str, Any],
    risk_score: float,
    risk_components: dict[str, Any],
    recommendation: str,
    alerts: list[dict[str, Any]],
    decision_support: dict[str, Any],
    explainable_ai: dict[str, Any] | None = None,
    telemetry_id: int | None = None,
    persist_alerts: bool = True,
    audit: bool = True,
) -> models.RiskPrediction:
    component_specs = (
        ("model_risk", "model", "model_risk_score"),
        ("geospatial_adjustment", "geospatial", "geo_adjustment_points"),
        ("operational_interaction", "operation", "interaction_risk_points"),
    )
    component_values: list[tuple[str, str, float]] = []
    for factor_name, category, key in component_specs:
        try:
            component_values.append((factor_name, category, float(risk_components.get(key, 0))))
        except (TypeError, ValueError):
            continue

    factors = [
        RiskPredictionFactorCreate(
            factor_name=factor_name,
            factor_category=category,
            raw_value=value,
            impact_score=value,
        )
        for factor_name, category, value in component_values
    ]
    category_by_factor = {
        "temperature": "iot_bme280",
        "humidity": "iot_bme280",
        "pressure": "iot_bme280",
        "obstacle": "iot_jsn_sr04t",
        "tilt": "iot_mpu6050",
        "movement_anomaly": "iot_mpu6050",
        "possible_impact": "iot_mpu6050",
        "telemetry_freshness": "iot_quality",
    }
    for factor in (explainable_ai or {}).get("factors", []):
        try:
            raw_value = factor.get("value")
            if isinstance(raw_value, bool):
                raw_value = float(raw_value)
            elif raw_value is not None:
                raw_value = float(raw_value)
            impact = float(factor.get("impact_points", 0) or 0)
        except (AttributeError, TypeError, ValueError):
            continue
        if impact <= 0:
            continue
        factor_name = str(factor.get("factor") or "sensor_signal")
        factors.append(
            RiskPredictionFactorCreate(
                factor_name=factor_name,
                factor_category=category_by_factor.get(factor_name, "context"),
                raw_value=raw_value,
                unit=str(factor.get("unit") or "") or None,
                impact_score=impact,
                explanation=str(factor.get("explanation") or "") or None,
            )
        )

    total_impact = sum(abs(float(factor.impact_score or 0)) for factor in factors)
    for factor in factors:
        impact = abs(float(factor.impact_score or 0))
        factor.importance_pct = round(impact * 100 / total_impact, 2) if total_impact else 0.0

    main_risk_factor = (explainable_ai or {}).get("main_factor")
    if not main_risk_factor and factors:
        main_risk_factor = max(factors, key=lambda item: abs(float(item.impact_score or 0))).factor_name
    model_version = (
        db.query(models.ModelVersion)
        .filter(models.ModelVersion.version == settings.model_version)
        .order_by(desc(models.ModelVersion.id))
        .first()
    )

    normalized_alerts = [
        DatabaseAlertCreate(
            client_id=client.id,
            farm_id=farm.id,
            equipment_id=equipment.id,
            alert_type=str(alert.get("type") or "risk_alert"),
            severity=_alert_severity(alert.get("severity")),
            title=str(alert.get("type") or "risk_alert").replace("_", " ").title(),
            message=str(alert.get("message") or "Alerta de risco operacional."),
        )
        for alert in alerts
    ] if persist_alerts else []

    return create_risk_prediction_bundle(
        db,
        prediction_data=RiskPredictionCreate(
            client_id=client.id,
            farm_id=farm.id,
            equipment_id=equipment.id,
            risk_score=risk_score,
            risk_level=_risk_level_for_score(risk_score),
            confidence_score=float(risk_components.get("confidence", 0) or 0) * 100,
            main_risk_factor=main_risk_factor,
            model_version_id=model_version.id if model_version else None,
            telemetry_id=telemetry_id,
            input_snapshot_json=full_payload,
            explanation_summary=str(decision_support.get("why") or ""),
            recommendation_summary=recommendation,
            factors=factors,
        ),
        alerts=normalized_alerts,
        recommendations=[
            RecommendationCreate(
                risk_prediction_id=0,
                equipment_id=equipment.id,
                recommendation_type=models.RecommendationType.OPERATIONAL,
                title="Recomendacao operacional",
                description=recommendation,
                expected_risk_reduction_pct=None,
                priority=_recommendation_priority_for_score(risk_score),
            )
        ],
        commit=False,
        audit=audit,
    )


def _infer_climate_from_esp(payload: ESPTelemetryInput) -> str:
    chuva_mm = float(payload.chuva_mm or 0)
    umidade_ar = float(payload.umidade_ar or 0)
    if chuva_mm >= 20:
        return "tempestade"
    if chuva_mm >= 5:
        return "chuva"
    if chuva_mm > 0:
        return "garoa"
    if umidade_ar >= 82:
        return "nublado"
    return "sol"


def _normalize_esp_payload(payload: ESPTelemetryInput, db: Session) -> TelemetryInput:
    inclinacoes = [
        abs(float(value))
        for value in (payload.inclinacao, payload.pitch_deg, payload.roll_deg)
        if value is not None
    ]
    inclinacao = max(inclinacoes) if inclinacoes else 0.0

    umidade_solo = payload.umidade_solo
    if umidade_solo is None:
        umidade_solo = min(100.0, max(0.0, float(payload.umidade_ar or 65) * 0.72 + float(payload.chuva_mm or 0) * 1.6))

    solo_instavel = payload.solo_instavel
    if solo_instavel is None:
        solo_instavel = int(float(umidade_solo) >= 80 and (float(payload.chuva_mm or 0) >= 5 or inclinacao >= 10))

    historico = payload.historico_sinistros
    if historico is None:
        historico = _equipment_history_signal(db, payload.equipment_id)

    return TelemetryInput(
        equipment_id=payload.equipment_id,
        farm_id=payload.farm_id,
        region=payload.region,
        operation_type=payload.operation_type,
        clima=_infer_climate_from_esp(payload),
        umidade_solo=float(umidade_solo),
        inclinacao=float(inclinacao),
        distancia_agua=float(payload.distancia_agua if payload.distancia_agua is not None else 999.0),
        velocidade=float(payload.velocidade or 0.0),
        historico_sinistros=float(historico or 0.0),
        chuva_mm=float(payload.chuva_mm or 0.0),
        solo_instavel=int(solo_instavel or 0),
        latitude=payload.latitude,
        longitude=payload.longitude,
        device_id=payload.device_id,
        device_identifier=payload.device_id,
        temperatura_c=payload.temperatura_c,
        umidade_ar=payload.umidade_ar,
        pressao_hpa=payload.pressao_hpa,
        distancia_obstaculo=payload.distancia_obstaculo,
        gps_accuracy_m=payload.gps_accuracy_m,
        gps_satellites=payload.gps_satellites,
        battery_voltage=payload.battery_voltage,
    )


def _persist_sensor_reading(
    db: Session,
    raw_payload: ESPTelemetryInput,
    normalized_payload: TelemetryInput,
    prediction: PredictionResponse,
) -> None:
    db.add(
        models.SensorReading(
            device_id=raw_payload.device_id,
            equipment_id=raw_payload.equipment_id,
            farm_id=raw_payload.farm_id,
            latitude=raw_payload.latitude,
            longitude=raw_payload.longitude,
            gps_accuracy_m=raw_payload.gps_accuracy_m,
            gps_satellites=raw_payload.gps_satellites,
            temperatura_c=raw_payload.temperatura_c,
            umidade_ar=raw_payload.umidade_ar,
            pressao_hpa=raw_payload.pressao_hpa,
            umidade_solo=raw_payload.umidade_solo,
            inclinacao=normalized_payload.inclinacao,
            distancia_obstaculo=raw_payload.distancia_obstaculo,
            distancia_agua=raw_payload.distancia_agua,
            velocidade=raw_payload.velocidade,
            chuva_mm=raw_payload.chuva_mm,
            battery_voltage=raw_payload.battery_voltage,
            predicted_risk=prediction.risk_score,
            risk_label=prediction.risk_label,
            raw_payload=raw_payload.model_dump(),
            normalized_payload=normalized_payload.model_dump(),
        )
    )
    db.commit()


@app.get("/")
def root():
    return {
        "app": settings.app_name,
        "version": settings.model_version,
        "status": "running",
        "docs": "/docs",
        "dashboard_hint": "Use a interface Streamlit para visualizar risco, alertas e relatórios.",
    }


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="12" fill="#071016"/><path d="M14 46 30 12h4l16 34h-8l-3-7H25l-3 7h-8Zm14-14h8l-4-10-4 10Z" fill="#8cffb2"/><path d="M43 18h7v28h-7z" fill="#49ead8"/></svg>"""
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


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
    payload: dict,
    policy,
    current_alert_level: str,
    current_recommendation: str,
):
    if not policy or not getattr(policy, "is_active", True):
        return current_alert_level, current_recommendation, []

    alerts = []
    reasons = []
    should_block = False

    velocidade = float(payload.get("velocidade", 0))
    inclinacao = float(payload.get("inclinacao", 0))
    chuva_mm = float(payload.get("chuva_mm", 0))
    distancia_agua = float(payload.get("distancia_agua", 999999))
    solo_instavel = int(payload.get("solo_instavel", 0))

    min_risk_alert = float(getattr(policy, "min_risk_alert", 40))
    min_risk_block = float(getattr(policy, "min_risk_block", 70))
    max_speed = float(getattr(policy, "max_speed", 999999))
    max_slope = float(getattr(policy, "max_slope", 999999))
    min_distance_water = float(getattr(policy, "min_distance_water", 0))
    max_rain_mm = float(getattr(policy, "max_rain_mm", 999999))
    block_on_water = bool(getattr(policy, "block_on_water", False))
    block_on_unstable_soil = bool(getattr(policy, "block_on_unstable_soil", False))

    if risk_score >= min_risk_alert:
        alerts.append(
            {
                "type": "policy_alert_threshold",
                "severity": "medium",
                "message": f"Score acima do limite de alerta da política ({min_risk_alert}).",
            }
        )

    if velocidade > max_speed:
        reasons.append(f"velocidade acima do limite ({max_speed})")
        alerts.append(
            {
                "type": "policy_speed",
                "severity": "medium",
                "message": f"Velocidade acima do limite da política ({max_speed}).",
            }
        )

    if inclinacao > max_slope:
        reasons.append(f"inclinação acima do limite ({max_slope})")
        alerts.append(
            {
                "type": "policy_slope",
                "severity": "medium",
                "message": f"Inclinação acima do limite da política ({max_slope}).",
            }
        )

    if chuva_mm > max_rain_mm:
        reasons.append(f"chuva acima do limite ({max_rain_mm} mm)")
        alerts.append(
            {
                "type": "policy_rain",
                "severity": "medium",
                "message": f"Chuva acima do limite da política ({max_rain_mm} mm).",
            }
        )

    if distancia_agua < min_distance_water:
        reasons.append(f"distância da água abaixo do mínimo ({min_distance_water} m)")
        alerts.append(
            {
                "type": "policy_water_distance",
                "severity": "medium",
                "message": f"Distância da água abaixo do mínimo da política ({min_distance_water} m).",
            }
        )
        if block_on_water:
            should_block = True

    if solo_instavel == 1 and block_on_unstable_soil:
        reasons.append("solo instável com bloqueio habilitado")
        alerts.append(
            {
                "type": "policy_unstable_soil",
                "severity": "high",
                "message": "Solo instável com bloqueio habilitado na política.",
            }
        )
        should_block = True

    if risk_score >= min_risk_block:
        reasons.append(f"score acima do limite de bloqueio ({min_risk_block})")
        should_block = True

    if should_block:
        alert_level = "🚫 Operação bloqueada por política"
        if reasons:
            recommendation = "Operação bloqueada pela política configurada. Motivos: " + "; ".join(reasons) + "."
        else:
            recommendation = "Operação bloqueada pela política configurada."
        alerts.append(
            {
                "type": "policy_block",
                "severity": "high",
                "message": recommendation,
            }
        )
        return alert_level, recommendation, alerts

    if alerts:
        recommendation = current_recommendation
        if reasons:
            recommendation = current_recommendation + " Ajustes sugeridos: " + "; ".join(reasons) + "."
        return current_alert_level, recommendation, alerts

    return current_alert_level, current_recommendation, alerts

@app.post("/api/v1/auth/login", response_model=TokenResponse)
def auth_login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = authenticate_user(db, payload.username, payload.password)

    if not user:
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
                role=get_primary_role(user),
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

    primary_role = get_primary_role(user)
    permissions = sorted(get_user_permissions(user))
    access_token = create_access_token({"sub": user.username, "role": primary_role})

    if isinstance(user, models.User):
        user.last_login_at = datetime.utcnow()
    db.add(
        models.AccessEvent(
            username=user.username,
            role=primary_role,
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
        role=primary_role,
        permissions=permissions,
    )

@app.post("/api/v1/auth/token", response_model=TokenResponse)
def auth_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = authenticate_user(db, form_data.username, form_data.password)

    if not user:
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
                role=get_primary_role(user),
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

    primary_role = get_primary_role(user)
    permissions = sorted(get_user_permissions(user))
    access_token = create_access_token({"sub": user.username, "role": primary_role})

    if isinstance(user, models.User):
        user.last_login_at = datetime.utcnow()
    db.add(
        models.AccessEvent(
            username=user.username,
            role=primary_role,
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
        role=primary_role,
        permissions=permissions,
    )


@app.get("/api/v1/auth/me", response_model=MeResponse)
def auth_me(current_user=Depends(get_current_user)):
    return MeResponse(
        id=getattr(current_user, "id", None),
        username=current_user.username,
        full_name=current_user.full_name,
        email=current_user.email,
        role=get_primary_role(current_user),
        roles=get_user_roles(current_user),
        permissions=sorted(get_user_permissions(current_user)),
        is_active=current_user.is_active,
        status=getattr(current_user, "status", None),
        last_login_at=current_user.last_login_at,
        created_at=getattr(current_user, "created_at", None),
    )


@app.post("/api/v1/auth/logout")
def auth_logout(
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.add(
        models.AccessEvent(
            username=current_user.username,
            role=get_primary_role(current_user),
            action="logout",
            endpoint=str(request.url.path),
            success=True,
            detail={"message": "logout_registrado"},
        )
    )
    db.commit()
    return {"status": "ok"}


@app.post("/api/v1/auth/change-password")
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not isinstance(current_user, models.User):
        raise HTTPException(status_code=400, detail="Usuario legado deve ser migrado antes de alterar senha.")
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Senha atual invalida.")
    current_user.password_hash = hash_password(payload.new_password)
    current_user.updated_at = datetime.utcnow()
    db.add(
        models.AccessEvent(
            username=current_user.username,
            role=get_primary_role(current_user),
            action="change_password",
            endpoint=str(request.url.path),
            success=True,
            detail={"message": "senha_alterada"},
        )
    )
    db.add(
        models.AuditLog(
            actor=current_user.username,
            action="change_password",
            payload={"user_id": current_user.id},
        )
    )
    db.commit()
    return {"status": "ok"}


@app.get("/api/v1/auth/access-events")
def auth_access_events(
    current_user=Depends(require_permission("audit.view")),
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


@app.get("/api/v1/admin/roles")
def admin_roles(
    current_user=Depends(require_permission("users.view")),
    db: Session = Depends(get_db),
):
    roles = db.query(models.Role).order_by(models.Role.name).all()
    return [_serialize_role(role) for role in roles]


@app.get("/api/v1/admin/permissions")
def admin_permissions(
    current_user=Depends(require_permission("users.view")),
    db: Session = Depends(get_db),
):
    permissions = db.query(models.Permission).order_by(models.Permission.code).all()
    return [
        {"id": permission.id, "code": permission.code, "description": permission.description}
        for permission in permissions
    ]


@app.get("/api/v1/admin/users", response_model=list[UserResponse])
def admin_list_users(
    q: str | None = None,
    role: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    client: str | None = None,
    farm_id: int | None = None,
    current_user=Depends(require_permission("users.view")),
    db: Session = Depends(get_db),
):
    query = db.query(models.User)
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                models.User.name.ilike(like),
                models.User.email.ilike(like),
                models.User.username.ilike(like),
            )
        )
    if status_filter:
        query = query.filter(models.User.status == status_filter)
    users = query.order_by(desc(models.User.created_at)).all()

    rows = []
    for user in users:
        serialized = _serialize_user(user)
        if role and normalize_role(role) not in serialized["roles"]:
            continue
        if client and not any(scope.get("client_name") == client for scope in serialized["access_scopes"]):
            continue
        if farm_id and not any(scope.get("farm_id") == farm_id for scope in serialized["access_scopes"]):
            continue
        rows.append(serialized)
    return rows


@app.post("/api/v1/admin/users", response_model=UserResponse)
def admin_create_user(
    payload: UserCreate,
    current_user=Depends(require_permission("users.create")),
    db: Session = Depends(get_db),
):
    existing = (
        db.query(models.User)
        .filter(or_(models.User.username == payload.username, models.User.email == payload.email))
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Username ou email ja cadastrado.")

    user = models.User(
        name=payload.name,
        email=payload.email,
        username=payload.username,
        password_hash=hash_password(payload.password),
        status=payload.status,
        is_active=payload.is_active,
    )
    db.add(user)
    db.flush()
    _sync_user_roles(db, user, payload.roles)
    _sync_user_permission_overrides(db, user, payload.permissions_add, payload.permissions_remove)
    _replace_access_scopes(db, user, payload.access_scopes)
    db.add(
        models.AuditLog(
            actor=current_user.username,
            action="user_created",
            payload={"user_id": user.id, "username": user.username, "roles": get_user_roles(user)},
        )
    )
    db.commit()
    db.refresh(user)
    return _serialize_user(user)


@app.get("/api/v1/admin/users/{user_id}", response_model=UserResponse)
def admin_get_user(
    user_id: int,
    current_user=Depends(require_permission("users.view")),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado.")
    return _serialize_user(user)


@app.put("/api/v1/admin/users/{user_id}", response_model=UserResponse)
def admin_update_user(
    user_id: int,
    payload: UserUpdate,
    current_user=Depends(require_permission("users.edit")),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado.")

    update_data = payload.model_dump(exclude_unset=True)
    if "username" in update_data or "email" in update_data:
        new_username = update_data.get("username", user.username)
        new_email = update_data.get("email", user.email)
        duplicate = (
            db.query(models.User)
            .filter(models.User.id != user.id)
            .filter(or_(models.User.username == new_username, models.User.email == new_email))
            .first()
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="Username ou email ja cadastrado.")

    for field in ("name", "email", "username", "status", "is_active"):
        if field in update_data:
            setattr(user, field, update_data[field])

    if payload.password:
        user.password_hash = hash_password(payload.password)
    if payload.roles is not None:
        _sync_user_roles(db, user, payload.roles)
    _sync_user_permission_overrides(db, user, payload.permissions_add, payload.permissions_remove)
    if payload.access_scopes is not None:
        _replace_access_scopes(db, user, payload.access_scopes)
    user.updated_at = datetime.utcnow()
    db.add(
        models.AuditLog(
            actor=current_user.username,
            action="user_updated",
            payload={"user_id": user.id, "username": user.username, "password_changed": bool(payload.password)},
        )
    )
    db.commit()
    db.refresh(user)
    return _serialize_user(user)


@app.put("/api/v1/admin/users/{user_id}/permissions", response_model=UserResponse)
def admin_update_user_permissions(
    user_id: int,
    payload: UserPermissionUpdate,
    current_user=Depends(require_permission("users.edit")),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado.")
    _sync_user_permission_overrides(db, user, payload.permissions_add, payload.permissions_remove)
    user.updated_at = datetime.utcnow()
    db.add(
        models.AuditLog(
            actor=current_user.username,
            action="user_permissions_updated",
            payload={
                "user_id": user.id,
                "permissions_add": payload.permissions_add,
                "permissions_remove": payload.permissions_remove,
            },
        )
    )
    db.commit()
    db.refresh(user)
    return _serialize_user(user)


@app.post("/api/v1/admin/users/{user_id}/reset-password")
def admin_reset_user_password(
    user_id: int,
    payload: ResetPasswordRequest,
    current_user=Depends(require_permission("users.edit")),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado.")
    user.password_hash = hash_password(payload.new_password)
    user.updated_at = datetime.utcnow()
    db.add(
        models.AuditLog(
            actor=current_user.username,
            action="user_password_reset",
            payload={"user_id": user.id, "username": user.username},
        )
    )
    db.commit()
    return {"status": "ok"}


@app.delete("/api/v1/admin/users/{user_id}")
def admin_delete_user(
    user_id: int,
    current_user=Depends(require_permission("users.delete")),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado.")
    user.is_active = False
    user.status = "deleted"
    user.updated_at = datetime.utcnow()
    db.add(
        models.AuditLog(
            actor=current_user.username,
            action="user_deleted",
            payload={"user_id": user.id, "username": user.username},
        )
    )
    db.commit()
    return {"status": "deleted", "user_id": user.id}


def _predict(
    payload: TelemetryInput,
    db: Session,
    *,
    commit: bool = True,
    iot_telemetry_record: models.IotTelemetry | None = None,
    audit: bool = True,
) -> PredictionResponse:
    payload = _with_latest_iot_context(payload, db)
    weather = get_weather(payload.latitude, payload.longitude)
    full_payload = _prepare_prediction(payload, weather)
    operational_context = {}

    geo_context = build_geo_context(
        latitude=float(full_payload.get("latitude", 0)),
        longitude=float(full_payload.get("longitude", 0)),
        solo_instavel=int(full_payload.get("solo_instavel", 0)),
        inclinacao=float(full_payload.get("inclinacao", 0)),
        gps_accuracy_m=full_payload.get("gps_accuracy_m"),
    )
    full_payload["distancia_agua_manual"] = full_payload.get("distancia_agua", 0)
    full_payload["distancia_agua"] = float(
        geo_context.get("nearest_water", {}).get(
            "distance_m",
            full_payload.get("distancia_agua", 0),
        )
    )
    if isinstance(full_payload.get("iot_snapshot"), dict):
        iot_snapshot = dict(full_payload["iot_snapshot"])
        iot_snapshot["weather"] = {
            "source": weather.get("source"),
            "temperature_c": weather.get("temperature"),
            "humidity_pct": weather.get("humidity"),
            "pressure_hpa": weather.get("pressure_hpa"),
            "rain_mm_1h": weather.get("rain_mm_1h"),
        }
        iot_snapshot["terrain"] = {
            "nearest_water_m": geo_context.get("nearest_water", {}).get("distance_m"),
            "geo_zone": geo_context.get("geo_risk", {}).get("geo_zone"),
        }
        iot_snapshot["history"] = {
            "equipment_risk_signal": _equipment_history_signal(db, payload.equipment_id),
        }
        full_payload["iot_snapshot"] = iot_snapshot

    operational_context = build_operational_context(
        input_payload=payload.model_dump(),
        weather=weather,
        geo_context=geo_context,
    )

    features = build_features(full_payload)
    model_risk_score = float(predict_risk(MODEL_BUNDLE, features))
    risk_components = calculate_contextual_risk(
        model_risk_score=model_risk_score,
        payload=full_payload,
        geo_context=geo_context,
        weather=weather,
    )
    risk_score = float(risk_components["final_risk_score"])

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
        _feature_vector(features),
        _feature_vector(features),
        _model_feature_names(),
    )
    if not explanation:
        explanation = heuristic_explanation(full_payload, risk_score)

    explainable_ai = build_structured_explanation(
        payload=full_payload,
        risk_score=risk_score,
        risk_label=risk_label,
        recommendation=recommendation,
        risk_components=risk_components,
    )

    decision_support = build_decision_support(
        risk_score=risk_score,
        risk_label=risk_label,
        alert_level=alert_level,
        payload=full_payload,
        risk_components=risk_components,
        alerts=alerts,
        recommendation=recommendation,
        route=route,
        explanation=explanation,
        geo_context=geo_context,
    )

    executive_explanation = build_executive_explanation(
        risk_score=risk_score,
        risk_label=risk_label,
        explanation=explanation,
        recommendation=recommendation,
        decision_support=decision_support,
        safe_route=route,
    )

    prediction_trace = build_prediction_trace(
        model_version=settings.model_version,
        features=features,
        risk_components=risk_components,
        explanation=explanation,
        safe_route=route,
        recommendation=recommendation,
        decision_support=decision_support,
    )

    audit_id = 0
    if audit:
        audit_id = write_audit(
            db,
            actor="api",
            action="risk_predict",
            payload={
                "operational_context": operational_context,
                "prediction_trace": prediction_trace,
                "risk_score": risk_score,
                "risk_label": risk_label,
                "alert_level": alert_level,
                "decision_support": decision_support,
            },
        )

    client, farm, equipment = _ensure_farm_and_equipment(db, full_payload)

    prediction_record = models.PredictionRecord(
        model_version=settings.model_version,
        source="esp32" if full_payload.get("device_id") else "api",
        input_payload=full_payload,
        predicted_risk=risk_score,
        risk_label=risk_label,
        alert_level=alert_level,
        explanation=explainable_ai,
        recommendation=recommendation,
        safe_route=route["recommended_route"],
        weather_payload=weather,
    )
    db.add(prediction_record)
    db.flush()

    legacy_telemetry_record = models.TelemetryRecord(
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
    db.add(legacy_telemetry_record)
    db.flush()

    for a in alerts:
        if iot_telemetry_record is not None and risk_score < 71:
            continue
        db.add(
            models.AlertRecord(
                alert_type=a["type"],
                severity=a["severity"],
                message=a["message"],
                context=full_payload,
                equipment_id=payload.equipment_id,
                device_id=full_payload.get("device_id"),
                # The normalized prediction owns the canonical telemetry link.
                # Keep the legacy alert record independent to avoid coupling
                # historical alert storage to the evolving IoT schema.
                telemetry_id=None,
                risk_prediction_id=prediction_record.id,
            )
        )

    normalized_prediction = _persist_normalized_prediction(
        db,
        client=client,
        farm=farm,
        equipment=equipment,
        full_payload=full_payload,
        risk_score=risk_score,
        risk_components=risk_components,
        recommendation=recommendation,
        alerts=alerts,
        decision_support=decision_support,
        explainable_ai=explainable_ai,
        telemetry_id=iot_telemetry_record.id if iot_telemetry_record else full_payload.get("telemetry_id"),
        persist_alerts=iot_telemetry_record is None,
        audit=audit,
    )
    if iot_telemetry_record is not None:
        iot_telemetry_record.risk_score = risk_score
        iot_telemetry_record.risk_level = risk_label
        iot_telemetry_record.confidence_score = round(float(risk_components.get("confidence", 0)) * 100, 2)
        iot_telemetry_record.explanation = explainable_ai
        iot_telemetry_record.risk_prediction_id = prediction_record.id
    if commit:
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
        explainable_ai=explainable_ai,
        executive_explanation=executive_explanation,
        geo_context=geo_context,
        risk_components=risk_components,
        decision_support=decision_support,
        confidence_score=round(float(risk_components.get("confidence", 0)) * 100, 2),
        telemetry_status=full_payload.get("telemetry_status"),
        data_quality_status=full_payload.get("data_quality_status"),
        iot_used=bool(full_payload.get("iot_used")),
        weather=weather,
        audit_id=audit_id,
        telemetry_id=iot_telemetry_record.id if iot_telemetry_record else full_payload.get("telemetry_id"),
        main_factor=explainable_ai.get("main_factor"),
        factors=explainable_ai.get("factors", []),
        summary=explainable_ai.get("summary"),
        normalized_prediction_id=normalized_prediction.id,
    )


@app.post("/api/v1/risk/predict", response_model=PredictionResponse)
def predict(
    payload: TelemetryInput,
    current_user=Depends(require_permission("risk.predict")),
    db: Session = Depends(get_db),
):
    equipment = db.query(models.Equipment).filter(models.Equipment.id == payload.equipment_id).first()
    if equipment:
        _assert_equipment_scope(current_user, equipment)
    return _predict(payload, db)


def _authenticate_iot_device(
    db: Session,
    payload: IotTelemetryInput,
    x_device_id: str | None,
    x_api_key: str | None,
) -> models.IotDevice:
    header_device_id = (x_device_id or "").strip()
    body_device_id = payload.device_id.strip()
    development_bypass = (
        not settings.iot_auth_enabled
        and settings.environment in {"development", "dev", "test", "testing"}
    )
    if development_bypass and not header_device_id:
        header_device_id = body_device_id
    if (not header_device_id or not x_api_key) and not development_bypass:
        raise HTTPException(status_code=401, detail="Headers X-Device-ID e X-API-Key sao obrigatorios.")
    if header_device_id != body_device_id:
        raise HTTPException(status_code=403, detail="Device ID do header diverge do payload.")

    device = db.query(models.IotDevice).filter(models.IotDevice.device_id == header_device_id).first()
    if not device:
        raise HTTPException(status_code=401, detail="Dispositivo desconhecido.")
    if str(device.status).upper() == "DISABLED" or not device.is_active:
        raise HTTPException(status_code=403, detail="Dispositivo desativado.")
    if device.api_key_revoked_at is not None:
        raise HTTPException(status_code=401, detail="API key revogada.")
    if not development_bypass and not verify_api_key(x_api_key or "", device.api_key_hash):
        raise HTTPException(status_code=401, detail="API key invalida.")
    return device


def _check_device_rate_limit(device_id: str) -> None:
    limit = max(1, int(settings.iot_rate_limit_per_minute))
    now = datetime.utcnow().timestamp()
    window_start = now - 60.0
    recent = [item for item in DEVICE_RATE_LIMIT.get(device_id, []) if item >= window_start]
    if len(recent) >= limit:
        DEVICE_RATE_LIMIT[device_id] = recent
        raise HTTPException(
            status_code=429,
            detail="Rate limit do dispositivo excedido.",
            headers={"Retry-After": "60"},
        )
    recent.append(now)
    DEVICE_RATE_LIMIT[device_id] = recent


def _persist_iot_telemetry(
    db: Session,
    device: models.IotDevice,
    payload: IotTelemetryInput,
    context: dict[str, Any],
) -> models.IotTelemetry:
    raw_values = context["raw_values"]
    quality = context["quality"]
    derived = context["derived"]
    recorded_at = normalize_timestamp(raw_values["timestamp"])
    record = models.IotTelemetry(
        device_id=device.device_id,
        iot_device_id=device.id,
        equipment_id=device.equipment_id,
        sequence_number=payload.sequence_number,
        # The legacy column is timezone-naive. The canonical column preserves UTC.
        timestamp=recorded_at.replace(tzinfo=None),
        recorded_at=recorded_at,
        received_at=datetime.utcnow(),
        telemetry_age_seconds=quality["telemetry_age_seconds"],
        telemetry_status=quality["telemetry_status"],
        data_quality_status=quality["data_quality_status"],
        data_quality_issues=quality["data_quality_issues"],
        missing_sensors=quality["missing_sensors"],
        confidence_score=quality["confidence_score"],
        raw_payload=redact_sensitive_fields(payload.model_dump(mode="json")),
        raw_payload_json=redact_sensitive_fields(payload.model_dump(mode="json")),
    )
    db.add(record)

    for field in (
        "temperature_c",
        "humidity_pct",
        "pressure_hpa",
        "altitude_m",
        "accel_x",
        "accel_y",
        "accel_z",
        "gyro_x",
        "gyro_y",
        "gyro_z",
        "pitch",
        "roll",
        "obstacle_detected",
        "obstacle_distance_cm",
        "distance_cm",
        "inclination_deg",
        "latitude",
        "longitude",
    ):
        setattr(record, field, raw_values.get(field))

    record.acceleration_magnitude = derived.get("acceleration_magnitude")
    record.gyro_magnitude = derived.get("gyro_magnitude")
    record.max_tilt_angle = derived.get("max_tilt_angle")
    record.movement_anomaly_score = derived.get("movement_anomaly_score")
    record.possible_impact = bool(derived.get("possible_impact"))
    db.flush()
    return record


def _recent_iot_prediction(
    db: Session,
    device_id: int,
    *,
    excluding_telemetry_id: int,
) -> models.IotTelemetry | None:
    return (
        db.query(models.IotTelemetry)
        .filter(
            models.IotTelemetry.iot_device_id == device_id,
            models.IotTelemetry.id != excluding_telemetry_id,
            models.IotTelemetry.risk_score.is_not(None),
        )
        .order_by(desc(models.IotTelemetry.received_at), desc(models.IotTelemetry.id))
        .first()
    )


def _prediction_interval_elapsed(row: models.IotTelemetry | None) -> bool:
    if row is None or settings.iot_min_prediction_interval_seconds <= 0:
        return True
    received_at = getattr(row, "received_at", None)
    if received_at is None:
        return True
    elapsed = (datetime.now(timezone.utc) - normalize_timestamp(received_at)).total_seconds()
    return elapsed >= settings.iot_min_prediction_interval_seconds


def _event_for_alert(alert_type: str, events: list[models.IotEvent]) -> models.IotEvent | None:
    normalized = alert_type.upper()
    for event in events:
        event_type = event.event_type.upper()
        if normalized == event_type:
            return event
        if "OBSTACLE" in normalized and "OBSTACLE" in event_type:
            return event
        if "TILT" in normalized and "INCLINATION" in event_type:
            return event
        if "IMPACT" in normalized and "ACCELERATION" in event_type:
            return event
        if "TEMPERATURE" in normalized and "TEMPERATURE" in event_type:
            return event
        if "HUMIDITY" in normalized and "HUMIDITY" in event_type:
            return event
    return None


def _persist_iot_events_and_alerts(
    db: Session,
    *,
    device: models.IotDevice,
    telemetry: models.IotTelemetry,
    risk_context,
    prediction: PredictionResponse,
) -> list[models.IotEvent]:
    event_rows: list[models.IotEvent] = []
    for event in build_iot_events(risk_context):
        row = models.IotEvent(
            device_id=device.id,
            equipment_id=device.equipment_id,
            telemetry_id=telemetry.id,
            risk_prediction_id=prediction.normalized_prediction_id,
            **event,
        )
        db.add(row)
        event_rows.append(row)
    db.flush()

    # A normal telemetry sample is evidence, not an alert. Material alerts are
    # kept only when the resulting operational risk is HIGH or CRITICAL.
    if prediction.risk_score < 71 or prediction.normalized_prediction_id is None:
        return event_rows
    normalized_prediction = db.get(models.RiskPrediction, prediction.normalized_prediction_id)
    if normalized_prediction is None:
        return event_rows
    for alert in prediction.alerts:
        if str(alert.get("type", "")).lower() == "operacao_segura":
            continue
        event = _event_for_alert(str(alert.get("type", "")), event_rows)
        db.add(
            models.Alert(
                client_id=normalized_prediction.client_id,
                farm_id=normalized_prediction.farm_id,
                equipment_id=device.equipment_id,
                risk_prediction_id=normalized_prediction.id,
                iot_event_id=event.id if event else None,
                alert_type=str(alert.get("type") or "risk_alert"),
                severity=_alert_severity(alert.get("severity")),
                title=str(alert.get("type") or "risk_alert").replace("_", " ").title(),
                message=str(alert.get("message") or "Alerta de risco operacional."),
            )
        )
    return event_rows


def _ingest_iot_telemetry(
    payload: IotTelemetryInput,
    x_device_id: str | None,
    x_api_key: str | None,
    db: Session,
) -> IotTelemetryResponse:
    if len(payload.model_dump_json()) > settings.iot_max_payload_bytes:
        raise HTTPException(status_code=413, detail="Payload de telemetria muito grande.")

    device = _authenticate_iot_device(db, payload, x_device_id, x_api_key)
    _check_device_rate_limit(device.device_id)
    equipment = db.query(models.Equipment).filter(models.Equipment.id == device.equipment_id).first()
    if not equipment:
        raise HTTPException(status_code=409, detail="Equipamento vinculado ao dispositivo nao existe.")
    farm = db.query(models.Farm).filter(models.Farm.id == equipment.farm_id).first()
    if not farm:
        raise HTTPException(status_code=409, detail="Fazenda vinculada ao equipamento nao existe.")

    context = build_iot_context(payload, equipment, farm)
    quality = context["quality"]
    if quality["data_quality_status"] == "INVALID":
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Payload sem dados validos de sensores.",
                "issues": quality["data_quality_issues"],
            },
        )
    if payload.sequence_number is not None:
        duplicate = (
            db.query(models.IotTelemetry.id)
            .filter(
                models.IotTelemetry.iot_device_id == device.id,
                models.IotTelemetry.sequence_number == payload.sequence_number,
            )
            .first()
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="Leitura duplicada para este sequence_number.")

    try:
        telemetry_record = _persist_iot_telemetry(db, device, payload, context)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Leitura duplicada para este sequence_number.") from exc

    risk_context = replace(
        context["risk_context"],
        telemetry_id=telemetry_record.id,
        received_at=normalize_timestamp(telemetry_record.received_at),
    )
    preview_events = build_iot_events(risk_context)
    valid_for_prediction = risk_context.is_usable
    previous_prediction = _recent_iot_prediction(
        db,
        device.id,
        excluding_telemetry_id=telemetry_record.id,
    )
    must_predict = valid_for_prediction and (
        _prediction_interval_elapsed(previous_prediction)
        or any(event["severity"] == "CRITICAL" for event in preview_events)
    )

    if valid_for_prediction:
        device.last_seen_at = datetime.utcnow()
        if str(device.status).upper() != "MAINTENANCE":
            device.status = "ONLINE"
    if payload.firmware_version:
        device.firmware_version = payload.firmware_version

    if not must_predict:
        db.commit()
        return IotTelemetryResponse(
            status="accepted",
            telemetry_id=telemetry_record.id,
            equipment_id=device.equipment_id,
            risk_updated=False,
            risk_score=previous_prediction.risk_score if previous_prediction else None,
            risk_level=previous_prediction.risk_level if previous_prediction else None,
            telemetry_status=telemetry_record.telemetry_status,
            data_quality_status=telemetry_record.data_quality_status,
            confidence_score=telemetry_record.confidence_score,
            recorded_at=telemetry_record.recorded_at,
            message=(
                "Telemetria armazenada; previsao mantida pelo intervalo minimo configurado."
                if valid_for_prediction
                else "Telemetria armazenada, mas nao foi usada pela IA por qualidade ou freshness insuficiente."
            ),
        )

    telemetry_input_data = context["telemetry_input"].model_dump()
    telemetry_input_data["telemetry_id"] = telemetry_record.id
    telemetry_input_data["iot_snapshot"] = risk_context.snapshot()
    prediction = _predict(
        TelemetryInput(**telemetry_input_data),
        db,
        commit=False,
        iot_telemetry_record=telemetry_record,
        audit=False,
    )
    event_rows = _persist_iot_events_and_alerts(
        db,
        device=device,
        telemetry=telemetry_record,
        risk_context=risk_context,
        prediction=prediction,
    )
    if any(event.severity == "CRITICAL" for event in event_rows):
        db.add(
            models.AuditLog(
                actor=device.device_id,
                action="iot_critical_event",
                payload={
                    "device_id": device.device_id,
                    "equipment_id": device.equipment_id,
                    "telemetry_id": telemetry_record.id,
                    "events": [event.event_type for event in event_rows if event.severity == "CRITICAL"],
                    "risk_score": prediction.risk_score,
                },
            )
        )
    db.commit()

    return IotTelemetryResponse(
        status="accepted",
        telemetry_id=telemetry_record.id,
        equipment_id=device.equipment_id,
        risk_updated=True,
        risk_score=prediction.risk_score,
        risk_level=prediction.risk_label,
        telemetry_status=telemetry_record.telemetry_status,
        data_quality_status=telemetry_record.data_quality_status,
        confidence_score=prediction.confidence_score,
        recorded_at=telemetry_record.recorded_at,
        events=[
            {
                "event_type": event.event_type,
                "severity": event.severity,
                "value": event.value,
                "unit": event.unit,
                "description": event.description,
            }
            for event in event_rows
        ],
    )


@app.post("/api/v1/iot/telemetry", response_model=IotTelemetryResponse, deprecated=True)
@app.post("/api/v1/telemetry/esp", response_model=IotTelemetryResponse)
def ingest_esp_telemetry(
    payload: IotTelemetryInput,
    x_device_id: str | None = Header(default=None, alias="X-Device-ID"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    return _ingest_iot_telemetry(payload, x_device_id, x_api_key, db)


@app.get("/api/v1/telemetry/sensors/latest")
def latest_sensor_readings(
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return list_sensor_readings_data(db, limit=limit)


@app.post("/api/v1/simulate", response_model=PredictionResponse)
def simulate(payload: ScenarioInput, db: Session = Depends(get_db)):
    weather = get_weather(payload.latitude, payload.longitude)
    simulated = payload.model_dump()
    simulated["clima"] = "chuva" if payload.scenario_name else payload.clima
    simulated["chuva_mm"] = max(payload.chuva_mm, weather.get("rain_mm_1h", 0) * 4 + 10)
    simulated["velocidade"] = max(0, payload.velocidade - 2)
    simulated["umidade_solo"] = min(100, payload.umidade_solo + 8)

    sim_input = TelemetryInput(**simulated)
    return _predict(sim_input, db)


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
        route_explanation=route.get("route_explanation"),
    )


@app.get("/api/v1/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db)):
    return build_summary(db)


@app.get("/api/v1/dashboard/ranking")
def dashboard_ranking(db: Session = Depends(get_db)):
    return build_ranking(db)


@app.get("/api/v1/risk/regions")
def region_risk_scores(db: Session = Depends(get_db)):
    return build_region_risk_scores(db)


@app.get("/api/v1/risk/equipment")
def equipment_risk_scores(db: Session = Depends(get_db)):
    return build_equipment_risk_scores(db)


@app.get("/api/v1/risk/equipment/{equipment_id}/history")
def equipment_risk_history(
    equipment_id: int,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return build_equipment_risk_history(db, equipment_id=equipment_id, limit=limit)


@app.get("/api/v1/dashboard/trends")
def dashboard_trends(db: Session = Depends(get_db)):
    return build_trends(db)


@app.get("/api/v1/dashboard/alerts")
def dashboard_alerts(db: Session = Depends(get_db)):
    return build_alerts_report(db)


@app.get("/api/v1/dashboard/audit")
def dashboard_audit(
    current_user=Depends(require_roles("admin", "sompo")),
    db: Session = Depends(get_db),
):
    return build_audit(db)


@app.get("/api/v1/farms")
def list_farms(db: Session = Depends(get_db)):
    return list_farms_data(db)


@app.get("/api/v1/equipment")
def list_equipment(db: Session = Depends(get_db)):
    return list_equipment_data(db)


@app.get("/api/v1/equipments")
def list_equipments(
    current_user=Depends(require_permission("equipments.view")),
    db: Session = Depends(get_db),
):
    equipment = db.query(models.Equipment).order_by(models.Equipment.id).all()
    return [_serialize_equipment(item) for item in _scoped_equipment(current_user, equipment)]


@app.post("/api/v1/admin/equipments")
def admin_create_equipment(
    payload: EquipmentCreate,
    current_user=Depends(require_permission("equipments.create")),
    db: Session = Depends(get_db),
):
    farm = db.query(models.Farm).filter(models.Farm.id == payload.farm_id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Fazenda nao encontrada.")
    equipment = models.Equipment(
        name=payload.name,
        equipment_type=payload.equipment_type,
        client_name=payload.client_name,
        farm_id=payload.farm_id,
        model=payload.model,
        year=payload.year,
        status=payload.status,
    )
    db.add(equipment)
    db.flush()
    db.add(
        models.AuditLog(
            actor=current_user.username,
            action="equipment_created",
            payload={"equipment_id": equipment.id, "name": equipment.name},
        )
    )
    db.commit()
    db.refresh(equipment)
    return _serialize_equipment(equipment)


@app.put("/api/v1/admin/equipments/{equipment_id}")
def admin_update_equipment(
    equipment_id: int,
    payload: EquipmentUpdate,
    current_user=Depends(require_permission("equipments.edit")),
    db: Session = Depends(get_db),
):
    equipment = db.query(models.Equipment).filter(models.Equipment.id == equipment_id).first()
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipamento nao encontrado.")
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(equipment, field, value)
    db.add(
        models.AuditLog(
            actor=current_user.username,
            action="equipment_updated",
            payload={"equipment_id": equipment.id, "fields": sorted(update_data.keys())},
        )
    )
    db.commit()
    db.refresh(equipment)
    return _serialize_equipment(equipment)


@app.delete("/api/v1/admin/equipments/{equipment_id}")
def admin_delete_equipment(
    equipment_id: int,
    current_user=Depends(require_permission("equipments.delete")),
    db: Session = Depends(get_db),
):
    equipment = db.query(models.Equipment).filter(models.Equipment.id == equipment_id).first()
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipamento nao encontrado.")
    equipment.status = "inactive"
    db.add(
        models.AuditLog(
            actor=current_user.username,
            action="equipment_deactivated",
            payload={"equipment_id": equipment.id, "name": equipment.name},
        )
    )
    db.commit()
    return {"status": "inactive", "equipment_id": equipment.id}


@app.get(
    "/api/v1/iot/devices",
    response_model=list[IotDeviceResponse],
    response_model_exclude_none=True,
)
def list_iot_devices(
    current_user=Depends(require_permission("iot.devices.view")),
    db: Session = Depends(get_db),
):
    devices = db.query(models.IotDevice).order_by(models.IotDevice.device_id).all()
    visible = []
    for device in devices:
        try:
            _assert_equipment_scope(current_user, device.equipment)
        except HTTPException:
            continue
        visible.append(_serialize_iot_device(device))
    return visible


@app.get(
    "/api/v1/admin/iot/devices",
    response_model=list[IotDeviceResponse],
    response_model_exclude_none=True,
)
def admin_list_iot_devices(
    current_user=Depends(require_permission("iot.devices.view")),
    db: Session = Depends(get_db),
):
    return list_iot_devices(current_user=current_user, db=db)


@app.get(
    "/api/v1/iot/devices/{device_id}",
    response_model=IotDeviceResponse,
    response_model_exclude_none=True,
)
def get_iot_device(
    device_id: str,
    current_user=Depends(require_permission("iot.devices.view")),
    db: Session = Depends(get_db),
):
    device = _iot_device_by_reference(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo nao encontrado.")
    _assert_equipment_scope(current_user, device.equipment)
    return _serialize_iot_device(device)


@app.get(
    "/api/v1/admin/iot/devices/{device_id}",
    response_model=IotDeviceResponse,
    response_model_exclude_none=True,
)
def admin_get_iot_device(
    device_id: str,
    current_user=Depends(require_permission("iot.devices.view")),
    db: Session = Depends(get_db),
):
    return get_iot_device(device_id=device_id, current_user=current_user, db=db)


@app.post("/api/v1/admin/iot/devices", response_model=IotDeviceResponse)
def admin_create_iot_device(
    payload: IotDeviceCreate,
    current_user=Depends(require_permission("iot.devices.manage")),
    db: Session = Depends(get_db),
):
    equipment = db.query(models.Equipment).filter(models.Equipment.id == payload.equipment_id).first()
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipamento nao encontrado.")
    _assert_equipment_scope(current_user, equipment)
    existing = db.query(models.IotDevice).filter(models.IotDevice.device_id == payload.device_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Device ID ja cadastrado.")
    api_key = generate_api_key()
    device = models.IotDevice(
        device_id=payload.device_id,
        device_identifier=payload.device_id,
        equipment_id=payload.equipment_id,
        name=payload.name,
        device_type=payload.device_type,
        firmware_version=payload.firmware_version,
        status=payload.status.upper(),
        metadata_json=payload.metadata_json,
        api_key_hash=hash_api_key(api_key),
    )
    db.add(device)
    db.flush()
    db.add(
        models.AuditLog(
            actor=current_user.username,
            action="iot_device_created",
            payload={"device_id": device.device_id, "equipment_id": device.equipment_id},
        )
    )
    db.commit()
    db.refresh(device)
    return _serialize_iot_device(device, api_key=api_key)


@app.put("/api/v1/admin/iot/devices/{device_id}", response_model=IotDeviceResponse)
def admin_update_iot_device(
    device_id: str,
    payload: IotDeviceUpdate,
    current_user=Depends(require_permission("iot.devices.manage")),
    db: Session = Depends(get_db),
):
    device = _iot_device_by_reference(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo nao encontrado.")
    _assert_equipment_scope(current_user, device.equipment)
    update_data = payload.model_dump(exclude_unset=True)
    if payload.equipment_id is not None:
        equipment = db.query(models.Equipment).filter(models.Equipment.id == payload.equipment_id).first()
        if not equipment:
            raise HTTPException(status_code=404, detail="Equipamento nao encontrado.")
        _assert_equipment_scope(current_user, equipment)
    api_key = None
    for field in ("equipment_id", "name", "device_type", "firmware_version", "status", "metadata_json", "is_active"):
        if field in update_data:
            value = update_data[field]
            setattr(device, field, str(value).upper() if field == "status" and value is not None else value)
    if payload.rotate_api_key:
        api_key = generate_api_key()
        device.api_key_hash = hash_api_key(api_key)
        device.api_key_revoked_at = None
    if payload.revoke_api_key:
        device.api_key_revoked_at = datetime.utcnow()
    device.updated_at = datetime.utcnow()
    db.add(
        models.AuditLog(
            actor=current_user.username,
            action="iot_device_updated",
            payload={
                "device_id": device.device_id,
                "equipment_id": device.equipment_id,
                "rotated_api_key": bool(payload.rotate_api_key),
                "revoked_api_key": bool(payload.revoke_api_key),
            },
        )
    )
    db.commit()
    db.refresh(device)
    return _serialize_iot_device(device, api_key=api_key)


@app.delete("/api/v1/admin/iot/devices/{device_id}")
def admin_delete_iot_device(
    device_id: str,
    current_user=Depends(require_permission("iot.devices.manage")),
    db: Session = Depends(get_db),
):
    device = _iot_device_by_reference(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo nao encontrado.")
    _assert_equipment_scope(current_user, device.equipment)
    device.status = "DISABLED"
    device.is_active = False
    device.api_key_revoked_at = datetime.utcnow()
    device.updated_at = datetime.utcnow()
    db.add(
        models.AuditLog(
            actor=current_user.username,
            action="iot_device_disabled",
            payload={"device_id": device.device_id, "equipment_id": device.equipment_id},
        )
    )
    db.commit()
    return {"status": "DISABLED", "device_id": device.device_id}


def _history_window(period: str | None) -> datetime | None:
    if not period:
        return None
    value = period.lower()
    now = datetime.utcnow()
    windows = {
        "5m": timedelta(minutes=5),
        "last_5_minutes": timedelta(minutes=5),
        "1h": timedelta(hours=1),
        "last_hour": timedelta(hours=1),
        "6h": timedelta(hours=6),
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
    }
    delta = windows.get(value)
    return now - delta if delta else None


@app.get("/api/v1/equipments/{equipment_id}/telemetry/latest")
def equipment_telemetry_latest(
    equipment_id: int,
    current_user=Depends(require_permission("telemetry.view")),
    db: Session = Depends(get_db),
):
    equipment = db.query(models.Equipment).filter(models.Equipment.id == equipment_id).first()
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipamento nao encontrado.")
    _assert_equipment_scope(current_user, equipment)
    row = (
        db.query(models.IotTelemetry)
        .filter(models.IotTelemetry.equipment_id == equipment_id)
        .order_by(desc(models.IotTelemetry.timestamp))
        .first()
    )
    if not row:
        return {"equipment_id": equipment_id, "telemetry": None}
    serialized = _serialize_iot_telemetry(row)
    return {
        "equipment_id": equipment_id,
        "device_status": current_device_status(row.iot_device) if row.iot_device else None,
        "telemetry": serialized,
    }


@app.get("/api/v1/equipments/{equipment_id}/telemetry/history")
def equipment_telemetry_history(
    equipment_id: int,
    period: str | None = Query(default="1h"),
    start_ts: datetime | None = Query(default=None, alias="start"),
    end_ts: datetime | None = Query(default=None, alias="end"),
    from_ts: datetime | None = Query(default=None, alias="from"),
    to_ts: datetime | None = Query(default=None, alias="to"),
    limit: int = Query(300, ge=1, le=5000),
    current_user=Depends(require_permission("telemetry.view")),
    db: Session = Depends(get_db),
):
    equipment = db.query(models.Equipment).filter(models.Equipment.id == equipment_id).first()
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipamento nao encontrado.")
    _assert_equipment_scope(current_user, equipment)
    query = db.query(models.IotTelemetry).filter(models.IotTelemetry.equipment_id == equipment_id)
    start = start_ts or from_ts or _history_window(period)
    end = end_ts or to_ts
    if start:
        query = query.filter(models.IotTelemetry.timestamp >= normalize_timestamp(start).replace(tzinfo=None))
    if end:
        query = query.filter(models.IotTelemetry.timestamp <= normalize_timestamp(end).replace(tzinfo=None))
    rows = query.order_by(desc(models.IotTelemetry.timestamp)).limit(limit).all()
    rows = list(reversed(rows))
    readings = [_serialize_iot_telemetry(row) for row in rows]
    return {
        "equipment_id": equipment_id,
        "period": period,
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "count": len(rows),
        "history": readings,
        "readings": readings,
    }


@app.get("/api/v1/equipments/{equipment_id}/risk/current")
def equipment_current_risk(
    equipment_id: int,
    current_user=Depends(require_permission("risk.view")),
    db: Session = Depends(get_db),
):
    equipment = db.query(models.Equipment).filter(models.Equipment.id == equipment_id).first()
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipamento nao encontrado.")
    _assert_equipment_scope(current_user, equipment)
    latest_iot = (
        db.query(models.IotTelemetry)
        .filter(models.IotTelemetry.equipment_id == equipment_id)
        .order_by(desc(models.IotTelemetry.timestamp))
        .first()
    )
    if latest_iot and latest_iot.risk_score is not None:
        return {
            "equipment_id": equipment_id,
            "source": "iot_telemetry",
            "risk_score": latest_iot.risk_score,
            "risk_level": latest_iot.risk_level,
            "confidence_score": latest_iot.confidence_score,
            "telemetry_status": _serialize_iot_telemetry(latest_iot)["telemetry_status"],
            "data_quality_status": latest_iot.data_quality_status,
            "explainable_ai": latest_iot.explanation,
            "telemetry": _serialize_iot_telemetry(latest_iot),
        }

    latest_record = (
        db.query(models.TelemetryRecord)
        .filter(models.TelemetryRecord.equipment_id == equipment_id)
        .order_by(desc(models.TelemetryRecord.timestamp))
        .first()
    )
    if not latest_record:
        raise HTTPException(status_code=404, detail="Sem risco registrado para este equipamento.")
    return {
        "equipment_id": equipment_id,
        "source": "telemetry_records",
        "risk_score": latest_record.predicted_risk,
        "risk_level": latest_record.risk_label,
        "confidence_score": None,
        "telemetry_status": None,
        "data_quality_status": None,
        "explainable_ai": latest_record.explanation,
    }


@app.get("/api/v1/equipments/{equipment_id}/iot-events")
def equipment_iot_events(
    equipment_id: int,
    period: str | None = Query(default="24h"),
    limit: int = Query(100, ge=1, le=1000),
    current_user=Depends(require_permission("telemetry.view")),
    db: Session = Depends(get_db),
):
    equipment = db.query(models.Equipment).filter(models.Equipment.id == equipment_id).first()
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipamento nao encontrado.")
    _assert_equipment_scope(current_user, equipment)
    query = db.query(models.IotEvent).filter(models.IotEvent.equipment_id == equipment_id)
    start = _history_window(period)
    if start:
        query = query.filter(models.IotEvent.created_at >= normalize_timestamp(start))
    rows = query.order_by(desc(models.IotEvent.created_at)).limit(limit).all()
    return {
        "equipment_id": equipment_id,
        "count": len(rows),
        "events": [
            {
                "id": row.id,
                "telemetry_id": row.telemetry_id,
                "risk_prediction_id": row.risk_prediction_id,
                "event_type": row.event_type,
                "severity": row.severity,
                "value": row.value,
                "unit": row.unit,
                "description": row.description,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
    }

@app.get("/api/v1/policies/alerts")
def list_alert_policies(db: Session = Depends(get_db)):
    policies = db.query(models.AlertPolicy).order_by(desc(models.AlertPolicy.id)).all()

    return [
        {
            "id": policy.id,
            "name": policy.name,
            "operation_type": policy.operation_type,
            "min_risk_alert": policy.min_risk_alert,
            "min_risk_block": policy.min_risk_block,
            "max_speed": policy.max_speed,
            "max_slope": policy.max_slope,
            "min_distance_water": policy.min_distance_water,
            "max_rain_mm": policy.max_rain_mm,
            "block_on_water": policy.block_on_water,
            "block_on_unstable_soil": policy.block_on_unstable_soil,
            "is_active": policy.is_active,
        }
        for policy in policies
    ]

@app.post("/api/v1/policies/alerts", response_model=AlertPolicyResponse)
def create_alert_policy(
    payload: AlertPolicyCreate,
    current_user=Depends(require_roles("admin", "gestor")),
    db: Session = Depends(get_db),
):
    policy = models.AlertPolicy(
        name=payload.name,
        operation_type=payload.operation_type,
        min_risk_alert=payload.min_risk_alert,
        min_risk_block=payload.min_risk_block,
        max_speed=payload.max_speed,
        max_slope=payload.max_slope,
        min_distance_water=payload.min_distance_water,
        max_rain_mm=payload.max_rain_mm,
        block_on_water=payload.block_on_water,
        block_on_unstable_soil=payload.block_on_unstable_soil,
        is_active=payload.is_active,
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy


@app.put("/api/v1/policies/alerts/{policy_id}", response_model=AlertPolicyResponse)
def update_alert_policy(
    policy_id: int,
    payload: AlertPolicyUpdate,
    current_user=Depends(require_roles("admin", "gestor")),
    db: Session = Depends(get_db),
):
    policy = db.query(models.AlertPolicy).filter(
        models.AlertPolicy.id == policy_id
    ).first()

    if not policy:
        raise HTTPException(status_code=404, detail="Política não encontrada")

    update_data = payload.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(policy, field, value)

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

def _legacy_predict_unused(payload: TelemetryInput, db: Session = Depends(get_db)):
    weather = get_weather(payload.latitude, payload.longitude)
    full_payload = _prepare_prediction(payload, weather)

    geo_context = build_geo_context(
        latitude=float(full_payload.get("latitude", 0)),
        longitude=float(full_payload.get("longitude", 0)),
        solo_instavel=int(full_payload.get("solo_instavel", 0)),
        inclinacao=float(full_payload.get("inclinacao", 0)),
        gps_accuracy_m=full_payload.get("gps_accuracy_m"),
    )
    full_payload["distancia_agua_manual"] = full_payload.get("distancia_agua", 0)
    full_payload["distancia_agua"] = float(
    geo_context.get("nearest_water", {}).get("distance_m", full_payload.get("distancia_agua", 0))
    )

    operational_context = build_operational_context(
    input_payload=payload.model_dump(),
    weather=weather,
    geo_context=geo_context,
)

    features = build_features(full_payload)
    model_risk_score = float(predict_risk(MODEL_BUNDLE, features))
    geo_risk_points = float(geo_context["geo_risk"]["geo_risk_points"])

    uncapped_final_score = model_risk_score + geo_risk_points

    risk_score = min(
        100.0,
        uncapped_final_score,
    )

    risk_components = {
        "model_risk_score": round(model_risk_score, 2),
        "geo_risk_points": round(geo_risk_points, 2),
        "uncapped_final_score": round(uncapped_final_score, 2),
        "final_risk_score": round(risk_score, 2),
    }

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
        _feature_vector(features),
        _feature_vector(features),
        _model_feature_names(),
    )
    if not explanation:
        explanation = heuristic_explanation(full_payload, risk_score)

    executive_explanation = build_executive_explanation(
        risk_score=risk_score,
        risk_label=risk_label,
        explanation=explanation,
        recommendation=recommendation,
    )

    prediction_trace = build_prediction_trace(
    model_version=settings.model_version,
    features=features,
    risk_components=risk_components,
    explanation=explanation,
    safe_route=route,
    recommendation=recommendation,
)

    audit_id = write_audit(
        db,
        actor="api",
        action="risk_predict",
        payload={
            "operational_context": operational_context,
            "prediction_trace": prediction_trace,
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
        executive_explanation=executive_explanation,
        geo_context=geo_context,
        risk_components=risk_components,
        weather=weather,
        audit_id=audit_id,
    )

@app.get("/api/v1/system/architecture")
def get_system_architecture():
    return build_system_architecture()


@app.get("/api/v1/system/status")
def get_system_status():
    return build_system_status()
