"""Pydantic contracts for the normalized AgroGuardian database domain.

Existing API contracts remain in ``backend.schemas``. These schemas are safe
for future routers and services: no password hash, token or device API key is
ever exposed in a response model.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .models_extended import (
    AlertSeverity,
    AlertStatus,
    ClientStatus,
    ClientType,
    DatasetSourceType,
    IncidentSeverity,
    IncidentStatus,
    IncidentType,
    ModelStatus,
    NotificationType,
    OperationStatus,
    OperationType,
    RecommendationPriority,
    RecommendationType,
    ReportStatus,
    RiskLevel,
    SoilSource,
    TerrainSource,
    WeatherSource,
)
from .schemas import UserCreate, UserResponse, UserUpdate


class ORMResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=40)
    description: str | None = None
    is_system_role: bool = False


class RoleUpdate(BaseModel):
    description: str | None = None
    is_system_role: bool | None = None


class RoleDatabaseResponse(ORMResponse):
    id: int
    name: str
    description: str | None = None
    is_system_role: bool
    created_at: datetime
    updated_at: datetime


class PermissionCreate(BaseModel):
    code: str = Field(min_length=3, max_length=80)
    name: str = Field(min_length=2, max_length=120)
    description: str | None = None


class PermissionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = None


class PermissionDatabaseResponse(ORMResponse):
    id: int
    code: str
    name: str
    description: str | None = None
    created_at: datetime


class UserClientGrant(BaseModel):
    user_id: int
    client_id: int


class UserFarmGrant(BaseModel):
    user_id: int
    farm_id: int


class UserEquipmentGrant(BaseModel):
    user_id: int
    equipment_id: int


class ClientBase(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    corporate_name: str | None = Field(default=None, max_length=200)
    document: str | None = Field(default=None, max_length=40)
    client_type: ClientType = ClientType.COMPANY
    email: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=40)
    status: ClientStatus = ClientStatus.ACTIVE
    region: str | None = Field(default=None, max_length=120)
    notes: str | None = None
    is_active: bool = True


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    corporate_name: str | None = Field(default=None, max_length=200)
    document: str | None = Field(default=None, max_length=40)
    client_type: ClientType | None = None
    email: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=40)
    status: ClientStatus | None = None
    region: str | None = Field(default=None, max_length=120)
    notes: str | None = None
    is_active: bool | None = None


class ClientResponse(ClientBase, ORMResponse):
    id: int
    created_at: datetime
    updated_at: datetime


class FarmBase(BaseModel):
    client_id: int | None = None
    name: str = Field(min_length=2, max_length=120)
    municipality: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=80)
    country: str = Field(default="BR", min_length=2, max_length=2)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    total_area_ha: float | None = Field(default=None, ge=0)
    cultivated_area_ha: float | None = Field(default=None, ge=0)
    main_crop: str | None = Field(default=None, max_length=120)
    status: str = Field(default="active", max_length=40)
    notes: str | None = None
    is_active: bool = True


class FarmCreate(FarmBase):
    region: str = Field(min_length=2, max_length=120)


class FarmUpdate(BaseModel):
    client_id: int | None = None
    name: str | None = Field(default=None, min_length=2, max_length=120)
    municipality: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=80)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    total_area_ha: float | None = Field(default=None, ge=0)
    cultivated_area_ha: float | None = Field(default=None, ge=0)
    main_crop: str | None = Field(default=None, max_length=120)
    status: str | None = Field(default=None, max_length=40)
    notes: str | None = None
    is_active: bool | None = None


class FarmResponse(FarmBase, ORMResponse):
    id: int
    region: str
    created_at: datetime
    updated_at: datetime


class EquipmentBase(BaseModel):
    farm_id: int
    name: str = Field(min_length=2, max_length=120)
    equipment_type: str = Field(min_length=2, max_length=60)
    manufacturer: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=120)
    year: int | None = Field(default=None, ge=1900, le=2100)
    serial_number: str | None = Field(default=None, max_length=120)
    internal_code: str | None = Field(default=None, max_length=120)
    status: str = Field(default="active", max_length=40)
    purchase_value: float | None = Field(default=None, ge=0)
    estimated_repair_cost: float | None = Field(default=None, ge=0)
    notes: str | None = None
    is_active: bool = True


class EquipmentDatabaseCreate(EquipmentBase):
    client_name: str = Field(min_length=2, max_length=120)


class EquipmentDatabaseUpdate(BaseModel):
    farm_id: int | None = None
    name: str | None = Field(default=None, min_length=2, max_length=120)
    equipment_type: str | None = Field(default=None, min_length=2, max_length=60)
    manufacturer: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=120)
    year: int | None = Field(default=None, ge=1900, le=2100)
    serial_number: str | None = Field(default=None, max_length=120)
    internal_code: str | None = Field(default=None, max_length=120)
    status: str | None = Field(default=None, max_length=40)
    purchase_value: float | None = Field(default=None, ge=0)
    estimated_repair_cost: float | None = Field(default=None, ge=0)
    notes: str | None = None
    is_active: bool | None = None


class EquipmentDatabaseResponse(EquipmentBase, ORMResponse):
    id: int
    client_name: str
    created_at: datetime
    updated_at: datetime


class IotDeviceDatabaseCreate(BaseModel):
    equipment_id: int
    device_identifier: str = Field(min_length=3, max_length=120)
    name: str = Field(min_length=2, max_length=160)
    device_type: str = Field(default="ESP32", max_length=60)
    firmware_version: str | None = Field(default=None, max_length=80)
    status: str = Field(default="offline", max_length=40)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class IotDeviceDatabaseUpdate(BaseModel):
    equipment_id: int | None = None
    name: str | None = Field(default=None, min_length=2, max_length=160)
    device_type: str | None = Field(default=None, max_length=60)
    firmware_version: str | None = Field(default=None, max_length=80)
    status: str | None = Field(default=None, max_length=40)
    metadata_json: dict[str, Any] | None = None
    is_active: bool | None = None


class IotDeviceDatabaseResponse(ORMResponse):
    id: int
    equipment_id: int
    device_identifier: str | None = None
    name: str
    device_type: str
    firmware_version: str | None = None
    status: str
    last_seen_at: datetime | None = None
    metadata_json: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class OperationBase(BaseModel):
    client_id: int
    farm_id: int
    equipment_id: int
    operation_type: OperationType
    crop_type: str | None = Field(default=None, max_length=120)
    started_at: datetime
    finished_at: datetime | None = None
    status: OperationStatus = OperationStatus.PLANNED
    operator_user_id: int | None = None
    notes: str | None = None
    is_active: bool = True


class OperationCreate(OperationBase):
    pass


class OperationUpdate(BaseModel):
    crop_type: str | None = Field(default=None, max_length=120)
    finished_at: datetime | None = None
    status: OperationStatus | None = None
    operator_user_id: int | None = None
    notes: str | None = None
    is_active: bool | None = None


class OperationResponse(OperationBase, ORMResponse):
    id: int
    created_at: datetime
    updated_at: datetime


class WeatherRecordBase(BaseModel):
    farm_id: int
    source: WeatherSource
    recorded_at: datetime
    temperature_c: float | None = None
    humidity_pct: float | None = Field(default=None, ge=0, le=100)
    precipitation_mm: float | None = Field(default=None, ge=0)
    wind_speed_kmh: float | None = Field(default=None, ge=0)
    pressure_hpa: float | None = Field(default=None, ge=0)
    weather_condition: str | None = Field(default=None, max_length=80)
    raw_data_json: dict[str, Any] | None = None


class WeatherRecordCreate(WeatherRecordBase):
    pass


class WeatherRecordUpdate(BaseModel):
    temperature_c: float | None = None
    humidity_pct: float | None = Field(default=None, ge=0, le=100)
    precipitation_mm: float | None = Field(default=None, ge=0)
    wind_speed_kmh: float | None = Field(default=None, ge=0)
    pressure_hpa: float | None = Field(default=None, ge=0)
    weather_condition: str | None = Field(default=None, max_length=80)
    raw_data_json: dict[str, Any] | None = None


class WeatherRecordResponse(WeatherRecordBase, ORMResponse):
    id: int
    created_at: datetime


class SoilRecordBase(BaseModel):
    farm_id: int
    source: SoilSource
    sampled_at: datetime
    soil_moisture_pct: float | None = Field(default=None, ge=0, le=100)
    clay_pct: float | None = Field(default=None, ge=0, le=100)
    sand_pct: float | None = Field(default=None, ge=0, le=100)
    silt_pct: float | None = Field(default=None, ge=0, le=100)
    organic_carbon: float | None = Field(default=None, ge=0)
    ph: float | None = Field(default=None, ge=0, le=14)
    bulk_density: float | None = Field(default=None, ge=0)
    drainage_class: str | None = Field(default=None, max_length=80)
    raw_data_json: dict[str, Any] | None = None


class SoilRecordCreate(SoilRecordBase):
    pass


class SoilRecordUpdate(BaseModel):
    soil_moisture_pct: float | None = Field(default=None, ge=0, le=100)
    clay_pct: float | None = Field(default=None, ge=0, le=100)
    sand_pct: float | None = Field(default=None, ge=0, le=100)
    silt_pct: float | None = Field(default=None, ge=0, le=100)
    organic_carbon: float | None = Field(default=None, ge=0)
    ph: float | None = Field(default=None, ge=0, le=14)
    bulk_density: float | None = Field(default=None, ge=0)
    drainage_class: str | None = Field(default=None, max_length=80)
    raw_data_json: dict[str, Any] | None = None


class SoilRecordResponse(SoilRecordBase, ORMResponse):
    id: int
    created_at: datetime


class TerrainRecordBase(BaseModel):
    farm_id: int
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    elevation_m: float | None = None
    slope_deg: float | None = Field(default=None, ge=0, le=90)
    distance_to_water_m: float | None = Field(default=None, ge=0)
    distance_to_road_m: float | None = Field(default=None, ge=0)
    road_type: str | None = Field(default=None, max_length=80)
    land_use_class: str | None = Field(default=None, max_length=120)
    source: TerrainSource


class TerrainRecordCreate(TerrainRecordBase):
    pass


class TerrainRecordUpdate(BaseModel):
    elevation_m: float | None = None
    slope_deg: float | None = Field(default=None, ge=0, le=90)
    distance_to_water_m: float | None = Field(default=None, ge=0)
    distance_to_road_m: float | None = Field(default=None, ge=0)
    road_type: str | None = Field(default=None, max_length=80)
    land_use_class: str | None = Field(default=None, max_length=120)
    source: TerrainSource | None = None


class TerrainRecordResponse(TerrainRecordBase, ORMResponse):
    id: int
    created_at: datetime
    updated_at: datetime


class IncidentBase(BaseModel):
    client_id: int
    farm_id: int
    equipment_id: int | None = None
    operation_id: int | None = None
    incident_type: IncidentType
    severity: IncidentSeverity
    occurred_at: datetime
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    description: str | None = None
    estimated_damage_brl: Decimal | None = Field(default=None, ge=0)
    was_preventable: bool | None = None
    status: IncidentStatus = IncidentStatus.OPEN


class IncidentCreate(IncidentBase):
    pass


class IncidentUpdate(BaseModel):
    severity: IncidentSeverity | None = None
    description: str | None = None
    estimated_damage_brl: Decimal | None = Field(default=None, ge=0)
    was_preventable: bool | None = None
    status: IncidentStatus | None = None


class IncidentResponse(IncidentBase, ORMResponse):
    id: int
    created_at: datetime
    updated_at: datetime


class RiskPredictionFactorCreate(BaseModel):
    factor_name: str = Field(min_length=1, max_length=120)
    factor_category: str | None = Field(default=None, max_length=80)
    raw_value: float | None = None
    normalized_value: float | None = None
    unit: str | None = Field(default=None, max_length=40)
    impact_score: float | None = Field(default=None, ge=-100, le=100)
    importance_pct: float | None = Field(default=None, ge=0, le=100)
    explanation: str | None = None


class RiskPredictionFactorResponse(RiskPredictionFactorCreate, ORMResponse):
    id: int
    risk_prediction_id: int
    created_at: datetime


class RiskPredictionBase(BaseModel):
    client_id: int
    farm_id: int
    equipment_id: int | None = None
    operation_id: int | None = None
    risk_score: float = Field(ge=0, le=100)
    risk_level: RiskLevel
    confidence_score: float | None = Field(default=None, ge=0, le=100)
    main_risk_factor: str | None = Field(default=None, max_length=160)
    model_version_id: int | None = None
    telemetry_id: int | None = None
    input_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    explanation_summary: str | None = None
    recommendation_summary: str | None = None


class RiskPredictionCreate(RiskPredictionBase):
    factors: list[RiskPredictionFactorCreate] = Field(default_factory=list)


class RiskPredictionResponse(RiskPredictionBase, ORMResponse):
    id: int
    created_at: datetime
    factors: list[RiskPredictionFactorResponse] = Field(default_factory=list)


class AlertBase(BaseModel):
    client_id: int
    farm_id: int
    equipment_id: int | None = None
    operation_id: int | None = None
    risk_prediction_id: int | None = None
    iot_event_id: int | None = None
    alert_type: str = Field(min_length=1, max_length=100)
    severity: AlertSeverity
    title: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1)
    status: AlertStatus = AlertStatus.OPEN


class AlertCreate(AlertBase):
    pass


class AlertUpdate(BaseModel):
    status: AlertStatus | None = None
    acknowledged_by_user_id: int | None = None
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None


class AlertResponse(AlertBase, ORMResponse):
    id: int
    acknowledged_by_user_id: int | None = None
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class RecommendationBase(BaseModel):
    risk_prediction_id: int
    equipment_id: int | None = None
    recommendation_type: RecommendationType
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    expected_risk_reduction_pct: float | None = Field(default=None, ge=0, le=100)
    priority: RecommendationPriority = RecommendationPriority.MEDIUM
    was_applied: bool = False


class RecommendationCreate(RecommendationBase):
    pass


class RecommendationUpdate(BaseModel):
    expected_risk_reduction_pct: float | None = Field(default=None, ge=0, le=100)
    priority: RecommendationPriority | None = None
    was_applied: bool | None = None
    applied_at: datetime | None = None
    applied_by_user_id: int | None = None


class RecommendationResponse(RecommendationBase, ORMResponse):
    id: int
    applied_at: datetime | None = None
    applied_by_user_id: int | None = None
    created_at: datetime
    updated_at: datetime


class RiskSimulationBase(BaseModel):
    user_id: int
    client_id: int
    farm_id: int
    equipment_id: int | None = None
    operation_id: int | None = None
    base_risk_score: float = Field(ge=0, le=100)
    simulated_risk_score: float = Field(ge=0, le=100)
    risk_difference: float
    risk_difference_pct: float | None = None
    base_conditions_json: dict[str, Any] = Field(default_factory=dict)
    simulated_conditions_json: dict[str, Any] = Field(default_factory=dict)
    recommendation: str | None = None


class RiskSimulationCreate(RiskSimulationBase):
    pass


class RiskSimulationResponse(RiskSimulationBase, ORMResponse):
    id: int
    created_at: datetime


class PreventedLossBase(BaseModel):
    equipment_id: int
    risk_prediction_id: int
    recommendation_id: int | None = None
    previous_risk_score: float = Field(ge=0, le=100)
    new_risk_score: float = Field(ge=0, le=100)
    risk_reduction_pct: float = Field(ge=0, le=100)
    possible_prevented_loss: Decimal | None = Field(default=None, ge=0)
    estimated_savings_brl: Decimal | None = Field(default=None, ge=0)
    calculation_method: str = Field(min_length=1, max_length=200)
    notes: str | None = None


class PreventedLossCreate(PreventedLossBase):
    pass


class PreventedLossResponse(PreventedLossBase, ORMResponse):
    id: int
    created_at: datetime


class DatasetVersionBase(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=80)
    description: str | None = None
    source_type: DatasetSourceType
    record_count: int = Field(default=0, ge=0)
    feature_count: int = Field(default=0, ge=0)
    file_path: str | None = Field(default=None, max_length=500)
    checksum: str | None = Field(default=None, max_length=128)
    metadata_json: dict[str, Any] | None = None


class DatasetVersionCreate(DatasetVersionBase):
    created_by_user_id: int | None = None


class DatasetVersionUpdate(BaseModel):
    description: str | None = None
    record_count: int | None = Field(default=None, ge=0)
    feature_count: int | None = Field(default=None, ge=0)
    file_path: str | None = Field(default=None, max_length=500)
    checksum: str | None = Field(default=None, max_length=128)
    metadata_json: dict[str, Any] | None = None


class DatasetVersionResponse(DatasetVersionBase, ORMResponse):
    id: int
    created_at: datetime
    created_by_user_id: int | None = None


class ModelVersionBase(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=80)
    algorithm: str = Field(min_length=1, max_length=120)
    status: ModelStatus = ModelStatus.TRAINING
    dataset_version_id: int | None = None
    trained_at: datetime | None = None
    deployed_at: datetime | None = None
    accuracy: float | None = Field(default=None, ge=0, le=1)
    precision_score: float | None = Field(default=None, ge=0, le=1)
    recall_score: float | None = Field(default=None, ge=0, le=1)
    f1_score: float | None = Field(default=None, ge=0, le=1)
    roc_auc: float | None = Field(default=None, ge=0, le=1)
    metrics_json: dict[str, Any] | None = None
    parameters_json: dict[str, Any] | None = None
    feature_list_json: list[str] | None = None
    artifact_path: str | None = Field(default=None, max_length=500)
    is_active: bool = True


class ModelVersionCreate(ModelVersionBase):
    pass


class ModelVersionUpdate(BaseModel):
    status: ModelStatus | None = None
    deployed_at: datetime | None = None
    accuracy: float | None = Field(default=None, ge=0, le=1)
    precision_score: float | None = Field(default=None, ge=0, le=1)
    recall_score: float | None = Field(default=None, ge=0, le=1)
    f1_score: float | None = Field(default=None, ge=0, le=1)
    roc_auc: float | None = Field(default=None, ge=0, le=1)
    metrics_json: dict[str, Any] | None = None
    parameters_json: dict[str, Any] | None = None
    feature_list_json: list[str] | None = None
    artifact_path: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class ModelVersionResponse(ModelVersionBase, ORMResponse):
    id: int
    created_at: datetime
    updated_at: datetime


class DataSourceBase(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    provider: str = Field(min_length=1, max_length=160)
    source_type: str = Field(min_length=1, max_length=100)
    description: str | None = None
    url_reference: str | None = Field(default=None, max_length=500)
    is_active: bool = True


class DataSourceCreate(DataSourceBase):
    pass


class DataSourceUpdate(BaseModel):
    description: str | None = None
    url_reference: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class DataSourceResponse(DataSourceBase, ORMResponse):
    id: int
    created_at: datetime
    updated_at: datetime


class SystemSettingCreate(BaseModel):
    key: str = Field(min_length=1, max_length=160)
    value_json: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None


class SystemSettingUpdate(BaseModel):
    value_json: dict[str, Any]
    description: str | None = None


class SystemSettingResponse(ORMResponse):
    id: int
    key: str
    value_json: dict[str, Any]
    description: str | None = None
    updated_by_user_id: int | None = None
    updated_at: datetime


class AlertPolicyDatabaseCreate(BaseModel):
    client_id: int | None = None
    farm_id: int | None = None
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    operation_type: str = Field(min_length=1, max_length=40)
    risk_threshold: float | None = Field(default=None, ge=0, le=100)
    severity: AlertSeverity | None = None
    action_type: str | None = Field(default=None, max_length=80)
    is_active: bool = True


class AlertPolicyDatabaseUpdate(BaseModel):
    description: str | None = None
    risk_threshold: float | None = Field(default=None, ge=0, le=100)
    severity: AlertSeverity | None = None
    action_type: str | None = Field(default=None, max_length=80)
    is_active: bool | None = None


class AlertPolicyDatabaseResponse(AlertPolicyDatabaseCreate, ORMResponse):
    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class GeneratedReportCreate(BaseModel):
    user_id: int
    client_id: int
    farm_id: int | None = None
    report_type: str = Field(min_length=1, max_length=120)
    period_start: date | None = None
    period_end: date | None = None
    parameters_json: dict[str, Any] | None = None


class GeneratedReportUpdate(BaseModel):
    file_path: str | None = Field(default=None, max_length=500)
    status: ReportStatus | None = None
    parameters_json: dict[str, Any] | None = None


class GeneratedReportResponse(GeneratedReportCreate, ORMResponse):
    id: int
    file_path: str | None = None
    status: ReportStatus
    created_at: datetime


class NotificationCreate(BaseModel):
    user_id: int
    alert_id: int | None = None
    notification_type: NotificationType
    title: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1)


class NotificationUpdate(BaseModel):
    is_read: bool
    read_at: datetime | None = None


class NotificationResponse(NotificationCreate, ORMResponse):
    id: int
    is_read: bool
    read_at: datetime | None = None
    created_at: datetime


class AuditLogResponse(ORMResponse):
    id: int
    user_id: int | None = None
    action: str
    entity_type: str | None = None
    entity_id: str | None = None
    request_id: str | None = None
    ip_address: str | None = None
    old_values_json: dict[str, Any] | None = None
    new_values_json: dict[str, Any] | None = None
    metadata_json: dict[str, Any] | None = None
    created_at: datetime | None = None


__all__ = [name for name in globals() if name.endswith(("Create", "Update", "Response", "Grant"))]
