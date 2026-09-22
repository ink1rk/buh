"""Стойки и размещение по юнитам.

Пересечение юнитов запрещено ограничением базы, а не только проверкой в сервисе:
перетаскивание пишет часто, и гонка «прочитал — проверил — записал» здесь недопустима.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, INT4RANGE, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from itms.models.base import Base, TimestampMixin, uuid_pk
from itms.models.enums import RackFace, RackFormFactor, ZeroUSide


class Rack(Base, TimestampMixin):
    """Инженерный профиль объекта типа RACK. Имя и размещение живут в ci."""

    __tablename__ = "rack"

    id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ci.id", ondelete="CASCADE"), primary_key=True
    )
    u_height: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=42)
    width_in: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=19)
    depth_mm: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    max_weight_kg: Mapped[float | None] = mapped_column(Numeric(7, 2))
    max_power_w: Mapped[int | None] = mapped_column(Integer)
    form_factor: Mapped[RackFormFactor] = mapped_column(
        ENUM(RackFormFactor, name="rack_form_factor", create_type=False),
        nullable=False,
        default=RackFormFactor.CABINET,
    )
    descending_units: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    plan_x: Mapped[float | None] = mapped_column(Numeric(8, 2))
    plan_y: Mapped[float | None] = mapped_column(Numeric(8, 2))
    plan_rotation: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)


class RackMount(Base, TimestampMixin):
    """Один объект — одна стойка. Резерв может пересекаться: это план, не факт."""

    __tablename__ = "rack_mount"
    __table_args__ = (
        CheckConstraint("position_u >= 1", name="position_u"),
        CheckConstraint("u_height >= 0 AND u_height <= 60", name="u_height"),
        CheckConstraint(
            "(u_height = 0 AND zero_u_side IS NOT NULL) "
            "OR (u_height > 0 AND zero_u_side IS NULL)",
            name="zero_u",
        ),
        ExcludeConstraint(
            ("rack_id", "="),
            ("u_range", "&&"),
            name="ex_rack_mount_front",
            using="gist",
            where=text("occupies_front AND NOT is_reservation"),
        ),
        ExcludeConstraint(
            ("rack_id", "="),
            ("u_range", "&&"),
            name="ex_rack_mount_rear",
            using="gist",
            where=text("occupies_rear AND NOT is_reservation"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    rack_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rack.id", ondelete="CASCADE"), nullable=False
    )
    ci_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ci.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    position_u: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    u_height: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    face: Mapped[RackFace] = mapped_column(
        ENUM(RackFace, name="rack_face", create_type=False),
        nullable=False,
        default=RackFace.FRONT,
    )
    zero_u_side: Mapped[ZeroUSide | None] = mapped_column(
        ENUM(ZeroUSide, name="zero_u_side", create_type=False)
    )
    depth_mm: Mapped[int | None] = mapped_column(Integer)
    weight_kg: Mapped[float | None] = mapped_column(Numeric(6, 2))
    is_reservation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    u_range: Mapped[Any] = mapped_column(
        INT4RANGE,
        Computed("int4range(position_u, position_u + u_height)", persisted=True),
    )
    occupies_front: Mapped[bool] = mapped_column(
        Computed(
            "((face IN ('FRONT', 'FULL')) AND (u_height > 0))",
            persisted=True,
        )
    )
    occupies_rear: Mapped[bool] = mapped_column(
        Computed(
            "((face IN ('REAR', 'FULL')) AND (u_height > 0))",
            persisted=True,
        )
    )
