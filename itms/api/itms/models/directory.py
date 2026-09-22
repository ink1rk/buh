from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from itms.models.base import ActorMixin, Base, LifecycleMixin, TimestampMixin, uuid_pk
from itms.models.enums import EmployeeStatus, SupportLine, UserRole, UserStatus


class Organization(Base, TimestampMixin, ActorMixin):
    __tablename__ = "organization"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    full_name: Mapped[str | None] = mapped_column(String(500))
    inn: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Europe/Moscow")
    notes: Mapped[str | None] = mapped_column(Text)

    departments: Mapped[list[Department]] = relationship(
        back_populates="organization", lazy="selectin"
    )


class Department(Base, TimestampMixin, ActorMixin):
    __tablename__ = "department"
    __table_args__ = (UniqueConstraint("organization_id", "name"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("department.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(50))
    head_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "employee.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_department_head_employee_employee",
        )
    )
    description: Mapped[str | None] = mapped_column(Text)

    organization: Mapped[Organization] = relationship(back_populates="departments", lazy="joined")
    employees: Mapped[list[Employee]] = relationship(
        back_populates="department",
        lazy="selectin",
        foreign_keys="Employee.department_id",
    )


class Employee(Base, TimestampMixin, ActorMixin, LifecycleMixin):
    """Сотрудник — субъект работ.

    Учётная запись (user_account) заводится не для всех: в Phase 1 вход в систему
    есть только у владельца, но исполнители уже моделируются и на них ставятся задачи.
    """

    __tablename__ = "employee"
    __table_args__ = (
        Index("ix_employee_full_name", "full_name"),
        Index("ix_employee_status", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("department.id", ondelete="SET NULL")
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(50))
    telegram: Mapped[str | None] = mapped_column(String(100))
    support_line: Mapped[SupportLine] = mapped_column(
        ENUM(SupportLine, name="support_line", create_type=False),
        nullable=False,
        default=SupportLine.NONE,
    )
    status: Mapped[EmployeeStatus] = mapped_column(
        ENUM(EmployeeStatus, name="employee_status", create_type=False),
        nullable=False,
        default=EmployeeStatus.ACTIVE,
    )
    hired_on: Mapped[date | None] = mapped_column(Date)
    dismissed_on: Mapped[date | None] = mapped_column(Date)
    weekly_hours: Mapped[int] = mapped_column(nullable=False, default=40, server_default=text("40"))
    notes: Mapped[str | None] = mapped_column(Text)

    department: Mapped[Department | None] = relationship(
        back_populates="employees", lazy="joined", foreign_keys=[department_id]
    )
    responsibilities: Mapped[list[ResponsibilityArea]] = relationship(
        secondary="employee_responsibility", back_populates="employees", lazy="selectin"
    )


class ResponsibilityArea(Base, TimestampMixin, ActorMixin):
    """Зона ответственности: «сеть», «серверы», «1С», «электрика»."""

    __tablename__ = "responsibility_area"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    code: Mapped[str | None] = mapped_column(String(50), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str | None] = mapped_column(String(16))

    employees: Mapped[list[Employee]] = relationship(
        secondary="employee_responsibility", back_populates="responsibilities", lazy="selectin"
    )


class EmployeeResponsibility(Base):
    __tablename__ = "employee_responsibility"

    employee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("employee.id", ondelete="CASCADE"), primary_key=True
    )
    area_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("responsibility_area.id", ondelete="CASCADE"), primary_key=True
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class UserAccount(Base, TimestampMixin):
    __tablename__ = "user_account"

    id: Mapped[uuid.UUID] = uuid_pk()
    employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employee.id", ondelete="SET NULL"), unique=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(512))
    role: Mapped[UserRole] = mapped_column(
        ENUM(UserRole, name="user_role", create_type=False),
        nullable=False,
        default=UserRole.VIEWER,
    )
    status: Mapped[UserStatus] = mapped_column(
        ENUM(UserStatus, name="user_status", create_type=False),
        nullable=False,
        default=UserStatus.ACTIVE,
    )
    locale: Mapped[str] = mapped_column(String(8), nullable=False, default="ru")
    theme: Mapped[str] = mapped_column(String(16), nullable=False, default="system")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_login_count: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default=text("0")
    )

    employee: Mapped[Employee | None] = relationship(lazy="joined", foreign_keys=[employee_id])

    @property
    def is_owner(self) -> bool:
        return self.role == UserRole.OWNER


class UserSession(Base):
    """Серверная сессия. В БД хранится только отпечаток токена."""

    __tablename__ = "user_session"
    __table_args__ = (Index("ix_user_session_user", "user_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))

    user: Mapped[UserAccount] = relationship(lazy="joined")
