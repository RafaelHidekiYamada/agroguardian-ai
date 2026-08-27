from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import shutil
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from backend import models
from backend import database_seed
from backend import config as config_module
from backend.config import settings
from backend.database_schemas import AlertCreate, RecommendationCreate, RiskPredictionCreate, RiskPredictionFactorCreate
from backend.database_services import create_risk_prediction_bundle
from backend.iot_dataset import export_equipment_telemetry_dataset


LEGACY_DATABASE_SNAPSHOT = (
    Path(__file__).resolve().parents[1]
    / "agroguardian.db.pre-alembic-backup-20260825-215354.sqlite"
)


@pytest.mark.skipif(
    not LEGACY_DATABASE_SNAPSHOT.exists(),
    reason="Legacy database snapshot is only available in the local migration workspace.",
)
def test_full_migration_preserves_real_legacy_snapshot(tmp_path, monkeypatch):
    database_path = tmp_path / "legacy_snapshot.db"
    shutil.copy2(LEGACY_DATABASE_SNAPSHOT, database_path)
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setattr(config_module, "settings", replace(settings, database_url=database_url))
    alembic_config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))

    source = create_engine(f"sqlite:///{LEGACY_DATABASE_SNAPSHOT.as_posix()}")
    target = create_engine(database_url)
    try:
        with source.connect() as connection:
            expected_telemetry_count = connection.execute(text("SELECT COUNT(*) FROM iot_telemetry")).scalar_one()
            expected_device_count = connection.execute(text("SELECT COUNT(*) FROM iot_devices")).scalar_one()

        command.upgrade(alembic_config, "head")

        with target.connect() as connection:
            assert connection.execute(text("SELECT COUNT(*) FROM iot_telemetry")).scalar_one() == expected_telemetry_count
            assert connection.execute(text("SELECT COUNT(*) FROM iot_devices")).scalar_one() == expected_device_count
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "c5d18e7a32bf"
            assert connection.execute(text("PRAGMA foreign_key_check")).fetchall() == []
        command.check(alembic_config)
    finally:
        source.dispose()
        target.dispose()


def test_iot_migration_upgrades_existing_legacy_telemetry(tmp_path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'legacy_iot.db').as_posix()}"
    monkeypatch.setattr(config_module, "settings", replace(settings, database_url=database_url))
    alembic_config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))

    command.upgrade(alembic_config, "6e9f1e6a4d7c")
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO farms (id, name, region, latitude, longitude) "
                    "VALUES (900, 'Legacy Farm', 'SP', -23.0, -46.0)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO equipment (id, name, equipment_type, client_name, status, farm_id) "
                    "VALUES (900, 'Legacy Tractor', 'tractor', 'Legacy Client', 'active', 900)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO iot_devices "
                    "(id, device_id, device_identifier, equipment_id, name, device_type, api_key_hash, status, created_at, updated_at) "
                    "VALUES (900, 'LEGACY-ESP32', 'LEGACY-ESP32', 900, 'Legacy ESP32', 'ESP32', 'hash', 'offline', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO iot_telemetry "
                    "(id, device_id, equipment_id, timestamp, received_at, possible_impact, telemetry_age_seconds, telemetry_status, "
                    "data_quality_status, data_quality_issues, missing_sensors, raw_payload, created_at, obstacle_distance_cm, max_tilt_angle) "
                    "VALUES (900, 'LEGACY-ESP32', 900, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0, 0, 'LIVE', 'VALID', '[]', '[]', '{}', CURRENT_TIMESTAMP, 120, 8)"
                )
            )

        command.upgrade(alembic_config, "head")
        with engine.connect() as connection:
            upgraded = connection.execute(
                text(
                    "SELECT iot_device_id, recorded_at, distance_cm, inclination_deg "
                    "FROM iot_telemetry WHERE id = 900"
                )
            ).one()
        assert upgraded.iot_device_id == 900
        assert upgraded.recorded_at is not None
        assert upgraded.distance_cm == 120
        assert upgraded.inclination_deg == 8
        command.check(alembic_config)
    finally:
        engine.dispose()


def _build_domain_records(db_session):
    suffix = uuid4().hex[:10]
    user = models.User(
        name=f"Database Test {suffix}",
        username=f"dbtest.{suffix}",
        email=f"dbtest.{suffix}@example.test",
        password_hash="not-used-by-database-tests",
        is_active=True,
    )
    client = models.Client(
        name=f"Cliente {suffix}",
        corporate_name=f"Cliente {suffix} Ltda.",
        document=f"DOC-{suffix}",
        client_type=models.ClientType.COMPANY,
        status=models.ClientStatus.ACTIVE,
    )
    db_session.add_all([user, client])
    db_session.flush()
    farm = models.Farm(
        client_id=client.id,
        name=f"Fazenda {suffix}",
        region="Teste - SP",
        municipality="Teste",
        state="SP",
        country="BR",
        latitude=-23.0,
        longitude=-46.0,
        total_area_ha=100.0,
        cultivated_area_ha=80.0,
    )
    db_session.add(farm)
    db_session.flush()
    equipment = models.Equipment(
        farm_id=farm.id,
        name=f"Trator {suffix}",
        equipment_type="tractor",
        client_name=client.name,
        internal_code=f"EQ-{suffix}",
        status="active",
    )
    db_session.add(equipment)
    db_session.flush()
    operation = models.Operation(
        client_id=client.id,
        farm_id=farm.id,
        equipment_id=equipment.id,
        operation_type=models.OperationType.FIELD,
        crop_type="Soja",
        started_at=datetime.now(timezone.utc),
        status=models.OperationStatus.PLANNED,
        operator_user_id=user.id,
    )
    db_session.add(operation)
    db_session.commit()
    return user, client, farm, equipment, operation


def test_complete_schema_and_expected_indexes(db_session):
    expected_tables = {
        "users",
        "roles",
        "permissions",
        "clients",
        "farms",
        "equipment",
        "iot_devices",
        "iot_telemetry",
        "iot_events",
        "operations",
        "weather_records",
        "soil_records",
        "terrain_records",
        "incidents",
        "risk_predictions",
        "risk_prediction_factors",
        "alerts",
        "recommendations",
        "risk_simulations",
        "prevented_loss_records",
        "model_versions",
        "dataset_versions",
        "data_sources",
        "audit_logs",
        "system_settings",
        "generated_reports",
        "notifications",
        "user_clients",
        "user_farms",
        "user_equipments",
    }
    inspector = inspect(db_session.bind)
    assert expected_tables.issubset(set(inspector.get_table_names()))
    assert "ix_risk_predictions_equipment_created_at" in {
        index["name"] for index in inspector.get_indexes("risk_predictions")
    }
    assert "ix_alerts_status_created_at" in {index["name"] for index in inspector.get_indexes("alerts")}
    assert "ix_operations_equipment_started_at" in {
        index["name"] for index in inspector.get_indexes("operations")
    }
    iot_columns = {column["name"] for column in inspector.get_columns("iot_devices")}
    assert {"device_identifier", "metadata_json", "is_active"}.issubset(iot_columns)
    table_names = set(inspector.get_table_names())
    assert "iot_sensor_readings" not in table_names
    assert "iot_device_health" not in table_names
    telemetry_columns = {column["name"] for column in inspector.get_columns("iot_telemetry")}
    assert {
        "iot_device_id",
        "sequence_number",
        "recorded_at",
        "distance_cm",
        "inclination_deg",
        "raw_payload_json",
    }.issubset(telemetry_columns)
    assert "uq_iot_telemetry_device_sequence" in {
        index["name"] for index in inspector.get_indexes("iot_telemetry")
    }


def test_iot_dataset_export_excludes_raw_payload_and_credentials(db_session, tmp_path):
    _user, _client, _farm, equipment, _operation = _build_domain_records(db_session)
    suffix = uuid4().hex[:10]
    device = models.IotDevice(
        device_id=f"EXPORT-{suffix}",
        device_identifier=f"EXPORT-{suffix}",
        equipment_id=equipment.id,
        name="ESP32 para exportacao",
        device_type="ESP32",
        api_key_hash="credential-that-must-not-be-exported",
        status="ONLINE",
    )
    db_session.add(device)
    db_session.flush()
    recorded_at = datetime.now(timezone.utc)
    db_session.add(
        models.IotTelemetry(
            device_id=device.device_id,
            iot_device_id=device.id,
            equipment_id=equipment.id,
            sequence_number=1,
            timestamp=recorded_at.replace(tzinfo=None),
            recorded_at=recorded_at,
            received_at=recorded_at.replace(tzinfo=None),
            temperature_c=28.5,
            humidity_pct=72.0,
            pressure_hpa=1009.0,
            accel_x=0.2,
            accel_y=0.1,
            accel_z=9.8,
            acceleration_magnitude=9.8,
            distance_cm=180.0,
            inclination_deg=6.0,
            possible_impact=False,
            telemetry_age_seconds=0.0,
            telemetry_status="LIVE",
            data_quality_status="VALID",
            data_quality_issues=[],
            missing_sensors=[],
            risk_score=12.0,
            risk_level="LOW",
            raw_payload={"api_key": "raw-secret", "temperature_c": 28.5},
            raw_payload_json={"api_key": "raw-secret"},
        )
    )
    db_session.commit()

    dataset_path = export_equipment_telemetry_dataset(
        db_session,
        equipment.id,
        tmp_path / "iot_dataset.csv",
    )
    exported = dataset_path.read_text(encoding="utf-8")

    assert "raw_payload" not in exported
    assert "raw-secret" not in exported
    assert "credential-that-must-not-be-exported" not in exported
    assert "temperature_c" in exported
    assert "distance_cm" in exported


def test_seed_reuses_existing_admin_without_credentials(db_session, monkeypatch):
    admin = (
        db_session.query(models.User)
        .join(models.User.roles)
        .filter(models.Role.name == "ADMIN")
        .first()
    )
    assert admin is not None

    monkeypatch.setattr(
        database_seed,
        "settings",
        replace(
            settings,
            initial_admin_username="",
            initial_admin_email="",
            initial_admin_password="",
        ),
    )

    result = database_seed.seed_database(db_session)

    db_session.refresh(admin)
    assert result["admin_id"] == admin.id
    assert admin.is_superuser is True
    assert "ADMIN" in {role.name for role in admin.roles}


def test_user_client_farm_equipment_relationships_and_uniqueness(db_session):
    user, client, farm, equipment, _operation = _build_domain_records(db_session)
    user.clients.append(client)
    user.farms.append(farm)
    user.equipments.append(equipment)
    db_session.commit()

    assert client in user.clients
    assert farm in client.farms
    assert equipment in farm.equipment

    duplicate = models.User(
        name="Duplicate",
        username=user.username,
        email=f"different.{uuid4().hex}@example.test",
        password_hash="not-used",
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    duplicate_email = models.User(
        name="Duplicate Email",
        username=f"different.{uuid4().hex}",
        email=user.email,
        password_hash="not-used",
    )
    db_session.add(duplicate_email)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_risk_bundle_is_atomic_and_enforces_score_constraints(db_session):
    user, client, farm, equipment, operation = _build_domain_records(db_session)

    invalid_prediction = models.RiskPrediction(
        client_id=client.id,
        farm_id=farm.id,
        equipment_id=equipment.id,
        operation_id=operation.id,
        risk_score=101.0,
        risk_level=models.RiskLevel.CRITICAL,
        input_snapshot_json={},
    )
    db_session.add(invalid_prediction)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    prediction = create_risk_prediction_bundle(
        db_session,
        prediction_data=RiskPredictionCreate(
            client_id=client.id,
            farm_id=farm.id,
            equipment_id=equipment.id,
            operation_id=operation.id,
            risk_score=76.0,
            risk_level=models.RiskLevel.HIGH,
            confidence_score=88.0,
            main_risk_factor="precipitation",
            input_snapshot_json={"rain_mm": 25.0},
            factors=[
                RiskPredictionFactorCreate(
                    factor_name="precipitation",
                    factor_category="weather",
                    raw_value=25.0,
                    unit="mm",
                    impact_score=24.0,
                    importance_pct=28.0,
                )
            ],
        ),
        alerts=[
            AlertCreate(
                client_id=client.id,
                farm_id=farm.id,
                equipment_id=equipment.id,
                operation_id=operation.id,
                alert_type="high_risk",
                severity=models.AlertSeverity.HIGH,
                title="Teste de alerta",
                message="Risco elevado para teste transacional.",
            )
        ],
        recommendations=[
            RecommendationCreate(
                risk_prediction_id=0,
                equipment_id=equipment.id,
                recommendation_type=models.RecommendationType.OPERATIONAL,
                title="Teste de recomendacao",
                description="Reduzir velocidade.",
                expected_risk_reduction_pct=20.0,
                priority=models.RecommendationPriority.HIGH,
            )
        ],
        actor_user_id=user.id,
        request_id="database-test",
    )

    assert prediction.id is not None
    assert db_session.query(models.RiskPredictionFactor).filter_by(risk_prediction_id=prediction.id).count() == 1
    assert db_session.query(models.Alert).filter_by(risk_prediction_id=prediction.id).count() == 1
    assert db_session.query(models.Recommendation).filter_by(risk_prediction_id=prediction.id).count() == 1
    assert db_session.query(models.AuditLog).filter_by(entity_id=str(prediction.id), action="RISK_PREDICTED").count() == 1

    existing_count = db_session.query(models.RiskPrediction).count()
    with pytest.raises(IntegrityError):
        create_risk_prediction_bundle(
            db_session,
            prediction_data=RiskPredictionCreate(
                client_id=client.id,
                farm_id=farm.id,
                equipment_id=equipment.id,
                operation_id=operation.id,
                risk_score=55.0,
                risk_level=models.RiskLevel.MEDIUM,
                input_snapshot_json={},
            ),
            alerts=[
                AlertCreate(
                    client_id=99999999,
                    farm_id=farm.id,
                    equipment_id=equipment.id,
                    operation_id=operation.id,
                    alert_type="invalid_fk",
                    severity=models.AlertSeverity.HIGH,
                    title="Falha esperada",
                    message="A FK invalida deve abortar a transacao.",
                )
            ],
        )
    assert db_session.query(models.RiskPrediction).count() == existing_count


def test_environment_incident_audit_and_soft_delete_preserve_history(db_session):
    user, client, farm, equipment, operation = _build_domain_records(db_session)
    db_session.add_all(
        [
            models.WeatherRecord(
                farm_id=farm.id,
                source=models.WeatherSource.SIMULATION,
                recorded_at=datetime.now(timezone.utc),
                humidity_pct=72.0,
                precipitation_mm=8.0,
            ),
            models.SoilRecord(
                farm_id=farm.id,
                source=models.SoilSource.MANUAL,
                sampled_at=datetime.now(timezone.utc),
                soil_moisture_pct=62.0,
                ph=6.0,
            ),
            models.TerrainRecord(
                farm_id=farm.id,
                latitude=farm.latitude,
                longitude=farm.longitude,
                slope_deg=7.0,
                source=models.TerrainSource.SRTM,
            ),
            models.Incident(
                client_id=client.id,
                farm_id=farm.id,
                equipment_id=equipment.id,
                operation_id=operation.id,
                incident_type=models.IncidentType.STUCK,
                severity=models.IncidentSeverity.MEDIUM,
                occurred_at=datetime.now(timezone.utc),
                status=models.IncidentStatus.CLOSED,
            ),
            models.AuditLog(
                actor="test",
                action="EQUIPMENT_CREATED",
                payload={},
                user_id=user.id,
                entity_type="equipment",
                entity_id=str(equipment.id),
                old_values_json={},
                new_values_json={"status": "active"},
            ),
        ]
    )
    db_session.commit()

    equipment.is_active = False
    equipment.status = "inactive"
    db_session.commit()

    assert db_session.get(models.Equipment, equipment.id) is not None
    assert db_session.get(models.Equipment, equipment.id).is_active is False
    assert db_session.query(models.Incident).filter_by(equipment_id=equipment.id).count() == 1

    invalid_equipment = models.Equipment(
        farm_id=99999999,
        name="Foreign Key Failure",
        equipment_type="other",
        client_name="Invalid",
        internal_code=f"INVALID-{uuid4().hex}",
    )
    db_session.add(invalid_equipment)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
