from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def _column_exists(inspector, table_name: str, column_name: str) -> bool:
    if table_name not in inspector.get_table_names():
        return False
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _add_column(engine: Engine, table_name: str, column_name: str, ddl: str) -> None:
    inspector = inspect(engine)
    if _column_exists(inspector, table_name, column_name):
        return
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"))


def _create_index(engine: Engine, ddl: str) -> None:
    with engine.begin() as conn:
        conn.execute(text(ddl))


def ensure_schema_compatibility(engine: Engine) -> None:
    """Small additive migration layer for SQLite/local and Render/Postgres."""
    _add_column(engine, "equipment", "model", "VARCHAR(120)")
    _add_column(engine, "equipment", "year", "INTEGER")
    _add_column(engine, "equipment", "status", "VARCHAR(40) DEFAULT 'active' NOT NULL")

    _add_column(engine, "alert_records", "equipment_id", "INTEGER")
    _add_column(engine, "alert_records", "device_id", "VARCHAR(120)")
    _add_column(engine, "alert_records", "telemetry_id", "INTEGER")
    _add_column(engine, "alert_records", "risk_prediction_id", "INTEGER")

    _create_index(engine, "CREATE INDEX IF NOT EXISTS ix_alert_records_equipment_id ON alert_records (equipment_id)")
    _create_index(engine, "CREATE INDEX IF NOT EXISTS ix_alert_records_device_id ON alert_records (device_id)")
    _create_index(engine, "CREATE INDEX IF NOT EXISTS ix_alert_records_telemetry_id ON alert_records (telemetry_id)")
    _create_index(engine, "CREATE INDEX IF NOT EXISTS ix_alert_records_risk_prediction_id ON alert_records (risk_prediction_id)")
