#!/usr/bin/env python3
"""Служебный скрипт: поиск текста, выходящего за границы блоков или за пределы рисунка.

Каждая диаграмма строится заново, после отрисовки сравниваются габариты подписей
и габариты прямоугольников, внутри которых они размещены.

    python3 check_layout.py [имя_диаграммы ...]
"""

from __future__ import annotations

import sys

from matplotlib.patches import FancyBboxPatch, Rectangle

import charts

TOL = 1.5  # допуск в пикселях отрисовки


def _patches(ax):
    out = []
    for p in ax.patches:
        if isinstance(p, (FancyBboxPatch, Rectangle)) and p.get_visible():
            try:
                out.append((p.get_extents(), p))
            except Exception:
                pass
    return out


def _overflow(name, fig) -> list[str]:
    fig.canvas.draw()
    problems = []
    fig_box = fig.bbox
    for ax in fig.axes:
        boxes = _patches(ax)
        for t in ax.texts:
            if not t.get_text().strip():
                continue
            tb = t.get_window_extent()
            label = " / ".join(t.get_text().splitlines())[:54]
            # подписи в системе координат осей выносятся за область намеренно,
            # итоговый PNG обрезается по фактическому содержимому
            outside_ok = t.get_transform() is ax.transAxes
            if not outside_ok and (tb.x0 < fig_box.x0 - TOL or tb.x1 > fig_box.x1 + TOL
                                   or tb.y0 < fig_box.y0 - TOL or tb.y1 > fig_box.y1 + TOL):
                problems.append(f"{name}: выходит за край рисунка — «{label}»")
                continue
            cx, cy = (tb.x0 + tb.x1) / 2, (tb.y0 + tb.y1) / 2
            host = None
            for pb, _p in boxes:
                if pb.x0 <= cx <= pb.x1 and pb.y0 <= cy <= pb.y1:
                    if host is None or (pb.width * pb.height) < (host.width * host.height):
                        host = pb
            if host is None:
                continue
            dx = max(host.x0 - tb.x0, tb.x1 - host.x1)
            dy = max(host.y0 - tb.y0, tb.y1 - host.y1)
            if dx > TOL or dy > TOL:
                axis = "по ширине" if dx > dy else "по высоте"
                problems.append(f"{name}: текст не влезает в блок {axis} "
                                f"({max(dx, dy):.0f} px) — «{label}»")

        visible = [t for t in ax.texts if t.get_text().strip()]
        for i, a in enumerate(visible):
            ab = a.get_window_extent()
            for b in visible[i + 1:]:
                bb = b.get_window_extent()
                ox = min(ab.x1, bb.x1) - max(ab.x0, bb.x0)
                oy = min(ab.y1, bb.y1) - max(ab.y0, bb.y0)
                if ox > TOL and oy > TOL:
                    la = " / ".join(a.get_text().splitlines())[:34]
                    lb = " / ".join(b.get_text().splitlines())[:34]
                    problems.append(f"{name}: подписи перекрываются "
                                    f"({ox:.0f}×{oy:.0f} px) — «{la}» и «{lb}»")
    return problems


def main() -> None:
    charts.setup_fonts()
    wanted = set(sys.argv[1:])
    problems = []
    for name, fn in charts.CHARTS.items():
        if wanted and name not in wanted:
            continue
        captured = {}
        original = charts._save
        charts._save = lambda fig, n, _c=captured: (_c.setdefault("fig", fig), n)[1]
        try:
            fn()
        finally:
            charts._save = original
        fig = captured.get("fig")
        if fig is None:
            continue
        problems.extend(_overflow(name, fig))
        charts.plt.close(fig)

    if problems:
        for line in problems:
            print(line)
        print(f"\nвсего замечаний: {len(problems)}")
    else:
        print("замечаний нет")


if __name__ == "__main__":
    main()
