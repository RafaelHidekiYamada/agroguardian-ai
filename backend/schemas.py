from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List
from pydantic import BaseModel, Field

class TelemetryInput(BaseModel):
    equipment_id: int = Field(default=1)
    farm_id: int = Field(default=1)
    region: str = Field(default="Guarulhos - SP")
    operation_type: str = Field(default="campo")
    clima: str = Field(default="chuva")
    umidade_solo: float = Field(ge=0, le=100)
    inclinacao: float = Field(ge=0, le=90)
    distancia_agua: float = Field(ge=0, le=10000)
    velocidade: float = Field(ge=0, le=200)
    historico_sinistros: float = Field(ge=0, le=100)
    chuva_mm: float = Field(ge=0, le=500)
    solo_instavel: int = Field(default=0, ge=0, le=1)
    latitude: float = Field(default=-23.455)
    longitude: float = Field(default=-46.533)

class ScenarioInput(TelemetryInput):
    scenario_name: str = Field(default="Chuva amanhã")

class PredictionResponse(BaseModel):
    timestamp: datetime
    model_version: str
    risk_score: float
    risk_label: str
    alert_level: str
    alerts: List[Dict[str, Any]]
    recommendation: str
    safe_route: Dict[str, Any]
    explanation: Dict[str, float]
    weather: Dict[str, Any]
    audit_id: int

class SafeRouteRequest(BaseModel):
    origin_name: str = "Ponto atual"
    destination_name: str = "Armazém / Oficina"
    latitude: float = -23.455
    longitude: float = -46.533

class SafeRouteResponse(BaseModel):
    recommended_route: str
    route_score: float
    alternatives: List[Dict[str, Any]]
    rationale: str

class SummaryResponse(BaseModel):
    total_predictions: int
    high_risk_count: int
    average_risk: float
    alerts_today: int
    top_equipment: List[Dict[str, Any]]
    top_regions: List[Dict[str, Any]]
    risk_trend: List[Dict[str, Any]]

class AuditResponse(BaseModel):
    id: int
    timestamp: datetime
    actor: str
    action: str
    payload: Dict[str, Any]
