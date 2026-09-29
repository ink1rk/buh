"""Виртуализация: ёмкость хоста и ресурсы, которые занимает гостевая машина.

Хост и машина остаются объектами `ci`. Здесь только инженерный профиль:
сколько ядер, памяти и диска есть у узла и сколько из этого забирает каждая VM.
"""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column

from itms.models.base import ActorMixin, Base, TimestampMixin
from itms.models.enums import HypervisorPlatform, VmPowerState


class ComputeHost(Base, TimestampMixin, ActorMixin):
    """Ёмкость узла или кластера, на котором запускаются виртуальные машины."""

    __tablename__ = "compute_host"
    __table_args__ = (
        CheckConstraint("cpu_cores >= 0", name="cpu_cores"),
        CheckConstraint("memory_mb >= 0", name="memory_mb"),
        CheckConstraint("storage_gb >= 0", name="storage_gb"),
    )

    id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ci.id", ondelete="CASCADE"), primary_key=True)
    platform: Mapped[HypervisorPlatform] = mapped_column(
        ENUM(HypervisorPlatform, name="hypervisor_platform", create_type=False),
        nullable=False,
        default=HypervisorPlatform.OTHER,
    )
    cpu_cores: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    memory_mb: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    storage_gb: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class VirtualMachine(Base, TimestampMixin, ActorMixin):
    """Ресурсы гостя. Перерасход относительно хоста допустим и показывается как есть."""

    __tablename__ = "virtual_machine"
    __table_args__ = (
        CheckConstraint("vcpu >= 1", name="vcpu"),
        CheckConstraint("memory_mb >= 1", name="memory_mb"),
        CheckConstraint("disk_gb >= 0", name="disk_gb"),
        Index("ix_virtual_machine_host_id", "host_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ci.id", ondelete="CASCADE"), primary_key=True)
    host_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compute_host.id", ondelete="SET NULL")
    )
    vcpu: Mapped[int] = mapped_column(Integer, nullable=False)
    memory_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    disk_gb: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    guest_os: Mapped[str | None] = mapped_column(String(128))
    power_state: Mapped[VmPowerState] = mapped_column(
        ENUM(VmPowerState, name="vm_power_state", create_type=False),
        nullable=False,
        default=VmPowerState.RUNNING,
    )
