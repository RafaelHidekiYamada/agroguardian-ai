"""add_physical_esp32_fields

Revision ID: 8f4c2a17d9be
Revises: c5d18e7a32bf
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8f4c2a17d9be"
down_revision: Union[str, Sequence[str], None] = "c5d18e7a32bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Persist the physical fields sent by the integrated PlatformIO firmware."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    op.add_column("iot_telemetry", sa.Column("soil_moisture_pct", sa.Float(), nullable=True))
    op.add_column("iot_telemetry", sa.Column("battery_voltage", sa.Float(), nullable=True))
    op.add_column("iot_telemetry", sa.Column("ultrasonic_sensor_model", sa.String(length=80), nullable=True))
    op.add_column("iot_telemetry", sa.Column("gps_accuracy_m", sa.Float(), nullable=True))
    op.add_column("iot_telemetry", sa.Column("gps_satellites", sa.Integer(), nullable=True))

    if not is_sqlite:
        op.create_check_constraint(
            "ck_iot_telemetry_soil_moisture_pct",
            "iot_telemetry",
            "soil_moisture_pct IS NULL OR (soil_moisture_pct >= 0 AND soil_moisture_pct <= 100)",
        )
        op.create_check_constraint(
            "ck_iot_telemetry_battery_voltage",
            "iot_telemetry",
            "battery_voltage IS NULL OR (battery_voltage >= 0 AND battery_voltage <= 30)",
        )
        op.create_check_constraint(
            "ck_iot_telemetry_gps_accuracy_m",
            "iot_telemetry",
            "gps_accuracy_m IS NULL OR (gps_accuracy_m >= 0 AND gps_accuracy_m <= 1000)",
        )
        op.create_check_constraint(
            "ck_iot_telemetry_gps_satellites",
            "iot_telemetry",
            "gps_satellites IS NULL OR (gps_satellites >= 0 AND gps_satellites <= 64)",
        )


def downgrade() -> None:
    raise RuntimeError("Downgrade bloqueado para preservar os dados fisicos do ESP32.")
