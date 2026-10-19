"""add_iot_store_and_forward_fields

Revision ID: d7e3a91b4c52
Revises: a6b4e2f19c73
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7e3a91b4c52"
down_revision: Union[str, Sequence[str], None] = "a6b4e2f19c73"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add store-and-forward provenance to iot_telemetry (additive, nullable).

    Existing rows keep NULL in every new column, which readers treat as a live
    reading with unknown boot. No data is rewritten and no constraint changes,
    so the migration is safe on SQLite and PostgreSQL alike.
    """
    op.add_column("iot_telemetry", sa.Column("ingestion_mode", sa.String(length=20), nullable=True))
    op.add_column("iot_telemetry", sa.Column("time_quality", sa.String(length=20), nullable=True))
    op.add_column("iot_telemetry", sa.Column("boot_id", sa.Integer(), nullable=True))
    op.add_column("iot_telemetry", sa.Column("uptime_ms", sa.BigInteger(), nullable=True))
    op.add_column("iot_telemetry", sa.Column("batch_id", sa.String(length=120), nullable=True))
    op.add_column("iot_telemetry", sa.Column("reset_reason", sa.String(length=40), nullable=True))
    op.create_index(
        "ix_iot_telemetry_iot_device_boot",
        "iot_telemetry",
        ["iot_device_id", "boot_id", "uptime_ms"],
        unique=False,
    )


def downgrade() -> None:
    raise RuntimeError("Downgrade bloqueado para preservar a procedencia da telemetria armazenada.")
