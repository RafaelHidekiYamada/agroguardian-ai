"""create_agroguardian_core_schema

Revision ID: 23b17f92af3e
Revises: 
Create Date: 2026-08-25 21:29:46.254466
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql
from sqlalchemy import Text
from backend import models as database_models  # noqa: F401 - registers metadata
from backend.database import Base

# revision identifiers, used by Alembic.
revision: str = '23b17f92af3e'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_CORE_TABLES = (
    "clients",
    "data_sources",
    "dataset_versions",
    "model_versions",
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
    "system_settings",
    "generated_reports",
    "notifications",
    "user_clients",
    "user_farms",
    "user_equipments",
)
LEGACY_MARKER_KEY = "__agroguardian_legacy_schema_upgrade__"


def _has_table(bind, table_name: str) -> bool:
    return table_name in sa.inspect(bind).get_table_names()


def _upgrade_existing_table(
    table_name: str,
    columns: tuple[sa.Column, ...] = (),
    foreign_keys: tuple[tuple[str, str, tuple[str, ...], tuple[str, ...], str | None], ...] = (),
    indexes: tuple[tuple[str, tuple[str, ...], bool], ...] = (),
    checks: tuple[tuple[str, str], ...] = (),
    uniques: tuple[tuple[str, tuple[str, ...]], ...] = (),
) -> None:
    """Add only missing legacy columns, FKs, indexes and constraints.

    The batch API recreates SQLite tables when required, preserving rows while
    allowing the same revision to run against PostgreSQL.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
    existing_fk_columns = {
        tuple(foreign_key["constrained_columns"])
        for foreign_key in inspector.get_foreign_keys(table_name)
    }
    existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    existing_uniques = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints(table_name)
        if constraint.get("column_names")
    }
    existing_checks = {constraint["name"] for constraint in inspector.get_check_constraints(table_name)}

    missing_columns = tuple(column for column in columns if column.name not in existing_columns)
    missing_foreign_keys = tuple(
        foreign_key
        for foreign_key in foreign_keys
        if foreign_key[2] not in existing_fk_columns
    )
    missing_indexes = tuple(index for index in indexes if index[0] not in existing_indexes)
    missing_checks = tuple(check for check in checks if check[0] not in existing_checks)
    missing_uniques = tuple(unique for unique in uniques if unique[1] not in existing_uniques)

    if not any((missing_columns, missing_foreign_keys, missing_indexes, missing_checks, missing_uniques)):
        return

    recreate = "always" if bind.dialect.name == "sqlite" else "auto"
    with op.batch_alter_table(table_name, recreate=recreate) as batch_op:
        for column in missing_columns:
            batch_op.add_column(column)
        for name, target_table, local_columns, remote_columns, ondelete in missing_foreign_keys:
            batch_op.create_foreign_key(name, target_table, list(local_columns), list(remote_columns), ondelete=ondelete)
        for name, columns_, unique in missing_indexes:
            batch_op.create_index(name, list(columns_), unique=unique)
        for name, sqltext in missing_checks:
            batch_op.create_check_constraint(name, sqltext)
        for name, columns_ in missing_uniques:
            batch_op.create_unique_constraint(name, list(columns_))


def _upgrade_legacy_schema() -> None:
    bind = op.get_bind()
    existing_tables = set(sa.inspect(bind).get_table_names())
    new_tables = [
        Base.metadata.tables[table_name]
        for table_name in NEW_CORE_TABLES
        if table_name not in existing_tables
    ]
    if new_tables:
        Base.metadata.create_all(bind=bind, tables=new_tables)

    _upgrade_existing_table(
        "farms",
        columns=(
            sa.Column("client_id", sa.Integer(), nullable=True),
            sa.Column("municipality", sa.String(length=120), nullable=True),
            sa.Column("state", sa.String(length=80), nullable=True),
            sa.Column("country", sa.String(length=2), nullable=False, server_default="BR"),
            sa.Column("total_area_ha", sa.Float(), nullable=True),
            sa.Column("cultivated_area_ha", sa.Float(), nullable=True),
            sa.Column("main_crop", sa.String(length=120), nullable=True),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        ),
        foreign_keys=(("fk_farms_client_id", "clients", ("client_id",), ("id",), "RESTRICT"),),
        indexes=(
            ("ix_farms_client_id", ("client_id",), False),
            ("ix_farms_municipality", ("municipality",), False),
            ("ix_farms_state", ("state",), False),
            ("ix_farms_client_state_municipality", ("client_id", "state", "municipality"), False),
        ),
    )
    _upgrade_existing_table(
        "equipment",
        columns=(
            sa.Column("manufacturer", sa.String(length=120), nullable=True),
            sa.Column("model", sa.String(length=120), nullable=True),
            sa.Column("year", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
            sa.Column("serial_number", sa.String(length=120), nullable=True),
            sa.Column("internal_code", sa.String(length=120), nullable=True),
            sa.Column("purchase_value", sa.Float(), nullable=True),
            sa.Column("estimated_repair_cost", sa.Float(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        ),
        indexes=(("ix_equipment_farm_type_status", ("farm_id", "equipment_type", "status"), False),),
        uniques=(
            ("uq_equipment_serial_number", ("serial_number",)),
            ("uq_equipment_internal_code", ("internal_code",)),
        ),
    )
    _upgrade_existing_table(
        "roles",
        columns=(
            sa.Column("is_system_role", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        ),
    )
    _upgrade_existing_table(
        "permissions",
        columns=(sa.Column("name", sa.String(length=120), nullable=False, server_default=""),),
    )
    _upgrade_existing_table(
        "users",
        columns=(sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.text("false")),),
    )
    _upgrade_existing_table(
        "user_access_scopes",
        columns=(sa.Column("client_id", sa.Integer(), nullable=True),),
        foreign_keys=(("fk_user_access_scopes_client_id", "clients", ("client_id",), ("id",), "RESTRICT"),),
        indexes=(("ix_user_access_scopes_client_id", ("client_id",), False),),
    )
    _upgrade_existing_table(
        "iot_devices",
        columns=(
            sa.Column("device_identifier", sa.String(length=120), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        ),
        indexes=(("ix_iot_devices_device_identifier", ("device_identifier",), False),),
        checks=(("ck_iot_device_identifier", "device_identifier IS NOT NULL OR device_id IS NOT NULL"),),
        uniques=(("uq_iot_devices_device_identifier", ("device_identifier",)),),
    )
    _upgrade_existing_table(
        "alert_policies",
        columns=(
            sa.Column("client_id", sa.Integer(), nullable=True),
            sa.Column("farm_id", sa.Integer(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("risk_threshold", sa.Float(), nullable=True),
            sa.Column("severity", sa.String(length=20), nullable=True),
            sa.Column("action_type", sa.String(length=80), nullable=True),
        ),
        foreign_keys=(
            ("fk_alert_policies_client_id", "clients", ("client_id",), ("id",), "RESTRICT"),
            ("fk_alert_policies_farm_id", "farms", ("farm_id",), ("id",), "RESTRICT"),
        ),
        indexes=(
            ("ix_alert_policies_client_id", ("client_id",), False),
            ("ix_alert_policies_farm_id", ("farm_id",), False),
            ("ix_alert_policies_client_farm_active", ("client_id", "farm_id", "is_active"), False),
        ),
        checks=(("ck_alert_policy_risk_threshold", "risk_threshold IS NULL OR (risk_threshold >= 0 AND risk_threshold <= 100)"),),
    )
    _upgrade_existing_table(
        "audit_logs",
        columns=(
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("entity_type", sa.String(length=120), nullable=True),
            sa.Column("entity_id", sa.String(length=120), nullable=True),
            sa.Column("request_id", sa.String(length=120), nullable=True),
            sa.Column("ip_address", sa.String(length=64), nullable=True),
            sa.Column("old_values_json", sa.JSON(), nullable=True),
            sa.Column("new_values_json", sa.JSON(), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        ),
        foreign_keys=(("fk_audit_logs_user_id", "users", ("user_id",), ("id",), "RESTRICT"),),
        indexes=(
            ("ix_audit_logs_user_id", ("user_id",), False),
            ("ix_audit_logs_entity_type", ("entity_type",), False),
            ("ix_audit_logs_entity_id", ("entity_id",), False),
            ("ix_audit_logs_request_id", ("request_id",), False),
            ("ix_audit_logs_entity_created_at", ("entity_type", "entity_id", "created_at"), False),
        ),
    )
    _upgrade_existing_table(
        "alert_records",
        columns=(
            sa.Column("equipment_id", sa.Integer(), nullable=True),
            sa.Column("device_id", sa.String(length=120), nullable=True),
            sa.Column("telemetry_id", sa.Integer(), nullable=True),
            sa.Column("risk_prediction_id", sa.Integer(), nullable=True),
        ),
        foreign_keys=(
            ("fk_alert_records_equipment_id", "equipment", ("equipment_id",), ("id",), None),
            ("fk_alert_records_telemetry_id", "iot_telemetry", ("telemetry_id",), ("id",), None),
            ("fk_alert_records_risk_prediction_id", "prediction_records", ("risk_prediction_id",), ("id",), None),
        ),
        indexes=(
            ("ix_alert_records_equipment_id", ("equipment_id",), False),
            ("ix_alert_records_device_id", ("device_id",), False),
            ("ix_alert_records_telemetry_id", ("telemetry_id",), False),
            ("ix_alert_records_risk_prediction_id", ("risk_prediction_id",), False),
        ),
    )

    bind.execute(sa.text("UPDATE permissions SET name = code WHERE name IS NULL OR name = ''"))
    bind.execute(sa.text("UPDATE iot_devices SET device_identifier = device_id WHERE device_identifier IS NULL"))
    bind.execute(sa.text("UPDATE audit_logs SET created_at = timestamp WHERE created_at IS NULL"))

    marker_exists = bind.execute(
        sa.text("SELECT 1 FROM system_settings WHERE key = :key"),
        {"key": LEGACY_MARKER_KEY},
    ).first()
    if not marker_exists:
        marker_table = sa.table(
            "system_settings",
            sa.column("key", sa.String()),
            sa.column("value_json", sa.JSON()),
            sa.column("description", sa.Text()),
        )
        op.bulk_insert(
            marker_table,
            [{
                "key": LEGACY_MARKER_KEY,
                "value_json": {"mode": "additive"},
                "description": "Marks a database upgraded from the pre-Alembic schema.",
            }],
        )


def upgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "farms"):
        _upgrade_legacy_schema()
        return
    _upgrade_fresh_schema()


def _upgrade_fresh_schema() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('access_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(), nullable=False),
    sa.Column('role', sa.String(), nullable=False),
    sa.Column('action', sa.String(), nullable=False),
    sa.Column('endpoint', sa.String(), nullable=False),
    sa.Column('success', sa.Boolean(), nullable=False),
    sa.Column('detail', sa.JSON(), nullable=True),
    sa.Column('timestamp', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('access_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_access_events_id'), ['id'], unique=False)

    op.create_table('clients',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('corporate_name', sa.String(length=200), nullable=True),
    sa.Column('document', sa.String(length=40), nullable=True),
    sa.Column('client_type', sa.Enum('INDIVIDUAL', 'COMPANY', 'INSURER', 'OTHER', name='client_type', native_enum=False, create_constraint=True), server_default='COMPANY', nullable=False),
    sa.Column('email', sa.String(length=160), nullable=True),
    sa.Column('phone', sa.String(length=40), nullable=True),
    sa.Column('status', sa.Enum('ACTIVE', 'INACTIVE', 'SUSPENDED', name='client_status', native_enum=False, create_constraint=True), server_default='ACTIVE', nullable=False),
    sa.Column('region', sa.String(length=120), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('(true)'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('document', name='uq_clients_document')
    )
    with op.batch_alter_table('clients', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_clients_email'), ['email'], unique=False)
        batch_op.create_index(batch_op.f('ix_clients_name'), ['name'], unique=False)
        batch_op.create_index(batch_op.f('ix_clients_region'), ['region'], unique=False)
        batch_op.create_index('ix_clients_status_region', ['status', 'region'], unique=False)

    op.create_table('data_sources',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('provider', sa.String(length=160), nullable=False),
    sa.Column('source_type', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('url_reference', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('(true)'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name', 'provider', name='uq_data_sources_name_provider')
    )
    with op.batch_alter_table('data_sources', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_data_sources_name'), ['name'], unique=False)
        batch_op.create_index(batch_op.f('ix_data_sources_source_type'), ['source_type'], unique=False)

    op.create_table('permissions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=80), nullable=False),
    sa.Column('name', sa.String(length=120), server_default=sa.text("('')"), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('permissions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_permissions_code'), ['code'], unique=True)
        batch_op.create_index(batch_op.f('ix_permissions_id'), ['id'], unique=False)

    op.create_table('prediction_records',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('timestamp', sa.DateTime(), nullable=False),
    sa.Column('model_version', sa.String(length=40), nullable=False),
    sa.Column('source', sa.String(length=40), nullable=False),
    sa.Column('input_payload', sa.JSON(), nullable=False),
    sa.Column('predicted_risk', sa.Float(), nullable=False),
    sa.Column('risk_label', sa.String(length=20), nullable=False),
    sa.Column('alert_level', sa.String(length=40), nullable=False),
    sa.Column('explanation', sa.JSON(), nullable=False),
    sa.Column('recommendation', sa.Text(), nullable=False),
    sa.Column('safe_route', sa.Text(), nullable=False),
    sa.Column('weather_payload', sa.JSON(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('prediction_records', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_prediction_records_id'), ['id'], unique=False)

    op.create_table('roles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=40), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_system_role', sa.Boolean(), server_default=sa.text('(false)'), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('roles', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_roles_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_roles_name'), ['name'], unique=True)

    op.create_table('route_recommendations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('timestamp', sa.DateTime(), nullable=False),
    sa.Column('origin_name', sa.String(length=120), nullable=False),
    sa.Column('destination_name', sa.String(length=120), nullable=False),
    sa.Column('recommended_route', sa.String(length=120), nullable=False),
    sa.Column('route_score', sa.Float(), nullable=False),
    sa.Column('alternatives', sa.JSON(), nullable=False),
    sa.Column('context', sa.JSON(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('route_recommendations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_route_recommendations_id'), ['id'], unique=False)

    op.create_table('user_accounts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(), nullable=False),
    sa.Column('full_name', sa.String(), nullable=False),
    sa.Column('email', sa.String(), nullable=True),
    sa.Column('hashed_password', sa.String(), nullable=False),
    sa.Column('role', sa.String(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('last_login_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    with op.batch_alter_table('user_accounts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_accounts_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_accounts_username'), ['username'], unique=True)

    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('email', sa.String(length=160), nullable=False),
    sa.Column('username', sa.String(length=80), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('status', sa.String(length=40), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('is_superuser', sa.Boolean(), server_default=sa.text('(false)'), nullable=False),
    sa.Column('last_login_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_email'), ['email'], unique=True)
        batch_op.create_index(batch_op.f('ix_users_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_users_username'), ['username'], unique=True)

    op.create_table('audit_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('timestamp', sa.DateTime(), nullable=False),
    sa.Column('actor', sa.String(length=40), nullable=False),
    sa.Column('action', sa.String(length=80), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('entity_type', sa.String(length=120), nullable=True),
    sa.Column('entity_id', sa.String(length=120), nullable=True),
    sa.Column('request_id', sa.String(length=120), nullable=True),
    sa.Column('ip_address', sa.String(length=64), nullable=True),
    sa.Column('old_values_json', sa.JSON(), nullable=True),
    sa.Column('new_values_json', sa.JSON(), nullable=True),
    sa.Column('metadata_json', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.create_index('ix_audit_logs_entity_created_at', ['entity_type', 'entity_id', 'created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_logs_entity_id'), ['entity_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_logs_entity_type'), ['entity_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_logs_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_logs_request_id'), ['request_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_logs_user_id'), ['user_id'], unique=False)

    op.create_table('dataset_versions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('version', sa.String(length=80), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('source_type', sa.Enum('SIMULATED', 'PUBLIC', 'INTEGRATED', 'REAL_OPERATIONAL', 'REAL_IOT', name='dataset_source_type', native_enum=False, create_constraint=True), nullable=False),
    sa.Column('record_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('feature_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('file_path', sa.String(length=500), nullable=True),
    sa.Column('checksum', sa.String(length=128), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('metadata_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=True),
    sa.CheckConstraint('feature_count >= 0', name='ck_dataset_feature_count'),
    sa.CheckConstraint('record_count >= 0', name='ck_dataset_record_count'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name', 'version', name='uq_dataset_versions_name_version')
    )
    with op.batch_alter_table('dataset_versions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_dataset_versions_checksum'), ['checksum'], unique=False)
        batch_op.create_index(batch_op.f('ix_dataset_versions_created_by_user_id'), ['created_by_user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_dataset_versions_name'), ['name'], unique=False)

    op.create_table('farms',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('region', sa.String(length=120), nullable=False),
    sa.Column('latitude', sa.Float(), nullable=False),
    sa.Column('longitude', sa.Float(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=True),
    sa.Column('municipality', sa.String(length=120), nullable=True),
    sa.Column('state', sa.String(length=80), nullable=True),
    sa.Column('country', sa.String(length=2), server_default='BR', nullable=False),
    sa.Column('total_area_ha', sa.Float(), nullable=True),
    sa.Column('cultivated_area_ha', sa.Float(), nullable=True),
    sa.Column('main_crop', sa.String(length=120), nullable=True),
    sa.Column('status', sa.String(length=40), server_default='active', nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('(true)'), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('farms', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_farms_client_id'), ['client_id'], unique=False)
        batch_op.create_index('ix_farms_client_state_municipality', ['client_id', 'state', 'municipality'], unique=False)
        batch_op.create_index(batch_op.f('ix_farms_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_farms_municipality'), ['municipality'], unique=False)
        batch_op.create_index(batch_op.f('ix_farms_state'), ['state'], unique=False)

    op.create_table('role_permissions',
    sa.Column('role_id', sa.Integer(), nullable=False),
    sa.Column('permission_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], ),
    sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ),
    sa.PrimaryKeyConstraint('role_id', 'permission_id')
    )
    op.create_table('system_settings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=160), nullable=False),
    sa.Column('value_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('system_settings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_system_settings_key'), ['key'], unique=True)
        batch_op.create_index(batch_op.f('ix_system_settings_updated_by_user_id'), ['updated_by_user_id'], unique=False)

    op.create_table('user_clients',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'client_id')
    )
    op.create_table('user_permissions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('permission_id', sa.Integer(), nullable=False),
    sa.Column('allowed', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'permission_id', name='uq_user_permission')
    )
    with op.batch_alter_table('user_permissions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_permissions_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_permissions_permission_id'), ['permission_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_permissions_user_id'), ['user_id'], unique=False)

    op.create_table('user_roles',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('role_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('user_id', 'role_id')
    )
    op.create_table('alert_policies',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=True),
    sa.Column('farm_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('operation_type', sa.String(length=40), nullable=False),
    sa.Column('risk_threshold', sa.Float(), nullable=True),
    sa.Column('severity', sa.String(length=20), nullable=True),
    sa.Column('action_type', sa.String(length=80), nullable=True),
    sa.Column('min_risk_alert', sa.Float(), nullable=True),
    sa.Column('min_risk_block', sa.Float(), nullable=True),
    sa.Column('max_speed', sa.Float(), nullable=True),
    sa.Column('max_slope', sa.Float(), nullable=True),
    sa.Column('min_distance_water', sa.Float(), nullable=True),
    sa.Column('max_rain_mm', sa.Float(), nullable=True),
    sa.Column('block_on_water', sa.Boolean(), nullable=True),
    sa.Column('block_on_unstable_soil', sa.Boolean(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.CheckConstraint('risk_threshold IS NULL OR (risk_threshold >= 0 AND risk_threshold <= 100)', name='ck_alert_policy_risk_threshold'),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['farm_id'], ['farms.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('alert_policies', schema=None) as batch_op:
        batch_op.create_index('ix_alert_policies_client_farm_active', ['client_id', 'farm_id', 'is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_alert_policies_client_id'), ['client_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_alert_policies_farm_id'), ['farm_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_alert_policies_id'), ['id'], unique=False)

    op.create_table('equipment',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('equipment_type', sa.String(length=60), nullable=False),
    sa.Column('client_name', sa.String(length=120), server_default=sa.text("('')"), nullable=False),
    sa.Column('manufacturer', sa.String(length=120), nullable=True),
    sa.Column('model', sa.String(length=120), nullable=True),
    sa.Column('year', sa.Integer(), nullable=True),
    sa.Column('serial_number', sa.String(length=120), nullable=True),
    sa.Column('internal_code', sa.String(length=120), nullable=True),
    sa.Column('status', sa.String(length=40), nullable=False),
    sa.Column('farm_id', sa.Integer(), nullable=False),
    sa.Column('purchase_value', sa.Float(), nullable=True),
    sa.Column('estimated_repair_cost', sa.Float(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('(true)'), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['farm_id'], ['farms.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('internal_code', name='uq_equipment_internal_code'),
    sa.UniqueConstraint('serial_number', name='uq_equipment_serial_number')
    )
    with op.batch_alter_table('equipment', schema=None) as batch_op:
        batch_op.create_index('ix_equipment_farm_type_status', ['farm_id', 'equipment_type', 'status'], unique=False)
        batch_op.create_index(batch_op.f('ix_equipment_id'), ['id'], unique=False)

    op.create_table('generated_reports',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=False),
    sa.Column('farm_id', sa.Integer(), nullable=True),
    sa.Column('report_type', sa.String(length=120), nullable=False),
    sa.Column('period_start', sa.Date(), nullable=True),
    sa.Column('period_end', sa.Date(), nullable=True),
    sa.Column('file_path', sa.String(length=500), nullable=True),
    sa.Column('status', sa.Enum('PENDING', 'GENERATING', 'READY', 'FAILED', name='generated_report_status', native_enum=False, create_constraint=True), server_default='PENDING', nullable=False),
    sa.Column('parameters_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['farm_id'], ['farms.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('generated_reports', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_generated_reports_client_id'), ['client_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_generated_reports_farm_id'), ['farm_id'], unique=False)
        batch_op.create_index('ix_generated_reports_farm_period', ['farm_id', 'period_start', 'period_end'], unique=False)
        batch_op.create_index(batch_op.f('ix_generated_reports_report_type'), ['report_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_generated_reports_user_id'), ['user_id'], unique=False)

    op.create_table('model_versions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('version', sa.String(length=80), nullable=False),
    sa.Column('algorithm', sa.String(length=120), nullable=False),
    sa.Column('status', sa.Enum('TRAINING', 'VALIDATION', 'ACTIVE', 'INACTIVE', 'DEPRECATED', name='model_status', native_enum=False, create_constraint=True), server_default='TRAINING', nullable=False),
    sa.Column('dataset_version_id', sa.Integer(), nullable=True),
    sa.Column('trained_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deployed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('accuracy', sa.Float(), nullable=True),
    sa.Column('precision_score', sa.Float(), nullable=True),
    sa.Column('recall_score', sa.Float(), nullable=True),
    sa.Column('f1_score', sa.Float(), nullable=True),
    sa.Column('roc_auc', sa.Float(), nullable=True),
    sa.Column('metrics_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=True),
    sa.Column('parameters_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=True),
    sa.Column('feature_list_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=True),
    sa.Column('artifact_path', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('(true)'), nullable=False),
    sa.CheckConstraint('accuracy IS NULL OR (accuracy >= 0 AND accuracy <= 1)', name='ck_model_accuracy'),
    sa.CheckConstraint('f1_score IS NULL OR (f1_score >= 0 AND f1_score <= 1)', name='ck_model_f1'),
    sa.CheckConstraint('precision_score IS NULL OR (precision_score >= 0 AND precision_score <= 1)', name='ck_model_precision'),
    sa.CheckConstraint('recall_score IS NULL OR (recall_score >= 0 AND recall_score <= 1)', name='ck_model_recall'),
    sa.CheckConstraint('roc_auc IS NULL OR (roc_auc >= 0 AND roc_auc <= 1)', name='ck_model_roc_auc'),
    sa.ForeignKeyConstraint(['dataset_version_id'], ['dataset_versions.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name', 'version', name='uq_model_versions_name_version')
    )
    with op.batch_alter_table('model_versions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_model_versions_dataset_version_id'), ['dataset_version_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_model_versions_name'), ['name'], unique=False)
        batch_op.create_index('ix_model_versions_status_deployed_at', ['status', 'deployed_at'], unique=False)

    op.create_table('soil_records',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('farm_id', sa.Integer(), nullable=False),
    sa.Column('source', sa.Enum('SoilGrids', 'dataset', 'manual', 'future_sensor', name='soil_source', native_enum=False, create_constraint=True), nullable=False),
    sa.Column('sampled_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('soil_moisture_pct', sa.Float(), nullable=True),
    sa.Column('clay_pct', sa.Float(), nullable=True),
    sa.Column('sand_pct', sa.Float(), nullable=True),
    sa.Column('silt_pct', sa.Float(), nullable=True),
    sa.Column('organic_carbon', sa.Float(), nullable=True),
    sa.Column('ph', sa.Float(), nullable=True),
    sa.Column('bulk_density', sa.Float(), nullable=True),
    sa.Column('drainage_class', sa.String(length=80), nullable=True),
    sa.Column('raw_data_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint('clay_pct IS NULL OR (clay_pct >= 0 AND clay_pct <= 100)', name='ck_soil_clay_pct'),
    sa.CheckConstraint('ph IS NULL OR (ph >= 0 AND ph <= 14)', name='ck_soil_ph'),
    sa.CheckConstraint('sand_pct IS NULL OR (sand_pct >= 0 AND sand_pct <= 100)', name='ck_soil_sand_pct'),
    sa.CheckConstraint('silt_pct IS NULL OR (silt_pct >= 0 AND silt_pct <= 100)', name='ck_soil_silt_pct'),
    sa.CheckConstraint('soil_moisture_pct IS NULL OR (soil_moisture_pct >= 0 AND soil_moisture_pct <= 100)', name='ck_soil_moisture_pct'),
    sa.ForeignKeyConstraint(['farm_id'], ['farms.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('soil_records', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_soil_records_farm_id'), ['farm_id'], unique=False)
        batch_op.create_index('ix_soil_records_farm_sampled_at', ['farm_id', 'sampled_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_soil_records_sampled_at'), ['sampled_at'], unique=False)

    op.create_table('terrain_records',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('farm_id', sa.Integer(), nullable=False),
    sa.Column('latitude', sa.Float(), nullable=False),
    sa.Column('longitude', sa.Float(), nullable=False),
    sa.Column('elevation_m', sa.Float(), nullable=True),
    sa.Column('slope_deg', sa.Float(), nullable=True),
    sa.Column('distance_to_water_m', sa.Float(), nullable=True),
    sa.Column('distance_to_road_m', sa.Float(), nullable=True),
    sa.Column('road_type', sa.String(length=80), nullable=True),
    sa.Column('land_use_class', sa.String(length=120), nullable=True),
    sa.Column('source', sa.Enum('SRTM', 'HydroRIVERS', 'MapBiomas', 'OpenStreetMap', name='terrain_source', native_enum=False, create_constraint=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint('distance_to_road_m IS NULL OR distance_to_road_m >= 0', name='ck_terrain_distance_road'),
    sa.CheckConstraint('distance_to_water_m IS NULL OR distance_to_water_m >= 0', name='ck_terrain_distance_water'),
    sa.CheckConstraint('latitude >= -90 AND latitude <= 90', name='ck_terrain_latitude'),
    sa.CheckConstraint('longitude >= -180 AND longitude <= 180', name='ck_terrain_longitude'),
    sa.CheckConstraint('slope_deg IS NULL OR (slope_deg >= 0 AND slope_deg <= 90)', name='ck_terrain_slope_deg'),
    sa.ForeignKeyConstraint(['farm_id'], ['farms.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('terrain_records', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_terrain_records_farm_id'), ['farm_id'], unique=False)
        batch_op.create_index('ix_terrain_records_farm_location', ['farm_id', 'latitude', 'longitude'], unique=False)

    op.create_table('user_farms',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('farm_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['farm_id'], ['farms.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'farm_id')
    )
    op.create_table('weather_records',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('farm_id', sa.Integer(), nullable=False),
    sa.Column('source', sa.Enum('OpenWeather', 'INMET', 'NASA_POWER', 'SIMULATION', name='weather_source', native_enum=False, create_constraint=True), nullable=False),
    sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('temperature_c', sa.Float(), nullable=True),
    sa.Column('humidity_pct', sa.Float(), nullable=True),
    sa.Column('precipitation_mm', sa.Float(), nullable=True),
    sa.Column('wind_speed_kmh', sa.Float(), nullable=True),
    sa.Column('pressure_hpa', sa.Float(), nullable=True),
    sa.Column('weather_condition', sa.String(length=80), nullable=True),
    sa.Column('raw_data_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint('humidity_pct IS NULL OR (humidity_pct >= 0 AND humidity_pct <= 100)', name='ck_weather_humidity_pct'),
    sa.CheckConstraint('precipitation_mm IS NULL OR precipitation_mm >= 0', name='ck_weather_precipitation_mm'),
    sa.CheckConstraint('wind_speed_kmh IS NULL OR wind_speed_kmh >= 0', name='ck_weather_wind_speed_kmh'),
    sa.ForeignKeyConstraint(['farm_id'], ['farms.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('weather_records', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_weather_records_farm_id'), ['farm_id'], unique=False)
        batch_op.create_index('ix_weather_records_farm_recorded_at', ['farm_id', 'recorded_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_weather_records_recorded_at'), ['recorded_at'], unique=False)

    op.create_table('iot_devices',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('device_id', sa.String(length=120), nullable=False),
    sa.Column('device_identifier', sa.String(length=120), nullable=True),
    sa.Column('equipment_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('device_type', sa.String(length=60), nullable=False),
    sa.Column('firmware_version', sa.String(length=80), nullable=True),
    sa.Column('api_key_hash', sa.String(length=255), nullable=False),
    sa.Column('status', sa.String(length=40), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(), nullable=True),
    sa.Column('metadata_json', sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('(true)'), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint('device_identifier IS NOT NULL OR device_id IS NOT NULL', name='ck_iot_device_identifier'),
    sa.ForeignKeyConstraint(['equipment_id'], ['equipment.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('device_identifier', name='uq_iot_devices_device_identifier')
    )
    with op.batch_alter_table('iot_devices', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_iot_devices_device_id'), ['device_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_iot_devices_device_identifier'), ['device_identifier'], unique=False)
        batch_op.create_index(batch_op.f('ix_iot_devices_equipment_id'), ['equipment_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_iot_devices_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_iot_devices_status'), ['status'], unique=False)

    op.create_table('operations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=False),
    sa.Column('farm_id', sa.Integer(), nullable=False),
    sa.Column('equipment_id', sa.Integer(), nullable=False),
    sa.Column('operation_type', sa.Enum('field', 'transport', 'harvest', 'spraying', 'maintenance', 'near_water', 'other', name='operation_type', native_enum=False, create_constraint=True), nullable=False),
    sa.Column('crop_type', sa.String(length=120), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.Enum('PLANNED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED', 'BLOCKED', name='operation_status', native_enum=False, create_constraint=True), server_default='PLANNED', nullable=False),
    sa.Column('operator_user_id', sa.Integer(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('(true)'), nullable=False),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['equipment_id'], ['equipment.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['farm_id'], ['farms.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['operator_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('operations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_operations_client_id'), ['client_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_operations_equipment_id'), ['equipment_id'], unique=False)
        batch_op.create_index('ix_operations_equipment_started_at', ['equipment_id', 'started_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_operations_farm_id'), ['farm_id'], unique=False)
        batch_op.create_index('ix_operations_farm_status', ['farm_id', 'status'], unique=False)
        batch_op.create_index(batch_op.f('ix_operations_operator_user_id'), ['operator_user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_operations_started_at'), ['started_at'], unique=False)

    op.create_table('sensor_readings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('timestamp', sa.DateTime(), nullable=False),
    sa.Column('device_id', sa.String(length=120), nullable=False),
    sa.Column('equipment_id', sa.Integer(), nullable=False),
    sa.Column('farm_id', sa.Integer(), nullable=False),
    sa.Column('latitude', sa.Float(), nullable=False),
    sa.Column('longitude', sa.Float(), nullable=False),
    sa.Column('gps_accuracy_m', sa.Float(), nullable=True),
    sa.Column('gps_satellites', sa.Integer(), nullable=True),
    sa.Column('temperatura_c', sa.Float(), nullable=True),
    sa.Column('umidade_ar', sa.Float(), nullable=True),
    sa.Column('pressao_hpa', sa.Float(), nullable=True),
    sa.Column('umidade_solo', sa.Float(), nullable=True),
    sa.Column('inclinacao', sa.Float(), nullable=True),
    sa.Column('distancia_obstaculo', sa.Float(), nullable=True),
    sa.Column('distancia_agua', sa.Float(), nullable=True),
    sa.Column('velocidade', sa.Float(), nullable=True),
    sa.Column('chuva_mm', sa.Float(), nullable=True),
    sa.Column('battery_voltage', sa.Float(), nullable=True),
    sa.Column('predicted_risk', sa.Float(), nullable=True),
    sa.Column('risk_label', sa.String(length=20), nullable=True),
    sa.Column('raw_payload', sa.JSON(), nullable=False),
    sa.Column('normalized_payload', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['equipment_id'], ['equipment.id'], ),
    sa.ForeignKeyConstraint(['farm_id'], ['farms.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('sensor_readings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_sensor_readings_id'), ['id'], unique=False)

    op.create_table('telemetry_records',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('timestamp', sa.DateTime(), nullable=False),
    sa.Column('equipment_id', sa.Integer(), nullable=False),
    sa.Column('farm_id', sa.Integer(), nullable=False),
    sa.Column('region', sa.String(length=120), nullable=False),
    sa.Column('operation_type', sa.String(length=40), nullable=False),
    sa.Column('clima', sa.String(length=40), nullable=False),
    sa.Column('umidade_solo', sa.Float(), nullable=False),
    sa.Column('inclinacao', sa.Float(), nullable=False),
    sa.Column('distancia_agua', sa.Float(), nullable=False),
    sa.Column('velocidade', sa.Float(), nullable=False),
    sa.Column('historico_sinistros', sa.Float(), nullable=False),
    sa.Column('chuva_mm', sa.Float(), nullable=False),
    sa.Column('solo_instavel', sa.Integer(), nullable=False),
    sa.Column('latitude', sa.Float(), nullable=False),
    sa.Column('longitude', sa.Float(), nullable=False),
    sa.Column('predicted_risk', sa.Float(), nullable=False),
    sa.Column('risk_label', sa.String(length=20), nullable=False),
    sa.Column('alert_level', sa.String(length=40), nullable=False),
    sa.Column('recommendation', sa.Text(), nullable=False),
    sa.Column('safe_route', sa.Text(), nullable=False),
    sa.Column('explanation', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['equipment_id'], ['equipment.id'], ),
    sa.ForeignKeyConstraint(['farm_id'], ['farms.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('telemetry_records', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_telemetry_records_id'), ['id'], unique=False)

    op.create_table('user_access_scopes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=True),
    sa.Column('client_name', sa.String(length=120), nullable=True),
    sa.Column('farm_id', sa.Integer(), nullable=True),
    sa.Column('equipment_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['equipment_id'], ['equipment.id'], ),
    sa.ForeignKeyConstraint(['farm_id'], ['farms.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('user_access_scopes', schema=None) as batch_op:
        batch_op.create_index('ix_user_access_scope_user_farm_equipment', ['user_id', 'farm_id', 'equipment_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_access_scopes_client_id'), ['client_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_access_scopes_client_name'), ['client_name'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_access_scopes_equipment_id'), ['equipment_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_access_scopes_farm_id'), ['farm_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_access_scopes_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_access_scopes_user_id'), ['user_id'], unique=False)

    op.create_table('user_equipments',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('equipment_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['equipment_id'], ['equipment.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'equipment_id')
    )
    op.create_table('incidents',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=False),
    sa.Column('farm_id', sa.Integer(), nullable=False),
    sa.Column('equipment_id', sa.Integer(), nullable=True),
    sa.Column('operation_id', sa.Integer(), nullable=True),
    sa.Column('incident_type', sa.Enum('collision', 'rollover', 'stuck', 'water_damage', 'mechanical_damage', 'transport_accident', 'fire', 'other', name='incident_type', native_enum=False, create_constraint=True), nullable=False),
    sa.Column('severity', sa.Enum('LOW', 'MEDIUM', 'HIGH', 'CRITICAL', name='incident_severity', native_enum=False, create_constraint=True), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('latitude', sa.Float(), nullable=True),
    sa.Column('longitude', sa.Float(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('estimated_damage_brl', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('was_preventable', sa.Boolean(), nullable=True),
    sa.Column('status', sa.Enum('OPEN', 'UNDER_REVIEW', 'CLOSED', 'DISMISSED', name='incident_status', native_enum=False, create_constraint=True), server_default='OPEN', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint('estimated_damage_brl IS NULL OR estimated_damage_brl >= 0', name='ck_incident_estimated_damage'),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['equipment_id'], ['equipment.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['farm_id'], ['farms.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['operation_id'], ['operations.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('incidents', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_incidents_client_id'), ['client_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_incidents_equipment_id'), ['equipment_id'], unique=False)
        batch_op.create_index('ix_incidents_equipment_occurred_at', ['equipment_id', 'occurred_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_incidents_farm_id'), ['farm_id'], unique=False)
        batch_op.create_index('ix_incidents_farm_status', ['farm_id', 'status'], unique=False)
        batch_op.create_index(batch_op.f('ix_incidents_occurred_at'), ['occurred_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_incidents_operation_id'), ['operation_id'], unique=False)

    op.create_table('iot_telemetry',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('device_id', sa.String(length=120), nullable=False),
    sa.Column('equipment_id', sa.Integer(), nullable=False),
    sa.Column('timestamp', sa.DateTime(), nullable=False),
    sa.Column('received_at', sa.DateTime(), nullable=False),
    sa.Column('temperature_c', sa.Float(), nullable=True),
    sa.Column('humidity_pct', sa.Float(), nullable=True),
    sa.Column('pressure_hpa', sa.Float(), nullable=True),
    sa.Column('altitude_m', sa.Float(), nullable=True),
    sa.Column('accel_x', sa.Float(), nullable=True),
    sa.Column('accel_y', sa.Float(), nullable=True),
    sa.Column('accel_z', sa.Float(), nullable=True),
    sa.Column('gyro_x', sa.Float(), nullable=True),
    sa.Column('gyro_y', sa.Float(), nullable=True),
    sa.Column('gyro_z', sa.Float(), nullable=True),
    sa.Column('pitch', sa.Float(), nullable=True),
    sa.Column('roll', sa.Float(), nullable=True),
    sa.Column('acceleration_magnitude', sa.Float(), nullable=True),
    sa.Column('gyro_magnitude', sa.Float(), nullable=True),
    sa.Column('max_tilt_angle', sa.Float(), nullable=True),
    sa.Column('movement_anomaly_score', sa.Float(), nullable=True),
    sa.Column('possible_impact', sa.Boolean(), nullable=False),
    sa.Column('obstacle_detected', sa.Boolean(), nullable=True),
    sa.Column('obstacle_distance_cm', sa.Float(), nullable=True),
    sa.Column('latitude', sa.Float(), nullable=True),
    sa.Column('longitude', sa.Float(), nullable=True),
    sa.Column('telemetry_age_seconds', sa.Float(), nullable=False),
    sa.Column('telemetry_status', sa.String(length=20), nullable=False),
    sa.Column('data_quality_status', sa.String(length=20), nullable=False),
    sa.Column('data_quality_issues', sa.JSON(), nullable=False),
    sa.Column('missing_sensors', sa.JSON(), nullable=False),
    sa.Column('confidence_score', sa.Float(), nullable=True),
    sa.Column('risk_score', sa.Float(), nullable=True),
    sa.Column('risk_level', sa.String(length=20), nullable=True),
    sa.Column('explanation', sa.JSON(), nullable=True),
    sa.Column('risk_prediction_id', sa.Integer(), nullable=True),
    sa.Column('raw_payload', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['device_id'], ['iot_devices.device_id'], ),
    sa.ForeignKeyConstraint(['equipment_id'], ['equipment.id'], ),
    sa.ForeignKeyConstraint(['risk_prediction_id'], ['prediction_records.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('iot_telemetry', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_iot_telemetry_device_id'), ['device_id'], unique=False)
        batch_op.create_index('ix_iot_telemetry_device_timestamp', ['device_id', 'timestamp'], unique=False)
        batch_op.create_index(batch_op.f('ix_iot_telemetry_equipment_id'), ['equipment_id'], unique=False)
        batch_op.create_index('ix_iot_telemetry_equipment_timestamp', ['equipment_id', 'timestamp'], unique=False)
        batch_op.create_index(batch_op.f('ix_iot_telemetry_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_iot_telemetry_risk_prediction_id'), ['risk_prediction_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_iot_telemetry_timestamp'), ['timestamp'], unique=False)

    op.create_table('risk_predictions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=False),
    sa.Column('farm_id', sa.Integer(), nullable=False),
    sa.Column('equipment_id', sa.Integer(), nullable=True),
    sa.Column('operation_id', sa.Integer(), nullable=True),
    sa.Column('risk_score', sa.Float(), nullable=False),
    sa.Column('risk_level', sa.Enum('LOW', 'MEDIUM', 'HIGH', 'CRITICAL', name='risk_level', native_enum=False, create_constraint=True), nullable=False),
    sa.Column('confidence_score', sa.Float(), nullable=True),
    sa.Column('main_risk_factor', sa.String(length=160), nullable=True),
    sa.Column('model_version_id', sa.Integer(), nullable=True),
    sa.Column('input_snapshot_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('explanation_summary', sa.Text(), nullable=True),
    sa.Column('recommendation_summary', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint('confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 100)', name='ck_risk_prediction_confidence'),
    sa.CheckConstraint('risk_score >= 0 AND risk_score <= 100', name='ck_risk_prediction_score'),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['equipment_id'], ['equipment.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['farm_id'], ['farms.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['model_version_id'], ['model_versions.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['operation_id'], ['operations.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('risk_predictions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_risk_predictions_client_id'), ['client_id'], unique=False)
        batch_op.create_index('ix_risk_predictions_equipment_created_at', ['equipment_id', 'created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_risk_predictions_equipment_id'), ['equipment_id'], unique=False)
        batch_op.create_index('ix_risk_predictions_farm_created_at', ['farm_id', 'created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_risk_predictions_farm_id'), ['farm_id'], unique=False)
        batch_op.create_index('ix_risk_predictions_level_created_at', ['risk_level', 'created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_risk_predictions_model_version_id'), ['model_version_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_risk_predictions_operation_id'), ['operation_id'], unique=False)

    op.create_table('risk_simulations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=False),
    sa.Column('farm_id', sa.Integer(), nullable=False),
    sa.Column('equipment_id', sa.Integer(), nullable=True),
    sa.Column('operation_id', sa.Integer(), nullable=True),
    sa.Column('base_risk_score', sa.Float(), nullable=False),
    sa.Column('simulated_risk_score', sa.Float(), nullable=False),
    sa.Column('risk_difference', sa.Float(), nullable=False),
    sa.Column('risk_difference_pct', sa.Float(), nullable=True),
    sa.Column('base_conditions_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('simulated_conditions_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('recommendation', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint('base_risk_score >= 0 AND base_risk_score <= 100', name='ck_simulation_base_score'),
    sa.CheckConstraint('simulated_risk_score >= 0 AND simulated_risk_score <= 100', name='ck_simulation_score'),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['equipment_id'], ['equipment.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['farm_id'], ['farms.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['operation_id'], ['operations.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('risk_simulations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_risk_simulations_client_id'), ['client_id'], unique=False)
        batch_op.create_index('ix_risk_simulations_equipment_created_at', ['equipment_id', 'created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_risk_simulations_equipment_id'), ['equipment_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_risk_simulations_farm_id'), ['farm_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_risk_simulations_operation_id'), ['operation_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_risk_simulations_user_id'), ['user_id'], unique=False)

    op.create_table('alert_records',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('timestamp', sa.DateTime(), nullable=False),
    sa.Column('alert_type', sa.String(length=60), nullable=False),
    sa.Column('severity', sa.String(length=20), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('context', sa.JSON(), nullable=False),
    sa.Column('equipment_id', sa.Integer(), nullable=True),
    sa.Column('device_id', sa.String(length=120), nullable=True),
    sa.Column('telemetry_id', sa.Integer(), nullable=True),
    sa.Column('risk_prediction_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['equipment_id'], ['equipment.id'], ),
    sa.ForeignKeyConstraint(['risk_prediction_id'], ['prediction_records.id'], ),
    sa.ForeignKeyConstraint(['telemetry_id'], ['iot_telemetry.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('alert_records', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_alert_records_device_id'), ['device_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_alert_records_equipment_id'), ['equipment_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_alert_records_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_alert_records_risk_prediction_id'), ['risk_prediction_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_alert_records_telemetry_id'), ['telemetry_id'], unique=False)

    op.create_table('alerts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=False),
    sa.Column('farm_id', sa.Integer(), nullable=False),
    sa.Column('equipment_id', sa.Integer(), nullable=True),
    sa.Column('operation_id', sa.Integer(), nullable=True),
    sa.Column('risk_prediction_id', sa.Integer(), nullable=True),
    sa.Column('alert_type', sa.String(length=100), nullable=False),
    sa.Column('severity', sa.Enum('INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL', name='alert_severity', native_enum=False, create_constraint=True), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('status', sa.Enum('OPEN', 'ACKNOWLEDGED', 'RESOLVED', 'DISMISSED', name='alert_status', native_enum=False, create_constraint=True), server_default='OPEN', nullable=False),
    sa.Column('acknowledged_by_user_id', sa.Integer(), nullable=True),
    sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['acknowledged_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['equipment_id'], ['equipment.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['farm_id'], ['farms.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['operation_id'], ['operations.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['risk_prediction_id'], ['risk_predictions.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('alerts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_alerts_acknowledged_by_user_id'), ['acknowledged_by_user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_alerts_alert_type'), ['alert_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_alerts_client_id'), ['client_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_alerts_equipment_id'), ['equipment_id'], unique=False)
        batch_op.create_index('ix_alerts_equipment_status_created_at', ['equipment_id', 'status', 'created_at'], unique=False)
        batch_op.create_index('ix_alerts_farm_created_at', ['farm_id', 'created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_alerts_farm_id'), ['farm_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_alerts_operation_id'), ['operation_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_alerts_risk_prediction_id'), ['risk_prediction_id'], unique=False)
        batch_op.create_index('ix_alerts_status_created_at', ['status', 'created_at'], unique=False)

    op.create_table('recommendations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('risk_prediction_id', sa.Integer(), nullable=False),
    sa.Column('equipment_id', sa.Integer(), nullable=True),
    sa.Column('recommendation_type', sa.Enum('OPERATIONAL', 'ROUTE', 'MAINTENANCE', 'SAFETY', 'OTHER', name='recommendation_type', native_enum=False, create_constraint=True), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('expected_risk_reduction_pct', sa.Float(), nullable=True),
    sa.Column('priority', sa.Enum('LOW', 'MEDIUM', 'HIGH', 'CRITICAL', name='recommendation_priority', native_enum=False, create_constraint=True), server_default='MEDIUM', nullable=False),
    sa.Column('was_applied', sa.Boolean(), server_default=sa.text('(false)'), nullable=False),
    sa.Column('applied_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('applied_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint('expected_risk_reduction_pct IS NULL OR (expected_risk_reduction_pct >= 0 AND expected_risk_reduction_pct <= 100)', name='ck_recommendation_reduction'),
    sa.ForeignKeyConstraint(['applied_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['equipment_id'], ['equipment.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['risk_prediction_id'], ['risk_predictions.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('recommendations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_recommendations_applied_by_user_id'), ['applied_by_user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_recommendations_equipment_id'), ['equipment_id'], unique=False)
        batch_op.create_index('ix_recommendations_equipment_priority', ['equipment_id', 'priority'], unique=False)
        batch_op.create_index(batch_op.f('ix_recommendations_risk_prediction_id'), ['risk_prediction_id'], unique=False)

    op.create_table('risk_prediction_factors',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('risk_prediction_id', sa.Integer(), nullable=False),
    sa.Column('factor_name', sa.String(length=120), nullable=False),
    sa.Column('factor_category', sa.String(length=80), nullable=True),
    sa.Column('raw_value', sa.Float(), nullable=True),
    sa.Column('normalized_value', sa.Float(), nullable=True),
    sa.Column('unit', sa.String(length=40), nullable=True),
    sa.Column('impact_score', sa.Float(), nullable=True),
    sa.Column('importance_pct', sa.Float(), nullable=True),
    sa.Column('explanation', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint('impact_score IS NULL OR (impact_score >= -100 AND impact_score <= 100)', name='ck_risk_factor_impact'),
    sa.CheckConstraint('importance_pct IS NULL OR (importance_pct >= 0 AND importance_pct <= 100)', name='ck_risk_factor_importance'),
    sa.ForeignKeyConstraint(['risk_prediction_id'], ['risk_predictions.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('risk_prediction_factors', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_risk_prediction_factors_factor_category'), ['factor_category'], unique=False)
        batch_op.create_index('ix_risk_prediction_factors_prediction_category', ['risk_prediction_id', 'factor_category'], unique=False)
        batch_op.create_index(batch_op.f('ix_risk_prediction_factors_risk_prediction_id'), ['risk_prediction_id'], unique=False)

    op.create_table('notifications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('alert_id', sa.Integer(), nullable=True),
    sa.Column('notification_type', sa.Enum('DASHBOARD', 'EMAIL', 'PUSH', 'WHATSAPP', name='notification_type', native_enum=False, create_constraint=True), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('is_read', sa.Boolean(), server_default=sa.text('(false)'), nullable=False),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['alert_id'], ['alerts.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_notifications_alert_id'), ['alert_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_notifications_user_id'), ['user_id'], unique=False)
        batch_op.create_index('ix_notifications_user_read_created_at', ['user_id', 'is_read', 'created_at'], unique=False)

    op.create_table('prevented_loss_records',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('equipment_id', sa.Integer(), nullable=False),
    sa.Column('risk_prediction_id', sa.Integer(), nullable=False),
    sa.Column('recommendation_id', sa.Integer(), nullable=True),
    sa.Column('previous_risk_score', sa.Float(), nullable=False),
    sa.Column('new_risk_score', sa.Float(), nullable=False),
    sa.Column('risk_reduction_pct', sa.Float(), nullable=False),
    sa.Column('possible_prevented_loss', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('estimated_savings_brl', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('calculation_method', sa.String(length=200), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint('estimated_savings_brl IS NULL OR estimated_savings_brl >= 0', name='ck_prevented_loss_savings'),
    sa.CheckConstraint('new_risk_score >= 0 AND new_risk_score <= 100', name='ck_prevented_loss_new_score'),
    sa.CheckConstraint('possible_prevented_loss IS NULL OR possible_prevented_loss >= 0', name='ck_prevented_loss_possible'),
    sa.CheckConstraint('previous_risk_score >= 0 AND previous_risk_score <= 100', name='ck_prevented_loss_previous_score'),
    sa.CheckConstraint('risk_reduction_pct >= 0 AND risk_reduction_pct <= 100', name='ck_prevented_loss_reduction'),
    sa.ForeignKeyConstraint(['equipment_id'], ['equipment.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['recommendation_id'], ['recommendations.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['risk_prediction_id'], ['risk_predictions.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('prevented_loss_records', schema=None) as batch_op:
        batch_op.create_index('ix_prevented_loss_records_equipment_created_at', ['equipment_id', 'created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_prevented_loss_records_equipment_id'), ['equipment_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_prevented_loss_records_recommendation_id'), ['recommendation_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_prevented_loss_records_risk_prediction_id'), ['risk_prediction_id'], unique=False)

    # ### end Alembic commands ###


def _downgrade_fresh_schema() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('prevented_loss_records', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_prevented_loss_records_risk_prediction_id'))
        batch_op.drop_index(batch_op.f('ix_prevented_loss_records_recommendation_id'))
        batch_op.drop_index(batch_op.f('ix_prevented_loss_records_equipment_id'))
        batch_op.drop_index('ix_prevented_loss_records_equipment_created_at')

    op.drop_table('prevented_loss_records')
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.drop_index('ix_notifications_user_read_created_at')
        batch_op.drop_index(batch_op.f('ix_notifications_user_id'))
        batch_op.drop_index(batch_op.f('ix_notifications_alert_id'))

    op.drop_table('notifications')
    with op.batch_alter_table('risk_prediction_factors', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_risk_prediction_factors_risk_prediction_id'))
        batch_op.drop_index('ix_risk_prediction_factors_prediction_category')
        batch_op.drop_index(batch_op.f('ix_risk_prediction_factors_factor_category'))

    op.drop_table('risk_prediction_factors')
    with op.batch_alter_table('recommendations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_recommendations_risk_prediction_id'))
        batch_op.drop_index('ix_recommendations_equipment_priority')
        batch_op.drop_index(batch_op.f('ix_recommendations_equipment_id'))
        batch_op.drop_index(batch_op.f('ix_recommendations_applied_by_user_id'))

    op.drop_table('recommendations')
    with op.batch_alter_table('alerts', schema=None) as batch_op:
        batch_op.drop_index('ix_alerts_status_created_at')
        batch_op.drop_index(batch_op.f('ix_alerts_risk_prediction_id'))
        batch_op.drop_index(batch_op.f('ix_alerts_operation_id'))
        batch_op.drop_index(batch_op.f('ix_alerts_farm_id'))
        batch_op.drop_index('ix_alerts_farm_created_at')
        batch_op.drop_index('ix_alerts_equipment_status_created_at')
        batch_op.drop_index(batch_op.f('ix_alerts_equipment_id'))
        batch_op.drop_index(batch_op.f('ix_alerts_client_id'))
        batch_op.drop_index(batch_op.f('ix_alerts_alert_type'))
        batch_op.drop_index(batch_op.f('ix_alerts_acknowledged_by_user_id'))

    op.drop_table('alerts')
    with op.batch_alter_table('alert_records', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_alert_records_telemetry_id'))
        batch_op.drop_index(batch_op.f('ix_alert_records_risk_prediction_id'))
        batch_op.drop_index(batch_op.f('ix_alert_records_id'))
        batch_op.drop_index(batch_op.f('ix_alert_records_equipment_id'))
        batch_op.drop_index(batch_op.f('ix_alert_records_device_id'))

    op.drop_table('alert_records')
    with op.batch_alter_table('risk_simulations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_risk_simulations_user_id'))
        batch_op.drop_index(batch_op.f('ix_risk_simulations_operation_id'))
        batch_op.drop_index(batch_op.f('ix_risk_simulations_farm_id'))
        batch_op.drop_index(batch_op.f('ix_risk_simulations_equipment_id'))
        batch_op.drop_index('ix_risk_simulations_equipment_created_at')
        batch_op.drop_index(batch_op.f('ix_risk_simulations_client_id'))

    op.drop_table('risk_simulations')
    with op.batch_alter_table('risk_predictions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_risk_predictions_operation_id'))
        batch_op.drop_index(batch_op.f('ix_risk_predictions_model_version_id'))
        batch_op.drop_index('ix_risk_predictions_level_created_at')
        batch_op.drop_index(batch_op.f('ix_risk_predictions_farm_id'))
        batch_op.drop_index('ix_risk_predictions_farm_created_at')
        batch_op.drop_index(batch_op.f('ix_risk_predictions_equipment_id'))
        batch_op.drop_index('ix_risk_predictions_equipment_created_at')
        batch_op.drop_index(batch_op.f('ix_risk_predictions_client_id'))

    op.drop_table('risk_predictions')
    with op.batch_alter_table('iot_telemetry', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_iot_telemetry_timestamp'))
        batch_op.drop_index(batch_op.f('ix_iot_telemetry_risk_prediction_id'))
        batch_op.drop_index(batch_op.f('ix_iot_telemetry_id'))
        batch_op.drop_index('ix_iot_telemetry_equipment_timestamp')
        batch_op.drop_index(batch_op.f('ix_iot_telemetry_equipment_id'))
        batch_op.drop_index('ix_iot_telemetry_device_timestamp')
        batch_op.drop_index(batch_op.f('ix_iot_telemetry_device_id'))

    op.drop_table('iot_telemetry')
    with op.batch_alter_table('incidents', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_incidents_operation_id'))
        batch_op.drop_index(batch_op.f('ix_incidents_occurred_at'))
        batch_op.drop_index('ix_incidents_farm_status')
        batch_op.drop_index(batch_op.f('ix_incidents_farm_id'))
        batch_op.drop_index('ix_incidents_equipment_occurred_at')
        batch_op.drop_index(batch_op.f('ix_incidents_equipment_id'))
        batch_op.drop_index(batch_op.f('ix_incidents_client_id'))

    op.drop_table('incidents')
    op.drop_table('user_equipments')
    with op.batch_alter_table('user_access_scopes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_access_scopes_user_id'))
        batch_op.drop_index(batch_op.f('ix_user_access_scopes_id'))
        batch_op.drop_index(batch_op.f('ix_user_access_scopes_farm_id'))
        batch_op.drop_index(batch_op.f('ix_user_access_scopes_equipment_id'))
        batch_op.drop_index(batch_op.f('ix_user_access_scopes_client_name'))
        batch_op.drop_index(batch_op.f('ix_user_access_scopes_client_id'))
        batch_op.drop_index('ix_user_access_scope_user_farm_equipment')

    op.drop_table('user_access_scopes')
    with op.batch_alter_table('telemetry_records', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_telemetry_records_id'))

    op.drop_table('telemetry_records')
    with op.batch_alter_table('sensor_readings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_sensor_readings_id'))

    op.drop_table('sensor_readings')
    with op.batch_alter_table('operations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_operations_started_at'))
        batch_op.drop_index(batch_op.f('ix_operations_operator_user_id'))
        batch_op.drop_index('ix_operations_farm_status')
        batch_op.drop_index(batch_op.f('ix_operations_farm_id'))
        batch_op.drop_index('ix_operations_equipment_started_at')
        batch_op.drop_index(batch_op.f('ix_operations_equipment_id'))
        batch_op.drop_index(batch_op.f('ix_operations_client_id'))

    op.drop_table('operations')
    with op.batch_alter_table('iot_devices', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_iot_devices_status'))
        batch_op.drop_index(batch_op.f('ix_iot_devices_id'))
        batch_op.drop_index(batch_op.f('ix_iot_devices_equipment_id'))
        batch_op.drop_index(batch_op.f('ix_iot_devices_device_identifier'))
        batch_op.drop_index(batch_op.f('ix_iot_devices_device_id'))

    op.drop_table('iot_devices')
    with op.batch_alter_table('weather_records', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_weather_records_recorded_at'))
        batch_op.drop_index('ix_weather_records_farm_recorded_at')
        batch_op.drop_index(batch_op.f('ix_weather_records_farm_id'))

    op.drop_table('weather_records')
    op.drop_table('user_farms')
    with op.batch_alter_table('terrain_records', schema=None) as batch_op:
        batch_op.drop_index('ix_terrain_records_farm_location')
        batch_op.drop_index(batch_op.f('ix_terrain_records_farm_id'))

    op.drop_table('terrain_records')
    with op.batch_alter_table('soil_records', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_soil_records_sampled_at'))
        batch_op.drop_index('ix_soil_records_farm_sampled_at')
        batch_op.drop_index(batch_op.f('ix_soil_records_farm_id'))

    op.drop_table('soil_records')
    with op.batch_alter_table('model_versions', schema=None) as batch_op:
        batch_op.drop_index('ix_model_versions_status_deployed_at')
        batch_op.drop_index(batch_op.f('ix_model_versions_name'))
        batch_op.drop_index(batch_op.f('ix_model_versions_dataset_version_id'))

    op.drop_table('model_versions')
    with op.batch_alter_table('generated_reports', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_generated_reports_user_id'))
        batch_op.drop_index(batch_op.f('ix_generated_reports_report_type'))
        batch_op.drop_index('ix_generated_reports_farm_period')
        batch_op.drop_index(batch_op.f('ix_generated_reports_farm_id'))
        batch_op.drop_index(batch_op.f('ix_generated_reports_client_id'))

    op.drop_table('generated_reports')
    with op.batch_alter_table('equipment', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_equipment_id'))
        batch_op.drop_index('ix_equipment_farm_type_status')

    op.drop_table('equipment')
    with op.batch_alter_table('alert_policies', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_alert_policies_id'))
        batch_op.drop_index(batch_op.f('ix_alert_policies_farm_id'))
        batch_op.drop_index(batch_op.f('ix_alert_policies_client_id'))
        batch_op.drop_index('ix_alert_policies_client_farm_active')

    op.drop_table('alert_policies')
    op.drop_table('user_roles')
    with op.batch_alter_table('user_permissions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_permissions_user_id'))
        batch_op.drop_index(batch_op.f('ix_user_permissions_permission_id'))
        batch_op.drop_index(batch_op.f('ix_user_permissions_id'))

    op.drop_table('user_permissions')
    op.drop_table('user_clients')
    with op.batch_alter_table('system_settings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_system_settings_updated_by_user_id'))
        batch_op.drop_index(batch_op.f('ix_system_settings_key'))

    op.drop_table('system_settings')
    op.drop_table('role_permissions')
    with op.batch_alter_table('farms', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_farms_state'))
        batch_op.drop_index(batch_op.f('ix_farms_municipality'))
        batch_op.drop_index(batch_op.f('ix_farms_id'))
        batch_op.drop_index('ix_farms_client_state_municipality')
        batch_op.drop_index(batch_op.f('ix_farms_client_id'))

    op.drop_table('farms')
    with op.batch_alter_table('dataset_versions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_dataset_versions_name'))
        batch_op.drop_index(batch_op.f('ix_dataset_versions_created_by_user_id'))
        batch_op.drop_index(batch_op.f('ix_dataset_versions_checksum'))

    op.drop_table('dataset_versions')
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_audit_logs_user_id'))
        batch_op.drop_index(batch_op.f('ix_audit_logs_request_id'))
        batch_op.drop_index(batch_op.f('ix_audit_logs_id'))
        batch_op.drop_index(batch_op.f('ix_audit_logs_entity_type'))
        batch_op.drop_index(batch_op.f('ix_audit_logs_entity_id'))
        batch_op.drop_index('ix_audit_logs_entity_created_at')

    op.drop_table('audit_logs')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_username'))
        batch_op.drop_index(batch_op.f('ix_users_id'))
        batch_op.drop_index(batch_op.f('ix_users_email'))

    op.drop_table('users')
    with op.batch_alter_table('user_accounts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_accounts_username'))
        batch_op.drop_index(batch_op.f('ix_user_accounts_id'))

    op.drop_table('user_accounts')
    with op.batch_alter_table('route_recommendations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_route_recommendations_id'))

    op.drop_table('route_recommendations')
    with op.batch_alter_table('roles', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_roles_name'))
        batch_op.drop_index(batch_op.f('ix_roles_id'))

    op.drop_table('roles')
    with op.batch_alter_table('prediction_records', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_prediction_records_id'))

    op.drop_table('prediction_records')
    with op.batch_alter_table('permissions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_permissions_id'))
        batch_op.drop_index(batch_op.f('ix_permissions_code'))

    op.drop_table('permissions')
    with op.batch_alter_table('data_sources', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_data_sources_source_type'))
        batch_op.drop_index(batch_op.f('ix_data_sources_name'))

    op.drop_table('data_sources')
    with op.batch_alter_table('clients', schema=None) as batch_op:
        batch_op.drop_index('ix_clients_status_region')
        batch_op.drop_index(batch_op.f('ix_clients_region'))
        batch_op.drop_index(batch_op.f('ix_clients_name'))
        batch_op.drop_index(batch_op.f('ix_clients_email'))

    op.drop_table('clients')
    with op.batch_alter_table('access_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_access_events_id'))

    op.drop_table('access_events')
    # ### end Alembic commands ###


def downgrade() -> None:
    """Allow rollback only for an empty database created by this revision.

    A legacy database is upgraded additively and must be restored from backup
    rather than dropped back to a schema that would lose historical columns.
    """
    bind = op.get_bind()
    if _has_table(bind, "system_settings"):
        legacy_marker = bind.execute(
            sa.text("SELECT 1 FROM system_settings WHERE key = :key"),
            {"key": LEGACY_MARKER_KEY},
        ).first()
        if legacy_marker:
            raise RuntimeError(
                "Refusing destructive downgrade of a legacy AgroGuardian database. Restore a backup instead."
            )

    inspector = sa.inspect(bind)
    for table_name in inspector.get_table_names():
        if table_name == "alembic_version":
            continue
        if bind.execute(sa.text(f"SELECT 1 FROM {table_name} LIMIT 1")).first():
            raise RuntimeError(
                "Downgrade is only safe for an empty database. Restore a backup for databases with data."
            )
    _downgrade_fresh_schema()
