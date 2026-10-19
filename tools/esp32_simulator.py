from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timedelta, timezone

import requests


CANONICAL_TELEMETRY_PATH = "/api/v1/telemetry/esp"
LEGACY_TELEMETRY_PATH = "/api/v1/iot/telemetry"
BATCH_TELEMETRY_PATH = "/api/v1/telemetry/esp/batch"

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


def batch_url(api_url: str) -> str:
    """URL do endpoint de lote, a partir de qualquer URL base ou de endpoint conhecido."""
    base = api_url.rstrip("/")
    if base.endswith(BATCH_TELEMETRY_PATH):
        return base
    for suffix in (CANONICAL_TELEMETRY_PATH, LEGACY_TELEMETRY_PATH):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return f"{base}{BATCH_TELEMETRY_PATH}"


def build_buffered_reading(
    scenario: str,
    sequence_number: int,
    recorded_at: datetime | None,
    *,
    boot_id: int = 1,
    uptime_ms: int = 0,
    time_quality: str = "synced",
    reset_reason: str | None = None,
) -> dict:
    """Leitura de um lote: o que o firmware guarda na flash e reenvia ao reconectar.

    device_id, versao e tipo de operacao vao no cabecalho do lote. Com
    time_quality="unknown" o timestamp e omitido (ESP32 que nunca sincronizou o NTP).
    """
    scenario = SCENARIO_ALIASES.get(scenario, scenario)
    reading = {
        "sequence_number": sequence_number,
        "boot_id": boot_id,
        "uptime_ms": uptime_ms,
        "time_quality": time_quality,
        "buffered": True,
        **SCENARIOS[scenario],
    }
    if recorded_at is not None and time_quality != "unknown":
        reading["timestamp"] = recorded_at.astimezone(timezone.utc).isoformat()
    if reset_reason:
        reading["reset_reason"] = reset_reason
    reading["jsn_sr04t"] = {"timeout": False, "out_of_range": False, **reading["jsn_sr04t"]}
    return reading


def simulate_offline_backlog(
    scenario: str,
    sequence_start: int,
    count: int,
    interval_seconds: float,
    *,
    end_time: datetime | None = None,
    boot_id: int = 1,
    restart_after: int | None = None,
    restart_gap_seconds: float = 0.0,
    time_quality: str = "synced",
) -> list[dict]:
    """Gera `count` leituras coletadas offline, em ordem cronologica, terminando em `end_time`.

    restart_after=K simula uma queda de energia depois da K-esima leitura: o boot_id sobe,
    o uptime recomeca, o numero de sequencia continua (ele fica na NVS) e o relogio
    avanca `restart_gap_seconds` sem leituras.
    """
    if count < 1:
        raise ValueError("count deve ser maior que zero")
    end_time = end_time or datetime.now(timezone.utc)
    gap = restart_gap_seconds if restart_after is not None and 0 < restart_after < count else 0.0
    start_time = end_time - timedelta(seconds=interval_seconds * (count - 1) + gap)
    readings: list[dict] = []
    current_boot = boot_id
    boot_start_index = 0
    clock = start_time
    for index in range(count):
        reset_reason = None
        if restart_after is not None and index == restart_after:
            current_boot += 1
            boot_start_index = index
            clock += timedelta(seconds=gap)
            reset_reason = "poweron"
        readings.append(
            build_buffered_reading(
                scenario,
                sequence_start + index,
                clock,
                boot_id=current_boot,
                uptime_ms=int((index - boot_start_index) * interval_seconds * 1000),
                time_quality=time_quality,
                reset_reason=reset_reason,
            )
        )
        clock += timedelta(seconds=interval_seconds)
    return readings


def chunk_readings(readings: list[dict], batch_size: int) -> list[list[dict]]:
    if batch_size < 1:
        raise ValueError("batch_size deve ser maior que zero")
    return [readings[start : start + batch_size] for start in range(0, len(readings), batch_size)]


def build_batch(device_id: str, readings: list[dict], *, more_pending: bool = False) -> dict:
    first, last = readings[0], readings[-1]
    return {
        "device_id": device_id,
        "batch_id": f"b{first.get('boot_id', 0)}-{first['sequence_number']}-{last['sequence_number']}",
        "firmware_version": "esp32-simulator-2.0",
        "operation_type": "campo",
        "more_pending": more_pending,
        "readings": readings,
    }


def run_offline_flush(args, headers: dict) -> int:
    """Simula `--offline-seconds` de coleta sem rede e envia o acumulado em lotes."""
    count = max(1, int(args.offline_seconds / args.offline_interval))
    readings = simulate_offline_backlog(
        args.scenario,
        args.sequence_start,
        count,
        args.offline_interval,
        restart_after=args.restart_after,
        restart_gap_seconds=args.restart_gap,
        time_quality="unknown" if args.unknown_time else "synced",
    )
    batches = chunk_readings(readings, args.batch_size)
    url = batch_url(args.api_url)
    print(f"Offline simulado: {count} leituras em {len(batches)} lote(s) para {url}")
    failures = 0
    for number, chunk in enumerate(batches, start=1):
        body = build_batch(args.device_id, chunk, more_pending=number < len(batches))
        for attempt in range(2 if args.duplicate_batch and number == 1 else 1):
            try:
                response = requests.post(url, json=body, headers=headers, timeout=30)
                label = "reenvio" if attempt else "envio"
                print(f"[lote {number}/{len(batches)} {label}] {response.status_code} {response.text[:300]}")
                if not response.ok:
                    failures += 1
            except requests.RequestException as exc:
                print(f"[lote {number}/{len(batches)}] request failed: {exc}")
                failures += 1
        if number < len(batches):
            time.sleep(max(0.0, args.batch_pause))
    return 1 if failures else 0


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
    offline = parser.add_argument_group("modo offline (store-and-forward)")
    offline.add_argument(
        "--offline-seconds",
        type=float,
        default=0.0,
        help="Simula essa duracao sem rede e envia o acumulado em lotes (0 = modo normal).",
    )
    offline.add_argument("--offline-interval", type=float, default=5.0, help="Segundos entre leituras gravadas.")
    offline.add_argument("--batch-size", type=int, default=40, help="Leituras por lote.")
    offline.add_argument("--batch-pause", type=float, default=0.6, help="Pausa entre lotes, em segundos.")
    offline.add_argument(
        "--restart-after",
        type=int,
        default=None,
        help="Simula um reinicio (novo boot_id) apos essa quantidade de leituras.",
    )
    offline.add_argument("--restart-gap", type=float, default=60.0, help="Segundos sem leituras durante o reinicio.")
    offline.add_argument("--unknown-time", action="store_true", help="Leituras sem horario confiavel.")
    offline.add_argument("--duplicate-batch", action="store_true", help="Reenvia o primeiro lote para testar duplicatas.")
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
    if args.offline_seconds > 0:
        if args.offline_interval <= 0 or args.batch_size < 1:
            raise SystemExit("--offline-interval e --batch-size devem ser maiores que zero.")
        return run_offline_flush(args, headers)
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
