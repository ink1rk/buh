"""План помещения. Координаты в миллиметрах, объекты — ссылки на CI."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from itms.models.base import Base, uuid_pk


class Floorplan(Base):
    __tablename__ = "floorplan"

    id: Mapped[uuid.UUID] = uuid_pk()
    location_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("location.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    width_mm: Mapped[int] = mapped_column(Integer, nullable=False)
    height_mm: Mapped[int] = mapped_column(Integer, nullable=False)
    background_file_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("file_object.id", ondelete="SET NULL")
    )
    scale_px_per_m: Mapped[float | None] = mapped_column(Numeric(8, 3))


class FloorplanItem(Base):
    __tablename__ = "floorplan_item"
    __table_args__ = (
        CheckConstraint(
            "item_kind IN ('RACK', 'DEVICE', 'POWER', 'ANNOTATION', 'ROUTE')",
            name="kind",
        ),
        CheckConstraint("rotation IN (0, 90, 180, 270)", name="rotation"),
        CheckConstraint("width > 0 AND height > 0", name="size"),
        Index(
            "uq_floorplan_item_ci",
            "floorplan_id",
            "ci_id",
            unique=True,
            postgresql_where=text("ci_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    floorplan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("floorplan.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ci_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ci.id", ondelete="CASCADE"))
    item_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    x: Mapped[float] = mapped_column(Numeric(9, 2), nullable=False)
    y: Mapped[float] = mapped_column(Numeric(9, 2), nullable=False)
    width: Mapped[float] = mapped_column(Numeric(9, 2), nullable=False)
    height: Mapped[float] = mapped_column(Numeric(9, 2), nullable=False)
    rotation: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0"
    )
    label: Mapped[str | None] = mapped_column(String(255))
    style: Mapped[dict[str, Any]] = mapped_column(nullable=False, default=dict)
