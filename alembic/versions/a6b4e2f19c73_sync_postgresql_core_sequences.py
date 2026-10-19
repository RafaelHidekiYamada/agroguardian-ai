"""sync_postgresql_core_sequences

Revision ID: a6b4e2f19c73
Revises: 8f4c2a17d9be
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a6b4e2f19c73"
down_revision: Union[str, Sequence[str], None] = "8f4c2a17d9be"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CORE_TABLES = ("clients", "farms", "equipment")


def upgrade() -> None:
    """Move legacy PostgreSQL sequences past explicitly assigned primary keys."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # Predictions created legacy farm/equipment rows with explicit IDs. Such
    # inserts do not advance PostgreSQL sequences, so the next normal INSERT
    # could reuse ID 1. Lock the small set while each sequence is repaired.
    bind.execute(
        sa.text(
            'LOCK TABLE "clients", "farms", "equipment" '
            "IN SHARE ROW EXCLUSIVE MODE"
        )
    )
    for table_name in CORE_TABLES:
        sequence_name = bind.execute(
            sa.text("SELECT pg_get_serial_sequence(:table_name, 'id')"),
            {"table_name": table_name},
        ).scalar_one_or_none()
        if not sequence_name:
            continue
        bind.execute(
            sa.text(
                f'SELECT setval(CAST(:sequence_name AS regclass), '
                f'COALESCE(MAX("id"), 1), MAX("id") IS NOT NULL) '
                f'FROM "{table_name}"'
            ),
            {"sequence_name": sequence_name},
        )


def downgrade() -> None:
    # Sequence advancement is data maintenance and must not be reversed.
    pass
