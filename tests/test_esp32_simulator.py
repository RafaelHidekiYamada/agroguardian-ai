from __future__ import annotations

from tools.esp32_simulator import CANONICAL_TELEMETRY_PATH, build_payload, telemetry_url


def test_simulator_uses_the_official_endpoint_and_canonical_payload():
    payload = build_payload("ESP32-SIM", "normal", 42)

    assert telemetry_url("https://agroguardian.example") == f"https://agroguardian.example{CANONICAL_TELEMETRY_PATH}"
    assert telemetry_url(f"https://agroguardian.example{CANONICAL_TELEMETRY_PATH}") == (
        f"https://agroguardian.example{CANONICAL_TELEMETRY_PATH}"
    )
    assert telemetry_url("https://agroguardian.example/api/v1/iot/telemetry") == (
        f"https://agroguardian.example{CANONICAL_TELEMETRY_PATH}"
    )
    assert payload["device_id"] == "ESP32-SIM"
    assert payload["sequence_number"] == 42
    assert {"bme280", "mpu6050", "jsn_sr04t"}.issubset(payload)
    assert {"pitch", "roll", "inclination_deg"}.issubset(payload["mpu6050"])
    assert payload["jsn_sr04t"]["timeout"] is False
    assert payload["jsn_sr04t"]["out_of_range"] is False
