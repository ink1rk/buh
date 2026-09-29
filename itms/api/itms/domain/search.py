"""Подготовка данных для глобального поиска.

Поиск обязан находить объект по неточному названию и по точным идентификаторам:
IP, MAC, hostname, серийному номеру, инвентарному номеру, номеру порта.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_SPLIT_RE = re.compile(r"[\s,;]+")


@dataclass(frozen=True, slots=True)
class SearchDocument:
    entity_type: str
    title: str
    subtitle: str | None = None
    body: str | None = None
    keywords: str | None = None


def normalize_keywords(values: list[str | None]) -> str:
    """Готовит строку точных идентификаторов.

    Для каждого значения дополнительно добавляется вариант без разделителей,
    чтобы MAC-адрес находился и как `00:1A:2B:3C:4D:5E`, и как `001a2b3c4d5e`.
    """
    tokens: list[str] = []
    for value in values:
        if not value:
            continue
        for raw in _SPLIT_RE.split(str(value)):
            token = raw.strip().lower()
            if not token:
                continue
            tokens.append(token)
            stripped = re.sub(r"[^a-z0-9а-яё]", "", token)
            if stripped and stripped != token:
                tokens.append(stripped)
    seen: set[str] = set()
    unique = [t for t in tokens if not (t in seen or seen.add(t))]
    return " ".join(unique)


def ci_document(ci: Any, location_path: str | None = None) -> SearchDocument:
    subtitle_parts = [ci.ci_type.value if hasattr(ci.ci_type, "value") else str(ci.ci_type)]
    if location_path:
        subtitle_parts.append(location_path)
    body_parts = [ci.description or "", ci.vendor or "", ci.model or ""]
    return SearchDocument(
        entity_type="CI",
        title=ci.name,
        subtitle=" · ".join(p for p in subtitle_parts if p),
        body=" ".join(p for p in body_parts if p).strip() or None,
        keywords=normalize_keywords(
            [ci.code, ci.serial_number, ci.inventory_number, ci.vendor, ci.model, ci.name]
        ),
    )


def document_document(doc: Any, content: str | None) -> SearchDocument:
    return SearchDocument(
        entity_type="DOCUMENT",
        title=doc.title,
        subtitle=doc.kind.value if hasattr(doc.kind, "value") else str(doc.kind),
        body=(content or doc.summary or "")[:20000] or None,
        keywords=normalize_keywords([doc.title]),
    )


def location_document(loc: Any) -> SearchDocument:
    return SearchDocument(
        entity_type="LOCATION",
        title=loc.name,
        subtitle=loc.path,
        body=loc.address,
        keywords=normalize_keywords([loc.code, loc.name]),
    )


def employee_document(emp: Any) -> SearchDocument:
    return SearchDocument(
        entity_type="EMPLOYEE",
        title=emp.full_name,
        subtitle=emp.position,
        body=None,
        keywords=normalize_keywords([emp.email, emp.phone, emp.telegram, emp.full_name]),
    )
