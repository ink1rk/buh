"""Каталог оборудования: производитель → модель → шаблон портов.

Габариты, вес и мощность живут у модели, а не у экземпляра. Это даёт редактору стоек
и электрическому расчёту исходные данные ещё до того, как устройство куплено и размещено.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from itms.models.base import ActorMixin, Base, TimestampMixin, uuid_pk
from itms.models.enums import DeviceRole, InterfaceType


class Manufacturer(Base, TimestampMixin, ActorMixin):
    __tablename__ = "manufacturer"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    support_url: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class DeviceModel(Base, TimestampMixin, ActorMixin):
    __tablename__ = "device_model"
    __table_args__ = (
        Index("uq_device_model_key", "manufacturer_id", "model", unique=True),
        {"comment": "Каталог моделей: источник габаритов, веса и мощности"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    manufacturer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("manufacturer.id", ondelete="RESTRICT"), nullable=False
    )
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    part_number: Mapped[str | None] = mapped_column(String(128))
    default_role: Mapped[DeviceRole] = mapped_column(
        ENUM(DeviceRole, name="device_role", create_type=False),
        nullable=False,
        default=DeviceRole.OTHER,
    )
    #: 0 — не стоечное оборудование, 0.5 — half-U.
    u_height: Mapped[float] = mapped_column(Numeric(3, 1), nullable=False, default=1)
    is_full_depth: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    depth_mm: Mapped[int | None] = mapped_column(Integer)
    weight_kg: Mapped[float | None] = mapped_column(Numeric(6, 2))
    psu_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    #: Номинальное (типовое) потребление по паспорту.
    power_nameplate_w: Mapped[int | None] = mapped_column(Integer)
    #: Максимум по шильдику блока питания.
    power_max_w: Mapped[int | None] = mapped_column(Integer)
    power_factor: Mapped[float | None] = mapped_column(Numeric(4, 3))
    utilization_factor: Mapped[float | None] = mapped_column(Numeric(4, 3))
    airflow: Mapped[str | None] = mapped_column(String(32))
    notes: Mapped[str | None] = mapped_column(Text)

    manufacturer: Mapped[Manufacturer] = relationship(lazy="joined")
    port_templates: Mapped[list[PortTemplate]] = relationship(
        back_populates="device_model", lazy="selectin", cascade="all, delete-orphan"
    )


class PortTemplate(Base, TimestampMixin, ActorMixin):
    """Шаблон портов модели: `Gi1/0/{n}` × 48 разворачивается в интерфейсы устройства."""

    __tablename__ = "port_template"

    id: Mapped[uuid.UUID] = uuid_pk()
    device_model_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("device_model.id", ondelete="CASCADE"), nullable=False
    )
    name_pattern: Mapped[str] = mapped_column(String(64), nullable=False)
    count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    start_index: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    interface_type: Mapped[InterfaceType] = mapped_column(
        ENUM(InterfaceType, name="interface_type", create_type=False), nullable=False
    )
    speed_mbps: Mapped[int | None] = mapped_column(Integer)
    poe_capable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    device_model: Mapped[DeviceModel] = relationship(back_populates="port_templates")
