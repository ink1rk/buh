"""План помещения: габарит предмета и пересечение прямоугольников.

Поворот 90° и 270° меняет местами ширину и глубину. Касание сторон
пересечением не считается: стойки можно ставить вплотную.
"""

from __future__ import annotations

from dataclasses import dataclass

RACK_WIDTH_MM = 600
PANEL_WIDTH_MM = 800
PANEL_DEPTH_MM = 250


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    width: float
    height: float
    rotation: int = 0


def footprint(box: Box) -> tuple[float, float]:
    if box.rotation % 180 == 90:
        return box.height, box.width
    return box.width, box.height


def bounds(box: Box) -> tuple[float, float, float, float]:
    width, height = footprint(box)
    return box.x, box.y, box.x + width, box.y + height


def overlaps(left: Box, right: Box) -> bool:
    al, at, ar, ab = bounds(left)
    bl, bt, br, bb = bounds(right)
    return al < br and bl < ar and at < bb and bt < ab


def inside(box: Box, room_width_mm: float, room_height_mm: float) -> bool:
    left, top, right, bottom = bounds(box)
    return left >= 0 and top >= 0 and right <= room_width_mm and bottom <= room_height_mm
