from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .database import Base


JSON_DOCUMENT = JSON().with_variant(JSONB, "postgresql")


user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id"), primary_key=True),
)


role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.id"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("permissions.id"), primary_key=True),
)


class Farm(Base):
    __tablename__ = "farms"
    __table_args__ = (
        Index("ix_farms_client_state_municipality", "client_id", "state", "municipality"),
    )

    id = Column(Integer, primary_key=True, index=True)
    # Legacy geographic fields remain required because existing prediction and
    # dashboard flows use them directly.
    name = Column(String(120), nullable=False)
    region = Column(String(120), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=True, index=True)
    municipality = Column(String(120), nullable=True, index=True)
    state = Column(String(80), nullable=True, index=True)
    country = Column(String(2), nullable=False, default="BR", server_default="BR")
    total_area_ha = Column(Float, nullable=True)
    cultivated_area_ha = Column(Float, nullable=True)
    main_crop = Column(String(120), nullable=True)
    status = Column(String(40), nullable=False, default="active", server_default="active")
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    client = relationship("Client", back_populates="farms")
    equipment = relationship("Equipment", back_populates="farm")
    users = relationship("User", secondary="user_farms", back_populates="farms")
    operations = relationship("Operation", back_populates="farm")
    weather_records = relationship("WeatherRecord", back_populates="farm")
    soil_records = relationship("SoilRecord", back_populates="farm")
    terrain_records = relationship("TerrainRecord", back_populates="farm")
    incidents = relationship("Incident", back_populates="farm")
    risk_predictions = relationship("RiskPrediction", back_populates="farm")
    alerts = relationship("Alert", back_populates="farm")
    simulations = relationship("RiskSimulation", back_populates="farm")
    alert_policies = relationship("AlertPolicy", back_populates="farm")
    generated_reports = relationship("GeneratedReport", back_populates="farm")


class Equipment(Base):
    __tablename__ = "equipment"
    __table_args__ = (
        UniqueConstraint("serial_number", name="uq_equipment_serial_number"),
        UniqueConstraint("internal_code", name="uq_equipment_internal_code"),
        Index("ix_equipment_farm_type_status", "farm_id", "equipment_type", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    equipment_type = Column(String(60), nullable=False)
    # client_name is retained while client ownership is normalized through Farm.
    client_name = Column(String(120), nullable=False, server_default=text("''"))
    manufacturer = Column(String(120), nullable=True)
    model = Column(String(120), nullable=True)
    year = Column(Integer, nullable=True)
    serial_number = Column(String(120), nullable=True)
    internal_code = Column(String(120), nullable=True)
    status = Column(String(40), default="active", nullable=False)
    farm_id = Column(Integer, ForeignKey("farms.id"), nullable=False)
    purchase_value = Column(Float, nullable=True)
    estimated_repair_cost = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    farm = relationship("Farm", back_populates="equipment")
    telemetry = relationship("TelemetryRecord", back_populates="equipment")
    iot_devices = relationship("IotDevice", back_populates="equipment")
    users = relationship("User", secondary="user_equipments", back_populates="equipments")
    operations = relationship("Operation", back_populates="equipment")
    incidents = relationship("Incident", back_populates="equipment")
    risk_predictions = relationship("RiskPrediction", back_populates="equipment")
    alerts = relationship("Alert", back_populates="equipment")
    recommendations = relationship("Recommendation", back_populates="equipment")
    simulations = relationship("RiskSimulation", back_populates="equipment")
    prevented_losses = relationship("PreventedLossRecord", back_populates="equipment")


class TelemetryRecord(Base):
    __tablename__ = "telemetry_records"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    equipment_id = Column(Integer, ForeignKey("equipment.id"), nullable=False)
    farm_id = Column(Integer, ForeignKey("farms.id"), nullable=False)

    region = Column(String(120), nullable=False)
    operation_type = Column(String(40), nullable=False)
    clima = Column(String(40), nullable=False)
    umidade_solo = Column(Float, nullable=False)
    inclinacao = Column(Float, nullable=False)
    distancia_agua = Column(Float, nullable=False)
    velocidade = Column(Float, nullable=False)
    historico_sinistros = Column(Float, nullable=False)
    chuva_mm = Column(Float, nullable=False)
    solo_instavel = Column(Integer, default=0, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)

    predicted_risk = Column(Float, nullable=False)
    risk_label = Column(String(20), nullable=False)
    alert_level = Column(String(40), nullable=False)
    recommendation = Column(Text, nullable=False)
    safe_route = Column(Text, nullable=False)
    explanation = Column(JSON, nullable=False)

    equipment = relationship("Equipment", back_populates="telemetry")


class SensorReading(Base):
    __tablename__ = "sensor_readings"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    device_id = Column(String(120), nullable=False)
    equipment_id = Column(Integer, ForeignKey("equipment.id"), nullable=False)
    farm_id = Column(Integer, ForeignKey("farms.id"), nullable=False)

    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    gps_accuracy_m = Column(Float, nullable=True)
    gps_satellites = Column(Integer, nullable=True)

    temperatura_c = Column(Float, nullable=True)
    umidade_ar = Column(Float, nullable=True)
    pressao_hpa = Column(Float, nullable=True)
    umidade_solo = Column(Float, nullable=True)
    inclinacao = Column(Float, nullable=True)
    distancia_obstaculo = Column(Float, nullable=True)
    distancia_agua = Column(Float, nullable=True)
    velocidade = Column(Float, nullable=True)
    chuva_mm = Column(Float, nullable=True)
    battery_voltage = Column(Float, nullable=True)

    predicted_risk = Column(Float, nullable=True)
    risk_label = Column(String(20), nullable=True)
    raw_payload = Column(JSON, nullable=False)
    normalized_payload = Column(JSON, nullable=False)


class PredictionRecord(Base):
    __tablename__ = "prediction_records"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    model_version = Column(String(40), nullable=False)
    source = Column(String(40), nullable=False)
    input_payload = Column(JSON, nullable=False)
    predicted_risk = Column(Float, nullable=False)
    risk_label = Column(String(20), nullable=False)
    alert_level = Column(String(40), nullable=False)
    explanation = Column(JSON, nullable=False)
    recommendation = Column(Text, nullable=False)
    safe_route = Column(Text, nullable=False)
    weather_payload = Column(JSON, nullable=True)


class AlertRecord(Base):
    __tablename__ = "alert_records"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    alert_type = Column(String(60), nullable=False)
    severity = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)
    context = Column(JSON, nullable=False)
    equipment_id = Column(Integer, ForeignKey("equipment.id"), nullable=True, index=True)
    device_id = Column(String(120), nullable=True, index=True)
    telemetry_id = Column(Integer, ForeignKey("iot_telemetry.id"), nullable=True, index=True)
    risk_prediction_id = Column(Integer, ForeignKey("prediction_records.id"), nullable=True, index=True)


class RouteRecommendation(Base):
    __tablename__ = "route_recommendations"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    origin_name = Column(String(120), nullable=False)
    destination_name = Column(String(120), nullable=False)
    recommended_route = Column(String(120), nullable=False)
    route_score = Column(Float, nullable=False)
    alternatives = Column(JSON, nullable=False)
    context = Column(JSON, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_entity_created_at", "entity_type", "entity_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    # actor and payload are legacy fields still written by the existing API.
    actor = Column(String(40), nullable=False)
    action = Column(String(80), nullable=False)
    payload = Column(JSON, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True)
    entity_type = Column(String(120), nullable=True, index=True)
    entity_id = Column(String(120), nullable=True, index=True)
    request_id = Column(String(120), nullable=True, index=True)
    ip_address = Column(String(64), nullable=True)
    old_values_json = Column(JSON, nullable=True)
    new_values_json = Column(JSON, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)

    user = relationship("User", foreign_keys=[user_id])


class AlertPolicy(Base):
    __tablename__ = "alert_policies"
    __table_args__ = (
        CheckConstraint("risk_threshold IS NULL OR (risk_threshold >= 0 AND risk_threshold <= 100)", name="ck_alert_policy_risk_threshold"),
        Index("ix_alert_policies_client_farm_active", "client_id", "farm_id", "is_active"),
    )

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=True, index=True)
    farm_id = Column(Integer, ForeignKey("farms.id", ondelete="RESTRICT"), nullable=True, index=True)
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    operation_type = Column(String(40), nullable=False)  # campo, transporte, proximidade_agua, all
    risk_threshold = Column(Float, nullable=True)
    severity = Column(String(20), nullable=True)
    action_type = Column(String(80), nullable=True)

    min_risk_alert = Column(Float, default=40.0)
    min_risk_block = Column(Float, default=70.0)

    max_speed = Column(Float, default=25.0)
    max_slope = Column(Float, default=15.0)
    min_distance_water = Column(Float, default=30.0)
    max_rain_mm = Column(Float, default=20.0)

    block_on_water = Column(Boolean, default=False)
    block_on_unstable_soil = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    client = relationship("Client", back_populates="alert_policies")
    farm = relationship("Farm", back_populates="alert_policies")


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(40), unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)
    is_system_role = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    users = relationship("User", secondary=user_roles, back_populates="roles")
    permissions = relationship("Permission", secondary=role_permissions, back_populates="roles")


class Permission(Base):
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(80), unique=True, index=True, nullable=False)
    name = Column(String(120), nullable=False, server_default=text("''"))
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    roles = relationship("Role", secondary=role_permissions, back_populates="permissions")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(160), nullable=False)
    email = Column(String(160), unique=True, index=True, nullable=False)
    username = Column(String(80), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    status = Column(String(40), default="active", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False, server_default=text("false"))
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    roles = relationship("Role", secondary=user_roles, back_populates="users")
    permission_overrides = relationship(
        "UserPermission",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    access_scopes = relationship(
        "UserAccessScope",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    clients = relationship("Client", secondary="user_clients", back_populates="users")
    farms = relationship("Farm", secondary="user_farms", back_populates="users")
    equipments = relationship("Equipment", secondary="user_equipments", back_populates="users")
    operations = relationship("Operation", foreign_keys="Operation.operator_user_id", back_populates="operator")
    notifications = relationship("Notification", back_populates="user")

    @property
    def full_name(self) -> str:
        return self.name

    @property
    def hashed_password(self) -> str:
        return self.password_hash

    @property
    def role(self) -> str:
        if not self.roles:
            return "LEITURA"
        return self.roles[0].name


class UserPermission(Base):
    __tablename__ = "user_permissions"
    __table_args__ = (UniqueConstraint("user_id", "permission_id", name="uq_user_permission"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    permission_id = Column(Integer, ForeignKey("permissions.id"), nullable=False, index=True)
    allowed = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="permission_overrides")
    permission = relationship("Permission")


class UserAccessScope(Base):
    __tablename__ = "user_access_scopes"
    __table_args__ = (
        Index("ix_user_access_scope_user_farm_equipment", "user_id", "farm_id", "equipment_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=True, index=True)
    client_name = Column(String(120), nullable=True, index=True)
    farm_id = Column(Integer, ForeignKey("farms.id"), nullable=True, index=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="access_scopes")
    client = relationship("Client", foreign_keys=[client_id])


class IotDevice(Base):
    __tablename__ = "iot_devices"
    __table_args__ = (
        UniqueConstraint("device_identifier", name="uq_iot_devices_device_identifier"),
        CheckConstraint("device_identifier IS NOT NULL OR device_id IS NOT NULL", name="ck_iot_device_identifier"),
    )

    id = Column(Integer, primary_key=True, index=True)
    # device_id remains the authenticated integration key used by existing APIs.
    device_id = Column(String(120), unique=True, index=True, nullable=False)
    device_identifier = Column(String(120), nullable=True, index=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id"), nullable=False, index=True)
    name = Column(String(160), nullable=False)
    device_type = Column(String(60), default="ESP32", nullable=False)
    firmware_version = Column(String(80), nullable=True)
    api_key_hash = Column(String(255), nullable=False)
    status = Column(String(40), default="OFFLINE", nullable=False, index=True)
    last_seen_at = Column(DateTime, nullable=True)
    api_key_revoked_at = Column(DateTime, nullable=True)
    metadata_json = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    equipment = relationship("Equipment", back_populates="iot_devices")
    telemetry = relationship(
        "IotTelemetry",
        foreign_keys="IotTelemetry.device_id",
        back_populates="device",
    )
    telemetry_by_id = relationship(
        "IotTelemetry",
        foreign_keys="IotTelemetry.iot_device_id",
        back_populates="iot_device",
    )
    events = relationship("IotEvent", back_populates="device")


class IotTelemetry(Base):
    # Legacy columns remain available while canonical ESP32 fields are added
    # incrementally for physical hardware integration.
    __tablename__ = "iot_telemetry"
    __table_args__ = (
        Index("ix_iot_telemetry_equipment_timestamp", "equipment_id", "timestamp"),
        Index("ix_iot_telemetry_device_timestamp", "device_id", "timestamp"),
        Index("ix_iot_telemetry_equipment_recorded_at", "equipment_id", "recorded_at"),
        Index("ix_iot_telemetry_iot_device_recorded_at", "iot_device_id", "recorded_at"),
        Index("uq_iot_telemetry_device_sequence", "iot_device_id", "sequence_number", unique=True),
        CheckConstraint(
            "data_quality_status IN ('VALID', 'PARTIAL', 'SUSPECT', 'INVALID')",
            name="ck_iot_telemetry_quality_status",
        ),
        CheckConstraint("distance_cm IS NULL OR distance_cm >= 0", name="ck_iot_telemetry_distance_cm"),
    )

    id = Column(Integer, primary_key=True, index=True)
    # device_id remains the legacy authenticated identifier. iot_device_id is
    # the canonical FK used by new integrations and sequence constraints.
    device_id = Column(String(120), ForeignKey("iot_devices.device_id"), nullable=False, index=True)
    iot_device_id = Column(
        Integer,
        ForeignKey("iot_devices.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    equipment_id = Column(Integer, ForeignKey("equipment.id"), nullable=False, index=True)
    sequence_number = Column(Integer, nullable=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    recorded_at = Column(DateTime(timezone=True), nullable=True, index=True)
    received_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    temperature_c = Column(Float, nullable=True)
    humidity_pct = Column(Float, nullable=True)
    pressure_hpa = Column(Float, nullable=True)
    altitude_m = Column(Float, nullable=True)

    accel_x = Column(Float, nullable=True)
    accel_y = Column(Float, nullable=True)
    accel_z = Column(Float, nullable=True)
    gyro_x = Column(Float, nullable=True)
    gyro_y = Column(Float, nullable=True)
    gyro_z = Column(Float, nullable=True)
    pitch = Column(Float, nullable=True)
    roll = Column(Float, nullable=True)

    acceleration_magnitude = Column(Float, nullable=True)
    gyro_magnitude = Column(Float, nullable=True)
    max_tilt_angle = Column(Float, nullable=True)
    movement_anomaly_score = Column(Float, nullable=True)
    possible_impact = Column(Boolean, default=False, nullable=False)

    obstacle_detected = Column(Boolean, nullable=True)
    obstacle_distance_cm = Column(Float, nullable=True)
    distance_cm = Column(Float, nullable=True)
    inclination_deg = Column(Float, nullable=True)

    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    telemetry_age_seconds = Column(Float, nullable=False, default=0.0)
    telemetry_status = Column(String(20), default="LIVE", nullable=False)
    data_quality_status = Column(String(20), default="VALID", nullable=False)
    data_quality_issues = Column(JSON, nullable=False, default=list)
    missing_sensors = Column(JSON, nullable=False, default=list)
    confidence_score = Column(Float, nullable=True)

    risk_score = Column(Float, nullable=True)
    risk_level = Column(String(20), nullable=True)
    explanation = Column(JSON, nullable=True)
    risk_prediction_id = Column(Integer, ForeignKey("prediction_records.id"), nullable=True, index=True)

    raw_payload = Column(JSON, nullable=False)
    raw_payload_json = Column(JSON_DOCUMENT, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    device = relationship(
        "IotDevice",
        foreign_keys=[device_id],
        back_populates="telemetry",
    )
    iot_device = relationship("IotDevice", foreign_keys=[iot_device_id], back_populates="telemetry_by_id")
    normalized_predictions = relationship(
        "RiskPrediction",
        foreign_keys="RiskPrediction.telemetry_id",
        back_populates="telemetry",
    )
    events = relationship("IotEvent", back_populates="telemetry")


class IotEvent(Base):
    __tablename__ = "iot_events"
    __table_args__ = (
        UniqueConstraint("telemetry_id", "event_type", name="uq_iot_event_telemetry_type"),
        Index("ix_iot_events_equipment_created_at", "equipment_id", "created_at"),
        Index("ix_iot_events_device_created_at", "device_id", "created_at"),
        Index("ix_iot_events_type_severity", "event_type", "severity"),
    )

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("iot_devices.id", ondelete="RESTRICT"), nullable=False, index=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="RESTRICT"), nullable=False, index=True)
    telemetry_id = Column(Integer, ForeignKey("iot_telemetry.id", ondelete="RESTRICT"), nullable=False, index=True)
    risk_prediction_id = Column(
        Integer,
        ForeignKey("risk_predictions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    event_type = Column(String(80), nullable=False, index=True)
    severity = Column(String(20), nullable=False, index=True)
    value = Column(Float, nullable=True)
    unit = Column(String(40), nullable=True)
    description = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    device = relationship("IotDevice", back_populates="events")
    telemetry = relationship("IotTelemetry", back_populates="events")
    risk_prediction = relationship("RiskPrediction", back_populates="iot_events")


class UserAccount(Base):
    __tablename__ = "user_accounts"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=True)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False, default="operador")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)

class AccessEvent(Base):
    __tablename__ = "access_events"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, nullable=False)
    role = Column(String, nullable=False)
    action = Column(String, nullable=False)
    endpoint = Column(String, nullable=False)
    success = Column(Boolean, nullable=False, default=True)
    detail = Column(JSON, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)


# New relational models live separately to avoid destabilizing imports used by
# the current API. Importing them here registers every table in Base.metadata.
from .models_extended import *  # noqa: F403
