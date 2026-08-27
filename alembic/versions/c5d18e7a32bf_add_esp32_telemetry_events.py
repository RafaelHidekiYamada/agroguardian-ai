"""add_esp32_telemetry_events

Revision ID: c5d18e7a32bf
Revises: 6e9f1e6a4d7c
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c5d18e7a32bf"
down_revision: Union[str, Sequence[str], None] = "6e9f1e6a4d7c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


JSON_DOCUMENT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    """Evolve the compatibility telemetry table without dropping history."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # SQLite cannot add FK/check constraints without rebuilding a referenced
    # table. Rebuilding iot_telemetry would rewrite legacy alert FKs, so local
    # compatibility uses additive columns and indexes while PostgreSQL owns the
    # canonical constraints used in production.
    op.add_column("iot_devices", sa.Column("api_key_revoked_at", sa.DateTime(), nullable=True))
    op.add_column("iot_telemetry", sa.Column("iot_device_id", sa.Integer(), nullable=True))
    op.add_column("iot_telemetry", sa.Column("sequence_number", sa.Integer(), nullable=True))
    op.add_column("iot_telemetry", sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("iot_telemetry", sa.Column("distance_cm", sa.Float(), nullable=True))
    op.add_column("iot_telemetry", sa.Column("inclination_deg", sa.Float(), nullable=True))
    op.add_column("iot_telemetry", sa.Column("raw_payload_json", JSON_DOCUMENT, nullable=True))
    if not is_sqlite:
        op.create_foreign_key(
            "fk_iot_telemetry_iot_device_id",
            "iot_telemetry",
            "iot_devices",
            ["iot_device_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_check_constraint(
            "ck_iot_telemetry_quality_status",
            "iot_telemetry",
            "data_quality_status IN ('VALID', 'PARTIAL', 'SUSPECT', 'INVALID')",
        )
        op.create_check_constraint(
            "ck_iot_telemetry_distance_cm",
            "iot_telemetry",
            "distance_cm IS NULL OR distance_cm >= 0",
        )
    op.create_index("ix_iot_telemetry_iot_device_id", "iot_telemetry", ["iot_device_id"], unique=False)
    op.create_index("ix_iot_telemetry_recorded_at", "iot_telemetry", ["recorded_at"], unique=False)
    op.create_index("ix_iot_telemetry_equipment_recorded_at", "iot_telemetry", ["equipment_id", "recorded_at"], unique=False)
    op.create_index("ix_iot_telemetry_iot_device_recorded_at", "iot_telemetry", ["iot_device_id", "recorded_at"], unique=False)
    op.create_index("uq_iot_telemetry_device_sequence", "iot_telemetry", ["iot_device_id", "sequence_number"], unique=True)

    op.execute(
        sa.text(
            "UPDATE iot_telemetry "
            "SET iot_device_id = (SELECT id FROM iot_devices WHERE iot_devices.device_id = iot_telemetry.device_id) "
            "WHERE iot_device_id IS NULL"
        )
    )
    op.execute(sa.text("UPDATE iot_telemetry SET recorded_at = timestamp WHERE recorded_at IS NULL"))
    op.execute(sa.text("UPDATE iot_telemetry SET distance_cm = obstacle_distance_cm WHERE distance_cm IS NULL"))
    op.execute(sa.text("UPDATE iot_telemetry SET inclination_deg = max_tilt_angle WHERE inclination_deg IS NULL"))
    op.execute(sa.text("UPDATE iot_devices SET status = UPPER(status) WHERE status IS NOT NULL"))

    op.add_column("risk_predictions", sa.Column("telemetry_id", sa.Integer(), nullable=True))
    if not is_sqlite:
        op.create_foreign_key(
            "fk_risk_predictions_telemetry_id",
            "risk_predictions",
            "iot_telemetry",
            ["telemetry_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    op.create_index("ix_risk_predictions_telemetry_id", "risk_predictions", ["telemetry_id"], unique=False)

    op.create_table(
        "iot_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("equipment_id", sa.Integer(), nullable=False),
        sa.Column("telemetry_id", sa.Integer(), nullable=False),
        sa.Column("risk_prediction_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=40), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["device_id"], ["iot_devices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["equipment_id"], ["equipment.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["telemetry_id"], ["iot_telemetry.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["risk_prediction_id"], ["risk_predictions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telemetry_id", "event_type", name="uq_iot_event_telemetry_type"),
    )
    op.create_index("ix_iot_events_id", "iot_events", ["id"], unique=False)
    op.create_index("ix_iot_events_device_id", "iot_events", ["device_id"], unique=False)
    op.create_index("ix_iot_events_equipment_id", "iot_events", ["equipment_id"], unique=False)
    op.create_index("ix_iot_events_telemetry_id", "iot_events", ["telemetry_id"], unique=False)
    op.create_index("ix_iot_events_risk_prediction_id", "iot_events", ["risk_prediction_id"], unique=False)
    op.create_index("ix_iot_events_event_type", "iot_events", ["event_type"], unique=False)
    op.create_index("ix_iot_events_severity", "iot_events", ["severity"], unique=False)
    op.create_index("ix_iot_events_equipment_created_at", "iot_events", ["equipment_id", "created_at"], unique=False)
    op.create_index("ix_iot_events_device_created_at", "iot_events", ["device_id", "created_at"], unique=False)
    op.create_index("ix_iot_events_type_severity", "iot_events", ["event_type", "severity"], unique=False)

    op.add_column("alerts", sa.Column("iot_event_id", sa.Integer(), nullable=True))
    if not is_sqlite:
        op.create_foreign_key(
            "fk_alerts_iot_event_id",
            "alerts",
            "iot_events",
            ["iot_event_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    op.create_index("ix_alerts_iot_event_id", "alerts", ["iot_event_id"], unique=False)


def downgrade() -> None:
    raise RuntimeError("Downgrade bloqueado para preservar telemetria, eventos e vinculos de risco.")
