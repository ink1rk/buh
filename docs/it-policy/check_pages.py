#!/usr/bin/env python3
"""Служебный скрипт: поиск висячих заголовков в готовом PDF.

Заголовок считается висячим, если ниже него на странице нет ни текста, ни рисунка,
ни таблицы.

    python3 check_pages.py [pdf]
"""

from __future__ import annotations

import sys
from pathlib import Path

import pymupdf

BASE = Path(__file__).resolve().parent
HEAD_COLORS = {0x2B6CB0, 0x14263C}  # синий H2 и тёмный H3


def main() -> None:
    pdf = Path(sys.argv[1]) if len(sys.argv) > 1 else next(BASE.glob("Политика_*.pdf"))
    doc = pymupdf.open(pdf)
    problems = []
    for page in doc:
        body_bottom = page.rect.height - 52  # выше колонтитула
        spans = []
        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    if span["text"].strip() and span["bbox"][3] < body_bottom:
                        spans.append(span)
        if not spans:
            continue
        # страницы оглавления пропускаем: там точечная отбивка, а не заголовки
        if sum(1 for s in spans if s["text"].count(".") >= 5) > 5:
            continue
        if not spans:
            continue
        spans.sort(key=lambda s: (s["bbox"][3], s["bbox"][0]))
        last = spans[-1]
        is_head = last["color"] in HEAD_COLORS and last["size"] > 9.0 and "Bold" in last["font"]
        if not is_head:
            continue
        # рисунки и заливки таблиц текстом не считаются, но содержимым являются
        below = [r.y1 for x in page.get_images(full=True) for r in page.get_image_rects(x[0])]
        below += [d["rect"].y1 for d in page.get_drawings()]
        if any(last["bbox"][3] + 2 < y < body_bottom for y in below):
            continue
        problems.append(f"стр. {page.number + 1}: страница заканчивается заголовком "
                        f"«{last['text'].strip()[:50]}»")

    print("\n".join(problems) if problems else "замечаний нет")
    if problems:
        print(f"\nвсего замечаний: {len(problems)}")


if __name__ == "__main__":
    main()
