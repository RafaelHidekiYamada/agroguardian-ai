from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine


def ensure_schema_compatibility(engine: Engine) -> None:
    """Apply the same versioned migrations used by the deployment command."""
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    # A config without an ini file preserves application logging at startup.
    if engine.dialect.name != "sqlite":
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        return

    # Legacy SQLite migrations rebuild referenced tables. Foreign key checks
    # must be suspended outside a transaction, then verified before commit.
    with engine.connect() as connection:
        foreign_keys = int(connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one())
        connection.commit()
        try:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
            with connection.begin():
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
                if connection.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
                    raise RuntimeError("Migration left invalid SQLite foreign key references.")
        finally:
            connection.rollback()
            connection.exec_driver_sql(f"PRAGMA foreign_keys={foreign_keys}")
            connection.commit()
