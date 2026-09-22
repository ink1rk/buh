from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import DateTime, ForeignKey, MetaData, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    type_annotation_map: ClassVar[dict] = {
        dict[str, Any]: JSONB,
        list[str]: JSONB,
        uuid.UUID: UUID(as_uuid=True),
        datetime: DateTime(timezone=True),
        str: String,
    }

    def __repr__(self) -> str:  # pragma: no cover - удобство отладки
        pk = getattr(self, "id", None)
        return f"<{type(self).__name__} {pk}>"


def uuid_pk() -> Mapped[uuid.UUID]:
    """Идентификатор генерируется приложением.

    Это важно для аудита: запись истории создаётся до flush, и объект уже должен
    знать свой идентификатор. server_default оставлен для вставок напрямую в SQL.
    """
    return mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ActorMixin:
    """Кто создал и кто последним изменил запись.

    Ссылки создаются отложенно (`use_alter`): справочник, учётные записи и сотрудники
    ссылаются друг на друга, и без этого порядок создания таблиц становится неразрешимым.
    """

    @declared_attr
    def created_by(cls) -> Mapped[uuid.UUID | None]:
        return mapped_column(
            ForeignKey(
                "user_account.id",
                ondelete="SET NULL",
                use_alter=True,
                name=f"fk_{cls.__tablename__}_created_by_user_account",
            ),
            nullable=True,
        )

    @declared_attr
    def updated_by(cls) -> Mapped[uuid.UUID | None]:
        return mapped_column(
            ForeignKey(
                "user_account.id",
                ondelete="SET NULL",
                use_alter=True,
                name=f"fk_{cls.__tablename__}_updated_by_user_account",
            ),
            nullable=True,
        )


class LifecycleMixin:
    """Архивирование и мягкое удаление.

    Физическое удаление критических инфраструктурных объектов запрещено:
    объект переводится в RETIRED либо архивируется.
    """

    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class VersionMixin:
    """Оптимистичная блокировка: конкурирующая правка не затирает чужую молча."""

    version: Mapped[int] = mapped_column(nullable=False, default=1, server_default=text("1"))
