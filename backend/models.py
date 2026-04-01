from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from .database import Base


class Farm(Base):
    __tablename__ = "farms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    region = Column(String(120), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)

    equipment = relationship("Equipment", back_populates="farm")


class Equipment(Base):
    __tablename__ = "equipment"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    equipment_type = Column(String(60), nullable=False)
    client_name = Column(String(120), nullable=False)
    farm_id = Column(Integer, ForeignKey("farms.id"), nullable=False)

    farm = relationship("Farm", back_populates="equipment")
    telemetry = relationship("TelemetryRecord", back_populates="equipment")


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

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    actor = Column(String(40), nullable=False)
    action = Column(String(80), nullable=False)
    payload = Column(JSON, nullable=False)


class AlertPolicy(Base):
    __tablename__ = "alert_policies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    operation_type = Column(String(40), nullable=False)  # campo, transporte, proximidade_agua, all

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
