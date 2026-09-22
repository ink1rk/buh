"""Сетевой слой: каталог оборудования, устройства, интерфейсы, кабели, адресация

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-22 12:30:00.000000+00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENUMS: dict[str, tuple[str, ...]] = {
    "device_role": ("SERVER", "ROUTER", "L3_SWITCH", "L2_SWITCH", "FIREWALL", "ACCESS_POINT",
                    "WLC", "MODEM", "PATCH_PANEL", "WALL_OUTLET", "STORAGE", "KVM", "UPS",
                    "PDU", "PRINTER", "OTHER"),
    "interface_type": ("RJ45", "SFP", "SFP_PLUS", "SFP28", "QSFP_PLUS", "QSFP28", "LC", "SC",
                       "CONSOLE", "USB", "WIRELESS", "VIRTUAL", "LAG", "VLAN_IF", "OTHER"),
    "cable_medium": ("COPPER", "FIBER", "COAX", "WIRELESS", "OTHER"),
    "cable_category": ("CAT5E", "CAT6", "CAT6A", "CAT7", "OM3", "OM4", "OM5", "OS2", "OTHER"),
    "connection_status": ("PLANNED", "RESERVED", "ACTIVE", "FAULTY", "DECOMMISSIONED"),
    "panel_side": ("FRONT", "REAR"),
    "vlan_mode": ("ACCESS", "TAGGED", "NATIVE"),
    "ip_status": ("ACTIVE", "RESERVED", "DHCP", "DEPRECATED"),
    "ip_role": ("PRIMARY", "SECONDARY", "MANAGEMENT", "VIP", "GATEWAY", "OTHER"),
}

DEVICE_ROLE = postgresql.ENUM(*ENUMS["device_role"], name="device_role", create_type=False)
INTERFACE_TYPE = postgresql.ENUM(
    *ENUMS["interface_type"], name="interface_type", create_type=False
)
CABLE_MEDIUM = postgresql.ENUM(*ENUMS["cable_medium"], name="cable_medium", create_type=False)
CABLE_CATEGORY = postgresql.ENUM(
    *ENUMS["cable_category"], name="cable_category", create_type=False
)
CONNECTION_STATUS = postgresql.ENUM(
    *ENUMS["connection_status"], name="connection_status", create_type=False
)
PANEL_SIDE = postgresql.ENUM(*ENUMS["panel_side"], name="panel_side", create_type=False)
VLAN_MODE = postgresql.ENUM(*ENUMS["vlan_mode"], name="vlan_mode", create_type=False)
IP_STATUS = postgresql.ENUM(*ENUMS["ip_status"], name="ip_status", create_type=False)
IP_ROLE = postgresql.ENUM(*ENUMS["ip_role"], name="ip_role", create_type=False)

#: Ссылки created_by/updated_by объявлены в моделях как use_alter: op.create_table их
#: не создаёт, поэтому они добавляются отдельным шагом — вместе с теми, что не доехали
#: из ревизии 0001.
ACTOR_FK_TABLES = (
    "manufacturer", "device_model", "port_template", "device", "interface",
    "cable_route", "connection", "vrf", "vlan", "prefix", "ip_address",
    "ci", "ci_relation", "custom_field_def", "department", "document",
    "document_folder", "employee", "location", "organization",
    "responsibility_area", "tag",
)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'),
                  nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'),
                  nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('updated_by', sa.UUID(), nullable=True),
    ]


def upgrade() -> None:
    for name, values in ENUMS.items():
        rendered = ", ".join(f"'{value}'" for value in values)
        op.execute(f"CREATE TYPE {name} AS ENUM ({rendered})")

    op.create_table(
        'manufacturer',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('support_url', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_manufacturer')),
        sa.UniqueConstraint('name', name=op.f('uq_manufacturer_name')),
    )

    op.create_table(
        'device_model',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('manufacturer_id', sa.UUID(), nullable=False),
        sa.Column('model', sa.String(length=128), nullable=False),
        sa.Column('part_number', sa.String(length=128), nullable=True),
        sa.Column('default_role', DEVICE_ROLE, nullable=False),
        sa.Column('u_height', sa.Numeric(precision=3, scale=1), nullable=False),
        sa.Column('is_full_depth', sa.Boolean(), nullable=False),
        sa.Column('depth_mm', sa.Integer(), nullable=True),
        sa.Column('weight_kg', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('psu_count', sa.SmallInteger(), nullable=False),
        sa.Column('power_nameplate_w', sa.Integer(), nullable=True),
        sa.Column('power_max_w', sa.Integer(), nullable=True),
        sa.Column('power_factor', sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column('utilization_factor', sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column('airflow', sa.String(length=32), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(['manufacturer_id'], ['manufacturer.id'],
                                name=op.f('fk_device_model_manufacturer_id_manufacturer'),
                                ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_device_model')),
        comment='Каталог моделей: источник габаритов, веса и мощности',
    )
    op.create_index('uq_device_model_key', 'device_model', ['manufacturer_id', 'model'],
                    unique=True)

    op.create_table(
        'port_template',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('device_model_id', sa.UUID(), nullable=False),
        sa.Column('name_pattern', sa.String(length=64), nullable=False),
        sa.Column('count', sa.SmallInteger(), nullable=False),
        sa.Column('start_index', sa.SmallInteger(), nullable=False),
        sa.Column('interface_type', INTERFACE_TYPE, nullable=False),
        sa.Column('speed_mbps', sa.Integer(), nullable=True),
        sa.Column('poe_capable', sa.Boolean(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(['device_model_id'], ['device_model.id'],
                                name=op.f('fk_port_template_device_model_id_device_model'),
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_port_template')),
    )

    op.create_table(
        'device',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('device_model_id', sa.UUID(), nullable=True),
        sa.Column('device_role', DEVICE_ROLE, nullable=False),
        sa.Column('asset_tag', sa.String(length=64), nullable=True),
        sa.Column('hostname', sa.String(length=255), nullable=True),
        sa.Column('mgmt_ip', postgresql.INET(), nullable=True),
        sa.Column('mgmt_mac', postgresql.MACADDR(), nullable=True),
        sa.Column('firmware', sa.String(length=128), nullable=True),
        sa.Column('os_version', sa.String(length=128), nullable=True),
        sa.Column('purchase_date', sa.Date(), nullable=True),
        sa.Column('warranty_until', sa.Date(), nullable=True),
        sa.Column('psu_count', sa.SmallInteger(), nullable=False),
        sa.Column('power_nameplate_w', sa.Integer(), nullable=True),
        sa.Column('power_max_w', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(['device_model_id'], ['device_model.id'],
                                name=op.f('fk_device_device_model_id_device_model'),
                                ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['id'], ['ci.id'], name=op.f('fk_device_id_ci'),
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_device')),
    )
    op.create_index('ix_device_role', 'device', ['device_role'])
    op.create_index('ix_device_mgmt_ip', 'device', ['mgmt_ip'])
    op.create_index('ix_device_hostname_trgm', 'device', ['hostname'], postgresql_using='gin',
                    postgresql_ops={'hostname': 'gin_trgm_ops'})
    op.create_index('uq_device_asset_tag', 'device', [sa.text('lower(asset_tag)')], unique=True,
                    postgresql_where=sa.text('asset_tag IS NOT NULL'))

    op.create_table(
        'interface',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('ci_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('position', sa.Integer(), nullable=True),
        sa.Column('interface_type', INTERFACE_TYPE, nullable=False),
        sa.Column('medium', CABLE_MEDIUM, nullable=True),
        sa.Column('speed_mbps', sa.Integer(), nullable=True),
        sa.Column('duplex', sa.String(length=16), nullable=True),
        sa.Column('mac', postgresql.MACADDR(), nullable=True),
        sa.Column('description', sa.Text(), server_default='', nullable=False),
        sa.Column('purpose', sa.String(length=255), nullable=True),
        sa.Column('admin_enabled', sa.Boolean(), nullable=False),
        sa.Column('oper_status', sa.String(length=16), server_default='UNKNOWN', nullable=False),
        sa.Column('is_management', sa.Boolean(), nullable=False),
        sa.Column('poe_mode', sa.String(length=32), nullable=True),
        sa.Column('mtu', sa.Integer(), nullable=True),
        sa.Column('lag_parent_id', sa.UUID(), nullable=True),
        sa.Column('panel_side', PANEL_SIDE, nullable=True),
        sa.Column('paired_interface_id', sa.UUID(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(['ci_id'], ['ci.id'], name=op.f('fk_interface_ci_id_ci'),
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['lag_parent_id'], ['interface.id'],
                                name=op.f('fk_interface_lag_parent_id_interface'),
                                ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['paired_interface_id'], ['interface.id'],
                                name=op.f('fk_interface_paired_interface_id_interface'),
                                ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_interface')),
        sa.UniqueConstraint('ci_id', 'name', name=op.f('uq_interface_ci_id_name')),
    )
    op.create_index('ix_interface_ci', 'interface', ['ci_id', 'position'])
    op.create_index('ix_interface_mac', 'interface', ['mac'])
    op.create_index('ix_interface_description_trgm', 'interface', ['description'],
                    postgresql_using='gin', postgresql_ops={'description': 'gin_trgm_ops'})

    op.create_table(
        'cable_route',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('route_type', sa.String(length=64), nullable=True),
        sa.Column('from_location_id', sa.UUID(), nullable=True),
        sa.Column('to_location_id', sa.UUID(), nullable=True),
        sa.Column('length_m', sa.Numeric(precision=7, scale=2), nullable=True),
        sa.Column('capacity', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(['from_location_id'], ['location.id'],
                                name=op.f('fk_cable_route_from_location_id_location'),
                                ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['to_location_id'], ['location.id'],
                                name=op.f('fk_cable_route_to_location_id_location'),
                                ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_cable_route')),
        sa.UniqueConstraint('name', name=op.f('uq_cable_route_name')),
    )

    op.create_table(
        'connection',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('label', sa.String(length=64), nullable=True),
        sa.Column('medium', CABLE_MEDIUM, nullable=False),
        sa.Column('category', CABLE_CATEGORY, nullable=True),
        sa.Column('connector_a', sa.String(length=32), nullable=True),
        sa.Column('connector_b', sa.String(length=32), nullable=True),
        sa.Column('a_interface_id', sa.UUID(), nullable=False),
        sa.Column('b_interface_id', sa.UUID(), nullable=False),
        sa.Column('length_m', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('speed_mbps', sa.Integer(), nullable=True),
        sa.Column('color', sa.String(length=32), nullable=True),
        sa.Column('status', CONNECTION_STATUS, nullable=False),
        sa.Column('route_id', sa.UUID(), nullable=True),
        sa.Column('is_redundant', sa.Boolean(), nullable=False),
        sa.Column('redundancy_group', sa.String(length=64), nullable=True),
        sa.Column('installed_on', sa.Date(), nullable=True),
        sa.Column('tested_on', sa.Date(), nullable=True),
        sa.Column('test_result', sa.String(length=64), nullable=True),
        sa.Column('description', sa.Text(), server_default='', nullable=False),
        *_timestamps(),
        sa.CheckConstraint('a_interface_id <> b_interface_id',
                           name=op.f('ck_connection_distinct_ends')),
        sa.ForeignKeyConstraint(['a_interface_id'], ['interface.id'],
                                name=op.f('fk_connection_a_interface_id_interface'),
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['b_interface_id'], ['interface.id'],
                                name=op.f('fk_connection_b_interface_id_interface'),
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['route_id'], ['cable_route.id'],
                                name=op.f('fk_connection_route_id_cable_route'),
                                ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_connection')),
    )
    op.create_index('ix_connection_label_trgm', 'connection', ['label'], postgresql_using='gin',
                    postgresql_ops={'label': 'gin_trgm_ops'})
    # Порт не может быть занят двумя кабелями одновременно — правило держит база.
    op.create_index('uq_connection_a', 'connection', ['a_interface_id'], unique=True,
                    postgresql_where=sa.text("status IN ('ACTIVE','RESERVED')"))
    op.create_index('uq_connection_b', 'connection', ['b_interface_id'], unique=True,
                    postgresql_where=sa.text("status IN ('ACTIVE','RESERVED')"))

    op.create_table(
        'vrf',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('rd', sa.String(length=64), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_vrf')),
        sa.UniqueConstraint('name', name=op.f('uq_vrf_name')),
    )

    op.create_table(
        'vlan',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('vid', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('site_id', sa.UUID(), nullable=True),
        sa.Column('purpose', sa.String(length=128), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint('vid BETWEEN 1 AND 4094', name=op.f('ck_vlan_vid_range')),
        sa.ForeignKeyConstraint(['site_id'], ['location.id'],
                                name=op.f('fk_vlan_site_id_location'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_vlan')),
        sa.UniqueConstraint('site_id', 'vid', name=op.f('uq_vlan_site_id_vid')),
    )

    op.create_table(
        'prefix',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('cidr', postgresql.CIDR(), nullable=False),
        sa.Column('vrf_id', sa.UUID(), nullable=True),
        sa.Column('vlan_id', sa.UUID(), nullable=True),
        sa.Column('gateway', postgresql.INET(), nullable=True),
        sa.Column('dhcp_from', postgresql.INET(), nullable=True),
        sa.Column('dhcp_to', postgresql.INET(), nullable=True),
        sa.Column('site_id', sa.UUID(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(['site_id'], ['location.id'],
                                name=op.f('fk_prefix_site_id_location'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['vlan_id'], ['vlan.id'], name=op.f('fk_prefix_vlan_id_vlan'),
                                ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['vrf_id'], ['vrf.id'], name=op.f('fk_prefix_vrf_id_vrf'),
                                ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_prefix')),
        sa.UniqueConstraint('vrf_id', 'cidr', name=op.f('uq_prefix_vrf_id_cidr')),
    )
    op.create_index('ix_prefix_cidr', 'prefix', ['cidr'], postgresql_using='gist',
                    postgresql_ops={'cidr': 'inet_ops'})

    op.create_table(
        'ip_address',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('address', postgresql.INET(), nullable=False),
        sa.Column('vrf_id', sa.UUID(), nullable=True),
        sa.Column('prefix_id', sa.UUID(), nullable=True),
        sa.Column('interface_id', sa.UUID(), nullable=True),
        sa.Column('ci_id', sa.UUID(), nullable=True),
        sa.Column('dns_name', sa.String(length=255), nullable=True),
        sa.Column('role', IP_ROLE, nullable=False),
        sa.Column('status', IP_STATUS, nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(['ci_id'], ['ci.id'], name=op.f('fk_ip_address_ci_id_ci'),
                                ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['interface_id'], ['interface.id'],
                                name=op.f('fk_ip_address_interface_id_interface'),
                                ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['prefix_id'], ['prefix.id'],
                                name=op.f('fk_ip_address_prefix_id_prefix'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['vrf_id'], ['vrf.id'], name=op.f('fk_ip_address_vrf_id_vrf'),
                                ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_ip_address')),
    )
    op.create_index('ix_ip_address_interface', 'ip_address', ['interface_id'])
    op.create_index('ix_ip_address_value', 'ip_address', ['address'], postgresql_using='gist',
                    postgresql_ops={'address': 'inet_ops'})
    op.create_index('uq_ip_per_vrf', 'ip_address', ['vrf_id', 'address'], unique=True,
                    postgresql_where=sa.text("status <> 'DEPRECATED'"))

    op.create_table(
        'interface_vlan',
        sa.Column('interface_id', sa.UUID(), nullable=False),
        sa.Column('vlan_id', sa.UUID(), nullable=False),
        sa.Column('mode', VLAN_MODE, nullable=False),
        sa.ForeignKeyConstraint(['interface_id'], ['interface.id'],
                                name=op.f('fk_interface_vlan_interface_id_interface'),
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['vlan_id'], ['vlan.id'],
                                name=op.f('fk_interface_vlan_vlan_id_vlan'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('interface_id', 'vlan_id', name=op.f('pk_interface_vlan')),
    )

    for table in ACTOR_FK_TABLES:
        for column in ("created_by", "updated_by"):
            op.create_foreign_key(
                f"fk_{table}_{column}_user_account", table, "user_account", [column], ["id"],
                ondelete="SET NULL",
            )
    op.create_foreign_key(
        "fk_department_head_employee_id_employee", "department", "employee",
        ["head_employee_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_department_head_employee_id_employee", "department",
                       type_="foreignkey")
    for table in ACTOR_FK_TABLES:
        for column in ("created_by", "updated_by"):
            op.drop_constraint(f"fk_{table}_{column}_user_account", table, type_="foreignkey")

    op.drop_table('interface_vlan')
    op.drop_table('ip_address')
    op.drop_table('prefix')
    op.drop_table('vlan')
    op.drop_table('vrf')
    op.drop_table('connection')
    op.drop_table('cable_route')
    op.drop_table('interface')
    op.drop_table('device')
    op.drop_table('port_template')
    op.drop_table('device_model')
    op.drop_table('manufacturer')
    for name in ENUMS:
        op.execute(f"DROP TYPE IF EXISTS {name}")
