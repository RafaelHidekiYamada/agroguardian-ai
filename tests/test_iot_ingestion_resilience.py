from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend import main as main_module
from backend import models
from backend.database import SessionLocal


ESP_TELEMETRY_ENDPOINT = "/api/v1/telemetry/esp"


@pytest.fixture(scope="module")
def client():
    with TestClient(main_module.app) as test_client:
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


def _create_device(client: TestClient, suffix: str) -> tuple[str, str]:
    device_id = f"ESP32-RESILIENCE-{suffix}-{uuid4().hex[:10]}"
    response = client.post(
        "/api/v1/admin/iot/devices",
        headers=_admin_headers(client),
        json={
            "device_identifier": device_id,
            "equipment_id": 1,
            "name": f"ESP32 resilience {suffix}",
            "firmware_version": "resilience-test",
        },
    )
    assert response.status_code == 200, response.text
    return device_id, response.json()["api_key"]


def _headers(device_id: str, api_key: str) -> dict[str, str]:
    return {"X-Device-ID": device_id, "X-API-Key": api_key}


def _payload(device_id: str, sequence_number: int, *, critical: bool = False) -> dict:
    return {
        "device_id": device_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sequence_number": sequence_number,
        "operation_type": "campo",
        "firmware_version": "resilience-test",
        "bme280": {
            "temperature_c": 42.0 if critical else 27.0,
            "humidity_pct": 96.0 if critical else 68.0,
            "pressure_hpa": 955.0 if critical else 1011.0,
        },
        "jsn_sr04t": {
            "distance_cm": 20.0 if critical else 240.0,
            "timeout": False,
            "out_of_range": False,
        },
        "mpu6050": {
            "accel_x": 18.0 if critical else 0.1,
            "accel_y": -12.0 if critical else -0.1,
            "accel_z": 16.0 if critical else 9.78,
            "pitch": 30.0 if critical else 4.0,
            "roll": 12.0 if critical else 1.0,
            "inclination_deg": 30.0 if critical else 4.0,
        },
    }


def _side_effect_counts(telemetry_id: int) -> tuple[int, int, int]:
    with SessionLocal() as db:
        telemetry = db.get(models.IotTelemetry, telemetry_id)
        assert telemetry is not None
        telemetry_count = (
            db.query(models.IotTelemetry)
            .filter(
                models.IotTelemetry.iot_device_id == telemetry.iot_device_id,
                models.IotTelemetry.sequence_number == telemetry.sequence_number,
            )
            .count()
        )
        prediction_count = (
            db.query(models.RiskPrediction)
            .filter(models.RiskPrediction.telemetry_id == telemetry_id)
            .count()
        )
        event_count = (
            db.query(models.IotEvent)
            .filter(models.IotEvent.telemetry_id == telemetry_id)
            .count()
        )
        return telemetry_count, prediction_count, event_count


def test_identical_retry_replays_the_existing_result_without_duplicate_side_effects(client: TestClient):
    device_id, api_key = _create_device(client, "REPLAY")
    payload = _payload(device_id, 101, critical=True)

    first = client.post(
        ESP_TELEMETRY_ENDPOINT,
        headers=_headers(device_id, api_key),
        json=payload,
    )
    assert first.status_code == 200, first.text
    assert first.json()["risk_updated"] is True
    telemetry_id = first.json()["telemetry_id"]
    before_retry = _side_effect_counts(telemetry_id)
    assert before_retry[0] == 1
    assert before_retry[1] == 1
    assert before_retry[2] >= 1

    retry = client.post(
        ESP_TELEMETRY_ENDPOINT,
        headers=_headers(device_id, api_key),
        json=payload,
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["status"] == "accepted"
    assert retry.json()["telemetry_id"] == telemetry_id
    assert retry.json()["risk_updated"] is True
    assert retry.json()["risk_score"] == first.json()["risk_score"]
    assert retry.json()["events"] == first.json()["events"]
    assert _side_effect_counts(telemetry_id) == before_retry


def test_ai_failure_keeps_telemetry_and_retry_is_idempotent(client: TestClient, monkeypatch):
    device_id, api_key = _create_device(client, "AI-FAILURE")
    payload = _payload(device_id, 202)
    predict_calls = 0

    def fail_prediction(*_args, **_kwargs):
        nonlocal predict_calls
        predict_calls += 1
        raise RuntimeError("forced prediction failure")

    monkeypatch.setattr(main_module, "_predict", fail_prediction)

    first = client.post(
        ESP_TELEMETRY_ENDPOINT,
        headers=_headers(device_id, api_key),
        json=payload,
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["status"] == "accepted"
    assert body["risk_updated"] is False
    assert "Telemetria armazenada" in body["message"]
    telemetry_id = body["telemetry_id"]
    assert predict_calls == 1

    with SessionLocal() as db:
        telemetry = db.get(models.IotTelemetry, telemetry_id)
        assert telemetry is not None
        assert telemetry.sequence_number == 202
        assert telemetry.risk_score is None
        assert telemetry.raw_payload_json["device_id"] == device_id
        assert telemetry.iot_device.last_seen_at is not None
        assert (
            db.query(models.RiskPrediction)
            .filter(models.RiskPrediction.telemetry_id == telemetry_id)
            .count()
            == 0
        )

    retry = client.post(
        ESP_TELEMETRY_ENDPOINT,
        headers=_headers(device_id, api_key),
        json=payload,
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["telemetry_id"] == telemetry_id
    assert retry.json()["risk_updated"] is False
    assert predict_calls == 1
    assert _side_effect_counts(telemetry_id) == (1, 0, 0)

    conflicting_payload = deepcopy(payload)
    conflicting_payload["bme280"]["temperature_c"] = 28.0
    conflict = client.post(
        ESP_TELEMETRY_ENDPOINT,
        headers=_headers(device_id, api_key),
        json=conflicting_payload,
    )
    assert conflict.status_code == 409
    assert "payload diferente" in conflict.json()["detail"]
    assert predict_calls == 1
    assert _side_effect_counts(telemetry_id) == (1, 0, 0)
