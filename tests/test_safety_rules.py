from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.decision_engine import (
    SAFETY_FLOOR_CRITICAL,
    SAFETY_FLOOR_HIGH,
    _risk_band,
    calculate_contextual_risk,
)
from backend.main import app
from tests.test_iot_physical_flow import (
    ESP_TELEMETRY_ENDPOINT,
    _create_device,
    _device_headers,
    _physical_payload,
)


def _risk(**payload):
    return calculate_contextual_risk(
        model_risk_score=10.0,
        payload=payload,
        geo_context={},
        weather={"source": "fallback"},
    )


def test_rollover_alone_forces_high_risk_even_with_a_low_model_score():
    result = _risk(max_tilt_angle=50.0)

    assert result["final_risk_score"] >= SAFETY_FLOOR_HIGH
    assert result["risk_band"] == "alto"
    assert any("tombamento" in reason for reason in result["safety_floor_reasons"])


def test_close_obstacle_alone_forces_high_risk():
    result = _risk(obstacle_distance_cm=60.0)

    assert result["final_risk_score"] >= SAFETY_FLOOR_HIGH
    assert result["risk_band"] == "alto"
    assert any("obstaculo proximo" in reason for reason in result["safety_floor_reasons"])


def test_two_physical_hazards_together_force_critical_risk():
    result = _risk(max_tilt_angle=60.0, obstacle_distance_cm=30.0)

    assert result["final_risk_score"] >= SAFETY_FLOOR_CRITICAL
    assert result["risk_band"] == "critico"


def test_no_hazard_leaves_the_score_untouched_and_low_readings_do_not_trigger_the_floor():
    calm = _risk(max_tilt_angle=5.0, obstacle_distance_cm=240.0)
    steep_but_not_rollover = _risk(max_tilt_angle=30.0)

    assert calm["safety_floor_score"] == 0.0
    assert calm["risk_band"] == "baixo"
    assert steep_but_not_rollover["safety_floor_score"] == 0.0
    assert _risk_band(SAFETY_FLOOR_HIGH) == "alto"
    assert _risk_band(SAFETY_FLOOR_CRITICAL) == "critico"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _send(client: TestClient, device_id: str, api_key: str, sequence: int, *, tilt=None, distance=None):
    payload = _physical_payload(device_id, sequence)
    if tilt is not None:
        payload["mpu6050"].update(pitch=tilt, roll=1.0, inclination_deg=tilt)
    if distance is not None:
        payload["ultrasonic"]["distance_cm"] = distance
    response = client.post(
        ESP_TELEMETRY_ENDPOINT,
        headers=_device_headers(device_id, api_key),
        json=payload,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_hardware_readings_map_to_the_expected_risk_levels(client: TestClient):
    device_id, api_key, _ = _create_device(client, "SAFETY")

    idle = _send(client, device_id, api_key, 1)
    rollover = _send(client, device_id, api_key, 2, tilt=50.0)
    obstacle = _send(client, device_id, api_key, 3, distance=30.0)
    both = _send(client, device_id, api_key, 4, tilt=50.0, distance=30.0)

    assert idle["risk_level"] == "Baixo"
    assert rollover["risk_score"] >= SAFETY_FLOOR_HIGH
    assert rollover["risk_level"] in {"Alto", "Critico"}
    assert obstacle["risk_score"] >= SAFETY_FLOOR_HIGH
    assert obstacle["risk_level"] in {"Alto", "Critico"}
    assert both["risk_score"] >= SAFETY_FLOOR_CRITICAL
    assert both["risk_level"] == "Critico"
