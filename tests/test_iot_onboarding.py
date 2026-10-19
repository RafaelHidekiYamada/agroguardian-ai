from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend import models
from backend.database import SessionLocal
from backend.main import app


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


def test_admin_can_provision_farm_equipment_and_esp32_from_an_empty_onboarding_path(client: TestClient):
    headers = _admin_headers(client)
    suffix = uuid4().hex[:10]
    client_name = f"Cliente IoT {suffix}"
    farm_name = f"Fazenda IoT {suffix}"

    farm_response = client.post(
        "/api/v1/admin/farms",
        headers=headers,
        json={
            "client_name": client_name,
            "name": farm_name,
            "region": "Campinas - SP",
            "latitude": -22.9056,
            "longitude": -47.0608,
            "municipality": "Campinas",
            "state": "SP",
            "country": "br",
            "total_area_ha": 120.5,
            "cultivated_area_ha": 95.0,
            "main_crop": "Cafe",
        },
    )
    assert farm_response.status_code == 200, farm_response.text
    farm = farm_response.json()
    assert farm["client_name"] == client_name
    assert farm["country"] == "BR"

    duplicate_farm = client.post(
        "/api/v1/admin/farms",
        headers=headers,
        json={
            "client_name": client_name,
            "name": farm_name,
            "region": "Campinas - SP",
            "latitude": -22.9056,
            "longitude": -47.0608,
        },
    )
    assert duplicate_farm.status_code == 409

    equipment_response = client.post(
        "/api/v1/admin/equipments",
        headers=headers,
        json={
            "name": f"Trator IoT {suffix}",
            "equipment_type": "Trator",
            "client_name": client_name,
            "farm_id": farm["farm_id"],
            "model": "ESP32 Test Rig",
            "year": 2026,
            "status": "active",
        },
    )
    assert equipment_response.status_code == 200, equipment_response.text
    equipment = equipment_response.json()
    assert equipment["farm_id"] == farm["farm_id"]

    device_id = f"ESP32-ONBOARD-{suffix}".upper()
    device_response = client.post(
        "/api/v1/admin/iot/devices",
        headers=headers,
        json={
            "device_identifier": device_id,
            "equipment_id": equipment["equipment_id"],
            "name": f"ESP32 {suffix}",
            "firmware_version": "agroguardian-esp32-2.0.0",
            "status": "offline",
        },
    )
    assert device_response.status_code == 200, device_response.text
    created_device = device_response.json()
    assert created_device["device_id"] == device_id
    assert created_device["api_key"]

    detail = client.get(f"/api/v1/iot/devices/{device_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert "api_key" not in detail.json()
    assert detail.json()["farm_id"] == farm["farm_id"]

    telemetry_response = client.post(
        "/api/v1/telemetry/esp",
        headers={"X-Device-ID": device_id, "X-API-Key": created_device["api_key"]},
        json={
            "device_id": device_id,
            "sequence_number": 1,
            "soil_moisture_pct": 73.5,
            "bme280": {"temperature_c": 29.1, "humidity_pct": 71.0, "pressure_hpa": 1008.5},
            "mpu6050": {"accel_x": 0.1, "accel_y": 0.2, "accel_z": 9.8, "inclination_deg": 3.0},
            "ultrasonic": {"sensor_model": "HC-SR04", "distance_cm": 210.0},
            "gps": {"latitude": -22.91, "longitude": -47.07, "accuracy_m": 4.0, "satellites": 8},
        },
    )
    assert telemetry_response.status_code == 200, telemetry_response.text
    assert telemetry_response.json()["risk_updated"] is True

    forged_provenance = client.post(
        "/api/v1/risk/predict",
        headers=headers,
        json={
            "equipment_id": equipment["equipment_id"],
            "farm_id": farm["farm_id"],
            "region": "Campinas - SP",
            "operation_type": "campo",
            "clima": "sol",
            "umidade_solo": 1,
            "inclinacao": 0,
            "distancia_agua": 999,
            "velocidade": 0,
            "historico_sinistros": 0,
            "chuva_mm": 0,
            "latitude": -22.9056,
            "longitude": -47.0608,
            "iot_used": True,
            "telemetry_id": 999999999,
            "iot_snapshot": {"source": "forged"},
        },
    )
    assert forged_provenance.status_code == 200, forged_provenance.text
    assert forged_provenance.json()["iot_used"] is True
    assert forged_provenance.json()["telemetry_id"] == telemetry_response.json()["telemetry_id"]

    with SessionLocal() as db:
        stored_farm = db.get(models.Farm, farm["farm_id"])
        assert stored_farm is not None
        assert stored_farm.client.name == client_name
        assert stored_farm.latitude == -22.9056
        assert stored_farm.longitude == -47.0608
        assert stored_farm.equipment[0].iot_devices[0].device_id == device_id
        telemetry = db.get(models.IotTelemetry, telemetry_response.json()["telemetry_id"])
        assert telemetry is not None
        assert telemetry.latitude == -22.91
        assert telemetry.soil_moisture_pct == 73.5


def test_farms_listing_requires_authentication(client: TestClient):
    response = client.get("/api/v1/farms")

    assert response.status_code == 401


def test_farms_listing_is_available_to_authenticated_admin(client: TestClient):
    response = client.get("/api/v1/farms", headers=_admin_headers(client))

    assert response.status_code == 200
    assert isinstance(response.json(), list)
