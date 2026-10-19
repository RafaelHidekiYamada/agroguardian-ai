"""Store-and-forward: lote de telemetria, procedencia, segmentos e simulador offline.

Estes testes foram escritos junto com a fase 4 e ainda nao foram executados.
"""

from __future__ import annotations

import dataclasses
import os
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect

import backend.main as main_module
from backend import models
from backend.database import SessionLocal, engine
from backend.iot_processing import build_telemetry_segments, signal_status
from backend.main import app
from tools.esp32_simulator import (
    BATCH_TELEMETRY_PATH,
    build_batch,
    build_buffered_reading,
    chunk_readings,
    batch_url,
    simulate_offline_backlog,
)


BATCH_ENDPOINT = "/api/v1/telemetry/esp/batch"
LIVE_ENDPOINT = "/api/v1/telemetry/esp"


# --- helpers ----------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


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
    device_id = f"ESP32-BATCH-{suffix}-{int(time.time() * 1000)}"
    response = client.post(
        "/api/v1/admin/iot/devices",
        headers=admin_headers,
        json={
            "device_identifier": device_id,
            "equipment_id": 1,
            "name": f"ESP32 batch {suffix}",
            "firmware_version": "test-batch",
        },
    )
    assert response.status_code == 200, response.text
    return device_id, response.json()["api_key"], admin_headers


def _device_headers(device_id: str, api_key: str) -> dict[str, str]:
    return {"X-Device-ID": device_id, "X-API-Key": api_key}


def _post_batch(client: TestClient, device_id: str, api_key: str, readings: list[dict], **envelope):
    body = build_batch(device_id, readings)
    body.update(envelope)
    return client.post(BATCH_ENDPOINT, headers=_device_headers(device_id, api_key), json=body)


def _old_backlog(count: int, *, sequence_start: int = 1, hours_ago: float = 1.0, **kwargs) -> list[dict]:
    return simulate_offline_backlog(
        "normal",
        sequence_start,
        count,
        5.0,
        end_time=_now() - timedelta(hours=hours_ago),
        **kwargs,
    )


def _rows(device_id: str) -> list[models.IotTelemetry]:
    with SessionLocal() as db:
        return (
            db.query(models.IotTelemetry)
            .filter(models.IotTelemetry.device_id == device_id)
            .order_by(models.IotTelemetry.sequence_number)
            .all()
        )


def _critical_reading(sequence_number: int, recorded_at: datetime) -> dict:
    """Leitura critica no formato de lote (mesmos valores do teste de fluxo fisico)."""
    return {
        "sequence_number": sequence_number,
        "timestamp": recorded_at.isoformat(),
        "boot_id": 1,
        "uptime_ms": sequence_number * 5000,
        "time_quality": "synced",
        "buffered": True,
        "battery_voltage": 4.91,
        "bme280": {"temperature_c": 42.0, "humidity_pct": 96.0, "pressure_hpa": 955.0},
        "ultrasonic": {"sensor_model": "HC-SR04", "distance_cm": 20.0, "timeout": False, "out_of_range": False},
        "mpu6050": {
            "accel_x": 18.0,
            "accel_y": -12.0,
            "accel_z": 16.0,
            "gyro_x": 320.0,
            "gyro_y": 240.0,
            "gyro_z": 80.0,
            "pitch": 30.0,
            "roll": 12.0,
            "inclination_deg": 30.0,
        },
    }


# --- /batch: aceite, ordem e procedencia ------------------------------------


def test_batch_stores_old_readings_in_order_with_provenance(client: TestClient):
    device_id, api_key, admin_headers = _create_device(client, "ORDER")
    readings = _old_backlog(6)

    response = _post_batch(client, device_id, api_key, readings)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "accepted"
    assert (body["accepted"], body["duplicates"], body["rejected"]) == (6, 0, 0)
    assert [item["sequence_number"] for item in body["results"]] == [1, 2, 3, 4, 5, 6]
    assert all(item["result"] == "accepted" for item in body["results"])
    assert body["risk_updated"] is False  # leituras de uma hora atras nao movem o risco
    assert body["signal_status"] == "COM_SINAL"

    rows = _rows(device_id)
    assert len(rows) == 6
    recorded = [_naive_utc(row.recorded_at) for row in rows]
    assert recorded == sorted(recorded) and len(set(recorded)) == 6
    assert [row.uptime_ms for row in rows] == [0, 5000, 10000, 15000, 20000, 25000]
    assert {row.ingestion_mode for row in rows} == {"buffered"}
    assert {row.boot_id for row in rows} == {1}
    assert {row.time_quality for row in rows} == {"synced"}
    assert {row.batch_id for row in rows} == {body["batch_id"]}
    delay = _naive_utc(rows[0].received_at) - recorded[0]
    assert delay > timedelta(minutes=50)  # entregue bem depois de coletada

    # Um lote conta como contato: o dispositivo aparece online mesmo com dados antigos.
    device = client.get(f"/api/v1/iot/devices/{device_id}", headers=admin_headers)
    assert device.status_code == 200, device.text
    assert device.json()["status"] == "ONLINE"


def test_resending_a_batch_creates_no_duplicates(client: TestClient):
    device_id, api_key, _ = _create_device(client, "DUP")
    readings = _old_backlog(5)

    first = _post_batch(client, device_id, api_key, readings).json()
    second = _post_batch(client, device_id, api_key, readings)

    assert second.status_code == 200, second.text
    body = second.json()
    assert (body["accepted"], body["duplicates"], body["rejected"]) == (0, 5, 0)
    assert [item["telemetry_id"] for item in body["results"]] == [item["telemetry_id"] for item in first["results"]]
    assert len(_rows(device_id)) == 5


def test_reused_sequence_with_a_different_reading_is_rejected_for_good(client: TestClient):
    device_id, api_key, _ = _create_device(client, "CONFLICT")
    readings = _old_backlog(3)
    assert _post_batch(client, device_id, api_key, readings).status_code == 200

    conflicting = dict(readings[1])
    conflicting["uptime_ms"] = conflicting["uptime_ms"] + 123456  # outro instante, mesma sequencia
    response = _post_batch(client, device_id, api_key, [conflicting])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "partial"
    result = body["results"][0]
    assert result["result"] == "rejected"
    assert result["permanent"] is True
    assert "ja utilizado" in result["reason"]
    assert len(_rows(device_id)) == 3


def test_one_bad_reading_does_not_sink_the_rest_of_the_batch(client: TestClient):
    device_id, api_key, _ = _create_device(client, "PARTIAL")
    good = _old_backlog(4)
    no_sequence = dict(good[1])
    del no_sequence["sequence_number"]
    no_sensors = {
        "sequence_number": good[2]["sequence_number"],
        "timestamp": good[2]["timestamp"],
        "boot_id": 1,
        "uptime_ms": good[2]["uptime_ms"],
        "time_quality": "synced",
    }

    response = _post_batch(client, device_id, api_key, [good[0], no_sequence, no_sensors, good[3]])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "partial"
    assert [item["result"] for item in body["results"]] == ["accepted", "rejected", "rejected", "accepted"]
    assert body["results"][1]["sequence_number"] is None
    assert body["results"][1]["permanent"] is True
    assert body["results"][2]["sequence_number"] == good[2]["sequence_number"]
    assert body["results"][2]["permanent"] is True
    assert [row.sequence_number for row in _rows(device_id)] == [good[0]["sequence_number"], good[3]["sequence_number"]]


def test_reading_without_a_trusted_clock_is_kept_and_marked_unknown(client: TestClient):
    device_id, api_key, _ = _create_device(client, "UNKNOWN")
    readings = simulate_offline_backlog("normal", 1, 3, 5.0, time_quality="unknown")
    assert all("timestamp" not in reading for reading in readings)

    response = _post_batch(client, device_id, api_key, readings)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["accepted"] == 3
    assert {item["time_quality"] for item in body["results"]} == {"unknown"}
    for row in _rows(device_id):
        assert row.time_quality == "unknown"
        # Sem horario do aparelho, a leitura e datada na chegada.
        assert abs(_naive_utc(row.recorded_at) - datetime.utcnow()) < timedelta(minutes=2)


def test_stale_timestamp_before_2020_is_treated_as_unknown(client: TestClient):
    device_id, api_key, _ = _create_device(client, "EPOCH")
    reading = build_buffered_reading("normal", 1, _now(), boot_id=1, uptime_ms=1000)
    reading["timestamp"] = "1970-01-01T00:00:10+00:00"  # ESP32 que nunca sincronizou o NTP

    response = _post_batch(client, device_id, api_key, [reading])

    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["time_quality"] == "unknown"
    assert _rows(device_id)[0].time_quality == "unknown"


def test_future_timestamp_is_rejected_for_good(client: TestClient):
    device_id, api_key, _ = _create_device(client, "FUTURE")
    reading = build_buffered_reading("normal", 1, _now() + timedelta(days=2), boot_id=1, uptime_ms=1000)

    response = _post_batch(client, device_id, api_key, [reading])

    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["result"] == "rejected"
    assert result["permanent"] is True
    assert _rows(device_id) == []


# --- /batch: risco, eventos e alertas ---------------------------------------


def test_old_critical_readings_keep_their_events_but_raise_no_alert_or_prediction(client: TestClient):
    device_id, api_key, _ = _create_device(client, "EVENTS")
    recorded_at = _now() - timedelta(hours=2)

    response = _post_batch(client, device_id, api_key, [_critical_reading(1, recorded_at)])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["accepted"] == 1
    assert body["risk_updated"] is False
    telemetry_id = body["results"][0]["telemetry_id"]
    with SessionLocal() as db:
        telemetry = db.get(models.IotTelemetry, telemetry_id)
        assert telemetry.risk_score is None
        events = db.query(models.IotEvent).filter(models.IotEvent.telemetry_id == telemetry_id).all()
        assert {event.event_type for event in events} >= {
            "OBSTACLE_CRITICAL",
            "CRITICAL_INCLINATION",
            "ABNORMAL_ACCELERATION",
        }
        assert all("buffer" in event.description for event in events)
        assert all(event.risk_prediction_id is None for event in events)
        event_ids = [event.id for event in events]
        assert db.query(models.Alert).filter(models.Alert.iot_event_id.in_(event_ids)).count() == 0


def test_only_the_newest_live_reading_of_a_batch_drives_the_risk(client: TestClient):
    device_id, api_key, _ = _create_device(client, "LIVE-LAST")
    old = _old_backlog(3)
    newest = build_buffered_reading("normal", 4, _now(), boot_id=1, uptime_ms=15000)

    response = _post_batch(client, device_id, api_key, old + [newest])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["accepted"] == 4
    assert body["risk_updated"] is True
    assert body["risk_score"] is not None
    rows = _rows(device_id)
    assert [row.risk_score is not None for row in rows] == [False, False, False, True]


def test_buffered_age_does_not_downgrade_data_quality(client: TestClient):
    device_id, api_key, _ = _create_device(client, "QUALITY")

    assert _post_batch(client, device_id, api_key, _old_backlog(2, hours_ago=3)).status_code == 200

    for row in _rows(device_id):
        assert row.data_quality_status == "VALID"
        assert not any("telemetria" in str(issue) for issue in (row.data_quality_issues or []))


# --- /batch: limites, autenticacao e protocolo ------------------------------


def test_batch_with_too_many_readings_is_refused(client: TestClient, monkeypatch):
    device_id, api_key, _ = _create_device(client, "TOO-MANY")
    monkeypatch.setattr(main_module, "settings", dataclasses.replace(main_module.settings, iot_batch_max_readings=3))

    response = _post_batch(client, device_id, api_key, _old_backlog(4))

    assert response.status_code == 413
    assert _rows(device_id) == []


def test_batch_has_its_own_payload_limit_and_the_live_limit_is_unchanged(client: TestClient):
    device_id, api_key, _ = _create_device(client, "SIZE")
    readings = _old_backlog(2)

    medium = _post_batch(client, device_id, api_key, readings, padding="x" * 40_000)  # > 32 KB, < 64 KB
    assert medium.status_code == 200, medium.text

    huge = _post_batch(client, device_id, api_key, readings, padding="x" * 70_000)  # > 64 KB
    assert huge.status_code == 413
    assert huge.json()["detail"] == "Payload de telemetria muito grande."

    live = client.post(
        LIVE_ENDPOINT,
        headers=_device_headers(device_id, api_key),
        json={"device_id": device_id, "padding": "x" * 40_000},
    )
    assert live.status_code == 413  # o endpoint ao vivo continua com o limite de 32 KB


def test_batch_requires_json_content_type(client: TestClient):
    device_id, api_key, _ = _create_device(client, "CTYPE")

    response = client.post(
        BATCH_ENDPOINT,
        headers={**_device_headers(device_id, api_key), "Content-Type": "text/plain"},
        content="{}",
    )

    assert response.status_code == 415


def test_batch_authentication(client: TestClient):
    device_id, api_key, _ = _create_device(client, "AUTH")
    other_id, other_key, _ = _create_device(client, "AUTH-OTHER")
    body = build_batch(device_id, _old_backlog(1))

    assert client.post(BATCH_ENDPOINT, json=body).status_code == 401
    assert (
        client.post(BATCH_ENDPOINT, headers=_device_headers(device_id, "chave-errada"), json=body).status_code == 401
    )
    # A chave de outro dispositivo nao autoriza enviar em nome deste.
    assert client.post(BATCH_ENDPOINT, headers=_device_headers(other_id, other_key), json=body).status_code == 403
    assert _rows(device_id) == []


def test_batch_rate_limit_is_separate_from_the_live_endpoint(client: TestClient, monkeypatch):
    device_id, api_key, _ = _create_device(client, "RATE")
    monkeypatch.setattr(
        main_module, "settings", dataclasses.replace(main_module.settings, iot_batch_rate_limit_per_minute=2)
    )

    statuses = [
        _post_batch(client, device_id, api_key, _old_backlog(1, sequence_start=sequence)).status_code
        for sequence in (1, 2, 3)
    ]
    assert statuses[:2] == [200, 200]
    assert statuses[2] == 429

    limited = _post_batch(client, device_id, api_key, _old_backlog(1, sequence_start=4))
    assert limited.status_code == 429
    assert limited.headers.get("Retry-After") == "60"

    live = client.post(
        LIVE_ENDPOINT,
        headers=_device_headers(device_id, api_key),
        json={
            "device_id": device_id,
            "timestamp": _now().isoformat(),
            "sequence_number": 900,
            "bme280": {"temperature_c": 27.0, "humidity_pct": 60.0, "pressure_hpa": 1011.0},
        },
    )
    assert live.status_code == 200, live.text  # balde proprio: o ao vivo nao foi afetado


# --- compatibilidade com o endpoint ao vivo ---------------------------------


def _live_payload(device_id: str, sequence_number: int, uptime_ms: int) -> dict:
    return {
        "device_id": device_id,
        "timestamp": _now().isoformat(),
        "sequence_number": sequence_number,
        "operation_type": "campo",
        "firmware_version": "test-batch",
        "boot_id": 3,
        "uptime_ms": uptime_ms,
        "time_quality": "synced",
        "bme280": {"temperature_c": 27.0, "humidity_pct": 68.0, "pressure_hpa": 1011.0},
        "ultrasonic": {"sensor_model": "HC-SR04", "distance_cm": 240.0, "timeout": False, "out_of_range": False},
        "mpu6050": {
            "accel_x": 0.1,
            "accel_y": -0.1,
            "accel_z": 9.78,
            "pitch": 4.0,
            "roll": 1.0,
            "inclination_deg": 4.0,
        },
    }


def test_live_endpoint_still_works_and_records_provenance(client: TestClient):
    device_id, api_key, _ = _create_device(client, "LIVE")
    payload = _live_payload(device_id, 1, 90_000)

    response = client.post(LIVE_ENDPOINT, headers=_device_headers(device_id, api_key), json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "accepted"
    assert {"telemetry_id", "equipment_id", "risk_updated", "telemetry_status", "recorded_at"} <= set(body)
    row = _rows(device_id)[0]
    assert (row.ingestion_mode, row.boot_id, row.uptime_ms, row.time_quality) == ("live", 3, 90_000, "synced")

    # Payload simples, sem campos de procedencia: tudo continua como antes.
    plain = {key: value for key, value in _live_payload(device_id, 2, 0).items() if key not in {"boot_id", "uptime_ms", "time_quality"}}
    plain_response = client.post(LIVE_ENDPOINT, headers=_device_headers(device_id, api_key), json=plain)
    assert plain_response.status_code == 200, plain_response.text
    plain_row = _rows(device_id)[1]
    assert (plain_row.ingestion_mode, plain_row.boot_id, plain_row.uptime_ms, plain_row.time_quality) == (
        "live",
        None,
        None,
        None,
    )


def test_reading_sent_live_and_again_in_a_batch_is_a_duplicate(client: TestClient):
    device_id, api_key, _ = _create_device(client, "LIVE-THEN-BATCH")
    payload = _live_payload(device_id, 1, 90_000)
    assert client.post(LIVE_ENDPOINT, headers=_device_headers(device_id, api_key), json=payload).status_code == 200

    item = {k: v for k, v in payload.items() if k not in {"device_id", "operation_type", "firmware_version"}}
    item["buffered"] = True
    duplicate = _post_batch(client, device_id, api_key, [item])
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["results"][0]["result"] == "duplicate"

    other_instant = dict(item, uptime_ms=95_000)
    conflict = _post_batch(client, device_id, api_key, [other_instant])
    assert conflict.json()["results"][0]["result"] == "rejected"
    assert len(_rows(device_id)) == 1


# --- segmentos e SEM_SINAL --------------------------------------------------


def test_segments_endpoint_tells_offline_collection_restart_and_no_data_apart(client: TestClient):
    device_id, api_key, admin_headers = _create_device(client, "SEGMENTS")
    start = _now() - timedelta(minutes=30)
    first_boot = [
        build_buffered_reading("normal", index + 1, start + timedelta(seconds=5 * index), boot_id=1, uptime_ms=5000 * index)
        for index in range(5)
    ]
    second_boot_start = start + timedelta(minutes=10)
    second_boot = [
        build_buffered_reading(
            "normal",
            index + 6,
            second_boot_start + timedelta(seconds=5 * index),
            boot_id=2,
            uptime_ms=5000 * index,
            reset_reason="poweron" if index == 0 else None,
        )
        for index in range(5)
    ]
    assert _post_batch(client, device_id, api_key, first_boot + second_boot).status_code == 200

    response = client.get(
        f"/api/v1/iot/devices/{device_id}/telemetry/segments?hours=1", headers=admin_headers
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["device_id"] == device_id
    assert body["signal_status"] == "COM_SINAL"  # o lote acabou de chegar
    kinds = [segment["kind"] for segment in body["segments"]]
    assert kinds == ["offline_com_coleta", "sem_dados", "reiniciou", "offline_com_coleta", "sem_dados"]
    first, gap, restart, second, silence = body["segments"]
    assert (first["readings"], second["readings"]) == (5, 5)
    assert gap["open"] is False and gap["duration_seconds"] > 500
    assert (restart["from_boot_id"], restart["to_boot_id"], restart["reset_reason"]) == (1, 2, "poweron")
    assert silence["open"] is True and silence["end"] is None  # ultimo dado tem ~20 min: dispositivo mudo
    summary = body["summary"]
    assert summary["offline_com_coleta_readings"] == 10
    assert summary["online_readings"] == 0
    assert summary["restarts"] == 1
    assert summary["gaps"] == 2
    assert summary["missing_readings"] == 0
    assert summary["currently_silent"] is True


def test_segments_endpoint_requires_authentication_and_known_device(client: TestClient):
    device_id, _api_key, admin_headers = _create_device(client, "SEGMENTS-AUTH")

    assert client.get(f"/api/v1/iot/devices/{device_id}/telemetry/segments").status_code in {401, 403}
    assert (
        client.get("/api/v1/iot/devices/ESP32-NAO-EXISTE/telemetry/segments", headers=admin_headers).status_code == 404
    )
    empty = client.get(f"/api/v1/iot/devices/{device_id}/telemetry/segments", headers=admin_headers)
    assert empty.status_code == 200, empty.text
    assert empty.json()["segments"] == []
    assert empty.json()["signal_status"] == "SEM_SINAL"


def _segment_row(offset_seconds: float, base: datetime, sequence: int, **overrides):
    recorded = base + timedelta(seconds=offset_seconds)
    values = {
        "recorded_at": recorded,
        "timestamp": recorded,
        "received_at": recorded,
        "ingestion_mode": "live",
        "boot_id": 1,
        "sequence_number": sequence,
        "time_quality": "synced",
        "reset_reason": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_segment_builder_groups_live_readings_without_gaps():
    base = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    rows = [_segment_row(5 * index, base, index + 1) for index in range(10)]

    result = build_telemetry_segments(rows, now=base + timedelta(seconds=50))

    assert [segment["kind"] for segment in result["segments"]] == ["online"]
    assert result["segments"][0]["readings"] == 10
    assert result["summary"]["gaps"] == 0 and result["summary"]["restarts"] == 0
    assert result["summary"]["currently_silent"] is False


def test_segment_builder_reports_readings_discarded_by_the_buffer():
    base = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    rows = [_segment_row(0, base, 10), _segment_row(5, base, 11), _segment_row(10, base, 16)]

    result = build_telemetry_segments(rows, now=base + timedelta(seconds=15))

    gaps = [segment for segment in result["segments"] if segment["kind"] == "sem_dados"]
    assert len(gaps) == 1
    assert gaps[0]["missing_readings"] == 4
    assert result["summary"]["missing_readings"] == 4


def test_segment_builder_never_infers_gaps_from_unknown_times():
    base = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    rows = [
        _segment_row(0, base, 1),
        _segment_row(5, base, 2),
        _segment_row(3600, base, 3, time_quality="unknown"),
    ]

    result = build_telemetry_segments(rows, now=base + timedelta(seconds=3610))

    assert result["summary"]["unknown_time_readings"] == 1
    # Nenhuma lacuna entre a leitura 2 e a 3 (horario desconhecido); so o silencio atual
    # medido a partir da ultima leitura com horario confiavel.
    gaps = [segment for segment in result["segments"] if segment["kind"] == "sem_dados"]
    assert len(gaps) == 1 and gaps[0]["open"] is True


def test_segment_builder_flags_a_restart_between_consecutive_readings():
    base = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    rows = [
        _segment_row(0, base, 1),
        _segment_row(5, base, 2),
        _segment_row(10, base, 3, boot_id=2, reset_reason="panic"),
    ]

    result = build_telemetry_segments(rows, now=base + timedelta(seconds=12))

    restarts = [segment for segment in result["segments"] if segment["kind"] == "reiniciou"]
    assert len(restarts) == 1
    assert (restarts[0]["from_boot_id"], restarts[0]["to_boot_id"], restarts[0]["reset_reason"]) == (1, 2, "panic")


def test_signal_status_depends_on_the_last_contact():
    now = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

    assert signal_status(None, now=now) == "SEM_SINAL"
    assert signal_status(now - timedelta(seconds=20), now=now) == "COM_SINAL"
    assert signal_status(now - timedelta(hours=2), now=now) == "SEM_SINAL"


# --- esquema (migracao d7e3a91b4c52) ----------------------------------------


def test_migration_added_the_store_and_forward_columns_and_index():
    inspector = inspect(engine)
    columns = {column["name"]: column for column in inspector.get_columns("iot_telemetry")}

    for name in ("ingestion_mode", "time_quality", "boot_id", "uptime_ms", "batch_id", "reset_reason"):
        assert name in columns, name
        assert columns[name]["nullable"] is True  # linhas antigas continuam validas
    assert "ix_iot_telemetry_iot_device_boot" in {index["name"] for index in inspector.get_indexes("iot_telemetry")}


# --- simulador offline ------------------------------------------------------


def test_simulator_batch_url_accepts_any_known_url_shape():
    expected = f"https://agroguardian.example{BATCH_TELEMETRY_PATH}"

    assert batch_url("https://agroguardian.example") == expected
    assert batch_url("https://agroguardian.example/") == expected
    assert batch_url("https://agroguardian.example/api/v1/telemetry/esp") == expected
    assert batch_url("https://agroguardian.example/api/v1/iot/telemetry") == expected
    assert batch_url(expected) == expected


def test_simulator_reading_carries_provenance_and_omits_unknown_timestamp():
    when = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

    synced = build_buffered_reading("normal", 7, when, boot_id=4, uptime_ms=35_000)
    unknown = build_buffered_reading("normal", 8, when, boot_id=4, uptime_ms=40_000, time_quality="unknown")

    assert synced["timestamp"] == when.isoformat()
    assert (synced["sequence_number"], synced["boot_id"], synced["uptime_ms"], synced["buffered"]) == (7, 4, 35_000, True)
    assert synced["time_quality"] == "synced"
    assert "device_id" not in synced  # vai no cabecalho do lote
    assert "timestamp" not in unknown and unknown["time_quality"] == "unknown"


def test_simulator_backlog_is_chronological_and_ends_at_the_requested_time():
    end = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

    readings = simulate_offline_backlog("normal", 100, 12, 5.0, end_time=end)

    assert [reading["sequence_number"] for reading in readings] == list(range(100, 112))
    times = [datetime.fromisoformat(reading["timestamp"]) for reading in readings]
    assert times[-1] == end
    assert all((later - earlier).total_seconds() == 5.0 for earlier, later in zip(times, times[1:]))
    assert [reading["uptime_ms"] for reading in readings] == [5000 * index for index in range(12)]
    assert {reading["boot_id"] for reading in readings} == {1}


def test_simulator_backlog_can_inject_a_restart_with_a_silent_gap():
    end = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

    readings = simulate_offline_backlog(
        "normal", 1, 10, 5.0, end_time=end, restart_after=4, restart_gap_seconds=60.0
    )

    assert [reading["boot_id"] for reading in readings] == [1] * 4 + [2] * 6
    assert readings[4]["uptime_ms"] == 0 and readings[3]["uptime_ms"] == 15_000
    assert [reading["sequence_number"] for reading in readings] == list(range(1, 11))  # a sequencia nao reinicia
    assert readings[4]["reset_reason"] == "poweron"
    times = [datetime.fromisoformat(reading["timestamp"]) for reading in readings]
    assert (times[4] - times[3]).total_seconds() == 65.0  # 5 s de intervalo + 60 s de reinicio
    assert times[-1] == end


def test_simulator_chunks_and_batch_envelope():
    readings = simulate_offline_backlog("normal", 1, 85, 5.0)

    chunks = chunk_readings(readings, 40)
    body = build_batch("ESP32-SIM", chunks[0], more_pending=True)

    assert [len(chunk) for chunk in chunks] == [40, 40, 5]
    assert body["device_id"] == "ESP32-SIM"
    assert body["batch_id"] == "b1-1-40"
    assert body["more_pending"] is True and body["readings"] == chunks[0]
    with pytest.raises(ValueError):
        chunk_readings(readings, 0)
    with pytest.raises(ValueError):
        simulate_offline_backlog("normal", 1, 0, 5.0)
