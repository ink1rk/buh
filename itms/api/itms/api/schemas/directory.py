from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field

from itms.api.schemas.common import ORMModel
from itms.models.enums import EmployeeStatus, SupportLine, UserRole, UserStatus

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")


def _valid_email(value: str) -> str:
    value = value.strip().lower()
    if not _EMAIL_RE.match(value):
        raise ValueError("Некорректный адрес электронной почты")
    return value


Email = Annotated[str, AfterValidator(_valid_email)]


class LoginRequest(BaseModel):
    email: Email
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=256)


class SessionUser(ORMModel):
    id: uuid.UUID
    email: str
    display_name: str
    role: UserRole
    status: UserStatus
    locale: str
    theme: str
    permissions: list[str] = Field(default_factory=list)


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    locale: str | None = Field(default=None, pattern="^(ru|en)$")
    theme: str | None = Field(default=None, pattern="^(light|dark|system)$")


class OrganizationWrite(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    full_name: str | None = None
    inn: str | None = None
    address: str | None = None
    timezone: str | None = None
    notes: str | None = None


class OrganizationRead(ORMModel):
    id: uuid.UUID
    name: str
    full_name: str | None
    inn: str | None
    address: str | None
    timezone: str
    notes: str | None


class DepartmentWrite(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str | None = None
    parent_id: uuid.UUID | None = None
    head_employee_id: uuid.UUID | None = None
    description: str | None = None


class DepartmentRead(ORMModel):
    id: uuid.UUID
    name: str
    code: str | None
    parent_id: uuid.UUID | None
    head_employee_id: uuid.UUID | None
    description: str | None


class EmployeeWrite(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    position: str | None = None
    email: Email | None = None
    phone: str | None = None
    telegram: str | None = None
    support_line: SupportLine = SupportLine.NONE
    status: EmployeeStatus = EmployeeStatus.ACTIVE
    department_id: uuid.UUID | None = None
    hired_on: date | None = None
    dismissed_on: date | None = None
    weekly_hours: int = Field(default=40, ge=0, le=80)
    notes: str | None = None
    responsibility_ids: list[uuid.UUID] = Field(default_factory=list)


class EmployeeUpdate(BaseModel):
    full_name: str | None = None
    position: str | None = None
    email: Email | None = None
    phone: str | None = None
    telegram: str | None = None
    support_line: SupportLine | None = None
    status: EmployeeStatus | None = None
    department_id: uuid.UUID | None = None
    hired_on: date | None = None
    dismissed_on: date | None = None
    weekly_hours: int | None = Field(default=None, ge=0, le=80)
    notes: str | None = None
    responsibility_ids: list[uuid.UUID] | None = None


class ResponsibilityRead(ORMModel):
    id: uuid.UUID
    name: str
    code: str | None
    description: str | None
    color: str | None


class EmployeeRead(ORMModel):
    id: uuid.UUID
    full_name: str
    position: str | None
    email: str | None
    phone: str | None
    telegram: str | None
    support_line: SupportLine
    status: EmployeeStatus
    department_id: uuid.UUID | None
    hired_on: date | None
    dismissed_on: date | None
    weekly_hours: int
    notes: str | None
    created_at: datetime
    responsibilities: list[ResponsibilityRead] = Field(default_factory=list)


class ResponsibilityWrite(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str | None = None
    description: str | None = None
    color: str | None = None


class WorkloadRow(BaseModel):
    id: uuid.UUID
    full_name: str
    status: EmployeeStatus
    owned_ci: int
