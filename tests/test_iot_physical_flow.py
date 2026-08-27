from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend import models
from backend.database import SessionLocal
from backend.feature_engineering import STANDARD_GRAVITY_M_S2, build_mpu6050_features
from backend.iot_processing import RiskContext, build_iot_context, build_iot_events, telemetry_status
from backend.main import _latest_usable_iot_context, _prepare_prediction, app
from backend.schemas import IotTelemetryInput, TelemetryInput


ESP_TELEMETRY_ENDPOINT = "/api/v1/telemetry/esp"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "username": os.environ["INITIAL_ADMIN_USERNAME"],
            "password": os.environ["INITIAL_ADMIN_PASSWORD"],
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_device(client: TestClient, suffix: str) -> tuple[str, str, dict[str, str]]:
    admin_headers = _admin_headers(client)
    device_id = f"ESP32-PHYSICAL-{suffix}-{int(time.time() * 1000)}"
    response = client.post(
        "/api/v1/admin/iot/devices",
        headers=admin_headers,
        json={
            "device_identifier": device_id,
            "equipment_id": 1,
            "name": f"ESP32 {suffix}",
            "firmware_version": "test-physical",
        },
    )
    assert response.status_code == 200, response.text
    return device_id, response.json()["api_key"], admin_headers


def _physical_payload(device_id: str, sequence_number: int, *, critical: bool = False) -> dict:
    return {
        "device_id": device_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sequence_number": sequence_number,
        "operation_type": "campo",
        "firmware_version": "test-physical",
        "bme280": {
            "temperature_c": 42.0 if critical else 27.0,
            "humidity_pct": 96.0 if critical else 68.0,
            "pressure_hpa": 955.0 if critical else 1011.0,
        },
        "jsn_sr04t": {"distance_cm": 20.0 if critical else 240.0, "timeout": False, "out_of_range": False},
        "mpu6050": {
            "accel_x": 18.0 if critical else 0.1,
            "accel_y": -12.0 if critical else -0.1,
            "accel_z": 16.0 if critical else 9.78,
            "pitch": 30.0 if critical else 4.0,
            "roll": 12.0 if critical else 1.0,
            "inclination_deg": 30.0 if critical else 4.0,
        },
        "gps": {"latitude": -23.455, "longitude": -46.533},
        "speed_kmh": 0,
    }


def _device_headers(device_id: str, api_key: str) -> dict[str, str]:
    return {"X-Device-ID": device_id, "X-API-Key": api_key}


def test_canonical_payload_persists_prediction_factors_and_events(client: TestClient):
    device_id, api_key, _admin_headers_value = _create_device(client, "LINK")
    response = client.post(
        ESP_TELEMETRY_ENDPOINT,
        headers=_device_headers(device_id, api_key),
        json=_physical_payload(device_id, 1, critical=True),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["risk_updated"] is True
    assert body["events"]
    assert {event["event_type"] for event in body["events"]} >= {
        "OBSTACLE_CRITICAL",
        "CRITICAL_INCLINATION",
        "ABNORMAL_ACCELERATION",
    }

    with SessionLocal() as db:
        telemetry = db.get(models.IotTelemetry, body["telemetry_id"])
        assert telemetry is not None
        assert telemetry.iot_device_id is not None
        assert telemetry.sequence_number == 1
        assert telemetry.raw_payload_json["jsn_sr04t"]["distance_cm"] == 20.0
        prediction = (
            db.query(models.RiskPrediction)
            .filter(models.RiskPrediction.telemetry_id == telemetry.id)
            .one()
        )
        categories = {factor.factor_category for factor in prediction.factors}
        assert {"iot_jsn_sr04t", "iot_mpu6050", "iot_bme280"}.issubset(categories)
        events = db.query(models.IotEvent).filter(models.IotEvent.telemetry_id == telemetry.id).all()
        assert len(events) >= 3
        assert all(event.risk_prediction_id == prediction.id for event in events)
        assert db.query(models.AuditLog).filter(models.AuditLog.action == "iot_telemetry_received").count() == 0
        assert db.query(models.AuditLog).filter(models.AuditLog.action == "iot_critical_event").count() >= 1


def test_duplicate_sequence_and_api_key_revocation(client: TestClient):
    device_id, api_key, admin_headers = _create_device(client, "SECURITY")
    payload = _physical_payload(device_id, 99)
    first = client.post("/api/v1/iot/telemetry", headers=_device_headers(device_id, api_key), json=payload)
    assert first.status_code == 200, first.text
    duplicate = client.post(ESP_TELEMETRY_ENDPOINT, headers=_device_headers(device_id, api_key), json=payload)
    assert duplicate.status_code == 409

    revoked = client.put(
        f"/api/v1/admin/iot/devices/{device_id}",
        headers=admin_headers,
        json={"revoke_api_key": True},
    )
    assert revoked.status_code == 200, revoked.text
    rejected = client.post(
        ESP_TELEMETRY_ENDPOINT,
        headers=_device_headers(device_id, api_key),
        json=_physical_payload(device_id, 100),
    )
    assert rejected.status_code == 401


def test_latest_fresh_telemetry_is_applied_to_normal_risk_prediction(client: TestClient):
    device_id, api_key, admin_headers = _create_device(client, "CONTEXT")
    accepted = client.post(
        ESP_TELEMETRY_ENDPOINT,
        headers=_device_headers(device_id, api_key),
        json=_physical_payload(device_id, 7, critical=True),
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["data_quality_status"] == "VALID"
    assert accepted.json()["telemetry_status"] == "LIVE"
    with SessionLocal() as db:
        assert _latest_usable_iot_context(db, 1) is not None

    response = client.post(
        "/api/v1/risk/predict",
        headers=admin_headers,
        json={
            "equipment_id": 1,
            "farm_id": 1,
            "region": "Ribeirao Preto - SP",
            "operation_type": "campo",
            "clima": "sol",
            "umidade_solo": 30,
            "inclinacao": 1,
            "distancia_agua": 999,
            "velocidade": 0,
            "historico_sinistros": 0,
            "chuva_mm": 0,
            "solo_instavel": 0,
            "latitude": -23.455,
            "longitude": -46.533,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["iot_used"] is True
    assert body["telemetry_id"] == accepted.json()["telemetry_id"]
    assert {factor["factor"] for factor in body["factors"]} >= {"obstacle", "tilt"}


def test_stale_reading_is_not_used_by_ai(client: TestClient):
    device_id, api_key, _admin_headers_value = _create_device(client, "STALE")
    payload = _physical_payload(device_id, 11)
    payload["timestamp"] = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    stale_response = client.post(
        ESP_TELEMETRY_ENDPOINT,
        headers=_device_headers(device_id, api_key),
        json=payload,
    )
    assert stale_response.status_code == 200, stale_response.text
    assert stale_response.json()["risk_updated"] is False
    assert stale_response.json()["telemetry_status"] == "STALE"

    payload = _physical_payload(device_id, 12)
    payload["timestamp"] = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    response = client.post(
        ESP_TELEMETRY_ENDPOINT,
        headers=_device_headers(device_id, api_key),
        json=payload,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["risk_updated"] is False
    assert body["telemetry_status"] == "OFFLINE"


def test_pressure_pa_is_normalized_inside_bme280_payload():
    payload = IotTelemetryInput.model_validate(
        {
            "device_id": "ESP32-PARSER",
            "bme280": {"temperature_c": 25.0, "humidity_pct": 60.0, "pressure_pa": 100960},
            "jsn_sr04t": {"distance_cm": 200.0},
            "mpu6050": {"accel_x": 0.0, "accel_y": 0.0, "accel_z": 9.81, "inclination_deg": 0.0},
        }
    )
    assert payload.bme280 is not None
    assert payload.bme280.pressure_hpa == 1009.6


@pytest.mark.parametrize(
    "bme280",
    [
        {"temperature_c": 86.0, "humidity_pct": 60.0, "pressure_hpa": 1009.0},
        {"temperature_c": 25.0, "humidity_pct": 60.0, "pressure_hpa": 1200.0},
    ],
)
def test_bme280_rejects_absurd_temperature_or_pressure(bme280):
    with pytest.raises(ValidationError):
        IotTelemetryInput.model_validate({"device_id": "ESP32-BME-INVALID", "bme280": bme280})


def test_local_bme280_values_take_priority_over_regional_weather():
    prepared = _prepare_prediction(
        TelemetryInput(
            equipment_id=1,
            farm_id=1,
            region="Teste",
            operation_type="campo",
            clima="sol",
            umidade_solo=40,
            inclinacao=2,
            distancia_agua=999,
            velocidade=0,
            historico_sinistros=0,
            chuva_mm=0,
            solo_instavel=0,
            latitude=-23.455,
            longitude=-46.533,
            temperatura_c=35.0,
            umidade_ar=82.0,
            pressao_hpa=1002.0,
        ),
        {"temperature": 28.0, "humidity": 60.0, "pressure_hpa": 1012.0, "source": "OpenWeather"},
    )
    assert prepared["temperatura_c"] == 35.0
    assert prepared["umidade_ar"] == 82.0
    assert prepared["pressao_hpa"] == 1002.0


def test_mpu_resting_gravity_is_not_an_impact():
    features = build_mpu6050_features(accel_x=0.0, accel_y=0.0, accel_z=STANDARD_GRAVITY_M_S2)
    assert features["acceleration_magnitude"] == pytest.approx(STANDARD_GRAVITY_M_S2, abs=0.0001)
    assert features["movement_anomaly_score"] < 1
    assert features["possible_impact"] is False


def test_mpu_rejects_values_beyond_configured_meters_per_second_squared_range():
    with pytest.raises(ValidationError):
        IotTelemetryInput.model_validate(
            {
                "device_id": "ESP32-INVALID-ACCEL",
                "mpu6050": {"accel_x": 80.0, "accel_y": 0.0, "accel_z": STANDARD_GRAVITY_M_S2},
            }
        )


def test_flat_legacy_tilt_and_obstacle_detection_are_normalized():
    payload = IotTelemetryInput.model_validate(
        {
            "device_id": "ESP32-LEGACY-FLAT",
            "inclinacao": 23.0,
            "accel_x": 0.0,
            "accel_y": 0.0,
            "accel_z": STANDARD_GRAVITY_M_S2,
            "obstacle": {"detected": True},
        }
    )
    assert payload.mpu6050 is not None
    assert payload.mpu6050.inclination_deg == 23.0
    assert payload.jsn_sr04t is not None
    assert payload.jsn_sr04t.detected is True


def test_freshness_has_live_stale_and_offline_windows():
    assert telemetry_status(0) == "LIVE"
    assert telemetry_status(31) == "STALE"
    assert telemetry_status(301) == "OFFLINE"


def test_jsn_sr04t_thresholds_and_status_flags():
    def context_for_distance(distance_cm: float) -> RiskContext:
        return RiskContext(
            equipment_id=1,
            farm_id=1,
            device_id="ESP32-JSN",
            telemetry_id=1,
            operation="campo",
            recorded_at=datetime.now(timezone.utc),
            received_at=datetime.now(timezone.utc),
            data_quality_status="VALID",
            telemetry_status="LIVE",
            telemetry_age_seconds=0,
            confidence_score=96,
            iot={"distance_cm": distance_cm},
        )

    assert not build_iot_events(context_for_distance(240.0))
    assert build_iot_events(context_for_distance(80.0))[0]["event_type"] == "OBSTACLE_NEAR"
    assert build_iot_events(context_for_distance(45.0))[0]["event_type"] == "OBSTACLE_CRITICAL"

    equipment = SimpleNamespace(id=1, farm_id=1)
    farm = SimpleNamespace(region="Teste", latitude=-23.455, longitude=-46.533)
    base_payload = {
        "device_id": "ESP32-JSN-FLAGS",
        "bme280": {"temperature_c": 25.0, "humidity_pct": 60.0, "pressure_hpa": 1010.0},
        "mpu6050": {"accel_x": 0.0, "accel_y": 0.0, "accel_z": STANDARD_GRAVITY_M_S2},
    }
    timeout = build_iot_context(
        IotTelemetryInput.model_validate({**base_payload, "jsn_sr04t": {"timeout": True}}),
        equipment,
        farm,
    )
    out_of_range = build_iot_context(
        IotTelemetryInput.model_validate({**base_payload, "jsn_sr04t": {"out_of_range": True}}),
        equipment,
        farm,
    )
    assert timeout["quality"]["data_quality_status"] == "SUSPECT"
    assert out_of_range["quality"]["data_quality_status"] == "SUSPECT"


def test_critical_physical_signals_raise_risk_and_persist_critical_explanation(client: TestClient):
    device_id, api_key, _admin_headers_value = _create_device(client, "RISK")
    normal = client.post(
        ESP_TELEMETRY_ENDPOINT,
        headers=_device_headers(device_id, api_key),
        json=_physical_payload(device_id, 301),
    )
    critical = client.post(
        ESP_TELEMETRY_ENDPOINT,
        headers=_device_headers(device_id, api_key),
        json=_physical_payload(device_id, 302, critical=True),
    )
    assert normal.status_code == 200, normal.text
    assert critical.status_code == 200, critical.text
    assert critical.json()["risk_score"] > normal.json()["risk_score"]

    with SessionLocal() as db:
        telemetry = db.get(models.IotTelemetry, critical.json()["telemetry_id"])
        assert telemetry is not None
        assert telemetry.explanation["risk_level"] == "critico"
        assert telemetry.explanation["main_factor"] in {"obstacle", "tilt", "movement_anomaly", "possible_impact"}
