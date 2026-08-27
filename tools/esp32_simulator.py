from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timezone

import requests


CANONICAL_TELEMETRY_PATH = "/api/v1/telemetry/esp"
LEGACY_TELEMETRY_PATH = "/api/v1/iot/telemetry"

SCENARIOS = {
    "normal": {
        "bme280": {"temperature_c": 27.5, "humidity_pct": 68.0, "pressure_hpa": 1011.0},
        "mpu6050": {"accel_x": 0.1, "accel_y": -0.1, "accel_z": 9.78, "pitch": 4.0, "roll": 1.0, "inclination_deg": 4.0},
        "jsn_sr04t": {"distance_cm": 240.0},
    },
    "obstacle_near": {
        "bme280": {"temperature_c": 28.0, "humidity_pct": 71.0, "pressure_hpa": 1009.0},
        "mpu6050": {"accel_x": 0.2, "accel_y": 0.0, "accel_z": 9.75, "pitch": 5.0, "roll": 1.0, "inclination_deg": 5.0},
        "jsn_sr04t": {"distance_cm": 40.0},
    },
    "inclination_high": {
        "bme280": {"temperature_c": 29.0, "humidity_pct": 74.0, "pressure_hpa": 1005.0},
        "mpu6050": {"accel_x": 1.1, "accel_y": 0.8, "accel_z": 9.4, "pitch": 24.0, "roll": 6.0, "inclination_deg": 24.0},
        "jsn_sr04t": {"distance_cm": 230.0},
    },
    "accel_anormal": {
        "bme280": {"temperature_c": 30.0, "humidity_pct": 75.0, "pressure_hpa": 1002.0},
        "mpu6050": {"accel_x": 12.5, "accel_y": -8.2, "accel_z": 11.8, "pitch": 9.0, "roll": 4.0, "inclination_deg": 9.0},
        "jsn_sr04t": {"distance_cm": 180.0},
    },
    "temperature_high": {
        "bme280": {"temperature_c": 41.0, "humidity_pct": 70.0, "pressure_hpa": 1007.0},
        "mpu6050": {"accel_x": 0.1, "accel_y": 0.1, "accel_z": 9.8, "pitch": 4.0, "roll": 1.0, "inclination_deg": 4.0},
        "jsn_sr04t": {"distance_cm": 220.0},
    },
    "humidity_high": {
        "bme280": {"temperature_c": 29.0, "humidity_pct": 94.0, "pressure_hpa": 958.0},
        "mpu6050": {"accel_x": 0.2, "accel_y": 0.1, "accel_z": 9.7, "pitch": 8.0, "roll": 2.0, "inclination_deg": 8.0},
        "jsn_sr04t": {"distance_cm": 210.0},
    },
}

SCENARIO_ALIASES = {
    "obstacle": "obstacle_near",
    "dangerous_tilt": "inclination_high",
    "impact": "accel_anormal",
    "high_humidity": "humidity_high",
    "critical": "obstacle_near",
}


def build_payload(device_id: str, scenario: str, sequence_number: int) -> dict:
    scenario = SCENARIO_ALIASES.get(scenario, scenario)
    payload = {
        "device_id": device_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sequence_number": sequence_number,
        "operation_type": "campo",
        "firmware_version": "esp32-simulator-2.0",
        **SCENARIOS[scenario],
    }
    payload["jsn_sr04t"] = {
        "timeout": False,
        "out_of_range": False,
        **payload["jsn_sr04t"],
    }
    return payload


def telemetry_url(api_url: str) -> str:
    base = api_url.rstrip("/")
    if base.endswith(CANONICAL_TELEMETRY_PATH):
        return base
    if base.endswith(LEGACY_TELEMETRY_PATH):
        return f"{base[:-len(LEGACY_TELEMETRY_PATH)]}{CANONICAL_TELEMETRY_PATH}"
    return f"{base}{CANONICAL_TELEMETRY_PATH}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulador HTTP do ESP32 AgroGuardian.")
    parser.add_argument(
        "--api-url",
        default=os.getenv("AGROGUARDIAN_API_URL", os.getenv("API_BASE_URL", "http://127.0.0.1:8000")),
    )
    parser.add_argument("--device-id", default=os.getenv("ESP32_DEVICE_ID", "ESP32-TRATOR-001"))
    parser.add_argument("--api-key", default=os.getenv("ESP32_API_KEY", ""))
    parser.add_argument("--scenario", choices=sorted(set(SCENARIOS) | set(SCENARIO_ALIASES)), default="normal")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--interval", type=float, default=3.0)
    parser.add_argument("--sequence-start", type=int, default=int(time.time()))
    args = parser.parse_args()

    if not args.api_key:
        raise SystemExit("Informe --api-key ou defina ESP32_API_KEY.")
    if args.count < 1:
        raise SystemExit("--count deve ser maior que zero.")

    headers = {
        "Content-Type": "application/json",
        "X-Device-ID": args.device_id,
        "X-API-Key": args.api_key,
    }
    url = telemetry_url(args.api_url)
    failures = 0
    for index in range(args.count):
        payload = build_payload(args.device_id, args.scenario, args.sequence_start + index)
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=20)
            print(f"[{index + 1}/{args.count}] {response.status_code} {response.text}")
            if not response.ok:
                failures += 1
        except requests.RequestException as exc:
            print(f"[{index + 1}/{args.count}] request failed: {exc}")
            failures += 1
        if index + 1 < args.count:
            time.sleep(max(0.0, args.interval))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
