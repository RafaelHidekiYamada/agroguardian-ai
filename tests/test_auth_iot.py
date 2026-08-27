from __future__ import annotations

import json
import os
import secrets
import time

import pytest
from fastapi.testclient import TestClient

from backend import models
from backend.database import SessionLocal
from backend.main import app


ESP_TELEMETRY_ENDPOINT = "/api/v1/telemetry/esp"
LEGACY_IOT_TELEMETRY_ENDPOINT = "/api/v1/iot/telemetry"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def login(
    client: TestClient,
    username: str | None = None,
    password: str | None = None,
) -> dict[str, str]:
    username = username or os.environ["INITIAL_ADMIN_USERNAME"]
    password = password or os.environ["INITIAL_ADMIN_PASSWORD"]
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_device(client: TestClient, headers: dict[str, str], suffix: str) -> tuple[str, str]:
    device_id = f"ESP32-PYTEST-{suffix}-{int(time.time() * 1000)}"
    response = client.post(
        "/api/v1/admin/iot/devices",
        headers=headers,
        json={
            "device_id": device_id,
            "equipment_id": 1,
            "name": f"Device {suffix}",
            "device_type": "ESP32",
            "firmware_version": "pytest",
            "status": "offline",
            "metadata_json": {"source": "pytest", "suffix": suffix},
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["device_identifier"] == device_id
    assert body["metadata_json"] == {"source": "pytest", "suffix": suffix}
    return device_id, body["api_key"]


def telemetry_payload(device_id: str, *, critical: bool = False, partial: bool = False) -> dict:
    payload = {
        "device_id": device_id,
        "operation_type": "campo",
        "gps": {"latitude": -23.455, "longitude": -46.533},
        "bme280": {
            "temperature_c": 39.5 if critical else 28.7,
            "humidity_pct": 94.0 if critical else 78.3,
            "pressure_hpa": 955.0 if critical else 1009.6,
        },
    }
    if partial:
        return payload
    payload.update(
        {
            "mpu6050": {
                "accel_x": 10.8 if critical else 0.12,
                "accel_y": -6.5 if critical else -0.08,
                "accel_z": 13.2 if critical else 9.74,
                "gyro_x": 380.0 if critical else 0.43,
                "gyro_y": 290.0 if critical else 1.18,
                "gyro_z": 120.0 if critical else 0.21,
                "pitch": 15.0 if critical else 8.4,
                "roll": 24.5 if critical else 3.2,
            },
            "obstacle": {
                "detected": critical,
                "distance_cm": 32 if critical else 185,
            },
        }
    )
    return payload


def test_login_and_rbac(client: TestClient):
    bad = client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
    assert bad.status_code == 401

    admin_headers = login(client)
    me = client.get("/api/v1/auth/me", headers=admin_headers)
    assert me.status_code == 200
    assert me.json()["role"] == "ADMIN"
    assert "users.create" in me.json()["permissions"]

    operator_username = f"operator.{int(time.time() * 1000)}"
    operator_password = secrets.token_urlsafe(16)
    created = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={
            "name": "Test Operator",
            "email": f"{operator_username}@example.test",
            "username": operator_username,
            "password": operator_password,
            "roles": ["OPERADOR"],
        },
    )
    assert created.status_code == 200, created.text
    operator_headers = login(client, operator_username, operator_password)
    denied = client.get("/api/v1/admin/users", headers=operator_headers)
    assert denied.status_code == 403


def test_admin_user_crud_and_permissions(client: TestClient):
    headers = login(client)
    username = f"pytest.user.{int(time.time() * 1000)}"
    create = client.post(
        "/api/v1/admin/users",
        headers=headers,
        json={
            "name": "Pytest User",
            "email": f"{username}@agroguardian.ai",
            "username": username,
            "password": "StrongPass123",
            "roles": ["LEITURA"],
            "permissions_add": ["telemetry.view"],
            "permissions_remove": ["reports.view"],
            "access_scopes": [{"client_name": "Cliente Demo", "farm_id": 1, "equipment_id": 1}],
        },
    )
    assert create.status_code == 200, create.text
    user = create.json()
    assert "password_hash" not in user
    assert "telemetry.view" in user["permissions"]
    assert "reports.view" not in user["permissions"]

    update = client.put(
        f"/api/v1/admin/users/{user['id']}",
        headers=headers,
        json={"name": "Pytest User Updated", "roles": ["ANALISTA"], "permissions_add": ["users.view"]},
    )
    assert update.status_code == 200, update.text
    assert "ANALISTA" in update.json()["roles"]
    assert "users.view" in update.json()["permissions"]

    reset = client.post(
        f"/api/v1/admin/users/{user['id']}/reset-password",
        headers=headers,
        json={"new_password": "AnotherStrong123"},
    )
    assert reset.status_code == 200

    deleted = client.delete(f"/api/v1/admin/users/{user['id']}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"


def test_iot_device_security_and_telemetry(client: TestClient):
    headers = login(client)
    device_id, api_key = create_device(client, headers, "SEC")
    payload = telemetry_payload(device_id)

    device = client.get(f"/api/v1/iot/devices/{device_id}", headers=headers)
    assert device.status_code == 200, device.text
    assert "api_key" not in device.json()

    no_auth = client.post(ESP_TELEMETRY_ENDPOINT, json=payload)
    assert no_auth.status_code == 401

    bad_key = client.post(
        ESP_TELEMETRY_ENDPOINT,
        headers={"X-Device-ID": device_id, "X-API-Key": "wrong"},
        json=payload,
    )
    assert bad_key.status_code == 401

    unknown = client.post(
        ESP_TELEMETRY_ENDPOINT,
        headers={"X-Device-ID": "ESP32-UNKNOWN", "X-API-Key": api_key},
        json={**payload, "device_id": "ESP32-UNKNOWN"},
    )
    assert unknown.status_code == 401

    invalid_content_type = client.post(
        ESP_TELEMETRY_ENDPOINT,
        headers={"X-Device-ID": device_id, "X-API-Key": api_key, "Content-Type": "text/plain"},
        content=json.dumps(payload),
    )
    assert invalid_content_type.status_code == 415

    missing_content_type = client.post(
        ESP_TELEMETRY_ENDPOINT,
        headers={"X-Device-ID": device_id, "X-API-Key": api_key},
        content=json.dumps(payload),
    )
    assert missing_content_type.status_code == 415

    mismatch = client.post(
        ESP_TELEMETRY_ENDPOINT,
        headers={"X-Device-ID": device_id, "X-API-Key": api_key},
        json={**payload, "device_id": "ESP32-OTHER"},
    )
    assert mismatch.status_code == 403

    accepted = client.post(
        ESP_TELEMETRY_ENDPOINT,
        headers={"X-Device-ID": device_id, "X-API-Key": api_key},
        json={**payload, "equipment_id": 999999, "farm_id": 999999, "client_id": 999999},
    )
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    assert body["status"] == "accepted"
    assert body["equipment_id"] == 1
    assert body["risk_updated"] is True

    legacy_alias = client.post(
        LEGACY_IOT_TELEMETRY_ENDPOINT,
        headers={"X-Device-ID": device_id, "X-API-Key": api_key},
        json=payload,
    )
    assert legacy_alias.status_code == 200, legacy_alias.text

    with SessionLocal() as db:
        telemetry = (
            db.query(models.IotTelemetry)
            .filter(models.IotTelemetry.device_id == device_id)
            .order_by(models.IotTelemetry.id.desc())
            .first()
        )
        assert telemetry is not None
        assert telemetry.equipment_id == 1
        assert telemetry.recorded_at is not None
        assert "api_key" not in telemetry.raw_payload
        normalized_prediction = (
            db.query(models.RiskPrediction)
            .filter(models.RiskPrediction.equipment_id == 1)
            .order_by(models.RiskPrediction.id.desc())
            .first()
        )
        assert normalized_prediction is not None
        assert normalized_prediction.input_snapshot_json["device_id"] == device_id
        assert normalized_prediction.factors
        assert normalized_prediction.recommendations

    latest = client.get("/api/v1/equipments/1/telemetry/latest", headers=headers)
    assert latest.status_code == 200
    assert latest.json()["telemetry"]["device_id"] == device_id

    disabled = client.delete(f"/api/v1/admin/iot/devices/{device_id}", headers=headers)
    assert disabled.status_code == 200
    rejected = client.post(
        ESP_TELEMETRY_ENDPOINT,
        headers={"X-Device-ID": device_id, "X-API-Key": api_key},
        json=payload,
    )
    assert rejected.status_code == 403


def test_iot_rejects_credentials_in_payload_or_metadata(client: TestClient):
    headers = login(client)
    rejected_metadata = client.post(
        "/api/v1/admin/iot/devices",
        headers=headers,
        json={
            "device_identifier": f"ESP32-METADATA-{int(time.time() * 1000)}",
            "equipment_id": 1,
            "name": "Device with invalid metadata",
            "metadata_json": {"api_key": "must-not-be-stored"},
        },
    )
    assert rejected_metadata.status_code == 422

    device_id, api_key = create_device(client, headers, "NOSECRET")
    rejected_payload = client.post(
        ESP_TELEMETRY_ENDPOINT,
        headers={"X-Device-ID": device_id, "X-API-Key": api_key},
        json={**telemetry_payload(device_id), "api_key": "must-not-be-stored"},
    )
    assert rejected_payload.status_code == 422

    oversized = client.post(
        ESP_TELEMETRY_ENDPOINT,
        headers={"X-Device-ID": device_id, "X-API-Key": api_key},
        json={**telemetry_payload(device_id), "padding": "x" * 32768},
    )
    assert oversized.status_code == 413


def test_iot_quality_and_ai_explainability(client: TestClient):
    headers = login(client)
    device_id, api_key = create_device(client, headers, "AI")

    partial = client.post(
        ESP_TELEMETRY_ENDPOINT,
        headers={"X-Device-ID": device_id, "X-API-Key": api_key},
        json=telemetry_payload(device_id, partial=True),
    )
    assert partial.status_code == 200, partial.text
    assert partial.json()["data_quality_status"] == "PARTIAL"
    partial_score = partial.json()["risk_score"]

    invalid = client.post(
        ESP_TELEMETRY_ENDPOINT,
        headers={"X-Device-ID": device_id, "X-API-Key": api_key},
        json={"device_id": device_id, "bme280": {"humidity_pct": 130}},
    )
    assert invalid.status_code == 422

    critical = client.post(
        ESP_TELEMETRY_ENDPOINT,
        headers={"X-Device-ID": device_id, "X-API-Key": api_key},
        json=telemetry_payload(device_id, critical=True),
    )
    assert critical.status_code == 200, critical.text
    assert critical.json()["risk_score"] >= partial_score

    current = client.get("/api/v1/equipments/1/risk/current", headers=headers)
    assert current.status_code == 200
    explanation = current.json()["explainable_ai"]
    factors = {factor["factor"] for factor in explanation["factors"]}
    assert {"obstacle", "tilt"}.issubset(factors)
