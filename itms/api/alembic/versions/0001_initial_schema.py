"""Базовая схема: справочник, CMDB, документы, аудит, поиск, импорт

Revision ID: cae27c4f272a
Revises: 
Create Date: 2026-09-22 09:55:34.789959+00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENUMS: dict[str, tuple[str, ...]] = {
    "ci_type": ("LOCATION", "RACK", "DEVICE", "VM", "CLUSTER", "APPLICATION", "DATABASE",
                "SERVICE", "STORAGE", "POWER_NODE", "DOMAIN", "CERTIFICATE", "CIRCUIT", "OTHER"),
    "ci_status": ("PLANNED", "ORDERED", "IN_STOCK", "ACTIVE", "DEGRADED", "MAINTENANCE",
                  "RESERVED", "DECOMMISSIONING", "RETIRED"),
    "criticality": ("LOW", "MEDIUM", "HIGH", "CRITICAL"),
    "environment": ("PROD", "TEST", "DEV", "DR"),
    "location_type": ("ORG", "SITE", "BUILDING", "FLOOR", "ROOM", "ZONE"),
    # Значения POWERED_BY здесь нет намеренно: электрика описывается только
    # моделью питания (power_node + power_link), чтобы не было двух источников истины.
    "relation_type": ("DEPENDS_ON", "RUNS_ON", "MEMBER_OF", "PART_OF", "CONNECTED_TO",
                      "USES_STORAGE", "BACKED_UP_BY", "REPLICATES_TO", "MANAGES", "SERVES",
                      "RELATES_TO"),
    "document_status": ("DRAFT", "IN_REVIEW", "APPROVED", "OBSOLETE", "ARCHIVED"),
    "document_kind": ("INSTRUCTION", "REGULATION", "SCHEME", "PASSPORT", "CONTRACT", "ACT",
                      "RUNBOOK", "NOTE", "OTHER"),
    "employee_status": ("ACTIVE", "VACATION", "SICK_LEAVE", "DISMISSED"),
    "support_line": ("FIRST", "SECOND", "THIRD", "NONE"),
    "user_role": ("OWNER", "ENGINEER", "OPERATOR", "VIEWER"),
    "user_status": ("ACTIVE", "DISABLED", "INVITED"),
    "audit_action": ("CREATE", "UPDATE", "DELETE", "ARCHIVE", "RESTORE", "LINK", "UNLINK",
                     "STATUS", "APPLY", "LOGIN", "LOGIN_FAILED", "LOGOUT", "IMPORT", "EXPORT"),
    "import_status": ("DRAFT", "VALIDATED", "APPLIED", "FAILED"),
    "import_target": ("CI", "LOCATION", "EMPLOYEE"),
    "custom_field_type": ("TEXT", "NUMBER", "BOOLEAN", "DATE", "SELECT", "MULTISELECT", "URL"),
}


def _create_prerequisites() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    for name, values in ENUMS.items():
        rendered = ", ".join(f"'{value}'" for value in values)
        op.execute(f"CREATE TYPE {name} AS ENUM ({rendered})")


def _install_audit_immutability() -> None:
    """Аудит неизменяем: запись можно только добавить.

    Правило живёт в базе, а не в приложении: иначе «неизменяемость» держится
    исключительно на добросовестности кода.
    """
    op.execute(
        """
        CREATE OR REPLACE FUNCTION itms_audit_immutable() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Журнал аудита неизменяем: операция % запрещена', TG_OP
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table in ("audit_log", "audit_change"):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_immutable
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION itms_audit_immutable();
            """
        )




def upgrade() -> None:
    _create_prerequisites()
    op.create_table('custom_field_def',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('entity_type', sa.String(length=64), nullable=False),
    sa.Column('ci_type', postgresql.ENUM('LOCATION', 'RACK', 'DEVICE', 'VM', 'CLUSTER', 'APPLICATION', 'DATABASE', 'SERVICE', 'STORAGE', 'POWER_NODE', 'DOMAIN', 'CERTIFICATE', 'CIRCUIT', 'OTHER', name='ci_type', create_type=False), nullable=True),
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('label', sa.String(length=255), nullable=False),
    sa.Column('field_type', postgresql.ENUM('TEXT', 'NUMBER', 'BOOLEAN', 'DATE', 'SELECT', 'MULTISELECT', 'URL', name='custom_field_type', create_type=False), nullable=False),
    sa.Column('options', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('is_required', sa.Boolean(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('help_text', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['user_account.id'], name='fk_custom_field_def_created_by_user_account', ondelete='SET NULL', use_alter=True),
    sa.ForeignKeyConstraint(['updated_by'], ['user_account.id'], name='fk_custom_field_def_updated_by_user_account', ondelete='SET NULL', use_alter=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_custom_field_def')),
    sa.UniqueConstraint('entity_type', 'key', name=op.f('uq_custom_field_def_entity_type_key'))
    )
    op.create_table('document_folder',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('parent_id', sa.UUID(), nullable=True),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('path', sa.Text(), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['user_account.id'], name='fk_document_folder_created_by_user_account', ondelete='SET NULL', use_alter=True),
    sa.ForeignKeyConstraint(['parent_id'], ['document_folder.id'], name=op.f('fk_document_folder_parent_id_document_folder'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by'], ['user_account.id'], name='fk_document_folder_updated_by_user_account', ondelete='SET NULL', use_alter=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_document_folder')),
    sa.UniqueConstraint('parent_id', 'name', name=op.f('uq_document_folder_parent_id_name'))
    )
    op.create_table('organization',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('full_name', sa.String(length=500), nullable=True),
    sa.Column('inn', sa.String(length=20), nullable=True),
    sa.Column('address', sa.Text(), nullable=True),
    sa.Column('timezone', sa.String(length=64), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['user_account.id'], name='fk_organization_created_by_user_account', ondelete='SET NULL', use_alter=True),
    sa.ForeignKeyConstraint(['updated_by'], ['user_account.id'], name='fk_organization_updated_by_user_account', ondelete='SET NULL', use_alter=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_organization')),
    sa.UniqueConstraint('name', name=op.f('uq_organization_name'))
    )
    op.create_table('outbox_event',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('event_type', sa.String(length=64), nullable=False),
    sa.Column('entity_type', sa.String(length=64), nullable=False),
    sa.Column('entity_id', sa.UUID(), nullable=True),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_outbox_event'))
    )
    op.create_index('ix_outbox_pending', 'outbox_event', ['created_at'], unique=False, postgresql_where=sa.text('processed_at IS NULL'))
    op.create_table('responsibility_area',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('code', sa.String(length=50), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('color', sa.String(length=16), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['user_account.id'], name='fk_responsibility_area_created_by_user_account', ondelete='SET NULL', use_alter=True),
    sa.ForeignKeyConstraint(['updated_by'], ['user_account.id'], name='fk_responsibility_area_updated_by_user_account', ondelete='SET NULL', use_alter=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_responsibility_area')),
    sa.UniqueConstraint('code', name=op.f('uq_responsibility_area_code')),
    sa.UniqueConstraint('name', name=op.f('uq_responsibility_area_name'))
    )
    op.create_table('search_index',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('entity_type', sa.String(length=64), nullable=False),
    sa.Column('entity_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('subtitle', sa.Text(), nullable=True),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('keywords', sa.Text(), nullable=True),
    sa.Column('tsv', postgresql.TSVECTOR(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_search_index')),
    sa.UniqueConstraint('entity_type', 'entity_id', name=op.f('uq_search_index_entity_type_entity_id'))
    )
    op.create_index('ix_search_index_title_trgm', 'search_index', ['title'], unique=False, postgresql_using='gin', postgresql_ops={'title': 'gin_trgm_ops'})
    op.create_index('ix_search_index_tsv', 'search_index', ['tsv'], unique=False, postgresql_using='gin')
    op.create_table('tag',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('color', sa.String(length=16), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['user_account.id'], name='fk_tag_created_by_user_account', ondelete='SET NULL', use_alter=True),
    sa.ForeignKeyConstraint(['updated_by'], ['user_account.id'], name='fk_tag_updated_by_user_account', ondelete='SET NULL', use_alter=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_tag')),
    sa.UniqueConstraint('name', name=op.f('uq_tag_name'))
    )
    op.create_table('custom_field_value',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('field_id', sa.UUID(), nullable=False),
    sa.Column('entity_id', sa.UUID(), nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['field_id'], ['custom_field_def.id'], name=op.f('fk_custom_field_value_field_id_custom_field_def'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_custom_field_value')),
    sa.UniqueConstraint('field_id', 'entity_id', name=op.f('uq_custom_field_value_field_id_entity_id'))
    )
    op.create_table('department',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('parent_id', sa.UUID(), nullable=True),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('code', sa.String(length=50), nullable=True),
    sa.Column('head_employee_id', sa.UUID(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['user_account.id'], name='fk_department_created_by_user_account', ondelete='SET NULL', use_alter=True),
    sa.ForeignKeyConstraint(['head_employee_id'], ['employee.id'], name='fk_department_head_employee_employee', ondelete='SET NULL', use_alter=True),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], name=op.f('fk_department_organization_id_organization'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['parent_id'], ['department.id'], name=op.f('fk_department_parent_id_department'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by'], ['user_account.id'], name='fk_department_updated_by_user_account', ondelete='SET NULL', use_alter=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_department')),
    sa.UniqueConstraint('organization_id', 'name', name=op.f('uq_department_organization_id_name'))
    )
    op.create_table('employee',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('department_id', sa.UUID(), nullable=True),
    sa.Column('full_name', sa.String(length=255), nullable=False),
    sa.Column('position', sa.String(length=255), nullable=True),
    sa.Column('email', sa.String(length=320), nullable=True),
    sa.Column('phone', sa.String(length=50), nullable=True),
    sa.Column('telegram', sa.String(length=100), nullable=True),
    sa.Column('support_line', postgresql.ENUM('FIRST', 'SECOND', 'THIRD', 'NONE', name='support_line', create_type=False), nullable=False),
    sa.Column('status', postgresql.ENUM('ACTIVE', 'VACATION', 'SICK_LEAVE', 'DISMISSED', name='employee_status', create_type=False), nullable=False),
    sa.Column('hired_on', sa.Date(), nullable=True),
    sa.Column('dismissed_on', sa.Date(), nullable=True),
    sa.Column('weekly_hours', sa.Integer(), server_default=sa.text('40'), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['user_account.id'], name='fk_employee_created_by_user_account', ondelete='SET NULL', use_alter=True),
    sa.ForeignKeyConstraint(['department_id'], ['department.id'], name=op.f('fk_employee_department_id_department'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], name=op.f('fk_employee_organization_id_organization'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['updated_by'], ['user_account.id'], name='fk_employee_updated_by_user_account', ondelete='SET NULL', use_alter=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_employee'))
    )
    op.create_index('ix_employee_full_name', 'employee', ['full_name'], unique=False)
    op.create_index('ix_employee_status', 'employee', ['status'], unique=False)
    op.create_table('document',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('folder_id', sa.UUID(), nullable=True),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('kind', postgresql.ENUM('INSTRUCTION', 'REGULATION', 'SCHEME', 'PASSPORT', 'CONTRACT', 'ACT', 'RUNBOOK', 'NOTE', 'OTHER', name='document_kind', create_type=False), nullable=False),
    sa.Column('status', postgresql.ENUM('DRAFT', 'IN_REVIEW', 'APPROVED', 'OBSOLETE', 'ARCHIVED', name='document_status', create_type=False), nullable=False),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('owner_employee_id', sa.UUID(), nullable=True),
    sa.Column('current_version', sa.Integer(), nullable=False),
    sa.Column('reviewed_on', sa.Date(), nullable=True),
    sa.Column('review_due_on', sa.Date(), nullable=True),
    sa.Column('review_period_days', sa.Integer(), nullable=True),
    sa.Column('search_tsv', postgresql.TSVECTOR(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['user_account.id'], name='fk_document_created_by_user_account', ondelete='SET NULL', use_alter=True),
    sa.ForeignKeyConstraint(['folder_id'], ['document_folder.id'], name=op.f('fk_document_folder_id_document_folder'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['owner_employee_id'], ['employee.id'], name=op.f('fk_document_owner_employee_id_employee'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by'], ['user_account.id'], name='fk_document_updated_by_user_account', ondelete='SET NULL', use_alter=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_document'))
    )
    op.create_index('ix_document_review', 'document', ['review_due_on'], unique=False)
    op.create_index('ix_document_search', 'document', ['search_tsv'], unique=False, postgresql_using='gin')
    op.create_index('ix_document_status', 'document', ['status'], unique=False)
    op.create_table('employee_responsibility',
    sa.Column('employee_id', sa.UUID(), nullable=False),
    sa.Column('area_id', sa.UUID(), nullable=False),
    sa.Column('is_primary', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['area_id'], ['responsibility_area.id'], name=op.f('fk_employee_responsibility_area_id_responsibility_area'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['employee_id'], ['employee.id'], name=op.f('fk_employee_responsibility_employee_id_employee'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('employee_id', 'area_id', name=op.f('pk_employee_responsibility'))
    )
    op.create_table('location',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('parent_id', sa.UUID(), nullable=True),
    sa.Column('location_type', postgresql.ENUM('ORG', 'SITE', 'BUILDING', 'FLOOR', 'ROOM', 'ZONE', name='location_type', create_type=False), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('code', sa.String(length=50), nullable=True),
    sa.Column('path', sa.Text(), nullable=False),
    sa.Column('depth', sa.Integer(), nullable=False),
    sa.Column('address', sa.Text(), nullable=True),
    sa.Column('area_m2', sa.Numeric(precision=8, scale=2), nullable=True),
    sa.Column('responsible_employee_id', sa.UUID(), nullable=True),
    sa.Column('attributes', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['user_account.id'], name='fk_location_created_by_user_account', ondelete='SET NULL', use_alter=True),
    sa.ForeignKeyConstraint(['parent_id'], ['location.id'], name=op.f('fk_location_parent_id_location'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['responsible_employee_id'], ['employee.id'], name=op.f('fk_location_responsible_employee_id_employee'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by'], ['user_account.id'], name='fk_location_updated_by_user_account', ondelete='SET NULL', use_alter=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_location')),
    sa.UniqueConstraint('parent_id', 'name', name=op.f('uq_location_parent_id_name'))
    )
    op.create_index('ix_location_path', 'location', ['path'], unique=False)
    op.create_index('ix_location_type', 'location', ['location_type'], unique=False)
    op.create_table('user_account',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('employee_id', sa.UUID(), nullable=True),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('display_name', sa.String(length=255), nullable=False),
    sa.Column('password_hash', sa.String(length=512), nullable=True),
    sa.Column('role', postgresql.ENUM('OWNER', 'ENGINEER', 'OPERATOR', 'VIEWER', name='user_role', create_type=False), nullable=False),
    sa.Column('status', postgresql.ENUM('ACTIVE', 'DISABLED', 'INVITED', name='user_status', create_type=False), nullable=False),
    sa.Column('locale', sa.String(length=8), nullable=False),
    sa.Column('theme', sa.String(length=16), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('failed_login_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['employee_id'], ['employee.id'], name=op.f('fk_user_account_employee_id_employee'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_account')),
    sa.UniqueConstraint('email', name=op.f('uq_user_account_email')),
    sa.UniqueConstraint('employee_id', name=op.f('uq_user_account_employee_id'))
    )
    op.create_table('app_setting',
    sa.Column('key', sa.String(length=128), nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['updated_by'], ['user_account.id'], name=op.f('fk_app_setting_updated_by_user_account'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('key', name=op.f('pk_app_setting'))
    )
    op.create_table('audit_log',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('actor_id', sa.UUID(), nullable=True),
    sa.Column('actor_kind', sa.String(length=16), nullable=False),
    sa.Column('actor_label', sa.String(length=255), nullable=True),
    sa.Column('request_id', sa.String(length=64), nullable=True),
    sa.Column('entity_type', sa.String(length=64), nullable=False),
    sa.Column('entity_id', sa.UUID(), nullable=True),
    sa.Column('entity_label', sa.String(length=500), nullable=True),
    sa.Column('action', postgresql.ENUM('CREATE', 'UPDATE', 'DELETE', 'ARCHIVE', 'RESTORE', 'LINK', 'UNLINK', 'STATUS', 'APPLY', 'LOGIN', 'LOGIN_FAILED', 'LOGOUT', 'IMPORT', 'EXPORT', name='audit_action', create_type=False), nullable=False),
    sa.Column('change_id', sa.UUID(), nullable=True),
    sa.Column('project_id', sa.UUID(), nullable=True),
    sa.Column('task_id', sa.UUID(), nullable=True),
    sa.Column('document_id', sa.UUID(), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('ip', sa.String(length=64), nullable=True),
    sa.Column('context', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['user_account.id'], name=op.f('fk_audit_log_actor_id_user_account'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_log'))
    )
    op.create_index('ix_audit_log_actor', 'audit_log', ['actor_id'], unique=False)
    op.create_index('ix_audit_log_change', 'audit_log', ['change_id'], unique=False, postgresql_where=sa.text('change_id IS NOT NULL'))
    op.create_index('ix_audit_log_entity', 'audit_log', ['entity_type', 'entity_id', 'occurred_at'], unique=False)
    op.create_index('ix_audit_log_occurred', 'audit_log', ['occurred_at'], unique=False)
    op.create_index('ix_audit_log_project', 'audit_log', ['project_id'], unique=False, postgresql_where=sa.text('project_id IS NOT NULL'))
    op.create_table('ci',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('ci_type', postgresql.ENUM('LOCATION', 'RACK', 'DEVICE', 'VM', 'CLUSTER', 'APPLICATION', 'DATABASE', 'SERVICE', 'STORAGE', 'POWER_NODE', 'DOMAIN', 'CERTIFICATE', 'CIRCUIT', 'OTHER', name='ci_type', create_type=False), nullable=False),
    sa.Column('code', sa.String(length=64), nullable=True),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('status', postgresql.ENUM('PLANNED', 'ORDERED', 'IN_STOCK', 'ACTIVE', 'DEGRADED', 'MAINTENANCE', 'RESERVED', 'DECOMMISSIONING', 'RETIRED', name='ci_status', create_type=False), nullable=False),
    sa.Column('criticality', postgresql.ENUM('LOW', 'MEDIUM', 'HIGH', 'CRITICAL', name='criticality', create_type=False), nullable=False),
    sa.Column('environment', postgresql.ENUM('PROD', 'TEST', 'DEV', 'DR', name='environment', create_type=False), nullable=False),
    sa.Column('location_id', sa.UUID(), nullable=True),
    sa.Column('owner_employee_id', sa.UUID(), nullable=True),
    sa.Column('vendor', sa.String(length=128), nullable=True),
    sa.Column('model', sa.String(length=128), nullable=True),
    sa.Column('serial_number', sa.String(length=128), nullable=True),
    sa.Column('inventory_number', sa.String(length=64), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('attributes', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('valid_from', sa.Date(), nullable=True),
    sa.Column('valid_to', sa.Date(), nullable=True),
    sa.Column('search_tsv', postgresql.TSVECTOR(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('version', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['user_account.id'], name='fk_ci_created_by_user_account', ondelete='SET NULL', use_alter=True),
    sa.ForeignKeyConstraint(['location_id'], ['location.id'], name=op.f('fk_ci_location_id_location'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['owner_employee_id'], ['employee.id'], name=op.f('fk_ci_owner_employee_id_employee'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by'], ['user_account.id'], name='fk_ci_updated_by_user_account', ondelete='SET NULL', use_alter=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ci')),
    sa.UniqueConstraint('code', name=op.f('uq_ci_code'))
    )
    op.create_index('ix_ci_attributes', 'ci', ['attributes'], unique=False, postgresql_using='gin')
    op.create_index('ix_ci_location', 'ci', ['location_id'], unique=False)
    op.create_index('ix_ci_name', 'ci', ['name'], unique=False)
    op.create_index('ix_ci_owner', 'ci', ['owner_employee_id'], unique=False)
    op.create_index('ix_ci_search', 'ci', ['search_tsv'], unique=False, postgresql_using='gin')
    op.create_index('ix_ci_type_status', 'ci', ['ci_type', 'status'], unique=False)
    op.create_table('document_link',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('entity_type', sa.String(length=64), nullable=False),
    sa.Column('entity_id', sa.UUID(), nullable=False),
    sa.Column('relation', sa.String(length=64), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['user_account.id'], name=op.f('fk_document_link_created_by_user_account'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['document_id'], ['document.id'], name=op.f('fk_document_link_document_id_document'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_document_link')),
    sa.UniqueConstraint('document_id', 'entity_type', 'entity_id', name=op.f('uq_document_link_document_id_entity_type_entity_id'))
    )
    op.create_index('ix_document_link_entity', 'document_link', ['entity_type', 'entity_id'], unique=False)
    op.create_table('file_object',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('storage_key', sa.String(length=512), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('content_type', sa.String(length=255), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('uploaded_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['uploaded_by'], ['user_account.id'], name=op.f('fk_file_object_uploaded_by_user_account'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_file_object')),
    sa.UniqueConstraint('storage_key', name=op.f('uq_file_object_storage_key'))
    )
    op.create_index('ix_file_object_sha256', 'file_object', ['sha256'], unique=False)
    op.create_table('user_session',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('csrf_token', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ip', sa.String(length=64), nullable=True),
    sa.Column('user_agent', sa.String(length=512), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user_account.id'], name=op.f('fk_user_session_user_id_user_account'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_session')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_user_session_token_hash'))
    )
    op.create_index('ix_user_session_user', 'user_session', ['user_id'], unique=False)
    op.create_table('attachment',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('file_id', sa.UUID(), nullable=False),
    sa.Column('entity_type', sa.String(length=64), nullable=False),
    sa.Column('entity_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['user_account.id'], name=op.f('fk_attachment_created_by_user_account'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['file_id'], ['file_object.id'], name=op.f('fk_attachment_file_id_file_object'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_attachment'))
    )
    op.create_index('ix_attachment_entity', 'attachment', ['entity_type', 'entity_id'], unique=False)
    op.create_table('audit_change',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('audit_log_id', sa.UUID(), nullable=False),
    sa.Column('field', sa.String(length=128), nullable=False),
    sa.Column('old_value', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('new_value', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.ForeignKeyConstraint(['audit_log_id'], ['audit_log.id'], name=op.f('fk_audit_change_audit_log_id_audit_log'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_change'))
    )
    op.create_index('ix_audit_change_field', 'audit_change', ['field'], unique=False)
    op.create_table('ci_relation',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('source_ci_id', sa.UUID(), nullable=False),
    sa.Column('target_ci_id', sa.UUID(), nullable=False),
    sa.Column('rel_type', postgresql.ENUM('DEPENDS_ON', 'RUNS_ON', 'MEMBER_OF', 'PART_OF', 'CONNECTED_TO', 'USES_STORAGE', 'BACKED_UP_BY', 'REPLICATES_TO', 'MANAGES', 'SERVES', 'RELATES_TO', name='relation_type', create_type=False), nullable=False),
    sa.Column('criticality', postgresql.ENUM('LOW', 'MEDIUM', 'HIGH', 'CRITICAL', name='criticality', create_type=False), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('attributes', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('valid_from', sa.Date(), nullable=True),
    sa.Column('valid_to', sa.Date(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.CheckConstraint('source_ci_id <> target_ci_id', name=op.f('ck_ci_relation_no_self_relation')),
    sa.ForeignKeyConstraint(['created_by'], ['user_account.id'], name='fk_ci_relation_created_by_user_account', ondelete='SET NULL', use_alter=True),
    sa.ForeignKeyConstraint(['source_ci_id'], ['ci.id'], name=op.f('fk_ci_relation_source_ci_id_ci'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['target_ci_id'], ['ci.id'], name=op.f('fk_ci_relation_target_ci_id_ci'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['updated_by'], ['user_account.id'], name='fk_ci_relation_updated_by_user_account', ondelete='SET NULL', use_alter=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ci_relation')),
    sa.UniqueConstraint('source_ci_id', 'target_ci_id', 'rel_type', name=op.f('uq_ci_relation_source_ci_id_target_ci_id_rel_type'))
    )
    op.create_index('ix_ci_relation_source', 'ci_relation', ['source_ci_id'], unique=False)
    op.create_index('ix_ci_relation_target', 'ci_relation', ['target_ci_id'], unique=False)
    op.create_table('ci_tag',
    sa.Column('ci_id', sa.UUID(), nullable=False),
    sa.Column('tag_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['ci_id'], ['ci.id'], name=op.f('fk_ci_tag_ci_id_ci'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tag_id'], ['tag.id'], name=op.f('fk_ci_tag_tag_id_tag'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('ci_id', 'tag_id', name=op.f('pk_ci_tag'))
    )
    op.create_table('document_version',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('content_format', sa.String(length=16), nullable=False),
    sa.Column('file_id', sa.UUID(), nullable=True),
    sa.Column('change_note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('is_current', sa.Boolean(), nullable=False),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['user_account.id'], name=op.f('fk_document_version_created_by_user_account'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['document_id'], ['document.id'], name=op.f('fk_document_version_document_id_document'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['file_id'], ['file_object.id'], name=op.f('fk_document_version_file_id_file_object'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_document_version')),
    sa.UniqueConstraint('document_id', 'version', name=op.f('uq_document_version_document_id_version'))
    )
    op.create_table('import_job',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('target', postgresql.ENUM('CI', 'LOCATION', 'EMPLOYEE', name='import_target', create_type=False), nullable=False),
    sa.Column('status', postgresql.ENUM('DRAFT', 'VALIDATED', 'APPLIED', 'FAILED', name='import_status', create_type=False), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('file_id', sa.UUID(), nullable=True),
    sa.Column('mapping', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('options', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('columns', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('rows_total', sa.Integer(), nullable=False),
    sa.Column('rows_valid', sa.Integer(), nullable=False),
    sa.Column('rows_invalid', sa.Integer(), nullable=False),
    sa.Column('rows_created', sa.Integer(), nullable=False),
    sa.Column('rows_updated', sa.Integer(), nullable=False),
    sa.Column('errors', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('preview', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('applied_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['user_account.id'], name=op.f('fk_import_job_created_by_user_account'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['file_id'], ['file_object.id'], name=op.f('fk_import_job_file_id_file_object'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_import_job'))
    )
    # ### end Alembic commands ###
    _install_audit_immutability()


def downgrade() -> None:
    op.drop_table('import_job')
    op.drop_table('document_version')
    op.drop_table('ci_tag')
    op.drop_index('ix_ci_relation_target', table_name='ci_relation')
    op.drop_index('ix_ci_relation_source', table_name='ci_relation')
    op.drop_table('ci_relation')
    op.drop_index('ix_audit_change_field', table_name='audit_change')
    op.drop_table('audit_change')
    op.drop_index('ix_attachment_entity', table_name='attachment')
    op.drop_table('attachment')
    op.drop_index('ix_user_session_user', table_name='user_session')
    op.drop_table('user_session')
    op.drop_index('ix_file_object_sha256', table_name='file_object')
    op.drop_table('file_object')
    op.drop_index('ix_document_link_entity', table_name='document_link')
    op.drop_table('document_link')
    op.drop_index('ix_ci_type_status', table_name='ci')
    op.drop_index('ix_ci_search', table_name='ci', postgresql_using='gin')
    op.drop_index('ix_ci_owner', table_name='ci')
    op.drop_index('ix_ci_name', table_name='ci')
    op.drop_index('ix_ci_location', table_name='ci')
    op.drop_index('ix_ci_attributes', table_name='ci', postgresql_using='gin')
    op.drop_table('ci')
    op.drop_index('ix_audit_log_project', table_name='audit_log', postgresql_where=sa.text('project_id IS NOT NULL'))
    op.drop_index('ix_audit_log_occurred', table_name='audit_log')
    op.drop_index('ix_audit_log_entity', table_name='audit_log')
    op.drop_index('ix_audit_log_change', table_name='audit_log', postgresql_where=sa.text('change_id IS NOT NULL'))
    op.drop_index('ix_audit_log_actor', table_name='audit_log')
    op.drop_table('audit_log')
    op.drop_table('app_setting')
    op.drop_table('user_account')
    op.drop_index('ix_location_type', table_name='location')
    op.drop_index('ix_location_path', table_name='location')
    op.drop_table('location')
    op.drop_table('employee_responsibility')
    op.drop_index('ix_document_status', table_name='document')
    op.drop_index('ix_document_search', table_name='document', postgresql_using='gin')
    op.drop_index('ix_document_review', table_name='document')
    op.drop_table('document')
    op.drop_index('ix_employee_status', table_name='employee')
    op.drop_index('ix_employee_full_name', table_name='employee')
    op.drop_table('employee')
    op.drop_table('department')
    op.drop_table('custom_field_value')
    op.drop_table('tag')
    op.drop_index('ix_search_index_tsv', table_name='search_index', postgresql_using='gin')
    op.drop_index('ix_search_index_title_trgm', table_name='search_index', postgresql_using='gin', postgresql_ops={'title': 'gin_trgm_ops'})
    op.drop_table('search_index')
    op.drop_table('responsibility_area')
    op.drop_index('ix_outbox_pending', table_name='outbox_event', postgresql_where=sa.text('processed_at IS NULL'))
    op.drop_table('outbox_event')
    op.drop_table('organization')
    op.drop_table('document_folder')
    op.drop_table('custom_field_def')
    op.execute("DROP TRIGGER IF EXISTS trg_audit_change_immutable ON audit_change")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_log_immutable ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS itms_audit_immutable()")
    for name in ENUMS:
        op.execute(f"DROP TYPE IF EXISTS {name}")
