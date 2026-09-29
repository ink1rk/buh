"""Электрическая модель: узлы, ветки, связи и замеры.

Узел — это CI. Связь power_link — единственный способ описать, кто кого питает.
Ветка и узел ссылаются друг на друга: feed_id создаётся отложенно.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column

from itms.models.base import Base, uuid_pk
from itms.models.enums import ConnectionStatus, FeedSide, PhaseLabel, PowerNodeType


class PowerNode(Base):
    """Инженерный профиль объекта типа POWER_NODE. Имя живёт в ci."""

    __tablename__ = "power_node"
    __table_args__ = (
        CheckConstraint("phases IN (1, 3)", name="ck_power_node_phases"),
        CheckConstraint(
            "phases <> 1 OR node_type IN ('INPUT', 'PANEL') OR phase_label IS NOT NULL",
            name="ck_power_node_single_phase_label",
        ),
        CheckConstraint(
            "breaker_curve IS NULL OR breaker_curve IN ('B', 'C', 'D')",
            name="ck_power_node_breaker_curve",
        ),
        CheckConstraint(
            "breaker_poles IS NULL OR breaker_poles IN ('1P', '1P+N', '3P', '3P+N')",
            name="ck_power_node_breaker_poles",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ci.id", ondelete="CASCADE"), primary_key=True)
    node_type: Mapped[PowerNodeType] = mapped_column(
        ENUM(PowerNodeType, name="power_node_type", create_type=False),
        nullable=False,
        index=True,
    )
    parent_device_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ci.id", ondelete="CASCADE")
    )
    rack_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("rack.id", ondelete="SET NULL"), index=True
    )
    feed_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "power_feed.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_power_node_feed_id_power_feed",
        ),
        index=True,
    )
    feed_side: Mapped[FeedSide] = mapped_column(
        ENUM(FeedSide, name="feed_side", create_type=False),
        nullable=False,
        default=FeedSide.SINGLE,
        server_default="SINGLE",
    )
    voltage_v: Mapped[float | None] = mapped_column(Numeric(6, 1))
    phases: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, server_default="1")
    phase_label: Mapped[PhaseLabel | None] = mapped_column(
        ENUM(PhaseLabel, name="phase_label", create_type=False)
    )
    rated_current_a: Mapped[float | None] = mapped_column(Numeric(7, 2))
    breaker_curve: Mapped[str | None] = mapped_column(String(8))
    breaker_poles: Mapped[str | None] = mapped_column(String(8))
    cable_spec: Mapped[str | None] = mapped_column(Text)
    cable_length_m: Mapped[float | None] = mapped_column(Numeric(6, 2))
    cable_ampacity_a: Mapped[float | None] = mapped_column(Numeric(7, 2))
    derating_factor: Mapped[float] = mapped_column(
        Numeric(4, 3), nullable=False, default=0.8, server_default=text("0.8")
    )
    power_factor: Mapped[float | None] = mapped_column(Numeric(4, 3))
    efficiency: Mapped[float | None] = mapped_column(Numeric(4, 3))
    power_nameplate_w: Mapped[int | None] = mapped_column(Integer)
    power_max_w: Mapped[int | None] = mapped_column(Integer)
    max_load_w: Mapped[int | None] = mapped_column(Integer)
    ups_capacity_va: Mapped[int | None] = mapped_column(Integer)
    ups_capacity_w: Mapped[int | None] = mapped_column(Integer)
    ups_battery_minutes: Mapped[int | None] = mapped_column(SmallInteger)
    outlet_type: Mapped[str | None] = mapped_column(String(32))
    outlet_count: Mapped[int | None] = mapped_column(SmallInteger)
    utilization: Mapped[float | None] = mapped_column(Numeric(4, 3))
    notes: Mapped[str | None] = mapped_column(Text)


class PowerFeed(Base):
    """Ветка питания. Корень — ввод, от которого она начинается."""

    __tablename__ = "power_feed"
    __table_args__ = (UniqueConstraint("location_id", "name", name="uq_power_feed_location_name"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    side: Mapped[FeedSide] = mapped_column(
        ENUM(FeedSide, name="feed_side", create_type=False), nullable=False
    )
    root_node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("power_node.id", ondelete="RESTRICT"), nullable=False
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("location.id", ondelete="SET NULL")
    )
    is_protected: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")


class PowerMeasurement(Base):
    """История фактической мощности. В расчёт берётся свежая запись, старые остаются."""

    __tablename__ = "power_measurement"
    __table_args__ = (
        CheckConstraint(
            "source IN ('MANUAL', 'PDU', 'UPS', 'METER', 'IMPORT', 'MONITORING')",
            name="ck_power_measurement_source",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("power_node.id", ondelete="CASCADE"), nullable=False, index=True
    )
    measured_at: Mapped[datetime] = mapped_column(nullable=False)
    power_w: Mapped[int | None] = mapped_column(Integer)
    current_a: Mapped[float | None] = mapped_column(Numeric(7, 2))
    voltage_v: Mapped[float | None] = mapped_column(Numeric(6, 1))
    power_factor: Mapped[float | None] = mapped_column(Numeric(4, 3))
    phase_label: Mapped[PhaseLabel | None] = mapped_column(
        ENUM(PhaseLabel, name="phase_label", create_type=False)
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="MANUAL")
    measured_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employee.id", ondelete="SET NULL")
    )
    instrument: Mapped[str | None] = mapped_column(String(255))
    note: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    is_peak: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )


class PowerLink(Base):
    """Ребро DAG: source питает target. Цикл запрещён доменной проверкой до вставки."""

    __tablename__ = "power_link"
    __table_args__ = (
        CheckConstraint("source_node_id <> target_node_id", name="ck_power_link_distinct"),
        UniqueConstraint("source_node_id", "target_node_id", name="uq_power_link_pair"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    source_node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("power_node.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("power_node.id", ondelete="CASCADE"), nullable=False, index=True
    )
    phase_label: Mapped[PhaseLabel | None] = mapped_column(
        ENUM(PhaseLabel, name="phase_label", create_type=False)
    )
    rated_current_a: Mapped[float | None] = mapped_column(Numeric(7, 2))
    cable_spec: Mapped[str | None] = mapped_column(Text)
    length_m: Mapped[float | None] = mapped_column(Numeric(6, 2))
    status: Mapped[ConnectionStatus] = mapped_column(
        ENUM(ConnectionStatus, name="connection_status", create_type=False),
        nullable=False,
        default=ConnectionStatus.ACTIVE,
        server_default="ACTIVE",
    )
    outlet_number: Mapped[str | None] = mapped_column(String(32))


class PowerScenario(Base):
    """Сохранённый прогноз «что если». К текущей модели он ничего не применяет."""

    __tablename__ = "power_scenario"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    charge_w: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    ups_efficiency: Mapped[float | None] = mapped_column(Numeric(4, 3))
    reserve: Mapped[float] = mapped_column(
        Numeric(4, 3), nullable=False, default=0.2, server_default=text("0.20")
    )


class PowerScenarioItem(Base):
    """Одна строка прироста: паспорт, количество и коэффициент использования."""

    __tablename__ = "power_scenario_item"

    id: Mapped[uuid.UUID] = uuid_pk()
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("power_scenario.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    nameplate_w: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, server_default="1"
    )
    utilization: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    behind_new_ups: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
