#!/usr/bin/env python3
"""Схема архитектуры ИИ-платформы: точки входа, рабочие среды, модели, интеграции.

Собирает PNG и SVG рядом со скриптом:

    python3 architecture.py

Координатная сетка подобрана так, что одна единица равна 0.1 дюйма по обеим
осям, поэтому скругления и окружности не деформируются.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Circle, Ellipse, FancyArrowPatch, FancyBboxPatch

OUT_DIR = Path(__file__).resolve().parent
BASENAME = "Архитектура_ИИ-платформы"

NAVY = "#15273D"
BLUE = "#2B6CB0"
BLUE_L = "#DDE9F7"
BLUE_T = "#CFE0F2"
TEAL = "#2C8C99"
TEAL_L = "#DAEFF2"
GREEN = "#2E7D5B"
GREEN_L = "#DDEBE3"
AMBER = "#AE7D0C"
AMBER_L = "#FBF0D5"
GREY = "#67737F"
GREY_L = "#EDF1F5"
BAND = "#F5F8FA"
LINE = "#95A3B2"
WHITE = "#FFFFFF"
INK = "#1E2C3A"

UNIT_PT = 7.2  # 1 единица координат = 0.1 дюйма = 7.2 пункта

X0, X1 = 0.0, 166.0
Y0, Y1 = -17.5, 124.0

FONT_CANDIDATES = [
    ("/usr/share/fonts/truetype/macos/Inter-Regular.ttf",
     "/usr/share/fonts/truetype/macos/Inter-Bold.ttf"),
    ("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
     "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
]


def setup_fonts() -> str:
    family = "DejaVu Sans"
    for regular, bold in FONT_CANDIDATES:
        if Path(regular).exists() and Path(bold).exists():
            font_manager.fontManager.addfont(regular)
            font_manager.fontManager.addfont(bold)
            family = font_manager.FontProperties(fname=regular).get_name()
            break
    plt.rcParams.update({
        "font.family": family,
        "figure.facecolor": WHITE,
        "savefig.facecolor": WHITE,
        "text.color": INK,
        "svg.fonttype": "path",
    })
    return family


# --------------------------------------------------------------------------- #
# примитивы                                                                    #
# --------------------------------------------------------------------------- #

def line_h(size: float, lines: int = 1, spacing: float = 1.32) -> float:
    """Высота текстового блока в единицах координат."""
    return lines * size * spacing / UNIT_PT


def text_w(text: str, size: float, factor: float = 0.55) -> float:
    """Оценка ширины строки в единицах координат."""
    widest = max((len(part) for part in text.split("\n")), default=0)
    return widest * size * factor / UNIT_PT


def box(ax, x, y, w, h, *, fill=WHITE, edge=BLUE, lw=1.4, radius=1.2,
        ls="solid", z=2):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0,rounding_size={radius}",
        facecolor=fill, edgecolor=edge, linewidth=lw, linestyle=ls,
        mutation_aspect=1, zorder=z,
    ))


def pill(ax, cx, cy, text, *, fill, fg=WHITE, size=7.2, pad=2.4, z=6):
    w = text_w(text, size) + pad * 2
    h = line_h(size) + 1.2
    box(ax, cx - w / 2, cy - h / 2, w, h, fill=fill, edge=fill,
        radius=h / 2, lw=0.8, z=z)
    ax.text(cx, cy, text, ha="center", va="center", fontsize=size,
            color=fg, weight="bold", zorder=z + 1)


def card(ax, x, y, w, h, title, body=None, tag=None, *, fill=WHITE, edge=BLUE,
         title_color=None, body_color=None, tag_fill=None, tag_color=WHITE,
         title_size=11.0, body_size=8.2, tag_size=7.0, ls="solid", z=2):
    """Карточка: рамка, заголовок, пояснение и необязательная плашка снизу."""
    box(ax, x, y, w, h, fill=fill, edge=edge, ls=ls, z=z)
    cx, top = x + w / 2, y + h

    if body is None and tag is None:
        ax.text(cx, y + h / 2, title, ha="center", va="center",
                fontsize=title_size, color=title_color or edge,
                weight="bold", linespacing=1.32, zorder=z + 1)
        return

    cursor = top - 2.6
    ax.text(cx, cursor, title, ha="center", va="top", fontsize=title_size,
            color=title_color or edge, weight="bold", linespacing=1.32,
            zorder=z + 1)
    cursor -= line_h(title_size, title.count("\n") + 1) + 1.1

    if body:
        ax.text(cx, cursor, body, ha="center", va="top", fontsize=body_size,
                color=body_color or GREY, linespacing=1.36, zorder=z + 1)

    if tag:
        pill(ax, cx, y + 2.5, tag, fill=tag_fill or edge, fg=tag_color,
             size=tag_size, z=z + 2)


def arrow(ax, p0, p1, *, color=LINE, lw=1.5, head=12.0, z=4, both=False):
    ax.add_patch(FancyArrowPatch(
        p0, p1, arrowstyle="<|-|>" if both else "-|>",
        mutation_scale=head, linewidth=lw, color=color,
        shrinkA=0, shrinkB=0, joinstyle="miter", zorder=z,
    ))


def elbow(ax, points, *, color=LINE, lw=1.5, head=12.0, z=4):
    """Ломаная со стрелкой на последнем сегменте."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    ax.plot(xs[:-1], ys[:-1], color=color, lw=lw, solid_capstyle="round",
            solid_joinstyle="round", zorder=z)
    arrow(ax, points[-2], points[-1], color=color, lw=lw, head=head, z=z)


def cylinder(ax, cx, cy, w, h, *, fill, edge, lw=1.3, z=3):
    rx, ry = w / 2, h * 0.16
    ax.add_patch(FancyBboxPatch(
        (cx - rx, cy - h / 2 + ry), w, h - 2 * ry,
        boxstyle="round,pad=0,rounding_size=0",
        facecolor=fill, edgecolor="none", zorder=z))
    for side in (-rx, rx):
        ax.plot([cx + side, cx + side], [cy - h / 2 + ry, cy + h / 2 - ry],
                color=edge, lw=lw, zorder=z + 1)
    ax.add_patch(Ellipse((cx, cy - h / 2 + ry), w, 2 * ry, facecolor=fill,
                         edgecolor=edge, lw=lw, zorder=z))
    ax.add_patch(Ellipse((cx, cy + h / 2 - ry), w, 2 * ry, facecolor=fill,
                         edgecolor=edge, lw=lw, zorder=z + 2))


def person(ax, cx, cy, *, color=WHITE, scale=1.0, z=4):
    ax.add_patch(Circle((cx, cy + 1.9 * scale), 1.25 * scale, facecolor=color,
                        edgecolor="none", zorder=z))
    ax.add_patch(FancyBboxPatch(
        (cx - 1.7 * scale, cy - 2.6 * scale), 3.4 * scale, 3.7 * scale,
        boxstyle="round,pad=0,rounding_size=1.4",
        facecolor=color, edgecolor="none", mutation_aspect=1, zorder=z))


# --------------------------------------------------------------------------- #
# компоновка                                                                   #
# --------------------------------------------------------------------------- #

CENTER = 92.0
CONTENT = (20.0, 164.0)

BANDS = [
    ("ПОЛЬЗОВАТЕЛИ", 102.0, 114.0),
    ("ТОЧКИ ВХОДА", 86.0, 100.0),
    ("РАБОЧИЕ СРЕДЫ И ДАННЫЕ", 60.0, 84.0),
    ("СЛОЙ МОДЕЛЕЙ", 42.0, 58.0),
    ("ШЛЮЗ ИНТЕГРАЦИЙ", 31.0, 40.0),
    ("MCP-СЕРВЕРЫ И ЦЕЛЕВЫЕ СИСТЕМЫ", -1.0, 29.5),
]

ENV_Y, ENV_H = 64.0, 15.5
ENVS = [
    (50.0, "Platform", "рабочая среда\nпользователей", "права: чтение"),
    (79.0, "n8n", "агенты и сценарии\nавтоматизации", "права: чтение и запись"),
    (108.0, "Open Code", "разработка\nи работа с кодом", "права: чтение"),
]
ENV_W = 26.0
ENV_MODE = ["global", "local", "local"]

COL_W, COL_GAP = 26.0, 3.5
MCP_Y, MCP_H = 21.0, 7.0
PROXY_Y, PROXY_H = 11.0, 7.5
SYS_Y, SYS_H = 0.5, 7.0
INTEGRATIONS = [
    ("MCP · HR-системы", "HR Box · HR-Link\nPlanfix", True),
    ("MCP · 1С", "1С", False),
    ("MCP · Express", "Express", False),
    ("MCP · Active Directory", "Active Directory", False),
    ("MCP · Git", "Git", False),
]

LEGEND = [
    (NAVY, NAVY, "solid", "пользователи и корпоративные системы"),
    (TEAL_L, TEAL, "solid", "вход и аутентификация"),
    (BLUE_L, BLUE, "solid", "компоненты ИИ-платформы"),
    (GREEN_L, GREEN, "solid", "локальные модели"),
    (AMBER_L, AMBER, "dashed", "внешние сервисы за периметром"),
    (GREY_L, GREY, "dashed", "инфраструктура и хранилища"),
]

FOOTNOTES = (
    "global — среде разрешён вызов внешних моделей, local — только модели "
    "внутри периметра.    Права чтения и записи определяют, "
    "что среда может делать в корпоративных системах через MCP-инструменты."
)


def build(ax) -> None:
    # --- фон полос и их подписи ------------------------------------------- #
    for idx, (label, low, high) in enumerate(BANDS):
        if idx % 2 == 0:
            box(ax, 17.0, low, 148.0, high - low, fill=BAND, edge="none",
                lw=0, radius=1.5, z=0)
        ax.text(10.5, (low + high) / 2, label, rotation=90, ha="center",
                va="center", fontsize=8.4, color=GREY, weight="bold", zorder=1)

    # --- заголовок --------------------------------------------------------- #
    ax.text(X0 + 10.5, 121.0, "Архитектура ИИ-платформы",
            ha="left", va="center", fontsize=19, color=NAVY, weight="bold")
    ax.text(X0 + 10.5, 116.5,
            "единая точка входа для сотрудников, единая точка доступа "
            "к моделям и единый шлюз к корпоративным системам",
            ha="left", va="center", fontsize=10.2, color=GREY)

    # --- пользователи ------------------------------------------------------ #
    card(ax, 74.0, 104.0, 36.0, 8.0, "", fill=NAVY, edge=NAVY)
    person(ax, 81.0, 108.0, color=WHITE)
    ax.text(97.5, 109.4, "Пользователь", ha="center", va="center",
            fontsize=11.0, color=WHITE, weight="bold", zorder=4)
    ax.text(97.5, 106.4, "сотрудник компании", ha="center", va="center",
            fontsize=8.0, color=BLUE_T, zorder=4)

    # --- точки входа ------------------------------------------------------- #
    card(ax, 22.0, 88.0, 44.0, 10.0, "CLI + API-ключ",
         "сервисный и скриптовый доступ:\n"
         "прямой вызов моделей в обход рабочих сред",
         fill=TEAL_L, edge=TEAL, title_size=11.5, body_size=8.2)
    card(ax, 70.0, 88.0, 44.0, 10.0, "Active Directory",
         "вход по корпоративной учётной записи\n"
         "с двухфакторным подтверждением",
         fill=TEAL_L, edge=TEAL, title_size=11.5, body_size=8.2)

    elbow(ax, [(74.0, 109.4), (44.0, 109.4), (44.0, 98.0)])
    arrow(ax, (CENTER, 104.0), (CENTER, 98.0))

    # --- рабочие среды ----------------------------------------------------- #
    box(ax, 47.0, 61.0, 90.0, 22.0, fill=WHITE, edge=GREY, lw=1.2,
        ls=(0, (5, 3)), radius=1.6, z=1)
    ax.text(49.5, 62.4, "Kubernetes-кластер", ha="left", va="center",
            fontsize=8.4, color=GREY, weight="bold", zorder=3)

    # единый вход раздаётся во все среды кластера
    bus_y = 81.3
    ax.plot([CENTER, CENTER], [88.0, bus_y], color=LINE, lw=1.5, zorder=4)
    ax.plot([ENVS[0][0] + ENV_W / 2, ENVS[-1][0] + ENV_W / 2], [bus_y, bus_y],
            color=LINE, lw=1.5, solid_capstyle="round", zorder=4)
    pill(ax, CENTER, 85.5, "2FA", fill=GREEN)

    for (x, title, body, tag), mode in zip(ENVS, ENV_MODE):
        card(ax, x, ENV_Y, ENV_W, ENV_H, title, body, tag,
             fill=BLUE_L, edge=BLUE, title_size=12.0, body_size=8.2,
             tag_fill=BLUE, tag_size=7.0)
        cx = x + ENV_W / 2
        arrow(ax, (cx, bus_y), (cx, ENV_Y + ENV_H))
        arrow(ax, (cx, ENV_Y), (cx, 55.0))
        pill(ax, cx, 59.6, mode, fill=GREY)

    box(ax, 142.0, 62.0, 22.0, 17.5, fill=GREY_L, edge=GREY, ls=(0, (5, 3)))
    cylinder(ax, 153.0, 75.6, 9.0, 5.4, fill=WHITE, edge=GREY)
    ax.text(153.0, 71.2, "Векторная база\nданных", ha="center", va="top",
            fontsize=9.4, color=INK, weight="bold", linespacing=1.32, zorder=3)
    ax.text(153.0, 66.6, "контекст и поиск\nпо документам (RAG)",
            ha="center", va="top", fontsize=7.8, color=GREY, linespacing=1.36,
            zorder=3)
    arrow(ax, (134.0, 71.0), (142.0, 71.0))

    # --- слой моделей ------------------------------------------------------ #
    box(ax, 47.0, 45.0, 90.0, 10.0, fill=BLUE, edge=BLUE, radius=1.4, z=2)
    ax.text(CENTER, 51.4, "LiteLLM", ha="center", va="center", fontsize=13.5,
            color=WHITE, weight="bold", zorder=3)
    ax.text(CENTER, 47.8,
            "единая точка доступа к моделям: маршрутизация запросов, квоты, "
            "учёт расхода и журнал вызовов",
            ha="center", va="center", fontsize=8.6, color=BLUE_T, zorder=3)

    card(ax, 20.0, 43.0, 22.0, 14.0, "Внешние\nИИ-сервисы",
         "Grok, ChatGPT\nи другие", "внешний контур",
         fill=AMBER_L, edge=AMBER, ls=(0, (5, 3)), title_size=9.8,
         body_size=8.0, tag_fill=AMBER, tag_size=6.8)
    card(ax, 142.0, 43.0, 22.0, 14.0, "QWEN",
         "локальная модель\nна собственных\nмощностях",
         fill=GREEN_L, edge=GREEN, title_size=11.5, body_size=8.0)

    arrow(ax, (47.0, 50.0), (42.0, 50.0), both=True)
    arrow(ax, (137.0, 50.0), (142.0, 50.0), both=True)
    elbow(ax, [(44.0, 88.0), (44.0, 57.6), (51.0, 57.6), (51.0, 55.0)])

    # --- шлюз -------------------------------------------------------------- #
    box(ax, 20.0, 32.0, 144.0, 8.0, fill=BLUE, edge=BLUE, radius=1.4, z=2)
    ax.text(CENTER, 37.4, "Шлюз MCP", ha="center", va="center", fontsize=13.0,
            color=WHITE, weight="bold", zorder=3)
    ax.text(CENTER, 34.2,
            "единая точка подключения инструментов: проверка прав, "
            "журналирование вызовов, единые правила доступа",
            ha="center", va="center", fontsize=8.6, color=BLUE_T, zorder=3)
    arrow(ax, (CENTER, 45.0), (CENTER, 40.0))

    # --- MCP-серверы и целевые системы ------------------------------------- #
    left = CONTENT[0]
    for idx, (mcp_title, sys_title, external) in enumerate(INTEGRATIONS):
        x = left + idx * (COL_W + COL_GAP)
        cx = x + COL_W / 2

        card(ax, x, MCP_Y, COL_W, MCP_H, mcp_title,
             fill=BLUE_L, edge=BLUE, title_size=9.8)
        arrow(ax, (cx, 32.0), (cx, MCP_Y + MCP_H))

        if external:
            card(ax, x, PROXY_Y, COL_W, PROXY_H, "MCP провайдера",
                 "на стороне поставщика", fill=AMBER_L, edge=AMBER,
                 ls=(0, (5, 3)), title_size=9.2, title_color=INK,
                 body_size=7.6)
            arrow(ax, (cx, MCP_Y), (cx, PROXY_Y + PROXY_H))
            arrow(ax, (cx, PROXY_Y), (cx, SYS_Y + SYS_H))
            card(ax, x, SYS_Y, COL_W, SYS_H, sys_title, fill=AMBER_L,
                 edge=AMBER, ls=(0, (5, 3)), title_size=9.6, title_color=INK)
        else:
            arrow(ax, (cx, MCP_Y), (cx, SYS_Y + SYS_H))
            card(ax, x, SYS_Y, COL_W, SYS_H, sys_title, fill=NAVY, edge=NAVY,
                 title_size=10.5, title_color=WHITE)

    # --- легенда и сноски --------------------------------------------------- #
    for idx, (fill, edge, ls, label) in enumerate(LEGEND):
        x = CONTENT[0] + (idx % 3) * 48.0
        cy = -5.0 - (idx // 3) * 4.6
        box(ax, x, cy - 1.5, 3.4, 3.0, fill=fill, edge=edge, lw=1.2, ls=ls,
            radius=0.7, z=2)
        ax.text(x + 4.8, cy, label, ha="left", va="center", fontsize=8.2,
                color=GREY, zorder=3)

    ax.text(CONTENT[0], -14.6, FOOTNOTES, ha="left", va="center", fontsize=8.2,
            color=GREY, zorder=3)


def main() -> None:
    setup_fonts()
    fig = plt.figure(figsize=((X1 - X0) / 10.0, (Y1 - Y0) / 10.0))
    ax = fig.add_axes((0.0, 0.0, 1.0, 1.0))
    ax.set_xlim(X0, X1)
    ax.set_ylim(Y0, Y1)
    ax.axis("off")

    build(ax)

    for ext in ("png", "svg", "pdf"):
        path = OUT_DIR / f"{BASENAME}.{ext}"
        fig.savefig(path, dpi=200)
        print(f"{path}  ({path.stat().st_size / 1024:.0f} КБ)")
    plt.close(fig)


if __name__ == "__main__":
    main()
