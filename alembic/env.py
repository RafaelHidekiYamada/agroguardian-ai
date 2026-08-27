from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend.config import settings
from backend.database import Base
from backend import models  # noqa: F401 - registers all legacy and core tables


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The environment wins over the ini fallback so local SQLite and PostgreSQL
# deployments run the exact same revision history.
config.set_main_option("sqlalchemy.url", settings.database_url)
target_metadata = Base.metadata


def _include_object(object_, name, type_, reflected, compare_to, *, is_sqlite: bool) -> bool:
    if not is_sqlite or type_ != "foreign_key_constraint":
        return True

    # The ESP32 migration intentionally avoids rebuilding these referenced
    # SQLite tables. PostgreSQL receives the actual constraints, while SQLite
    # keeps legacy foreign keys intact and enforces the relation in the app.
    deferred_sqlite_foreign_keys = {
        ("alerts", ("iot_event_id",)),
        ("iot_telemetry", ("iot_device_id",)),
        ("risk_predictions", ("telemetry_id",)),
    }
    column_names = tuple(sorted(column.name for column in object_.columns))
    return (object_.table.name, column_names) not in deferred_sqlite_foreign_keys


def _configure_kwargs(url: str) -> dict:
    is_sqlite = url.startswith("sqlite")
    return {
        "target_metadata": target_metadata,
        "compare_type": True,
        # SQLite renders equivalent defaults differently (for example true vs
        # 1), which produces noisy revisions for the supported local fallback.
        "compare_server_default": False,
        # SQLite requires table recreation for several supported alterations.
        "render_as_batch": is_sqlite,
        "include_object": lambda object_, name, type_, reflected, compare_to: _include_object(
            object_,
            name,
            type_,
            reflected,
            compare_to,
            is_sqlite=is_sqlite,
        ),
    }


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_configure_kwargs(url),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, **_configure_kwargs(str(connection.engine.url)))

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
