#!/usr/bin/env python3
"""Служебный скрипт: рендер страниц PDF в PNG и сборка контактных листов
для визуальной проверки вёрстки.

    python3 preview.py [pdf] [страниц_на_лист]
"""

from __future__ import annotations

import sys
from pathlib import Path

import fitz
from PIL import Image

BASE = Path(__file__).resolve().parent
OUT = BASE / "build" / "preview"


def main() -> None:
    pdf = Path(sys.argv[1]) if len(sys.argv) > 1 else next(BASE.glob("Политика_*.pdf"))
    per_sheet = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("*.png"):
        f.unlink()

    doc = fitz.open(pdf)
    pages = []
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=110)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        pages.append((i + 1, img))

    cols = 3
    rows = (per_sheet + cols - 1) // cols
    for start in range(0, len(pages), per_sheet):
        chunk = pages[start:start + per_sheet]
        cw = max(im.width for _, im in chunk)
        ch = max(im.height for _, im in chunk)
        sheet = Image.new("RGB", (cols * cw + 4 * (cols + 1),
                                  rows * ch + 4 * (rows + 1)), "#8894a0")
        for idx, (num, im) in enumerate(chunk):
            r, c = divmod(idx, cols)
            sheet.paste(im, (4 + c * (cw + 4), 4 + r * (ch + 4)))
        name = f"sheet_{chunk[0][0]:03d}-{chunk[-1][0]:03d}.png"
        sheet.save(OUT / name)
        print(OUT / name)


if __name__ == "__main__":
    main()
