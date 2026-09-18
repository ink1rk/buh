#!/usr/bin/env python3
"""Сборка PDF-документа «Политика отдела технической инфраструктуры».

Запуск:
    python3 generate_policy.py [путь_к_выходному_файлу]

Скрипт строит все диаграммы (charts.py) и собирает многостраничный PDF
с оглавлением, таблицами, схемами и формами для заполнения.
"""

from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import charts  # noqa: E402
from builder import Builder  # noqa: E402
from content_core import (  # noqa: E402
    section_access,
    section_boundaries,
    section_catalog,
    section_changes,
    section_infrastructure,
    section_network,
    section_requests,
)
from content_final import (  # noqa: E402
    appendices,
    section_control,
    section_documentation,
    section_exceptions,
    section_kpi,
    section_related,
    section_responsibility,
    section_rollout,
)
from content_main import (  # noqa: E402
    cover,
    section_authority,
    section_general,
    section_goals,
    section_structure,
    toc_page,
    version_control,
)
from content_ops import (  # noqa: E402
    section_assets,
    section_backup,
    section_contractors,
    section_monitoring,
    section_procurement,
    section_security,
)

DEFAULT_OUT = BASE / "Политика_отдела_технической_инфраструктуры_v1.0.pdf"


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    print("Построение диаграмм…")
    chart_paths = charts.build_all()
    print(f"  готово: {len(chart_paths)} рисунков")

    b = Builder(str(out), chart_paths)

    cover(b)
    version_control(b)
    toc_page(b)

    section_general(b)
    section_goals(b)
    section_structure(b)
    section_authority(b)
    section_boundaries(b)
    section_catalog(b)
    section_requests(b)
    section_changes(b)
    section_infrastructure(b)
    section_network(b)
    section_access(b)
    section_security(b)
    section_assets(b)
    section_backup(b)
    section_monitoring(b)
    section_contractors(b)
    section_procurement(b)
    section_documentation(b)
    section_control(b)
    section_kpi(b)
    section_responsibility(b)
    section_exceptions(b)
    section_rollout(b)
    section_related(b)
    appendices(b)

    print("Сборка PDF…")
    path = b.build()
    size_kb = Path(path).stat().st_size / 1024
    print(f"Готово: {path} ({size_kb:.0f} КБ)")


if __name__ == "__main__":
    main()
