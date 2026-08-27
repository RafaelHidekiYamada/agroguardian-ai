from __future__ import annotations

from typing import Any, Dict

from .config import settings
from .feature_engineering import FEATURE_ORDER
from .ml_registry import get_ml_status


def build_operational_context(
    input_payload: Dict[str, Any],
    weather: Dict[str, Any],
    geo_context: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "input": input_payload,
        "weather": weather,
        "geo_context": geo_context,
        "sources": {
            "telemetry": "payload/esp32",
            "weather": weather.get("source", "unknown"),
            "geointelligence": geo_context.get("nearest_water", {}).get("source", "internal_geo_engine"),
        },
    }


def build_prediction_trace(
    model_version: str,
    features: Dict[str, Any],
    risk_components: Dict[str, Any],
    explanation: Dict[str, Any],
    safe_route: Dict[str, Any],
    recommendation: str,
    decision_support: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "model_version": model_version,
        "feature_order": FEATURE_ORDER,
        "features_used": features,
        "risk_components": risk_components,
        "explanation": explanation,
        "safe_route": safe_route,
        "recommendation": recommendation,
        "decision_support": decision_support,
    }


def build_system_architecture() -> Dict[str, Any]:
    return {
        "project": "AgroGuardian AI",
        "purpose": "Plataforma inteligente de prevenção de sinistros agrícolas",
        "central_module": "integration_hub",
        "layers": [
            {
                "name": "Entrada de dados",
                "components": [
                    "telemetria manual/simulada",
                    "telemetria ESP32",
                    "sensores de temperatura, umidade, pressao, inclinacao e obstaculo",
                    "coordenadas geográficas",
                    "clima externo",
                    "dados operacionais",
                ],
            },
            {
                "name": "Integração e processamento",
                "components": [
                    "integration_hub",
                    "feature_engineering",
                    "weather_service",
                    "geointelligence",
                    "openstreetmap_overpass",
                ],
            },
            {
                "name": "IA e decisão",
                "components": [
                    "risk_model",
                    "ml_registry",
                    "explainability",
                    "route_ai",
                    "alert_policy_engine",
                ],
            },
            {
                "name": "Governança e segurança",
                "components": [
                    "JWT auth",
                    "RBAC por perfil",
                    "audit trail",
                    "prediction records",
                    "telemetry records",
                ],
            },
            {
                "name": "Apresentação",
                "components": [
                    "FastAPI",
                    "Swagger",
                    "Streamlit dashboard",
                    "R analytics",
                ],
            },
        ],
        "core_flows": [
            "Payload operacional -> clima + geointeligência -> features -> score IA -> alertas -> recomendação -> auditoria -> dashboard",
            "Cenário simulado -> predição reutilizada -> comparação base vs simulado",
            "Usuário autenticado -> perfil autorizado -> acesso seletivo a dashboards e políticas",
        ],
        "deployment": {
            "current": {
                "platform": "Render",
                "services": ["API", "Dashboard"],
                "database": "SQLite/PostgreSQL-ready",
            },
            "future": {
                "platform": "AWS",
                "services": [
                    "EC2 ou ECS",
                    "RDS PostgreSQL",
                    "S3 para artefatos",
                    "CloudWatch",
                    "IAM",
                ],
            },
        },
        "security": {
            "authentication": "JWT",
            "authorization": ["admin", "gestor", "sompo", "operador"],
            "auditability": True,
            "api_docs": "Swagger/OpenAPI",
        },
    }


def build_system_status() -> Dict[str, Any]:
    ml_status = get_ml_status()

    return {
        "project": "AgroGuardian AI",
        "api": {
            "status": "online",
            "model_version": settings.model_version,
        },
        "ml": ml_status,
        "features": {
            "count": len(FEATURE_ORDER),
            "feature_order": FEATURE_ORDER,
        },
        "modules": {
            "weather_service": "enabled",
            "geointelligence": "enabled",
            "openstreetmap_overpass": "enabled",
            "esp32_telemetry": "enabled",
            "regional_risk": "enabled",
            "equipment_history_risk": "enabled",
            "route_ai": "enabled",
            "explainability": "enabled",
            "audit": "enabled",
            "security": "enabled",
            "dashboard": "enabled",
            "r_analytics": "enabled",
        },
        "deployment": {
            "current_target": "Render",
            "aws_ready": True,
        },
    }
