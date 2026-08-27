"""Additional relational domain models for the AgroGuardian database.

The existing application keeps its legacy tables in ``backend.models`` for
backwards compatibility. This module contains the additive core schema used by
new database workflows. Detailed ESP32 telemetry is intentionally not modeled
here: its final schema depends on physical sensor validation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum as SqlEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def enum_type(enum_class: type[Enum], name: str) -> SqlEnum:
    """Store portable enum values as checked strings on SQLite and PostgreSQL."""
    return SqlEnum(
        enum_class,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda values: [value.value for value in values],
    )


JSON_DOCUMENT = JSON().with_variant(JSONB, "postgresql")


class TimestampMixin:
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
    )


class ActiveMixin:
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))


class ClientType(str, Enum):
    INDIVIDUAL = "INDIVIDUAL"
    COMPANY = "COMPANY"
    INSURER = "INSURER"
    OTHER = "OTHER"


class ClientStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUSPENDED = "SUSPENDED"


class OperationType(str, Enum):
    FIELD = "field"
    TRANSPORT = "transport"
    HARVEST = "harvest"
    SPRAYING = "spraying"
    MAINTENANCE = "maintenance"
    NEAR_WATER = "near_water"
    OTHER = "other"


class OperationStatus(str, Enum):
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"


class WeatherSource(str, Enum):
    OPENWEATHER = "OpenWeather"
    INMET = "INMET"
    NASA_POWER = "NASA_POWER"
    SIMULATION = "SIMULATION"


class SoilSource(str, Enum):
    SOILGRIDS = "SoilGrids"
    DATASET = "dataset"
    MANUAL = "manual"
    FUTURE_SENSOR = "future_sensor"


class TerrainSource(str, Enum):
    SRTM = "SRTM"
    HYDRORIVERS = "HydroRIVERS"
    MAPBIOMAS = "MapBiomas"
    OPENSTREETMAP = "OpenStreetMap"


class IncidentType(str, Enum):
    COLLISION = "collision"
    ROLLOVER = "rollover"
    STUCK = "stuck"
    WATER_DAMAGE = "water_damage"
    MECHANICAL_DAMAGE = "mechanical_damage"
    TRANSPORT_ACCIDENT = "transport_accident"
    FIRE = "fire"
    OTHER = "other"


class IncidentSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IncidentStatus(str, Enum):
    OPEN = "OPEN"
    UNDER_REVIEW = "UNDER_REVIEW"
    CLOSED = "CLOSED"
    DISMISSED = "DISMISSED"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertSeverity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertStatus(str, Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class RecommendationType(str, Enum):
    OPERATIONAL = "OPERATIONAL"
    ROUTE = "ROUTE"
    MAINTENANCE = "MAINTENANCE"
    SAFETY = "SAFETY"
    OTHER = "OTHER"


class RecommendationPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ModelStatus(str, Enum):
    TRAINING = "TRAINING"
    VALIDATION = "VALIDATION"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    DEPRECATED = "DEPRECATED"


class DatasetSourceType(str, Enum):
    SIMULATED = "SIMULATED"
    PUBLIC = "PUBLIC"
    INTEGRATED = "INTEGRATED"
    REAL_OPERATIONAL = "REAL_OPERATIONAL"
    REAL_IOT = "REAL_IOT"


class ReportStatus(str, Enum):
    PENDING = "PENDING"
    GENERATING = "GENERATING"
    READY = "READY"
    FAILED = "FAILED"


class NotificationType(str, Enum):
    DASHBOARD = "DASHBOARD"
    EMAIL = "EMAIL"
    PUSH = "PUSH"
    WHATSAPP = "WHATSAPP"


# Access grants do not carry historical business data, so cleanup of their
# association rows is safe when an identity is physically removed.
user_clients = Table(
    "user_clients",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("client_id", Integer, ForeignKey("clients.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

user_farms = Table(
    "user_farms",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("farm_id", Integer, ForeignKey("farms.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

user_equipments = Table(
    "user_equipments",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("equipment_id", Integer, ForeignKey("equipment.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)


class Client(TimestampMixin, ActiveMixin, Base):
    __tablename__ = "clients"
    __table_args__ = (
        UniqueConstraint("document", name="uq_clients_document"),
        Index("ix_clients_status_region", "status", "region"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(160), nullable=False, index=True)
    corporate_name = Column(String(200), nullable=True)
    document = Column(String(40), nullable=True)
    client_type = Column(
        enum_type(ClientType, "client_type"),
        nullable=False,
        default=ClientType.COMPANY,
        server_default=ClientType.COMPANY.value,
    )
    email = Column(String(160), nullable=True, index=True)
    phone = Column(String(40), nullable=True)
    status = Column(
        enum_type(ClientStatus, "client_status"),
        nullable=False,
        default=ClientStatus.ACTIVE,
        server_default=ClientStatus.ACTIVE.value,
    )
    region = Column(String(120), nullable=True, index=True)
    notes = Column(Text, nullable=True)

    users = relationship("User", secondary="user_clients", back_populates="clients")
    farms = relationship("Farm", back_populates="client")
    operations = relationship("Operation", back_populates="client")
    incidents = relationship("Incident", back_populates="client")
    risk_predictions = relationship("RiskPrediction", back_populates="client")
    alerts = relationship("Alert", back_populates="client")
    simulations = relationship("RiskSimulation", back_populates="client")
    alert_policies = relationship("AlertPolicy", back_populates="client")
    generated_reports = relationship("GeneratedReport", back_populates="client")


class Operation(TimestampMixin, ActiveMixin, Base):
    __tablename__ = "operations"
    __table_args__ = (
        Index("ix_operations_equipment_started_at", "equipment_id", "started_at"),
        Index("ix_operations_farm_status", "farm_id", "status"),
    )

    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False, index=True)
    farm_id = Column(Integer, ForeignKey("farms.id", ondelete="RESTRICT"), nullable=False, index=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="RESTRICT"), nullable=False, index=True)
    operation_type = Column(enum_type(OperationType, "operation_type"), nullable=False)
    crop_type = Column(String(120), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, index=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(
        enum_type(OperationStatus, "operation_status"),
        nullable=False,
        default=OperationStatus.PLANNED,
        server_default=OperationStatus.PLANNED.value,
    )
    operator_user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True)
    notes = Column(Text, nullable=True)

    client = relationship("Client", back_populates="operations")
    farm = relationship("Farm", back_populates="operations")
    equipment = relationship("Equipment", back_populates="operations")
    operator = relationship("User", foreign_keys=[operator_user_id], back_populates="operations")
    incidents = relationship("Incident", back_populates="operation")
    risk_predictions = relationship("RiskPrediction", back_populates="operation")
    alerts = relationship("Alert", back_populates="operation")
    simulations = relationship("RiskSimulation", back_populates="operation")


class WeatherRecord(Base):
    __tablename__ = "weather_records"
    __table_args__ = (
        CheckConstraint("humidity_pct IS NULL OR (humidity_pct >= 0 AND humidity_pct <= 100)", name="ck_weather_humidity_pct"),
        CheckConstraint("precipitation_mm IS NULL OR precipitation_mm >= 0", name="ck_weather_precipitation_mm"),
        CheckConstraint("wind_speed_kmh IS NULL OR wind_speed_kmh >= 0", name="ck_weather_wind_speed_kmh"),
        Index("ix_weather_records_farm_recorded_at", "farm_id", "recorded_at"),
    )

    id = Column(Integer, primary_key=True)
    farm_id = Column(Integer, ForeignKey("farms.id", ondelete="RESTRICT"), nullable=False, index=True)
    source = Column(enum_type(WeatherSource, "weather_source"), nullable=False)
    recorded_at = Column(DateTime(timezone=True), nullable=False, index=True)
    temperature_c = Column(Float, nullable=True)
    humidity_pct = Column(Float, nullable=True)
    precipitation_mm = Column(Float, nullable=True)
    wind_speed_kmh = Column(Float, nullable=True)
    pressure_hpa = Column(Float, nullable=True)
    weather_condition = Column(String(80), nullable=True)
    raw_data_json = Column(JSON_DOCUMENT, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now())

    farm = relationship("Farm", back_populates="weather_records")


class SoilRecord(Base):
    __tablename__ = "soil_records"
    __table_args__ = (
        CheckConstraint("soil_moisture_pct IS NULL OR (soil_moisture_pct >= 0 AND soil_moisture_pct <= 100)", name="ck_soil_moisture_pct"),
        CheckConstraint("clay_pct IS NULL OR (clay_pct >= 0 AND clay_pct <= 100)", name="ck_soil_clay_pct"),
        CheckConstraint("sand_pct IS NULL OR (sand_pct >= 0 AND sand_pct <= 100)", name="ck_soil_sand_pct"),
        CheckConstraint("silt_pct IS NULL OR (silt_pct >= 0 AND silt_pct <= 100)", name="ck_soil_silt_pct"),
        CheckConstraint("ph IS NULL OR (ph >= 0 AND ph <= 14)", name="ck_soil_ph"),
        Index("ix_soil_records_farm_sampled_at", "farm_id", "sampled_at"),
    )

    id = Column(Integer, primary_key=True)
    farm_id = Column(Integer, ForeignKey("farms.id", ondelete="RESTRICT"), nullable=False, index=True)
    source = Column(enum_type(SoilSource, "soil_source"), nullable=False)
    sampled_at = Column(DateTime(timezone=True), nullable=False, index=True)
    soil_moisture_pct = Column(Float, nullable=True)
    clay_pct = Column(Float, nullable=True)
    sand_pct = Column(Float, nullable=True)
    silt_pct = Column(Float, nullable=True)
    organic_carbon = Column(Float, nullable=True)
    ph = Column(Float, nullable=True)
    bulk_density = Column(Float, nullable=True)
    drainage_class = Column(String(80), nullable=True)
    raw_data_json = Column(JSON_DOCUMENT, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now())

    farm = relationship("Farm", back_populates="soil_records")


class TerrainRecord(TimestampMixin, Base):
    __tablename__ = "terrain_records"
    __table_args__ = (
        CheckConstraint("latitude >= -90 AND latitude <= 90", name="ck_terrain_latitude"),
        CheckConstraint("longitude >= -180 AND longitude <= 180", name="ck_terrain_longitude"),
        CheckConstraint("slope_deg IS NULL OR (slope_deg >= 0 AND slope_deg <= 90)", name="ck_terrain_slope_deg"),
        CheckConstraint("distance_to_water_m IS NULL OR distance_to_water_m >= 0", name="ck_terrain_distance_water"),
        CheckConstraint("distance_to_road_m IS NULL OR distance_to_road_m >= 0", name="ck_terrain_distance_road"),
        Index("ix_terrain_records_farm_location", "farm_id", "latitude", "longitude"),
    )

    id = Column(Integer, primary_key=True)
    farm_id = Column(Integer, ForeignKey("farms.id", ondelete="RESTRICT"), nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    elevation_m = Column(Float, nullable=True)
    slope_deg = Column(Float, nullable=True)
    distance_to_water_m = Column(Float, nullable=True)
    distance_to_road_m = Column(Float, nullable=True)
    road_type = Column(String(80), nullable=True)
    land_use_class = Column(String(120), nullable=True)
    source = Column(enum_type(TerrainSource, "terrain_source"), nullable=False)

    farm = relationship("Farm", back_populates="terrain_records")


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_dataset_versions_name_version"),
        CheckConstraint("record_count >= 0", name="ck_dataset_record_count"),
        CheckConstraint("feature_count >= 0", name="ck_dataset_feature_count"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(160), nullable=False, index=True)
    version = Column(String(80), nullable=False)
    description = Column(Text, nullable=True)
    source_type = Column(enum_type(DatasetSourceType, "dataset_source_type"), nullable=False)
    record_count = Column(Integer, nullable=False, default=0, server_default=text("0"))
    feature_count = Column(Integer, nullable=False, default=0, server_default=text("0"))
    file_path = Column(String(500), nullable=True)
    checksum = Column(String(128), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now())
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True)
    metadata_json = Column(JSON_DOCUMENT, nullable=True)

    created_by = relationship("User", foreign_keys=[created_by_user_id])
    model_versions = relationship("ModelVersion", back_populates="dataset_version")


class ModelVersion(TimestampMixin, ActiveMixin, Base):
    __tablename__ = "model_versions"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_model_versions_name_version"),
        CheckConstraint("accuracy IS NULL OR (accuracy >= 0 AND accuracy <= 1)", name="ck_model_accuracy"),
        CheckConstraint("precision_score IS NULL OR (precision_score >= 0 AND precision_score <= 1)", name="ck_model_precision"),
        CheckConstraint("recall_score IS NULL OR (recall_score >= 0 AND recall_score <= 1)", name="ck_model_recall"),
        CheckConstraint("f1_score IS NULL OR (f1_score >= 0 AND f1_score <= 1)", name="ck_model_f1"),
        CheckConstraint("roc_auc IS NULL OR (roc_auc >= 0 AND roc_auc <= 1)", name="ck_model_roc_auc"),
        Index("ix_model_versions_status_deployed_at", "status", "deployed_at"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(160), nullable=False, index=True)
    version = Column(String(80), nullable=False)
    algorithm = Column(String(120), nullable=False)
    status = Column(
        enum_type(ModelStatus, "model_status"),
        nullable=False,
        default=ModelStatus.TRAINING,
        server_default=ModelStatus.TRAINING.value,
    )
    dataset_version_id = Column(Integer, ForeignKey("dataset_versions.id", ondelete="RESTRICT"), nullable=True, index=True)
    trained_at = Column(DateTime(timezone=True), nullable=True)
    deployed_at = Column(DateTime(timezone=True), nullable=True)
    accuracy = Column(Float, nullable=True)
    precision_score = Column(Float, nullable=True)
    recall_score = Column(Float, nullable=True)
    f1_score = Column(Float, nullable=True)
    roc_auc = Column(Float, nullable=True)
    metrics_json = Column(JSON_DOCUMENT, nullable=True)
    parameters_json = Column(JSON_DOCUMENT, nullable=True)
    feature_list_json = Column(JSON_DOCUMENT, nullable=True)
    artifact_path = Column(String(500), nullable=True)

    dataset_version = relationship("DatasetVersion", back_populates="model_versions")
    risk_predictions = relationship("RiskPrediction", back_populates="model_version")


class Incident(TimestampMixin, Base):
    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint("estimated_damage_brl IS NULL OR estimated_damage_brl >= 0", name="ck_incident_estimated_damage"),
        Index("ix_incidents_equipment_occurred_at", "equipment_id", "occurred_at"),
        Index("ix_incidents_farm_status", "farm_id", "status"),
    )

    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False, index=True)
    farm_id = Column(Integer, ForeignKey("farms.id", ondelete="RESTRICT"), nullable=False, index=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="RESTRICT"), nullable=True, index=True)
    operation_id = Column(Integer, ForeignKey("operations.id", ondelete="RESTRICT"), nullable=True, index=True)
    incident_type = Column(enum_type(IncidentType, "incident_type"), nullable=False)
    severity = Column(enum_type(IncidentSeverity, "incident_severity"), nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False, index=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    description = Column(Text, nullable=True)
    estimated_damage_brl = Column(Numeric(14, 2), nullable=True)
    was_preventable = Column(Boolean, nullable=True)
    status = Column(
        enum_type(IncidentStatus, "incident_status"),
        nullable=False,
        default=IncidentStatus.OPEN,
        server_default=IncidentStatus.OPEN.value,
    )

    client = relationship("Client", back_populates="incidents")
    farm = relationship("Farm", back_populates="incidents")
    equipment = relationship("Equipment", back_populates="incidents")
    operation = relationship("Operation", back_populates="incidents")


class RiskPrediction(Base):
    __tablename__ = "risk_predictions"
    __table_args__ = (
        CheckConstraint("risk_score >= 0 AND risk_score <= 100", name="ck_risk_prediction_score"),
        CheckConstraint("confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 100)", name="ck_risk_prediction_confidence"),
        Index("ix_risk_predictions_equipment_created_at", "equipment_id", "created_at"),
        Index("ix_risk_predictions_farm_created_at", "farm_id", "created_at"),
        Index("ix_risk_predictions_level_created_at", "risk_level", "created_at"),
    )

    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False, index=True)
    farm_id = Column(Integer, ForeignKey("farms.id", ondelete="RESTRICT"), nullable=False, index=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="RESTRICT"), nullable=True, index=True)
    operation_id = Column(Integer, ForeignKey("operations.id", ondelete="RESTRICT"), nullable=True, index=True)
    risk_score = Column(Float, nullable=False)
    risk_level = Column(enum_type(RiskLevel, "risk_level"), nullable=False)
    confidence_score = Column(Float, nullable=True)
    main_risk_factor = Column(String(160), nullable=True)
    model_version_id = Column(Integer, ForeignKey("model_versions.id", ondelete="RESTRICT"), nullable=True, index=True)
    telemetry_id = Column(Integer, ForeignKey("iot_telemetry.id", ondelete="RESTRICT"), nullable=True, index=True)
    input_snapshot_json = Column(JSON_DOCUMENT, nullable=False, default=dict, server_default=text("'{}'"))
    explanation_summary = Column(Text, nullable=True)
    recommendation_summary = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now())

    client = relationship("Client", back_populates="risk_predictions")
    farm = relationship("Farm", back_populates="risk_predictions")
    equipment = relationship("Equipment", back_populates="risk_predictions")
    operation = relationship("Operation", back_populates="risk_predictions")
    model_version = relationship("ModelVersion", back_populates="risk_predictions")
    telemetry = relationship("IotTelemetry", foreign_keys=[telemetry_id], back_populates="normalized_predictions")
    factors = relationship("RiskPredictionFactor", back_populates="risk_prediction")
    alerts = relationship("Alert", back_populates="risk_prediction")
    recommendations = relationship("Recommendation", back_populates="risk_prediction")
    prevented_losses = relationship("PreventedLossRecord", back_populates="risk_prediction")
    iot_events = relationship("IotEvent", back_populates="risk_prediction")


class RiskPredictionFactor(Base):
    __tablename__ = "risk_prediction_factors"
    __table_args__ = (
        CheckConstraint("importance_pct IS NULL OR (importance_pct >= 0 AND importance_pct <= 100)", name="ck_risk_factor_importance"),
        CheckConstraint("impact_score IS NULL OR (impact_score >= -100 AND impact_score <= 100)", name="ck_risk_factor_impact"),
        Index("ix_risk_prediction_factors_prediction_category", "risk_prediction_id", "factor_category"),
    )

    id = Column(Integer, primary_key=True)
    risk_prediction_id = Column(Integer, ForeignKey("risk_predictions.id", ondelete="RESTRICT"), nullable=False, index=True)
    factor_name = Column(String(120), nullable=False)
    factor_category = Column(String(80), nullable=True, index=True)
    raw_value = Column(Float, nullable=True)
    normalized_value = Column(Float, nullable=True)
    unit = Column(String(40), nullable=True)
    impact_score = Column(Float, nullable=True)
    importance_pct = Column(Float, nullable=True)
    explanation = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now())

    risk_prediction = relationship("RiskPrediction", back_populates="factors")


class Alert(TimestampMixin, Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_equipment_status_created_at", "equipment_id", "status", "created_at"),
        Index("ix_alerts_farm_created_at", "farm_id", "created_at"),
        Index("ix_alerts_status_created_at", "status", "created_at"),
    )

    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False, index=True)
    farm_id = Column(Integer, ForeignKey("farms.id", ondelete="RESTRICT"), nullable=False, index=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="RESTRICT"), nullable=True, index=True)
    operation_id = Column(Integer, ForeignKey("operations.id", ondelete="RESTRICT"), nullable=True, index=True)
    risk_prediction_id = Column(Integer, ForeignKey("risk_predictions.id", ondelete="RESTRICT"), nullable=True, index=True)
    iot_event_id = Column(Integer, ForeignKey("iot_events.id", ondelete="RESTRICT"), nullable=True, index=True)
    alert_type = Column(String(100), nullable=False, index=True)
    severity = Column(enum_type(AlertSeverity, "alert_severity"), nullable=False)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(
        enum_type(AlertStatus, "alert_status"),
        nullable=False,
        default=AlertStatus.OPEN,
        server_default=AlertStatus.OPEN.value,
    )
    acknowledged_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    client = relationship("Client", back_populates="alerts")
    farm = relationship("Farm", back_populates="alerts")
    equipment = relationship("Equipment", back_populates="alerts")
    operation = relationship("Operation", back_populates="alerts")
    risk_prediction = relationship("RiskPrediction", back_populates="alerts")
    iot_event = relationship("IotEvent", foreign_keys=[iot_event_id])
    acknowledged_by = relationship("User", foreign_keys=[acknowledged_by_user_id])
    notifications = relationship("Notification", back_populates="alert")


class Recommendation(TimestampMixin, Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        CheckConstraint("expected_risk_reduction_pct IS NULL OR (expected_risk_reduction_pct >= 0 AND expected_risk_reduction_pct <= 100)", name="ck_recommendation_reduction"),
        Index("ix_recommendations_equipment_priority", "equipment_id", "priority"),
    )

    id = Column(Integer, primary_key=True)
    risk_prediction_id = Column(Integer, ForeignKey("risk_predictions.id", ondelete="RESTRICT"), nullable=False, index=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="RESTRICT"), nullable=True, index=True)
    recommendation_type = Column(enum_type(RecommendationType, "recommendation_type"), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    expected_risk_reduction_pct = Column(Float, nullable=True)
    priority = Column(
        enum_type(RecommendationPriority, "recommendation_priority"),
        nullable=False,
        default=RecommendationPriority.MEDIUM,
        server_default=RecommendationPriority.MEDIUM.value,
    )
    was_applied = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    applied_at = Column(DateTime(timezone=True), nullable=True)
    applied_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True)

    risk_prediction = relationship("RiskPrediction", back_populates="recommendations")
    equipment = relationship("Equipment", back_populates="recommendations")
    applied_by = relationship("User", foreign_keys=[applied_by_user_id])
    prevented_losses = relationship("PreventedLossRecord", back_populates="recommendation")


class RiskSimulation(Base):
    __tablename__ = "risk_simulations"
    __table_args__ = (
        CheckConstraint("base_risk_score >= 0 AND base_risk_score <= 100", name="ck_simulation_base_score"),
        CheckConstraint("simulated_risk_score >= 0 AND simulated_risk_score <= 100", name="ck_simulation_score"),
        Index("ix_risk_simulations_equipment_created_at", "equipment_id", "created_at"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False, index=True)
    farm_id = Column(Integer, ForeignKey("farms.id", ondelete="RESTRICT"), nullable=False, index=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="RESTRICT"), nullable=True, index=True)
    operation_id = Column(Integer, ForeignKey("operations.id", ondelete="RESTRICT"), nullable=True, index=True)
    base_risk_score = Column(Float, nullable=False)
    simulated_risk_score = Column(Float, nullable=False)
    risk_difference = Column(Float, nullable=False)
    risk_difference_pct = Column(Float, nullable=True)
    base_conditions_json = Column(JSON_DOCUMENT, nullable=False, default=dict, server_default=text("'{}'"))
    simulated_conditions_json = Column(JSON_DOCUMENT, nullable=False, default=dict, server_default=text("'{}'"))
    recommendation = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now())

    user = relationship("User", foreign_keys=[user_id])
    client = relationship("Client", back_populates="simulations")
    farm = relationship("Farm", back_populates="simulations")
    equipment = relationship("Equipment", back_populates="simulations")
    operation = relationship("Operation", back_populates="simulations")


class PreventedLossRecord(Base):
    __tablename__ = "prevented_loss_records"
    __table_args__ = (
        CheckConstraint("previous_risk_score >= 0 AND previous_risk_score <= 100", name="ck_prevented_loss_previous_score"),
        CheckConstraint("new_risk_score >= 0 AND new_risk_score <= 100", name="ck_prevented_loss_new_score"),
        CheckConstraint("risk_reduction_pct >= 0 AND risk_reduction_pct <= 100", name="ck_prevented_loss_reduction"),
        CheckConstraint("possible_prevented_loss IS NULL OR possible_prevented_loss >= 0", name="ck_prevented_loss_possible"),
        CheckConstraint("estimated_savings_brl IS NULL OR estimated_savings_brl >= 0", name="ck_prevented_loss_savings"),
        Index("ix_prevented_loss_records_equipment_created_at", "equipment_id", "created_at"),
    )

    id = Column(Integer, primary_key=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="RESTRICT"), nullable=False, index=True)
    risk_prediction_id = Column(Integer, ForeignKey("risk_predictions.id", ondelete="RESTRICT"), nullable=False, index=True)
    recommendation_id = Column(Integer, ForeignKey("recommendations.id", ondelete="RESTRICT"), nullable=True, index=True)
    previous_risk_score = Column(Float, nullable=False)
    new_risk_score = Column(Float, nullable=False)
    risk_reduction_pct = Column(Float, nullable=False)
    possible_prevented_loss = Column(Numeric(14, 2), nullable=True)
    estimated_savings_brl = Column(Numeric(14, 2), nullable=True)
    calculation_method = Column(String(200), nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now())

    equipment = relationship("Equipment", back_populates="prevented_losses")
    risk_prediction = relationship("RiskPrediction", back_populates="prevented_losses")
    recommendation = relationship("Recommendation", back_populates="prevented_losses")


class DataSource(TimestampMixin, ActiveMixin, Base):
    __tablename__ = "data_sources"
    __table_args__ = (UniqueConstraint("name", "provider", name="uq_data_sources_name_provider"),)

    id = Column(Integer, primary_key=True)
    name = Column(String(160), nullable=False, index=True)
    provider = Column(String(160), nullable=False)
    source_type = Column(String(100), nullable=False, index=True)
    description = Column(Text, nullable=True)
    url_reference = Column(String(500), nullable=True)


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True)
    key = Column(String(160), nullable=False, unique=True, index=True)
    value_json = Column(JSON_DOCUMENT, nullable=False, default=dict, server_default=text("'{}'"))
    description = Column(Text, nullable=True)
    updated_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow, server_default=func.now())

    updated_by = relationship("User", foreign_keys=[updated_by_user_id])


class GeneratedReport(Base):
    __tablename__ = "generated_reports"
    __table_args__ = (Index("ix_generated_reports_farm_period", "farm_id", "period_start", "period_end"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False, index=True)
    farm_id = Column(Integer, ForeignKey("farms.id", ondelete="RESTRICT"), nullable=True, index=True)
    report_type = Column(String(120), nullable=False, index=True)
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)
    file_path = Column(String(500), nullable=True)
    status = Column(
        enum_type(ReportStatus, "generated_report_status"),
        nullable=False,
        default=ReportStatus.PENDING,
        server_default=ReportStatus.PENDING.value,
    )
    parameters_json = Column(JSON_DOCUMENT, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now())

    user = relationship("User", foreign_keys=[user_id])
    client = relationship("Client", back_populates="generated_reports")
    farm = relationship("Farm", back_populates="generated_reports")


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_read_created_at", "user_id", "is_read", "created_at"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id", ondelete="RESTRICT"), nullable=True, index=True)
    notification_type = Column(enum_type(NotificationType, "notification_type"), nullable=False)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now())

    user = relationship("User", foreign_keys=[user_id], back_populates="notifications")
    alert = relationship("Alert", back_populates="notifications")


__all__ = [
    "Alert",
    "AlertSeverity",
    "AlertStatus",
    "Client",
    "ClientStatus",
    "ClientType",
    "DataSource",
    "DatasetSourceType",
    "DatasetVersion",
    "GeneratedReport",
    "Incident",
    "IncidentSeverity",
    "IncidentStatus",
    "IncidentType",
    "ModelStatus",
    "ModelVersion",
    "Notification",
    "NotificationType",
    "Operation",
    "OperationStatus",
    "OperationType",
    "PreventedLossRecord",
    "Recommendation",
    "RecommendationPriority",
    "RecommendationType",
    "ReportStatus",
    "RiskLevel",
    "RiskPrediction",
    "RiskPredictionFactor",
    "RiskSimulation",
    "SoilRecord",
    "SoilSource",
    "SystemSetting",
    "TerrainRecord",
    "TerrainSource",
    "WeatherRecord",
    "WeatherSource",
    "user_clients",
    "user_equipments",
    "user_farms",
]
