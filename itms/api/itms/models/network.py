"""Сетевой слой: устройство, интерфейсы, кабели, трассы, адресация.

`device` — типизированное расширение `ci` с общим идентификатором: объект остаётся
единой конфигурационной единицей (связи, история, поиск), но получает инженерные поля.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import CIDR, ENUM, INET, MACADDR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from itms.models.base import ActorMixin, Base, TimestampMixin, uuid_pk
from itms.models.catalog import DeviceModel
from itms.models.enums import (
    CableCategory,
    CableMedium,
    ConnectionStatus,
    DeviceRole,
    InterfaceType,
    IpRole,
    IpStatus,
    PanelSide,
    VlanMode,
)


class Device(Base, TimestampMixin, ActorMixin):
    """Инженерная часть объекта типа DEVICE. Общие поля остаются в `ci`."""

    __tablename__ = "device"
    __table_args__ = (
        Index("ix_device_role", "device_role"),
        Index("ix_device_mgmt_ip", "mgmt_ip"),
        Index(
            "ix_device_hostname_trgm",
            "hostname",
            postgresql_using="gin",
            postgresql_ops={"hostname": "gin_trgm_ops"},
        ),
        Index(
            "uq_device_asset_tag",
            text("lower(asset_tag)"),
            unique=True,
            postgresql_where=text("asset_tag IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ci.id", ondelete="CASCADE"), primary_key=True
    )
    device_model_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("device_model.id", ondelete="RESTRICT")
    )
    device_role: Mapped[DeviceRole] = mapped_column(
        ENUM(DeviceRole, name="device_role", create_type=False),
        nullable=False,
        default=DeviceRole.OTHER,
    )
    asset_tag: Mapped[str | None] = mapped_column(String(64))
    hostname: Mapped[str | None] = mapped_column(String(255))
    mgmt_ip: Mapped[str | None] = mapped_column(INET)
    mgmt_mac: Mapped[str | None] = mapped_column(MACADDR)
    firmware: Mapped[str | None] = mapped_column(String(128))
    os_version: Mapped[str | None] = mapped_column(String(128))
    purchase_date: Mapped[date | None] = mapped_column(Date)
    warranty_until: Mapped[date | None] = mapped_column(Date)
    psu_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    #: Переопределяет модель, если у конкретного экземпляра измерено или указано иное.
    power_nameplate_w: Mapped[int | None] = mapped_column(Integer)
    power_max_w: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)

    model: Mapped[DeviceModel | None] = relationship(lazy="joined")


class Interface(Base, TimestampMixin, ActorMixin):
    """Порт устройства. Логические интерфейсы (LAG, SVI, туннели) живут здесь же."""

    __tablename__ = "interface"
    __table_args__ = (
        UniqueConstraint("ci_id", "name"),
        Index("ix_interface_ci", "ci_id", "position"),
        Index("ix_interface_mac", "mac"),
        Index(
            "ix_interface_description_trgm",
            "description",
            postgresql_using="gin",
            postgresql_ops={"description": "gin_trgm_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    ci_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ci.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    position: Mapped[int | None] = mapped_column(Integer)
    interface_type: Mapped[InterfaceType] = mapped_column(
        ENUM(InterfaceType, name="interface_type", create_type=False), nullable=False
    )
    medium: Mapped[CableMedium | None] = mapped_column(
        ENUM(CableMedium, name="cable_medium", create_type=False)
    )
    speed_mbps: Mapped[int | None] = mapped_column(Integer)
    duplex: Mapped[str | None] = mapped_column(String(16))
    mac: Mapped[str | None] = mapped_column(MACADDR)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    purpose: Mapped[str | None] = mapped_column(String(255))
    admin_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    oper_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="UNKNOWN", server_default="UNKNOWN"
    )
    is_management: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    poe_mode: Mapped[str | None] = mapped_column(String(32))
    mtu: Mapped[int | None] = mapped_column(Integer)
    lag_parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("interface.id", ondelete="SET NULL")
    )
    #: Патч-панель: сторона порта и парный порт на противоположной стороне.
    panel_side: Mapped[PanelSide | None] = mapped_column(
        ENUM(PanelSide, name="panel_side", create_type=False)
    )
    paired_interface_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("interface.id", ondelete="SET NULL")
    )

    vlans: Mapped[list[InterfaceVlan]] = relationship(
        back_populates="interface", lazy="selectin", cascade="all, delete-orphan"
    )


class CableRoute(Base, TimestampMixin, ActorMixin):
    """Трасса: лоток, короб, гофра, межэтажный стояк."""

    __tablename__ = "cable_route"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    route_type: Mapped[str | None] = mapped_column(String(64))
    from_location_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("location.id", ondelete="SET NULL")
    )
    to_location_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("location.id", ondelete="SET NULL")
    )
    length_m: Mapped[float | None] = mapped_column(Numeric(7, 2))
    capacity: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)


class Connection(Base, TimestampMixin, ActorMixin):
    """Кабель как самостоятельная сущность: у него своя история и свои свойства."""

    __tablename__ = "connection"
    __table_args__ = (
        CheckConstraint("a_interface_id <> b_interface_id", name="distinct_ends"),
        Index(
            "uq_connection_a",
            "a_interface_id",
            unique=True,
            postgresql_where=text("status IN ('ACTIVE','RESERVED')"),
        ),
        Index(
            "uq_connection_b",
            "b_interface_id",
            unique=True,
            postgresql_where=text("status IN ('ACTIVE','RESERVED')"),
        ),
        Index(
            "ix_connection_label_trgm",
            "label",
            postgresql_using="gin",
            postgresql_ops={"label": "gin_trgm_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    label: Mapped[str | None] = mapped_column(String(64))
    medium: Mapped[CableMedium] = mapped_column(
        ENUM(CableMedium, name="cable_medium", create_type=False), nullable=False
    )
    category: Mapped[CableCategory | None] = mapped_column(
        ENUM(CableCategory, name="cable_category", create_type=False)
    )
    connector_a: Mapped[str | None] = mapped_column(String(32))
    connector_b: Mapped[str | None] = mapped_column(String(32))
    a_interface_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interface.id", ondelete="CASCADE"), nullable=False
    )
    b_interface_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interface.id", ondelete="CASCADE"), nullable=False
    )
    length_m: Mapped[float | None] = mapped_column(Numeric(6, 2))
    speed_mbps: Mapped[int | None] = mapped_column(Integer)
    color: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[ConnectionStatus] = mapped_column(
        ENUM(ConnectionStatus, name="connection_status", create_type=False),
        nullable=False,
        default=ConnectionStatus.ACTIVE,
    )
    route_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cable_route.id", ondelete="SET NULL")
    )
    is_redundant: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    redundancy_group: Mapped[str | None] = mapped_column(String(64))
    installed_on: Mapped[date | None] = mapped_column(Date)
    tested_on: Mapped[date | None] = mapped_column(Date)
    test_result: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")

    a_interface: Mapped[Interface] = relationship(foreign_keys=[a_interface_id], lazy="joined")
    b_interface: Mapped[Interface] = relationship(foreign_keys=[b_interface_id], lazy="joined")
    route: Mapped[CableRoute | None] = relationship(lazy="joined")


class Vrf(Base, TimestampMixin, ActorMixin):
    __tablename__ = "vrf"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    rd: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)


class Vlan(Base, TimestampMixin, ActorMixin):
    __tablename__ = "vlan"
    __table_args__ = (
        UniqueConstraint("site_id", "vid"),
        CheckConstraint("vid BETWEEN 1 AND 4094", name="vid_range"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    vid: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("location.id", ondelete="SET NULL")
    )
    purpose: Mapped[str | None] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text)


class Prefix(Base, TimestampMixin, ActorMixin):
    __tablename__ = "prefix"
    __table_args__ = (
        UniqueConstraint("vrf_id", "cidr"),
        Index(
            "ix_prefix_cidr",
            "cidr",
            postgresql_using="gist",
            postgresql_ops={"cidr": "inet_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    cidr: Mapped[str] = mapped_column(CIDR, nullable=False)
    vrf_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vrf.id", ondelete="SET NULL"))
    vlan_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vlan.id", ondelete="SET NULL"))
    gateway: Mapped[str | None] = mapped_column(INET)
    dhcp_from: Mapped[str | None] = mapped_column(INET)
    dhcp_to: Mapped[str | None] = mapped_column(INET)
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("location.id", ondelete="SET NULL")
    )
    description: Mapped[str | None] = mapped_column(Text)

    vlan: Mapped[Vlan | None] = relationship(lazy="joined")
    vrf: Mapped[Vrf | None] = relationship(lazy="joined")


class IpAddress(Base, TimestampMixin, ActorMixin):
    __tablename__ = "ip_address"
    __table_args__ = (
        Index(
            "uq_ip_per_vrf",
            "vrf_id",
            "address",
            unique=True,
            postgresql_where=text("status <> 'DEPRECATED'"),
        ),
        Index(
            "ix_ip_address_value",
            "address",
            postgresql_using="gist",
            postgresql_ops={"address": "inet_ops"},
        ),
        Index("ix_ip_address_interface", "interface_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    address: Mapped[str] = mapped_column(INET, nullable=False)
    vrf_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vrf.id", ondelete="SET NULL"))
    prefix_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("prefix.id", ondelete="SET NULL")
    )
    interface_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("interface.id", ondelete="SET NULL")
    )
    #: Адрес, закреплённый за объектом, у которого нет интерфейса (например, за сервисом).
    ci_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ci.id", ondelete="SET NULL"))
    dns_name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[IpRole] = mapped_column(
        ENUM(IpRole, name="ip_role", create_type=False), nullable=False, default=IpRole.PRIMARY
    )
    status: Mapped[IpStatus] = mapped_column(
        ENUM(IpStatus, name="ip_status", create_type=False),
        nullable=False,
        default=IpStatus.ACTIVE,
    )
    description: Mapped[str | None] = mapped_column(Text)


class InterfaceVlan(Base):
    __tablename__ = "interface_vlan"

    interface_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interface.id", ondelete="CASCADE"), primary_key=True
    )
    vlan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vlan.id", ondelete="CASCADE"), primary_key=True
    )
    mode: Mapped[VlanMode] = mapped_column(
        ENUM(VlanMode, name="vlan_mode", create_type=False), nullable=False
    )

    interface: Mapped[Interface] = relationship(back_populates="vlans")
    vlan: Mapped[Vlan] = relationship(lazy="joined")
