from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from itms.models.base import (
    ActorMixin,
    Base,
    LifecycleMixin,
    TimestampMixin,
    VersionMixin,
    uuid_pk,
)
from itms.models.enums import (
    CiStatus,
    CiType,
    Criticality,
    CustomFieldType,
    Environment,
    LocationType,
    RelationType,
)


class Location(Base, TimestampMixin, ActorMixin, LifecycleMixin):
    """Физическая иерархия: Организация → Площадка → Здание → Этаж → Помещение → Зона."""

    __tablename__ = "location"
    __table_args__ = (
        UniqueConstraint("parent_id", "name"),
        Index("ix_location_type", "location_type"),
        Index("ix_location_path", "path"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("location.id", ondelete="RESTRICT")
    )
    location_type: Mapped[LocationType] = mapped_column(
        ENUM(LocationType, name="location_type", create_type=False), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(50))
    #: Материализованный путь «Офис / Здание А / 2 этаж / Серверная» — для списков и поиска.
    path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    address: Mapped[str | None] = mapped_column(Text)
    area_m2: Mapped[float | None] = mapped_column(Numeric(8, 2))
    responsible_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employee.id", ondelete="SET NULL")
    )
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    description: Mapped[str | None] = mapped_column(Text)

    parent: Mapped[Location | None] = relationship(
        back_populates="children", remote_side="Location.id", lazy="joined"
    )
    children: Mapped[list[Location]] = relationship(back_populates="parent", lazy="noload")


class Ci(Base, TimestampMixin, ActorMixin, LifecycleMixin, VersionMixin):
    """Конфигурационная единица — общая основа всей инфраструктурной модели.

    Типизированные расширения (device, rack, power_node …) подключаются в следующих фазах
    через joined-table inheritance; здесь живут общие атрибуты, связи, история и поиск.
    """

    __tablename__ = "ci"
    __table_args__ = (
        UniqueConstraint("code"),
        Index("ix_ci_type_status", "ci_type", "status"),
        Index("ix_ci_name", "name"),
        Index("ix_ci_location", "location_id"),
        Index("ix_ci_owner", "owner_employee_id"),
        Index("ix_ci_search", "search_tsv", postgresql_using="gin"),
        Index("ix_ci_attributes", "attributes", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    ci_type: Mapped[CiType] = mapped_column(
        ENUM(CiType, name="ci_type", create_type=False), nullable=False
    )
    #: Человекочитаемый идентификатор: SRV-01, SW-CORE-1.
    code: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[CiStatus] = mapped_column(
        ENUM(CiStatus, name="ci_status", create_type=False),
        nullable=False,
        default=CiStatus.ACTIVE,
    )
    criticality: Mapped[Criticality] = mapped_column(
        ENUM(Criticality, name="criticality", create_type=False),
        nullable=False,
        default=Criticality.MEDIUM,
    )
    environment: Mapped[Environment] = mapped_column(
        ENUM(Environment, name="environment", create_type=False),
        nullable=False,
        default=Environment.PROD,
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("location.id", ondelete="SET NULL")
    )
    owner_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employee.id", ondelete="SET NULL")
    )
    vendor: Mapped[str | None] = mapped_column(String(128))
    model: Mapped[str | None] = mapped_column(String(128))
    serial_number: Mapped[str | None] = mapped_column(String(128))
    inventory_number: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    search_tsv: Mapped[str | None] = mapped_column(TSVECTOR)

    location: Mapped[Location | None] = relationship(lazy="joined")

    @property
    def is_critical(self) -> bool:
        return self.criticality == Criticality.CRITICAL


class CiRelation(Base, TimestampMixin, ActorMixin):
    """Логическая связь между объектами.

    Электропитание через эту таблицу не выражается: для него существует power_link.
    """

    __tablename__ = "ci_relation"
    __table_args__ = (
        UniqueConstraint("source_ci_id", "target_ci_id", "rel_type"),
        CheckConstraint("source_ci_id <> target_ci_id", name="no_self_relation"),
        Index("ix_ci_relation_source", "source_ci_id"),
        Index("ix_ci_relation_target", "target_ci_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    source_ci_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ci.id", ondelete="CASCADE"), nullable=False
    )
    target_ci_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ci.id", ondelete="CASCADE"), nullable=False
    )
    rel_type: Mapped[RelationType] = mapped_column(
        ENUM(RelationType, name="relation_type", create_type=False), nullable=False
    )
    criticality: Mapped[Criticality] = mapped_column(
        ENUM(Criticality, name="criticality", create_type=False),
        nullable=False,
        default=Criticality.MEDIUM,
    )
    description: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)

    source: Mapped[Ci] = relationship(foreign_keys=[source_ci_id], lazy="joined")
    target: Mapped[Ci] = relationship(foreign_keys=[target_ci_id], lazy="joined")


class Tag(Base, TimestampMixin, ActorMixin):
    __tablename__ = "tag"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    color: Mapped[str | None] = mapped_column(String(16))
    description: Mapped[str | None] = mapped_column(Text)


class CiTag(Base):
    __tablename__ = "ci_tag"

    ci_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ci.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True
    )


class CustomFieldDef(Base, TimestampMixin, ActorMixin):
    """Произвольные поля: модель расширяется без миграций."""

    __tablename__ = "custom_field_def"
    __table_args__ = (UniqueConstraint("entity_type", "key"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, default="CI")
    ci_type: Mapped[CiType | None] = mapped_column(
        ENUM(CiType, name="ci_type", create_type=False)
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    field_type: Mapped[CustomFieldType] = mapped_column(
        ENUM(CustomFieldType, name="custom_field_type", create_type=False), nullable=False
    )
    options: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    help_text: Mapped[str | None] = mapped_column(Text)


class CustomFieldValue(Base, TimestampMixin):
    __tablename__ = "custom_field_value"
    __table_args__ = (UniqueConstraint("field_id", "entity_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    field_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("custom_field_def.id", ondelete="CASCADE"), nullable=False
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    value: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )


class SearchIndex(Base):
    """Единый индекс глобального поиска по всем сущностям системы."""

    __tablename__ = "search_index"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id"),
        Index("ix_search_index_tsv", "tsv", postgresql_using="gin"),
        Index("ix_search_index_title_trgm", "title", postgresql_using="gin",
              postgresql_ops={"title": "gin_trgm_ops"}),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    subtitle: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    #: Точные идентификаторы: IP, MAC, hostname, серийный номер, номер порта.
    keywords: Mapped[str | None] = mapped_column(Text)
    tsv: Mapped[str | None] = mapped_column(TSVECTOR)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
