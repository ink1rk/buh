"""Разрешения.

В Phase 1 полноценный доступ есть только у владельца системы, но проверки
выполняются через общий механизм: включение ролей исполнителей позже
не потребует переписывания обработчиков.
"""

from __future__ import annotations

from enum import StrEnum

from itms.core.errors import Forbidden
from itms.models.enums import UserRole


class Permission(StrEnum):
    CI_READ = "ci:read"
    CI_WRITE = "ci:write"
    CI_DELETE = "ci:delete"
    LOCATION_WRITE = "location:write"
    CATALOG_WRITE = "catalog:write"
    NETWORK_WRITE = "network:write"
    DIRECTORY_READ = "directory:read"
    DIRECTORY_WRITE = "directory:write"
    DOCUMENT_READ = "document:read"
    DOCUMENT_WRITE = "document:write"
    FILE_UPLOAD = "file:upload"
    IMPORT_RUN = "import:run"
    AUDIT_READ = "audit:read"
    SETTINGS_WRITE = "settings:write"
    USER_MANAGE = "user:manage"
    EXPORT_RUN = "export:run"


_READ_ONLY = frozenset(
    {
        Permission.CI_READ,
        Permission.DIRECTORY_READ,
        Permission.DOCUMENT_READ,
    }
)

ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    UserRole.OWNER: frozenset(Permission),
    UserRole.ENGINEER: _READ_ONLY
    | frozenset(
        {
            Permission.CI_WRITE,
            Permission.LOCATION_WRITE,
            Permission.CATALOG_WRITE,
            Permission.NETWORK_WRITE,
            Permission.DOCUMENT_WRITE,
            Permission.FILE_UPLOAD,
            Permission.EXPORT_RUN,
            Permission.AUDIT_READ,
        }
    ),
    UserRole.OPERATOR: _READ_ONLY | frozenset({Permission.DOCUMENT_WRITE, Permission.FILE_UPLOAD}),
    UserRole.VIEWER: _READ_ONLY,
}


def has_permission(role: UserRole, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


def require(role: UserRole, permission: Permission) -> None:
    if not has_permission(role, permission):
        raise Forbidden(
            "Недостаточно прав для выполнения операции",
            required=permission.value,
            role=role.value,
        )
