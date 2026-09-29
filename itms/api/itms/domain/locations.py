"""Правила физической иерархии размещения."""

from __future__ import annotations

from itms.core.errors import Invalid
from itms.models.enums import LOCATION_PARENTS, ROOT_LOCATION_TYPES, LocationType

PATH_SEPARATOR = " / "


def validate_hierarchy(child: LocationType, parent: LocationType | None) -> None:
    allowed = LOCATION_PARENTS[child]
    if parent is None:
        if allowed and child not in ROOT_LOCATION_TYPES:
            raise Invalid(
                f"Для типа «{child.value}» требуется родительский элемент",
                code_hint="parent_required",
                allowed=sorted(t.value for t in allowed),
            )
        return
    if not allowed:
        raise Invalid(
            f"Тип «{child.value}» не может быть вложен ни во что",
            code_hint="parent_not_allowed",
        )
    if parent not in allowed:
        raise Invalid(
            f"«{child.value}» нельзя разместить внутри «{parent.value}»",
            code_hint="invalid_hierarchy",
            allowed=sorted(t.value for t in allowed),
        )


def build_path(parent_path: str | None, name: str) -> str:
    return f"{parent_path}{PATH_SEPARATOR}{name}" if parent_path else name
