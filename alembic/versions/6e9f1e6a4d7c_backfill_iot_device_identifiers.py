"""backfill_iot_device_identifiers

Revision ID: 6e9f1e6a4d7c
Revises: 23b17f92af3e
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6e9f1e6a4d7c"
down_revision: Union[str, Sequence[str], None] = "23b17f92af3e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Give existing authenticated devices the generic public identifier."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "iot_devices" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("iot_devices")}
    if not {"device_id", "device_identifier"}.issubset(columns):
        return

    devices = sa.table(
        "iot_devices",
        sa.column("device_id", sa.String(length=120)),
        sa.column("device_identifier", sa.String(length=120)),
    )
    op.execute(
        devices.update()
        .where(devices.c.device_identifier.is_(None))
        .where(devices.c.device_id.is_not(None))
        .values(device_identifier=devices.c.device_id)
    )


def downgrade() -> None:
    # Keep migrated identifiers to avoid deleting device metadata on rollback.
    pass
