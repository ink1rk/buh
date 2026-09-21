"""Диаграммы и графики для Политики отдела технической инфраструктуры.

Каждая функция строит один рисунок и возвращает путь к PNG-файлу.
Все рисунки собираются в каталог build/charts/.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Rectangle, Wedge

OUT_DIR = Path(__file__).resolve().parent / "build" / "charts"

NAVY = "#14263C"
BLUE = "#2B6CB0"
BLUE_L = "#D8E6F3"
TEAL = "#2C8C99"
TEAL_L = "#D6ECEF"
GREEN = "#2E7D5B"
GREEN_L = "#DCEBE3"
AMBER = "#C98A0B"
AMBER_L = "#FAEDD2"
RED = "#B33A3A"
RED_L = "#F6DEDE"
GREY = "#6B7785"
GREY_L = "#EDF1F5"
WHITE = "#FFFFFF"
INK = "#20303F"

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/macos/Inter-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]
_FONT_BOLD_CANDIDATES = [
    "/usr/share/fonts/truetype/macos/Inter-SemiBold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def setup_fonts() -> str:
    family = "DejaVu Sans"
    for path in _FONT_CANDIDATES + _FONT_BOLD_CANDIDATES:
        p = Path(path)
        if p.exists():
            font_manager.fontManager.addfont(str(p))
    for path in _FONT_CANDIDATES:
        p = Path(path)
        if p.exists():
            family = font_manager.FontProperties(fname=str(p)).get_name()
            break
    plt.rcParams["font.family"] = family
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.facecolor"] = WHITE
    plt.rcParams["savefig.facecolor"] = WHITE
    plt.rcParams["text.color"] = INK
    plt.rcParams["axes.labelcolor"] = INK
    plt.rcParams["xtick.color"] = GREY
    plt.rcParams["ytick.color"] = GREY
    return family


def _save(fig, name: str) -> str:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{name}.png"
    fig.savefig(path, dpi=210, bbox_inches="tight", pad_inches=0.06)
    plt.close(fig)
    return str(path)


def _fill(text: str, width: int) -> str:
    """Переносит текст по ширине, сохраняя явные переводы строк и пустые строки."""
    out = []
    for line in text.split("\n"):
        out.append(textwrap.fill(line, width) if line.strip() else "")
    return "\n".join(out)


def _blank_axes(fig_w, fig_h, xlim=(0, 100), ylim=(0, 100)):
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.axis("off")
    return fig, ax


def _box(
    ax,
    x,
    y,
    w,
    h,
    text,
    fill=WHITE,
    edge=BLUE,
    fg=INK,
    fontsize=8.5,
    wrap=22,
    weight="normal",
    radius=1.6,
    lw=1.1,
    ls="solid",
    align="center",
):
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle=f"round,pad=0,rounding_size={radius}",
            linewidth=lw,
            edgecolor=edge,
            facecolor=fill,
            linestyle=ls,
            mutation_aspect=1,
        )
    )
    if text:
        ax.text(
            x + w / 2,
            y + h / 2,
            _fill(text, wrap),
            ha="center",
            va="center",
            fontsize=fontsize,
            color=fg,
            weight=weight,
            linespacing=1.32,
            multialignment=align,
        )


def _arrow(ax, p1, p2, color=GREY, lw=1.2, ls="solid", style="-|>", rad=0.0, mut=9):
    ax.add_patch(
        FancyArrowPatch(
            p1,
            p2,
            arrowstyle=style,
            mutation_scale=mut,
            linewidth=lw,
            color=color,
            linestyle=ls,
            connectionstyle=f"arc3,rad={rad}",
            shrinkA=1,
            shrinkB=1,
        )
    )


def _elbow(ax, x1, y1, x2, y2, color=GREY, lw=1.2, ls="solid"):
    ymid = (y1 + y2) / 2
    ax.plot([x1, x1], [y1, ymid], color=color, lw=lw, ls=ls, solid_capstyle="round")
    ax.plot([x1, x2], [ymid, ymid], color=color, lw=lw, ls=ls, solid_capstyle="round")
    _arrow(ax, (x2, ymid), (x2, y2), color=color, lw=lw, ls=ls)


def _grid_style(ax, axis="y"):
    ax.grid(axis=axis, color="#E3E9EF", lw=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#C9D3DC")


# --------------------------------------------------------------------------------------
# 1. Организационная структура
# --------------------------------------------------------------------------------------
def org_structure() -> str:
    fig, ax = _blank_axes(9.6, 5.6)

    _box(ax, 34, 86, 32, 10, "Генеральный директор / Правление", fill=GREY_L,
         edge=GREY, wrap=30, fontsize=8.5)
    _box(ax, 34, 69, 32, 11, "ИТ-директор", fill=NAVY, edge=NAVY, fg=WHITE,
         fontsize=10, weight="bold", wrap=26)
    _box(ax, 31, 50, 38, 12,
         "Руководитель отдела\nтехнической инфраструктуры (ОТИ)",
         fill=BLUE, edge=BLUE, fg=WHITE, fontsize=9.5, weight="bold", wrap=34)

    ax.plot([50, 50], [86, 80], color=GREY, lw=1.3)
    _arrow(ax, (50, 69), (50, 62), color=NAVY, lw=1.4)

    groups = [
        (2, "Системное\nадминистрирование", "2 ведущих системных\nадминистратора\n(2-я линия)", TEAL, TEAL_L),
        (35, "Сетевая\nинфраструктура", "1 ведущий сетевой\nинженер\n(2-я линия)", TEAL, TEAL_L),
        (68, "Служба поддержки\nпользователей", "Руководитель 1-й линии\n+ 2 специалиста\n(1-я линия)", TEAL, TEAL_L),
    ]
    for x, title, staff, edge, fill in groups:
        _box(ax, x, 27, 30, 10, title, fill=fill, edge=edge, fontsize=9, weight="bold", wrap=26)
        _box(ax, x, 11, 30, 13, staff, fill=WHITE, edge=GREY, fontsize=8, wrap=28)
        _elbow(ax, 50, 50, x + 15, 37, color=BLUE, lw=1.2)
        _arrow(ax, (x + 15, 27), (x + 15, 24), color=GREY, lw=1.0)

    _box(ax, 2, 46, 26, 42, "", fill="#FBFCFD", edge=GREY, ls="dashed")
    ax.text(15, 84, "Смежные подразделения", ha="center", fontsize=7.6, color=NAVY, weight="bold")
    for i, t in enumerate(["Отдел информационной\nбезопасности", "Отдел 1С и\nбизнес-приложений",
                           "Закупки", "Сервис-менеджер\n(склад, учёт техники)"]):
        ax.text(15, 77 - i * 7.5, t, ha="center", va="center", fontsize=6.8, color=INK,
                linespacing=1.3)
    ax.text(15, 49, "взаимодействие, не подчинение", ha="center", va="center",
            fontsize=6.6, color=GREY, style="italic")
    ax.plot([28, 31], [58, 58], color=GREY, lw=1.0, ls="dashed")

    _box(ax, 72, 46, 26, 42, "", fill="#FBFCFD", edge=GREY, ls="dashed")
    ax.text(85, 84, "Внешние подрядчики", ha="center", fontsize=7.6, color=NAVY, weight="bold")
    ax.text(85, 65, "Привлекаются на сложные\nработы, которые не могут\nбыть выполнены\nсобственными силами.\n\n"
                    "Доступ — только временный,\nпо решению ИБ",
            ha="center", va="center", fontsize=6.8, color=INK, linespacing=1.45)
    ax.plot([69, 72], [58, 58], color=GREY, lw=1.0, ls="dashed")

    return _save(fig, "org_structure")


# --------------------------------------------------------------------------------------
# 2. Зрелость процессов: текущее и целевое состояние
# --------------------------------------------------------------------------------------
def maturity_radar() -> str:
    labels = [
        "Управление\nобращениями",
        "Управление\nизменениями",
        "Каталог\nсервисов",
        "Мониторинг",
        "Резервное копирование\nи DR",
        "Управление\nдоступом",
        "Документирование",
        "Отчётность\nи контроль",
    ]
    current = [3.0, 1.6, 1.2, 2.0, 2.4, 2.2, 1.4, 1.5]
    target = [4.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0, 3.5]

    angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
    angles += angles[:1]
    cur = current + current[:1]
    tgt = target + target[:1]

    fig, ax = plt.subplots(figsize=(7.4, 5.6), subplot_kw={"polar": True})
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.plot(angles, tgt, color=TEAL, lw=1.6, label="Целевой уровень (12 месяцев)")
    ax.fill(angles, tgt, color=TEAL, alpha=0.12)
    ax.plot(angles, cur, color=BLUE, lw=1.8, label="Оценка текущего уровня")
    ax.fill(angles, cur, color=BLUE, alpha=0.18)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=7.6)
    ax.set_yticks([1, 2, 3, 4, 5])
    ax.set_yticklabels(["1", "2", "3", "4", "5"], fontsize=7, color=GREY)
    ax.set_ylim(0, 5)
    ax.grid(color="#DCE3EA", lw=0.8)
    ax.spines["polar"].set_color("#DCE3EA")
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.19), frameon=False, fontsize=8, ncol=2)
    ax.set_title("Уровень зрелости процессов ОТИ, шкала 1–5", fontsize=9.5, pad=18, color=NAVY)
    return _save(fig, "maturity_radar")


# --------------------------------------------------------------------------------------
# 3. Линии поддержки
# --------------------------------------------------------------------------------------
def support_lines() -> str:
    fig, ax = _blank_axes(9.8, 4.8)
    ax.text(50, 96, "Маршрут обращения и линии поддержки", ha="center", fontsize=10.5,
            color=NAVY, weight="bold")
    ax.text(50, 90, "Обращение передаётся на следующую линию только с результатами "
                    "диагностики предыдущей",
            ha="center", fontsize=7.8, color=GREY, style="italic")

    blocks = [
        ("Пользователь", "более 600 сотрудников\n11 площадок\n+ удалённые сотрудники",
         GREY, GREY_L),
        ("Единая точка входа", "help@exon-group.ru\n→ Итилиум\n100 % обращений", BLUE, BLUE_L),
        ("1-я линия", "руководитель\n+ 2 специалиста\nприём, классификация,\n"
                      "типовые операции", TEAL, TEAL_L),
        ("2-я линия", "2 системных админ.\n+ сетевой инженер\nсерверы, сеть, AD,\n"
                      "почта, СХД, backup", TEAL, TEAL_L),
        ("3-я линия", "вендоры и подрядчики\nпривлекает 2-я линия\nпо согласованию\n"
                      "с руководителем ОТИ", AMBER, AMBER_L),
    ]
    w, gap = 18.4, 1.6
    for i, (title, body, edge, fill) in enumerate(blocks):
        x = 1 + i * (w + gap)
        _box(ax, x, 44, w, 38, "", fill=fill, edge=edge, radius=1.4)
        ax.text(x + w / 2, 76, title, ha="center", fontsize=8.6, color=edge, weight="bold")
        ax.text(x + w / 2, 60, body, ha="center", va="center", fontsize=6.8, color=INK,
                linespacing=1.5)
        if i < len(blocks) - 1:
            _arrow(ax, (x + w, 63), (x + w + gap, 63), color=NAVY, lw=1.4, mut=11)

    _box(ax, 21, 10, 57, 22, "", fill="#FBFCFD", edge=GREY, ls="dashed", radius=1.4)
    ax.text(49.5, 26, "Смежные подразделения", ha="center", fontsize=7.8, color=NAVY,
            weight="bold")
    ax.text(49.5, 17, "отдел ИБ (инциденты и доступы) · отдел 1С (прикладной уровень) ·\n"
                      "сервис-менеджер (склад и учёт техники)\n"
                      "Задачи передаются заявкой в Итилиуме, а не «в обход»",
            ha="center", va="center", fontsize=6.9, color=INK, linespacing=1.45)
    _arrow(ax, (40, 44), (40, 32), color=GREY, lw=1.0, ls="dashed")
    _arrow(ax, (60, 44), (60, 32), color=GREY, lw=1.0, ls="dashed")
    return _save(fig, "support_lines")


# --------------------------------------------------------------------------------------
# 4. Границы ответственности
# --------------------------------------------------------------------------------------
def responsibility_scope() -> str:
    fig, ax = _blank_axes(9.6, 6.2)

    ax.text(50, 97, "Контур ответственности ОТИ и границы со смежными подразделениями",
            ha="center", fontsize=10, color=NAVY, weight="bold")

    _box(ax, 2, 25, 62, 65, "", fill="#F7FAFC", edge=BLUE, lw=1.6, radius=2.2)
    ax.text(33, 86, "Зона ответственности ОТИ", ha="center", fontsize=9.2,
            color=BLUE, weight="bold")

    items = [
        "Серверы и ОС", "Виртуализация", "СХД и хранение",
        "ЛВС, VLAN, маршрутизация", "Wi-Fi", "Firewall (администрирование)",
        "AD / DNS / DHCP", "VPN и удалённый доступ", "Почта Exchange",
        "Файловые хранилища", "Рабочие станции и ноутбуки", "Периферия и печать",
        "Телефония", "Видеонаблюдение", "Резервное копирование",
        "Мониторинг", "Облачные сервисы", "Учёт лицензий (техучёт)",
        "Каналы связи, провайдеры", "Инфраструктура 1С (серверы, БД)",
        "Подрядчики (техработы)", "Техническая документация",
    ]
    cols, x0, y0, w, h, gx, gy = 3, 4.5, 78, 19, 6.2, 0.7, 1.0
    for i, it in enumerate(items):
        r, c = divmod(i, cols)
        _box(ax, x0 + c * (w + gx), y0 - r * (h + gy), w, h, it,
             fill=WHITE, edge="#B9CFE4", fontsize=6.8, wrap=24, radius=1.0, lw=0.9)

    outs = [
        ("Отдел ИБ", "Политики и контроль ИБ,\nинциденты ИБ, блокировка\nУЗ, выдача доступов\nподрядчикам", RED, RED_L),
        ("Отдел 1С", "Прикладной уровень 1С:\nконфигурации, доработки,\nучётная логика, права\nв прикладных системах", AMBER, AMBER_L),
        ("Закупки", "Закупочные процедуры,\nдоговоры, поставщики,\nоплата", GREEN, GREEN_L),
    ]
    for i, (title, body, edge, fill) in enumerate(outs):
        y = 69 - i * 21.5
        _box(ax, 68, y, 30, 19, "", fill=fill, edge=edge, radius=1.6)
        ax.text(83, y + 15.4, title, ha="center", fontsize=8.6, color=edge, weight="bold")
        ax.text(83, y + 7.4, body, ha="center", va="center", fontsize=7.0, color=INK,
                linespacing=1.35)

    _box(ax, 2, 4, 96, 18,
         "Общие («серые») зоны: инфраструктурная часть ИБ (сегментация, патчи, антивирус, MFA, журналирование) — "
         "реализует ОТИ, требования и контроль устанавливает ИБ. Инфраструктура 1С (серверы, СУБД, резервные копии, "
         "производительность) — ОТИ; прикладная часть — отдел 1С. Технические требования к закупаемому оборудованию и ПО — "
         "ОТИ; закупочная процедура — закупки. Спорные зоны разбираются по п. 5.7 настоящей Политики.",
         fill="#FFFDF5", edge=AMBER, fontsize=7.4, wrap=118, radius=1.6, align="left")
    return _save(fig, "responsibility_scope")


# --------------------------------------------------------------------------------------
# 5. Классы критичности сервисов
# --------------------------------------------------------------------------------------
def criticality_pyramid() -> str:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.6, 3.9), gridspec_kw={"width_ratios": [1.25, 1]})
    ax1.set_xlim(0, 100)
    ax1.set_ylim(0, 100)
    ax1.axis("off")

    levels = [
        ("A — критичные", "Простой останавливает\nработу компании", RED, RED_L, 22, 74),
        ("B — важные", "Простой существенно\nзатрудняет работу", AMBER, AMBER_L, 15, 55),
        ("C — стандартные", "Простой создаёт\nнеудобства", BLUE, BLUE_L, 8, 36),
        ("D — вспомогательные", "Влияние на бизнес\nминимально", GREY, GREY_L, 1, 17),
    ]
    for name, desc, edge, fill, x, y in levels:
        w = 100 - 2 * x
        _box(ax1, x, y, w, 17, "", fill=fill, edge=edge, radius=1.4)
        ax1.text(50, y + 11.5, name, ha="center", fontsize=8.8, color=edge, weight="bold")
        ax1.text(50, y + 5.0, desc, ha="center", va="center", fontsize=7.0, color=INK, linespacing=1.3)
    ax1.text(50, 96, "Классы критичности ИТ-сервисов", ha="center", fontsize=9.5,
             color=NAVY, weight="bold")
    ax1.text(50, 8, "Класс присваивается совместно ОТИ и владельцем сервиса,\n"
                    "утверждается ИТ-директором",
             ha="center", fontsize=7, color=GREY, style="italic", linespacing=1.3)

    classes = ["A", "B", "C", "D"]
    counts = [7, 9, 11, 6]
    colors = [RED, AMBER, BLUE, GREY]
    bars = ax2.bar(classes, counts, color=colors, width=0.6)
    for b, c in zip(bars, counts):
        ax2.text(b.get_x() + b.get_width() / 2, c + 0.25, str(c), ha="center",
                 fontsize=8.5, color=INK, weight="bold")
    ax2.set_title("Ориентировочное распределение\nсервисов каталога по классам",
                  fontsize=9.2, color=NAVY)
    ax2.set_ylabel("количество сервисов", fontsize=7.6)
    ax2.set_ylim(0, max(counts) + 2.5)
    ax2.tick_params(labelsize=8)
    _grid_style(ax2)
    return _save(fig, "criticality_pyramid")


# --------------------------------------------------------------------------------------
# 6. Жизненный цикл сервиса
# --------------------------------------------------------------------------------------
def service_lifecycle() -> str:
    fig, ax = _blank_axes(9.6, 3.2)
    stages = [
        ("Потребность", "инициатор,\nвладелец процесса", BLUE_L, BLUE),
        ("Проектирование", "архитектура,\nтехнические требования", BLUE_L, BLUE),
        ("Внедрение", "план внедрения,\nтестирование", TEAL_L, TEAL),
        ("Ввод в\nэксплуатацию", "паспорт сервиса,\nмониторинг, backup", GREEN_L, GREEN),
        ("Эксплуатация", "SLA, изменения,\nревизия 1 раз в год", GREEN_L, GREEN),
        ("Вывод из\nэксплуатации", "архивация данных,\nотзыв доступов", GREY_L, GREY),
    ]
    w, gap = 14.6, 2.4
    for i, (title, desc, fill, edge) in enumerate(stages):
        x = 1 + i * (w + gap)
        _box(ax, x, 34, w, 34, "", fill=fill, edge=edge, radius=1.4)
        ax.text(x + w / 2, 58, title, ha="center", va="center", fontsize=8.3,
                color=edge, weight="bold", linespacing=1.25)
        ax.text(x + w / 2, 43, desc, ha="center", va="center", fontsize=6.5,
                color=INK, linespacing=1.35)
        if i < len(stages) - 1:
            _arrow(ax, (x + w, 51), (x + w + gap, 51), color=NAVY, lw=1.3, mut=10)

    ax.text(50, 88, "Жизненный цикл ИТ-сервиса", ha="center", fontsize=10,
            color=NAVY, weight="bold")
    ax.text(50, 79, "Сервис считается введённым в эксплуатацию только при наличии паспорта, мониторинга, "
                    "резервного копирования и документации",
            ha="center", fontsize=7.6, color=GREY, style="italic")
    _box(ax, 1, 8, 98, 16,
         "Контрольная точка ОТИ на каждом этапе: без паспорта сервиса и записи в реестре сервис не принимается "
         "на поддержку, обращения по нему обрабатываются как консультации, SLA не применяется",
         fill="#FFFDF5", edge=AMBER, fontsize=7.4, wrap=112, radius=1.4)
    return _save(fig, "service_lifecycle")


# --------------------------------------------------------------------------------------
# 7. Процесс обработки обращений
# --------------------------------------------------------------------------------------
def request_flow() -> str:
    fig, ax = _blank_axes(9.6, 6.4)
    ax.text(50, 98, "Процесс обработки обращения", ha="center", fontsize=10,
            color=NAVY, weight="bold")

    steps = [
        (30, 88, 40, 8, "Обращение: help@exon-group.ru / портал Итилиум", BLUE_L, BLUE),
        (30, 76, 40, 8, "Регистрация заявки в Итилиуме (автоматически)", WHITE, BLUE),
        (30, 64, 40, 8, "1-я линия: классификация, категория, приоритет", TEAL_L, TEAL),
        (30, 52, 40, 8, "Диагностика и попытка решения на 1-й линии", WHITE, TEAL),
        (30, 40, 40, 8, "Передача на 2-ю линию с результатами диагностики", WHITE, TEAL),
        (30, 28, 40, 8, "Решение, проверка результата с пользователем", WHITE, GREEN),
        (30, 16, 40, 8, "Закрытие заявки с описанием решения", GREEN_L, GREEN),
    ]
    for x, y, w, h, t, fill, edge in steps:
        _box(ax, x, y, w, h, t, fill=fill, edge=edge, fontsize=7.8, wrap=50, radius=1.2)
    for y in (88, 76, 64, 52, 40, 28):
        _arrow(ax, (50, y), (50, y - 4), color=NAVY, lw=1.2)

    _box(ax, 1, 60, 26, 16,
         "Обращение поступило вне Итилиума\n(лично, телефон, мессенджер)\n→ сотрудник ОТИ сам создаёт заявку "
         "и просит инициатора в дальнейшем писать на help@",
         fill=AMBER_L, edge=AMBER, fontsize=7.0, wrap=34, radius=1.2)
    _arrow(ax, (27, 68), (30, 68), color=AMBER, lw=1.2, ls="dashed")

    _box(ax, 73, 60, 26, 16,
         "Обращение содержит признаки\nинцидента ИБ\n→ немедленное уведомление отдела ИБ, "
         "дальнейшие действия по указанию ИБ",
         fill=RED_L, edge=RED, fontsize=7.0, wrap=34, radius=1.2)
    _arrow(ax, (70, 68), (73, 68), color=RED, lw=1.2, ls="dashed")

    _box(ax, 73, 36, 26, 16,
         "Требуется изменение\nинфраструктуры\n→ оформляется RFC,\nдалее процесс управления\nизменениями (раздел 8)",
         fill=BLUE_L, edge=BLUE, fontsize=7.0, wrap=34, radius=1.2)
    _arrow(ax, (70, 44), (73, 44), color=BLUE, lw=1.2, ls="dashed")

    _box(ax, 1, 36, 26, 16,
         "Требуется 3-я линия\n(вендор, подрядчик)\n→ согласование с руководителем ОТИ, "
         "заявка остаётся на контроле 2-й линии",
         fill=GREY_L, edge=GREY, fontsize=7.0, wrap=34, radius=1.2)
    _arrow(ax, (30, 44), (27, 44), color=GREY, lw=1.2, ls="dashed")

    _box(ax, 1, 4, 98, 9,
         "Заявка не может быть закрыта без: описания причины, описания выполненных действий, отметки категории "
         "и подтверждения пользователя (для запросов на обслуживание)",
         fill="#F7FAFC", edge=BLUE, fontsize=7.4, wrap=118, radius=1.2)
    return _save(fig, "request_flow")


# --------------------------------------------------------------------------------------
# 8. Матрица приоритетов
# --------------------------------------------------------------------------------------
def priority_matrix() -> str:
    fig, ax = plt.subplots(figsize=(7.6, 4.2))
    urgency = ["Низкая", "Средняя", "Высокая", "Критическая"]
    impact = ["Один\nпользователь", "Группа\nпользователей", "Площадка /\nподразделение", "Компания /\nкритичный сервис"]
    matrix = [
        [4, 4, 3, 2],
        [4, 3, 3, 2],
        [3, 3, 2, 1],
        [2, 2, 1, 1],
    ]
    colors = {1: RED, 2: AMBER, 3: BLUE, 4: GREY}
    labels = {1: "P1", 2: "P2", 3: "P3", 4: "P4"}
    for i in range(4):
        for j in range(4):
            v = matrix[i][j]
            ax.add_patch(Rectangle((j, i), 1, 1, facecolor=colors[v], edgecolor=WHITE, lw=2, alpha=0.88))
            ax.text(j + 0.5, i + 0.5, labels[v], ha="center", va="center",
                    fontsize=11, color=WHITE, weight="bold")
    ax.set_xlim(0, 4)
    ax.set_ylim(0, 4)
    ax.set_xticks(np.arange(4) + 0.5)
    ax.set_xticklabels(impact, fontsize=7.6)
    ax.set_yticks(np.arange(4) + 0.5)
    ax.set_yticklabels(urgency, fontsize=8)
    ax.set_xlabel("Влияние (масштаб)", fontsize=8.5, labelpad=8)
    ax.set_ylabel("Срочность", fontsize=8.5, labelpad=8)
    ax.set_title("Матрица определения приоритета заявки", fontsize=9.8, color=NAVY, pad=12)
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    legend = "P1 — критический · P2 — высокий · P3 — обычный · P4 — низкий"
    ax.text(0.5, -0.24, legend, ha="center", va="top", fontsize=7.8, color=GREY,
            transform=ax.transAxes)
    return _save(fig, "priority_matrix")


# --------------------------------------------------------------------------------------
# 9. Эскалация
# --------------------------------------------------------------------------------------
def escalation_ladder() -> str:
    fig, ax = _blank_axes(9.6, 3.6)
    ax.text(50, 94, "Схема эскалации", ha="center", fontsize=10, color=NAVY, weight="bold")
    steps = [
        ("Уровень 0", "Исполнитель заявки", "истёк 50 % целевого времени", GREY_L, GREY),
        ("Уровень 1", "Руководитель 1-й линии", "истекло целевое время\nили заявка P1/P2", BLUE_L, BLUE),
        ("Уровень 2", "Руководитель ОТИ", "P1 — сразу; P2 — при\nпросрочке; спорный приоритет", TEAL_L, TEAL),
        ("Уровень 3", "ИТ-директор", "крупный инцидент, риск\nсрыва бизнес-процесса", AMBER_L, AMBER),
        ("Уровень 4", "Правление / владелец\nбизнес-процесса", "остановка деятельности,\nинцидент с данными", RED_L, RED),
    ]
    w = 18.2
    for i, (lvl, who, when, fill, edge) in enumerate(steps):
        x = 1 + i * (w + 1.5)
        y = 18 + i * 8.5
        _box(ax, x, y, w, 44, "", fill=fill, edge=edge, radius=1.4)
        ax.text(x + w / 2, y + 37, lvl, ha="center", fontsize=7.4, color=edge, weight="bold")
        ax.text(x + w / 2, y + 27, _fill(who, 17), ha="center", va="center",
                fontsize=7.6, color=INK, weight="bold", linespacing=1.25)
        ax.text(x + w / 2, y + 11, _fill(when, 24), ha="center", va="center", fontsize=6.5,
                color=GREY, linespacing=1.35)
        if i < len(steps) - 1:
            _arrow(ax, (x + w, y + 26), (x + w + 1.5, y + 29), color=NAVY, lw=1.2, mut=9)
    ax.text(50, 6, "Эскалация — штатный рабочий инструмент, а не жалоба. Неэскалированная просроченная заявка "
                   "считается нарушением дисциплины исполнения",
            ha="center", fontsize=7.4, color=GREY, style="italic")
    return _save(fig, "escalation_ladder")


# --------------------------------------------------------------------------------------
# 10. Процесс управления изменениями
# --------------------------------------------------------------------------------------
def change_flow() -> str:
    fig, ax = _blank_axes(9.8, 6.8)
    ax.text(50, 98, "Процесс управления изменениями инфраструктуры", ha="center",
            fontsize=10.5, color=NAVY, weight="bold")

    lanes = [
        ("Инициатор", 78, 20, GREY_L),
        ("ОТИ:\nисполнитель", 57, 21, BLUE_L),
        ("Согласование", 35, 22, TEAL_L),
        ("Контроль\nи закрытие", 12, 23, GREEN_L),
    ]
    for name, y, h, fill in lanes:
        ax.add_patch(Rectangle((0, y), 100, h, facecolor=fill, edgecolor="#E1E8EE", lw=0.8, alpha=0.55))
        ax.text(1.5, y + h / 2, name, ha="left", va="center", fontsize=7.6,
                color=NAVY, weight="bold", rotation=0)

    def step(x, y, w, h, t, fill=WHITE, edge=BLUE, fs=7.0, wrap=26):
        _box(ax, x, y, w, h, t, fill=fill, edge=edge, fontsize=fs, wrap=wrap, radius=1.1, lw=1.0)

    step(14, 82, 20, 12, "Потребность\nв изменении\n(заявка, проект, инцидент)", fill=WHITE, edge=GREY)
    step(40, 82, 20, 12, "Оформление RFC\nв Итилиуме\n(приложение C)", fill=WHITE, edge=GREY)
    _arrow(ax, (34, 88), (40, 88), color=NAVY, lw=1.2)

    step(14, 59, 20, 15, "Классификация:\nстандартное / обычное /\nсущественное / аварийное")
    step(40, 59, 20, 15, "Разработка плана:\nвнедрение, тестирование,\nоткат, окно работ")
    step(66, 59, 20, 15, "Оценка риска и влияния\nна действующие сервисы")
    _arrow(ax, (50, 82), (24, 74), color=NAVY, lw=1.2, rad=-0.15)
    _arrow(ax, (34, 66.5), (40, 66.5), color=NAVY, lw=1.2)
    _arrow(ax, (60, 66.5), (66, 66.5), color=NAVY, lw=1.2)

    step(14, 38, 20, 15, "Руководитель ОТИ:\nтехническое согласование", fill=TEAL_L, edge=TEAL)
    step(40, 38, 20, 15, "Отдел ИБ:\nсогласование при влиянии\nна защищённость", fill=TEAL_L, edge=TEAL)
    step(66, 38, 20, 15, "ИТ-директор / владелец\nсервиса: согласование\nсущественных изменений", fill=TEAL_L, edge=TEAL)
    _arrow(ax, (76, 59), (24, 53), color=NAVY, lw=1.2, rad=-0.12)
    _arrow(ax, (34, 45.5), (40, 45.5), color=TEAL, lw=1.2)
    _arrow(ax, (60, 45.5), (66, 45.5), color=TEAL, lw=1.2)

    step(13, 15, 20, 16, "Выполнение\nв согласованное окно\n+ фиксация хода работ", fill=WHITE, edge=GREEN)
    step(35, 15, 20, 16, "Тестирование\nпо плану, проверка\nкритериев успеха", fill=WHITE, edge=GREEN)
    step(57, 15, 20, 16, "Ввод в эксплуатацию\nили откат\nпо плану rollback", fill=WHITE, edge=GREEN)
    step(79, 15, 20, 16, "Обновление документации\nи закрытие RFC,\nзапись в журнале", fill=GREEN_L, edge=GREEN, wrap=28)
    _arrow(ax, (76, 38), (23, 31), color=NAVY, lw=1.2, rad=-0.1)
    for x in (33, 55, 77):
        _arrow(ax, (x, 23), (x + 2, 23), color=GREEN, lw=1.2)

    _box(ax, 1, 2, 98, 9,
         "Изменение без согласованного RFC, плана тестирования и плана откатa считается несанкционированным. "
         "Руководитель ОТИ вправе остановить такое изменение и инициировать возврат к исходному состоянию.",
         fill="#FFF6F6", edge=RED, fontsize=7.4, wrap=120, radius=1.2)
    return _save(fig, "change_flow")


# --------------------------------------------------------------------------------------
# 11. Окна обслуживания
# --------------------------------------------------------------------------------------
def maintenance_windows() -> str:
    fig, ax = plt.subplots(figsize=(9.4, 3.8))
    days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    ax.set_xlim(0, 24)
    ax.set_ylim(-0.7, 6.7)

    bh = 0.62
    for i in range(5):
        y = 6 - i - bh / 2
        ax.add_patch(Rectangle((0, y), 6, bh, facecolor=BLUE_L, edgecolor=BLUE, lw=0.8))
        ax.add_patch(Rectangle((9, y), 9, bh, facecolor=RED_L, edgecolor=RED, lw=0.8))
        ax.add_patch(Rectangle((20, y), 4, bh, facecolor=BLUE_L, edgecolor=BLUE, lw=0.8))
    for i in (5, 6):
        y = 6 - i - bh / 2
        ax.add_patch(Rectangle((0, y), 24, bh, facecolor=TEAL_L, edgecolor=TEAL, lw=0.8))

    ax.set_yticks(list(range(6, -1, -1)))
    ax.set_yticklabels(days, fontsize=8)
    ax.set_xticks(range(0, 25, 2))
    ax.set_xticklabels([f"{h:02d}:00" for h in range(0, 25, 2)], fontsize=7)
    ax.set_title("Типовые окна проведения работ (утверждается приказом, уточняется по площадкам)",
                 fontsize=9.2, color=NAVY, pad=10)
    ax.set_xlabel("Интервалы 06:00–09:00 и 18:00–20:00 — работы только по отдельному согласованию "
                  "с владельцем сервиса",
                  fontsize=7.2, color=GREY, labelpad=8)
    handles = [
        Rectangle((0, 0), 1, 1, facecolor=BLUE_L, edgecolor=BLUE, lw=0.8,
                  label="стандартное окно: 20:00–06:00 по будням"),
        Rectangle((0, 0), 1, 1, facecolor=TEAL_L, edgecolor=TEAL, lw=0.8,
                  label="расширенное окно: выходные, для существенных изменений"),
        Rectangle((0, 0), 1, 1, facecolor=RED_L, edgecolor=RED, lw=0.8,
                  label="рабочее время: изменения запрещены, кроме аварийных"),
    ]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.24), ncol=3,
              frameon=False, fontsize=7.0, handlelength=1.4, handleheight=0.9,
              columnspacing=1.4, labelcolor=GREY)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#C9D3DC")
    ax.grid(axis="x", color="#E8EDF2", lw=0.7)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    return _save(fig, "maintenance_windows")


# --------------------------------------------------------------------------------------
# 12. Динамика изменений (пример отчёта)
# --------------------------------------------------------------------------------------
def change_metrics() -> str:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.4, 3.4), gridspec_kw={"width_ratios": [1.3, 1]})
    months = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн"]
    planned = [18, 22, 25, 24, 28, 30]
    emergency = [7, 6, 5, 4, 3, 2]
    failed = [3, 3, 2, 2, 1, 1]
    x = np.arange(len(months))
    ax1.bar(x - 0.25, planned, width=0.25, label="Плановые изменения", color=BLUE)
    ax1.bar(x, emergency, width=0.25, label="Аварийные изменения", color=AMBER)
    ax1.bar(x + 0.25, failed, width=0.25, label="Неуспешные / с откатом", color=RED)
    ax1.set_xticks(x)
    ax1.set_xticklabels(months, fontsize=8)
    ax1.set_title("Пример отчёта: изменения по месяцам", fontsize=9.2, color=NAVY)
    ax1.legend(fontsize=7, frameon=False, loc="upper left")
    ax1.set_ylim(0, max(planned) * 1.28)
    ax1.set_ylabel("количество", fontsize=7.6)
    _grid_style(ax1)

    sizes = [46, 34, 14, 6]
    labels = ["Стандартные", "Обычные", "Существенные", "Аварийные"]
    colors = [GREEN, BLUE, AMBER, RED]
    wedges, _, autotexts = ax2.pie(
        sizes, colors=colors, autopct="%1.0f%%", startangle=90,
        wedgeprops={"width": 0.42, "edgecolor": WHITE, "linewidth": 1.5},
        textprops={"fontsize": 7.5, "color": WHITE, "weight": "bold"},
        pctdistance=0.79,
    )
    ax2.legend(wedges, labels, fontsize=7, frameon=False, loc="center", bbox_to_anchor=(0.5, -0.06))
    ax2.set_title("Целевая структура изменений\nпо классам", fontsize=9.2, color=NAVY)
    return _save(fig, "change_metrics")


# --------------------------------------------------------------------------------------
# 13. Планирование ёмкости
# --------------------------------------------------------------------------------------
def capacity_forecast() -> str:
    fig, ax = plt.subplots(figsize=(9.2, 3.4))
    quarters = ["Q1", "Q2", "Q3", "Q4", "Q1+1", "Q2+1", "Q3+1", "Q4+1"]
    used = [58, 63, 67, 72, None, None, None, None]
    forecast = [None, None, None, 72, 77, 82, 87, 92]
    x = np.arange(len(quarters))
    ax.plot(x, [u if u is not None else np.nan for u in used], marker="o", color=BLUE,
            lw=2, label="Фактическая утилизация, %")
    ax.plot(x, [f if f is not None else np.nan for f in forecast], marker="o", ls="--",
            color=TEAL, lw=1.8, label="Прогноз при текущем темпе роста")
    ax.axhline(80, color=AMBER, lw=1.4, ls=":")
    ax.text(0.1, 81.5, "порог планирования расширения — 80 %", fontsize=7.2, color=AMBER)
    ax.axhline(90, color=RED, lw=1.4, ls=":")
    ax.text(0.1, 91.5, "критический порог — 90 %", fontsize=7.2, color=RED)
    ax.set_xticks(x)
    ax.set_xticklabels(quarters, fontsize=8)
    ax.set_ylim(40, 100)
    ax.set_ylabel("утилизация ресурса, %", fontsize=7.8)
    ax.set_title("Планирование ёмкости: пример контроля утилизации (CPU / RAM / дисковое пространство / порты)",
                 fontsize=9.2, color=NAVY)
    ax.legend(fontsize=7.4, frameon=False, loc="lower right")
    _grid_style(ax)
    return _save(fig, "capacity_forecast")


# --------------------------------------------------------------------------------------
# 14. Жизненный цикл оборудования
# --------------------------------------------------------------------------------------
def equipment_lifecycle() -> str:
    fig, ax = _blank_axes(7.8, 6.0)
    ax.text(50, 98, "Жизненный цикл оборудования и ПО", ha="center", fontsize=10,
            color=NAVY, weight="bold")
    stages = [
        ("Заявка", "инициатор → Итилиум", BLUE),
        ("Согласование", "руководитель, ОТИ, бюджет", BLUE),
        ("Выдача", "1-я линия получает технику\nу сервис-менеджера", TEAL),
        ("Эксплуатация", "учёт, мониторинг, обновления", GREEN),
        ("Ремонт /\nзамена", "подменный фонд, гарантия", AMBER),
        ("Возврат", "1-я линия принимает\nи проверяет комплектность", TEAL),
        ("Списание", "акт, утилизация,\nуничтожение данных (ИБ)", GREY),
    ]
    cx, cy, R = 50, 48, 33
    n = len(stages)
    for i, (title, desc, color) in enumerate(stages):
        ang = np.pi / 2 - i * 2 * np.pi / n
        x = cx + R * np.cos(ang)
        y = cy + R * np.sin(ang) * 0.92
        _box(ax, x - 13, y - 7.5, 26, 15, "", fill=WHITE, edge=color, radius=1.4, lw=1.3)
        ax.text(x, y + 3.6, title, ha="center", va="center", fontsize=8.0, color=color,
                weight="bold", linespacing=1.2)
        ax.text(x, y - 3.0, _fill(desc, 30), ha="center", va="center", fontsize=6.4,
                color=INK, linespacing=1.25)
        ang2 = np.pi / 2 - (i + 0.5) * 2 * np.pi / n
        ax.add_patch(
            FancyArrowPatch(
                (cx + (R - 15) * np.cos(ang - 0.28), cy + (R - 15) * np.sin(ang - 0.28) * 0.92),
                (cx + (R - 15) * np.cos(ang2 - 0.30), cy + (R - 15) * np.sin(ang2 - 0.30) * 0.92),
                arrowstyle="-|>", mutation_scale=9, color=GREY, lw=1.1,
                connectionstyle="arc3,rad=-0.25",
            )
        )
    _box(ax, 33, 38, 34, 20,
         "Каждый переход фиксируется\nв системе учёта.\nОтветственный за актуальность\nданных — сервис-менеджер",
         fill=GREY_L, edge=GREY, fontsize=7.0, wrap=34, radius=1.4)
    return _save(fig, "equipment_lifecycle")


# --------------------------------------------------------------------------------------
# 15. Сроки службы оборудования
# --------------------------------------------------------------------------------------
def refresh_cycle() -> str:
    fig, ax = plt.subplots(figsize=(9.2, 3.4))
    items = ["Ноутбук\nруководителя", "Рабочая станция\n(офис)", "Ноутбук\n(инженер)",
             "Монитор", "Сетевое\nоборудование", "Сервер", "СХД", "ИБП\n(батареи)"]
    years = [4, 5, 4, 7, 7, 6, 6, 3]
    colors = [BLUE, BLUE, BLUE, GREY, TEAL, NAVY, NAVY, AMBER]
    bars = ax.barh(items, years, color=colors, height=0.6)
    for b, v in zip(bars, years):
        ax.text(v + 0.12, b.get_y() + b.get_height() / 2, f"{v} лет", va="center",
                fontsize=8, color=INK)
    ax.invert_yaxis()
    ax.set_xlabel("нормативный срок эксплуатации до плановой замены, лет", fontsize=8)
    ax.set_xlim(0, 8.6)
    ax.set_title("Целевые сроки обновления оборудования (значения уточняются при утверждении Technology Standard)",
                 fontsize=9.0, color=NAVY)
    ax.tick_params(labelsize=7.4)
    _grid_style(ax, axis="x")
    return _save(fig, "refresh_cycle")


# --------------------------------------------------------------------------------------
# 16. RPO / RTO
# --------------------------------------------------------------------------------------
def rpo_rto() -> str:
    fig, ax = plt.subplots(figsize=(9.4, 3.8))
    systems = ["Базы данных 1С", "Доменная\nинфраструктура AD", "Почта Exchange",
               "Файловые\nхранилища", "Система резервного\nкопирования",
               "Сеть и доступ\nв интернет", "Телефония", "Видеонаблюдение"]
    rpo = [1, 4, 4, 8, 24, 1, 8, 24]
    rto = [2, 2, 4, 8, 12, 1, 8, 24]
    x = np.arange(len(systems))
    ax.bar(x - 0.2, rpo, width=0.38, color=BLUE, label="RPO, ч (допустимая потеря данных)")
    ax.bar(x + 0.2, rto, width=0.38, color=TEAL, label="RTO, ч (срок восстановления)")
    for i, (a, b) in enumerate(zip(rpo, rto)):
        ax.text(i - 0.2, a + 0.3, str(a), ha="center", fontsize=7.4, color=INK)
        ax.text(i + 0.2, b + 0.3, str(b), ha="center", fontsize=7.4, color=INK)
    ax.set_xticks(x)
    ax.set_xticklabels(systems, fontsize=6.4)
    ax.set_ylabel("часы", fontsize=8)
    ax.set_ylim(0, max(rpo + rto) + 3)
    ax.set_title("Целевые RPO / RTO по критичным системам (проект значений для утверждения)",
                 fontsize=9.2, color=NAVY)
    ax.legend(fontsize=7.4, frameon=False)
    _grid_style(ax)
    return _save(fig, "rpo_rto")


# --------------------------------------------------------------------------------------
# 17. Схема резервного копирования
# --------------------------------------------------------------------------------------
def backup_scheme() -> str:
    fig, ax = _blank_axes(9.6, 4.6)
    ax.text(50, 97, "Целевая схема резервного копирования (принцип 3-2-1)", ha="center",
            fontsize=10, color=NAVY, weight="bold")

    _box(ax, 2, 48, 26, 40, "", fill=BLUE_L, edge=BLUE, radius=1.6)
    ax.text(15, 84, "Продуктивный контур", ha="center", fontsize=8.4, color=BLUE, weight="bold")
    ax.text(15, 78.5, "Базы данных 1С\nAD / DNS / DHCP\nExchange\nФайловые хранилища\n"
                      "Конфигурации сетевого\nоборудования",
            ha="center", va="top", fontsize=6.6, color=INK, linespacing=1.4)

    _box(ax, 36, 48, 26, 40, "", fill=TEAL_L, edge=TEAL, radius=1.6)
    ax.text(49, 84, "Копия 1 — основная", ha="center", fontsize=8.4, color=TEAL, weight="bold")
    ax.text(49, 78.5, "Дисковое хранилище\nрезервных копий\nна основной площадке\n\n"
                      "Ежедневно, хранение\nпо регламенту",
            ha="center", va="top", fontsize=6.6, color=INK, linespacing=1.4)

    _box(ax, 70, 48, 28, 40, "", fill=GREEN_L, edge=GREEN, radius=1.6)
    ax.text(84, 84, "Копия 2 — вне площадки", ha="center", fontsize=8.4, color=GREEN, weight="bold")
    ax.text(84, 78.5, "Отдельная площадка\nили изолированное\nхранилище (immutable),\n\n"
                      "недоступное из\nпродуктивного домена",
            ha="center", va="top", fontsize=6.6, color=INK, linespacing=1.4)

    _arrow(ax, (28, 68), (36, 68), color=NAVY, lw=1.4, mut=11)
    _arrow(ax, (62, 68), (70, 68), color=NAVY, lw=1.4, mut=11)

    _box(ax, 2, 27, 46, 17,
         "Контроль: ежедневная проверка результатов заданий,\nежедневный отчёт по неуспешным задачам,\n"
         "ежемесячный сводный отчёт руководителю ОТИ",
         fill=WHITE, edge=BLUE, fontsize=7.4, wrap=54, radius=1.4)
    _box(ax, 52, 27, 46, 17,
         "Тестовое восстановление: по классу A — ежеквартально,\nB — раз в полгода. Результат оформляется актом "
         "(приложение H)",
         fill=WHITE, edge=GREEN, fontsize=7.4, wrap=54, radius=1.4)

    _box(ax, 2, 6, 96, 16,
         "Ответственность: 2-я линия ОТИ — настройка, выполнение, контроль заданий и восстановление; "
         "отдел ИБ — требования к защите и изоляции копий, контроль соблюдения, участие в тестовом восстановлении. "
         "Резервные копии критичных систем не хранятся только в одном контуре и только на одном носителе.",
         fill="#F7FAFC", edge=GREY, fontsize=7.4, wrap=116, radius=1.4)
    return _save(fig, "backup_scheme")


# --------------------------------------------------------------------------------------
# 18. Уровни мониторинга
# --------------------------------------------------------------------------------------
def monitoring_layers() -> str:
    fig, ax = _blank_axes(9.4, 4.2)
    ax.text(50, 97, "Уровни мониторинга: от оборудования к бизнес-процессу", ha="center",
            fontsize=10, color=NAVY, weight="bold")
    layers = [
        ("Уровень 4. Бизнес-процесс", "Доступность сервиса для пользователя: вход в 1С, отправка почты, "
         "работа площадки, печать документов", RED, RED_L),
        ("Уровень 3. Сервис", "Состояние служб и приложений: SQL, Exchange, AD, файловые службы, VPN, "
         "задания резервного копирования", AMBER, AMBER_L),
        ("Уровень 2. Платформа", "Виртуализация, СХД, кластеры, ОС: загрузка, память, дисковое пространство, "
         "состояние узлов", TEAL, TEAL_L),
        ("Уровень 1. Оборудование и каналы", "Серверы, коммутаторы, маршрутизаторы, Wi-Fi, ИБП, "
         "каналы связи, температура в серверных", BLUE, BLUE_L),
    ]
    for i, (title, desc, edge, fill) in enumerate(layers):
        y = 68 - i * 19
        _box(ax, 4, y, 92, 17, "", fill=fill, edge=edge, radius=1.4)
        ax.text(7, y + 11.6, title, ha="left", fontsize=8.6, color=edge, weight="bold")
        ax.text(7, y + 4.6, textwrap.fill(desc, 108), ha="left", va="center", fontsize=7.2,
                color=INK, linespacing=1.3)
    ax.annotate("", xy=(2, 86), xytext=(2, 10),
                arrowprops={"arrowstyle": "-|>", "color": NAVY, "lw": 1.4})
    ax.text(0.2, 48, "приоритет\nреагирования", rotation=90, ha="center", va="center",
            fontsize=6.8, color=GREY, linespacing=1.2)
    ax.text(50, 4, "Принцип: сервис не считается введённым в эксплуатацию, если он не покрыт мониторингом "
                   "минимум на уровнях 1–3",
            ha="center", fontsize=7.4, color=GREY, style="italic")
    return _save(fig, "monitoring_layers")


# --------------------------------------------------------------------------------------
# 19. Доступность и допустимый простой
# --------------------------------------------------------------------------------------
def availability_chart() -> str:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.4, 3.3), gridspec_kw={"width_ratios": [1, 1.15]})
    classes = ["Класс A\n99,5 %", "Класс B\n99,0 %", "Класс C\n98,0 %", "Класс D\nбез гарантий"]
    minutes = [219, 438, 876, 0]
    colors = [RED, AMBER, BLUE, GREY]
    bars = ax1.bar(classes, minutes, color=colors, width=0.62)
    for b, v in zip(bars, minutes):
        label = f"{v} мин/мес" if v else "не нормируется"
        ax1.text(b.get_x() + b.get_width() / 2, v + 18, label, ha="center", fontsize=7.2, color=INK)
    ax1.set_ylim(0, 1050)
    ax1.set_ylabel("допустимый простой, мин/мес", fontsize=7.6)
    ax1.set_title("Целевая доступность по классам сервисов", fontsize=9.0, color=NAVY)
    ax1.tick_params(labelsize=7.4)
    _grid_style(ax1)

    months = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг"]
    fact = [99.2, 99.4, 99.6, 99.3, 99.7, 99.8, 99.6, 99.9]
    ax2.plot(months, fact, marker="o", color=BLUE, lw=2, label="Фактическая доступность класса A")
    ax2.axhline(99.5, color=RED, ls="--", lw=1.3, label="Целевое значение 99,5 %")
    ax2.set_ylim(98.8, 100.05)
    ax2.set_ylabel("%", fontsize=8)
    ax2.set_title("Пример отчёта о доступности", fontsize=9.0, color=NAVY)
    ax2.legend(fontsize=7.0, frameon=False, loc="lower right")
    ax2.tick_params(labelsize=7.4)
    _grid_style(ax2)
    return _save(fig, "availability_chart")


# --------------------------------------------------------------------------------------
# 20. Управление инцидентами
# --------------------------------------------------------------------------------------
def incident_flow() -> str:
    fig, ax = _blank_axes(9.6, 4.6)
    ax.text(50, 97, "Управление инцидентами, включая крупные (major)", ha="center",
            fontsize=10, color=NAVY, weight="bold")
    steps = [
        ("Обнаружение", "мониторинг,\nпользователь,\nдежурный", BLUE_L, BLUE),
        ("Регистрация", "заявка\nв Итилиуме,\nsev-уровень", BLUE_L, BLUE),
        ("Локализация", "поиск причины,\nоценка влияния", TEAL_L, TEAL),
        ("Восстановление", "приоритет —\nвернуть сервис", AMBER_L, AMBER),
        ("Закрытие", "подтверждение\nвосстановления", GREEN_L, GREEN),
        ("Разбор", "постмортем,\nкорректирующие\nмеры", GREEN_L, GREEN),
    ]
    w, gap = 14.4, 2.2
    for i, (t, d, fill, edge) in enumerate(steps):
        x = 0.4 + i * (w + gap)
        _box(ax, x, 52, w, 26, "", fill=fill, edge=edge, radius=1.3)
        ax.text(x + w / 2, 71, t, ha="center", fontsize=8.0, color=edge, weight="bold")
        ax.text(x + w / 2, 62, d, ha="center", va="center", fontsize=6.5, color=INK,
                linespacing=1.4)
        if i < len(steps) - 1:
            _arrow(ax, (x + w, 65), (x + w + gap, 65), color=NAVY, lw=1.3, mut=10)

    _box(ax, 1.5, 24, 47, 20,
         "Крупный инцидент (Sev-1): назначается координатор (руководитель ОТИ или дежурный "
         "руководитель), открывается канал коммуникаций, уведомляются ИТ-директор, ИБ, владельцы "
         "затронутых процессов. Статус — каждые 30 минут.",
         fill="#FFF6F6", edge=RED, fontsize=7.2, wrap=62, radius=1.3)
    _box(ax, 51.5, 24, 47, 20,
         "Постмортем обязателен для Sev-1 и Sev-2: срок — 5 рабочих дней. Разбор без поиска виновных: "
         "хронология, причина, что сработало, что нет, корректирующие меры с ответственными и сроками "
         "(приложение I).",
         fill="#F4FAF6", edge=GREEN, fontsize=7.2, wrap=62, radius=1.3)

    _box(ax, 1.5, 4, 97, 14,
         "Инцидент с признаками нарушения ИБ (утечка, шифровальщик, компрометация учётной записи, подозрительная "
         "активность) немедленно передаётся в отдел ИБ; ОТИ выполняет технические действия по указанию ИБ и "
         "сохраняет данные для разбора, не уничтожая следы.",
         fill="#F7FAFC", edge=GREY, fontsize=7.3, wrap=126, radius=1.3)
    return _save(fig, "incident_flow")


# --------------------------------------------------------------------------------------
# 21. Дежурства в праздники
# --------------------------------------------------------------------------------------
def duty_schedule() -> str:
    fig, ax = plt.subplots(figsize=(9.4, 3.4))
    people = ["Системный админ. 1", "Системный админ. 2", "Сетевой инженер",
              "1-я линия (специалист 1)", "1-я линия (специалист 2)", "Руководитель ОТИ"]
    tasks = [
        (0, 0, 2, BLUE), (0, 4, 2, BLUE),
        (1, 2, 2, BLUE), (1, 6, 2, BLUE),
        (2, 0, 8, TEAL),
        (3, 0, 4, GREEN),
        (4, 4, 4, GREEN),
        (5, 0, 8, AMBER),
    ]
    for row, start, dur, color in tasks:
        ax.barh(row, dur, left=start, height=0.52, color=color,
                edgecolor=WHITE, lw=1.2)
    ax.set_yticks(range(len(people)))
    ax.set_yticklabels(people, fontsize=7.6)
    ax.invert_yaxis()
    ax.set_xticks(range(9))
    ax.set_xticklabels(["1", "2", "3", "4", "5", "6", "7", "8", "9"], fontsize=7.6)
    ax.set_xlabel("дни праздничного периода", fontsize=8)
    ax.set_xlim(-0.1, 8.1)
    ax.set_title("Пример графика дежурств на праздничный период (форма — приложение J)",
                 fontsize=9.2, color=NAVY)
    handles = [
        Rectangle((0, 0), 1, 1, color=BLUE),
        Rectangle((0, 0), 1, 1, color=TEAL),
        Rectangle((0, 0), 1, 1, color=GREEN),
        Rectangle((0, 0), 1, 1, color=AMBER),
    ]
    ax.legend(handles, ["Дежурство по серверам и сервисам", "Дежурство по сети",
                        "Дежурство 1-й линии", "Дежурный руководитель (эскалация)"],
              fontsize=7.0, frameon=False, ncol=2, loc="lower center", bbox_to_anchor=(0.5, -0.52))
    _grid_style(ax, axis="x")
    return _save(fig, "duty_schedule")


# --------------------------------------------------------------------------------------
# 22. Доступ подрядчика
# --------------------------------------------------------------------------------------
def contractor_access() -> str:
    fig, ax = _blank_axes(9.6, 3.8)
    ax.text(50, 96, "Порядок предоставления доступа подрядчику", ha="center", fontsize=10,
            color=NAVY, weight="bold")
    steps = [
        ("1. Обоснование", "Ответственный инженер ОТИ описывает\nработы, состав доступа, срок", BLUE_L, BLUE),
        ("2. Согласование ОТИ", "Руководитель ОТИ подтверждает\nнеобходимость и объём", TEAL_L, TEAL),
        ("3. Решение ИБ", "Доступ предоставляет отдел ИБ;\nбез решения ИБ доступа нет", RED_L, RED),
        ("4. Выдача и журнал", "Временный доступ, срок, запись\nв журнале (приложение K)", AMBER_L, AMBER),
        ("5. Сопровождение", "Работы — под контролем куратора\nот ОТИ", GREEN_L, GREEN),
        ("6. Отзыв и приёмка", "Доступ отзывается сразу после работ,\nрезультат принимает владелец процесса", GREEN_L, GREEN),
    ]
    w, gap = 15.0, 1.5
    for i, (t, d, fill, edge) in enumerate(steps):
        x = 0.5 + i * (w + gap)
        _box(ax, x, 36, w, 40, "", fill=fill, edge=edge, radius=1.3)
        ax.text(x + w / 2, 68, t, ha="center", fontsize=7.4, color=edge, weight="bold")
        ax.text(x + w / 2, 51, textwrap.fill(d.replace("\n", " "), 20), ha="center", va="center",
                fontsize=6.4, color=INK, linespacing=1.4)
        if i < len(steps) - 1:
            _arrow(ax, (x + w, 56), (x + w + gap, 56), color=NAVY, lw=1.2, mut=9)
    _box(ax, 1, 8, 98, 20,
         "Обязательные условия: доступ только временный и персонифицированный; общие учётные записи подрядчику "
         "не выдаются; все действия журналируются; удалённые работы проводятся через контролируемый канал с записью "
         "сессии, если это технически возможно; после завершения работ подрядчик передаёт документацию и описание "
         "внесённых изменений — без этого работы не считаются принятыми.",
         fill="#F7FAFC", edge=GREY, fontsize=7.4, wrap=126, radius=1.3)
    return _save(fig, "contractor_access")


# --------------------------------------------------------------------------------------
# 23. Процесс закупки
# --------------------------------------------------------------------------------------
def procurement_flow() -> str:
    fig, ax = _blank_axes(9.6, 3.9)
    ax.text(50, 96, "Процесс от потребности до ввода в эксплуатацию", ha="center",
            fontsize=10, color=NAVY, weight="bold")
    steps = [
        ("Потребность", "инициатор /\nОТИ / проект", GREY, GREY_L),
        ("Техническое\nобоснование", "ОТИ: требования,\nварианты, риски\n(приложение P)", BLUE, BLUE_L),
        ("Бюджет", "проверка лимита,\nсогласование\nИТ-директора", TEAL, TEAL_L),
        ("Закупка", "закупки: процедура,\nдоговор, поставка", GREEN, GREEN_L),
        ("Внедрение", "ОТИ: монтаж,\nнастройка, тест", BLUE, BLUE_L),
        ("Ввод в\nэксплуатацию", "учёт, паспорт,\nмониторинг, backup,\nдокументация", AMBER, AMBER_L),
    ]
    w, gap = 15.0, 1.9
    for i, (t, d, edge, fill) in enumerate(steps):
        x = 1 + i * (w + gap)
        _box(ax, x, 34, w, 42, "", fill=fill, edge=edge, radius=1.3)
        ax.text(x + w / 2, 67, t, ha="center", va="center", fontsize=8.0, color=edge,
                weight="bold", linespacing=1.2)
        ax.text(x + w / 2, 48, d, ha="center", va="center", fontsize=6.8, color=INK, linespacing=1.32)
        if i < len(steps) - 1:
            _arrow(ax, (x + w, 55), (x + w + gap, 55), color=NAVY, lw=1.2, mut=9)
    _box(ax, 1, 4, 48, 26,
         "Технические требования к ИТ-оборудованию и ПО определяет только ОТИ. Самостоятельная закупка ИТ-решений "
         "подразделениями не допускается: такое оборудование не принимается на поддержку, не подключается к сети "
         "и не включается в учёт до приведения в соответствие стандарту.",
         fill="#FFF6F6", edge=RED, fontsize=7.2, wrap=64, radius=1.3)
    _box(ax, 51, 4, 48, 26,
         "Бюджет отдела технической инфраструктуры формирует руководитель ОТИ и согласует с ИТ-директором. "
         "В рамках утверждённого бюджета и стандарта руководитель ОТИ принимает решения самостоятельно; "
         "внеплановые расходы согласуются с ИТ-директором отдельно.",
         fill="#F4FAF6", edge=GREEN, fontsize=7.2, wrap=64, radius=1.3)
    return _save(fig, "procurement_flow")


# --------------------------------------------------------------------------------------
# 24. Структура бюджета
# --------------------------------------------------------------------------------------
def budget_structure() -> str:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.4, 3.5), gridspec_kw={"width_ratios": [1.2, 1]})
    cats = ["Рабочие\nместа", "Серверы\nи СХД", "Сеть\nи каналы",
            "Лицензии,\nподписки", "Сервис,\nподрядчики", "Резерв\n(5–10 %)"]
    capex = [30, 28, 18, 4, 2, 6]
    opex = [6, 4, 22, 26, 20, 4]
    x = np.arange(len(cats))
    ax1.bar(x, capex, width=0.58, label="CAPEX", color=NAVY)
    ax1.bar(x, opex, width=0.58, bottom=capex, label="OPEX", color=TEAL)
    ax1.set_xticks(x)
    ax1.set_xticklabels(cats, fontsize=6.4)
    ax1.set_ylabel("условные единицы", fontsize=7.6)
    ax1.set_title("Структура бюджета ОТИ: пример формы планирования", fontsize=9.0, color=NAVY)
    ax1.legend(fontsize=7.4, frameon=False)
    _grid_style(ax1)

    labels = ["Плановое обновление\nоборудования", "Развитие и проекты",
              "Поддержка и лицензии", "Аварийный резерв"]
    sizes = [34, 26, 32, 8]
    colors = [BLUE, TEAL, GREEN, AMBER]
    wedges, _, autotexts = ax2.pie(
        sizes, colors=colors, autopct="%1.0f%%", startangle=120,
        wedgeprops={"width": 0.44, "edgecolor": WHITE, "linewidth": 1.5},
        textprops={"fontsize": 7.4, "color": WHITE, "weight": "bold"}, pctdistance=0.78,
    )
    ax2.legend(wedges, labels, fontsize=6.8, frameon=False, loc="center", bbox_to_anchor=(0.5, -0.1))
    ax2.set_title("Целевое распределение\nбюджета по назначению", fontsize=9.0, color=NAVY)
    return _save(fig, "budget_structure")


# --------------------------------------------------------------------------------------
# 25. Структура хранения документации
# --------------------------------------------------------------------------------------
def documentation_tree() -> str:
    fig, ax = _blank_axes(9.8, 5.2)
    ax.text(50, 97, "Структура хранения технической документации", ha="center", fontsize=10.5,
            color=NAVY, weight="bold")
    _box(ax, 2, 87, 46, 7.5,
         "\\\\<файловый сервер>\\IT-Docs$   ·   сетевой диск, доступ по ролям",
         fill=NAVY, edge=NAVY, fg=WHITE, fontsize=7.2, wrap=70, radius=1.0)

    folders = [
        ("01_Политики_и_регламенты", "действующие редакции, архив версий"),
        ("02_Каталог_сервисов", "паспорта сервисов, реестр, классы критичности"),
        ("03_Сеть", "схемы L1/L2/L3, IP-план, реестр VLAN"),
        ("04_Серверы_и_виртуализация", "реестр ВМ, схемы кластеров"),
        ("05_Резервное_копирование", "регламенты, расписания, акты восстановления"),
        ("06_Мониторинг", "перечень объектов, пороги, состав оповещений"),
        ("07_Доступы", "матрица доступа, реестр административных УЗ"),
        ("08_Площадки", "паспорта 11 площадок, серверные, каналы связи"),
        ("09_Инструкции_и_runbook", "пошаговые инструкции по типовым операциям"),
        ("10_Подрядчики_и_договоры", "реестр, контакты, условия поддержки"),
        ("11_Инциденты_и_постмортемы", "разборы, корректирующие меры"),
        ("12_Отчётность", "периодические отчёты, аудиты соблюдения"),
    ]
    for i, (name, desc) in enumerate(folders):
        y = 76 - i * 6.4
        ax.plot([5, 8], [y + 2.3, y + 2.3], color=BLUE, lw=0.9)
        ax.plot([5, 5], [87, y + 2.3], color=BLUE, lw=0.9)
        _box(ax, 8, y, 27, 4.7, name, fill=BLUE_L, edge=BLUE, fontsize=6.7, wrap=44,
             radius=0.8, lw=0.8)
        ax.text(36.5, y + 2.3, desc, ha="left", va="center", fontsize=6.4, color=GREY)

    _box(ax, 70, 47, 28, 35, "", fill=RED_L, edge=RED, radius=1.4)
    ax.text(84, 79, "Бумажная копия", ha="center", va="top", fontsize=8.2, color=RED,
            weight="bold")
    ax.text(84, 73.5, "Ключевые документы:\nПолитика, схемы критичной\nинфраструктуры, DRP,\n"
                      "матрица доступа, пароли\nаварийного доступа —\nв отделе ИБ, "
                      "в актуальной редакции",
            ha="center", va="top", fontsize=6.4, color=INK, linespacing=1.4)

    _box(ax, 70, 8, 28, 35, "", fill=AMBER_L, edge=AMBER, radius=1.4)
    ax.text(84, 40, "Правило", ha="center", va="top", fontsize=8.2, color=AMBER, weight="bold")
    ax.text(84, 34.5, "Не задокументировано —\nне сделано.\n\nСрок документирования —\n"
                      "одновременно с работами,\nно не позднее\n3 рабочих дней",
            ha="center", va="top", fontsize=6.4, color=INK, linespacing=1.4)
    return _save(fig, "documentation_tree")


# --------------------------------------------------------------------------------------
# 26. Цикл отчётности
# --------------------------------------------------------------------------------------
def reporting_cadence() -> str:
    fig, ax = _blank_axes(9.4, 3.4)
    ax.text(50, 95, "Цикл отчётности и контроля", ha="center", fontsize=10, color=NAVY, weight="bold")
    items = [
        ("Ежедневно", "результаты заданий резервного копирования,\nкритические события мониторинга,\n"
                      "открытые заявки P1/P2", BLUE, BLUE_L),
        ("Еженедельно", "статус заявок и просрочек, ход изменений,\nплан работ на неделю,\nстатус проектов", TEAL, TEAL_L),
        ("Ежемесячно", "доступность сервисов, статистика обращений,\nизменения и инциденты,\nотчёт ИТ-директору", GREEN, GREEN_L),
        ("Ежеквартально", "тестовое восстановление, пересмотр прав,\nинвентаризация выборочно,\nаудит документации", AMBER, AMBER_L),
        ("Ежегодно", "ревизия каталога сервисов, пересмотр политики,\nинвентаризация полная,\nбюджетный цикл", GREY, GREY_L),
    ]
    w, gap = 18.4, 1.6
    for i, (t, d, edge, fill) in enumerate(items):
        x = 1 + i * (w + gap)
        _box(ax, x, 22, w, 56, "", fill=fill, edge=edge, radius=1.4)
        ax.text(x + w / 2, 70, t, ha="center", fontsize=8.6, color=edge, weight="bold")
        ax.text(x + w / 2, 46, textwrap.fill(d.replace("\n", " "), 24), ha="center", va="center",
                fontsize=6.6, color=INK, linespacing=1.45)
        if i < len(items) - 1:
            _arrow(ax, (x + w, 50), (x + w + gap, 50), color=NAVY, lw=1.1, mut=8)
    ax.text(50, 12, "Отчётность за действия: каждое действие в инфраструктуре имеет след — заявку, RFC, запись "
                    "в журнале изменений или запись в журнале доступа",
            ha="center", fontsize=7.4, color=GREY, style="italic")
    return _save(fig, "reporting_cadence")


# --------------------------------------------------------------------------------------
# 27. Дашборд KPI
# --------------------------------------------------------------------------------------
def kpi_dashboard() -> str:
    fig = plt.figure(figsize=(9.4, 5.4))
    gs = fig.add_gridspec(2, 3, hspace=0.55, wspace=0.35)
    fig.suptitle("Пример ежемесячного дашборда ОТИ (состав и целевые значения утверждаются отдельным документом)",
                 fontsize=9.6, color=NAVY, y=0.99)

    ax = fig.add_subplot(gs[0, 0])
    months = ["М1", "М2", "М3", "М4", "М5", "М6"]
    ax.plot(months, [96, 97, 98, 97, 99, 99], marker="o", color=BLUE, lw=1.8)
    ax.axhline(95, color=RED, ls="--", lw=1.1)
    ax.set_ylim(90, 100.5)
    ax.set_title("Выполнение целевого\nвремени по заявкам, %", fontsize=8.2, color=NAVY)
    ax.tick_params(labelsize=7)
    _grid_style(ax)

    ax = fig.add_subplot(gs[0, 1])
    ax.bar(months, [140, 155, 132, 148, 126, 118], color=TEAL, width=0.6)
    ax.set_title("Количество обращений\nв месяц", fontsize=8.2, color=NAVY)
    ax.tick_params(labelsize=7)
    _grid_style(ax)

    ax = fig.add_subplot(gs[0, 2])
    vals = [0.99, 0.01]
    ax.pie(vals, colors=[GREEN, RED], startangle=90,
           wedgeprops={"width": 0.4, "edgecolor": WHITE, "linewidth": 1.4})
    ax.text(0, 0, "99 %", ha="center", va="center", fontsize=13, color=GREEN, weight="bold")
    ax.set_title("Успешность заданий\nрезервного копирования", fontsize=8.2, color=NAVY)

    ax = fig.add_subplot(gs[1, 0])
    ax.bar(months, [8, 6, 5, 4, 2, 1], color=AMBER, width=0.6)
    ax.set_title("Изменения без\nсогласования (цель — 0)", fontsize=8.2, color=NAVY)
    ax.tick_params(labelsize=7)
    _grid_style(ax)

    ax = fig.add_subplot(gs[1, 1])
    ax.barh(["Каталог\nсервисов", "Схемы\nсети", "Паспорта\nсерверов", "Runbook"],
            [72, 85, 64, 41], color=[BLUE, TEAL, BLUE, GREY], height=0.58)
    ax.set_xlim(0, 100)
    ax.set_title("Полнота документации, %", fontsize=8.2, color=NAVY)
    ax.tick_params(labelsize=6.8)
    _grid_style(ax, axis="x")

    ax = fig.add_subplot(gs[1, 2])
    sev = ["Sev-1", "Sev-2", "Sev-3"]
    ax.bar(sev, [1, 4, 17], color=[RED, AMBER, BLUE], width=0.55)
    ax.set_title("Инциденты по уровням", fontsize=8.2, color=NAVY)
    ax.tick_params(labelsize=7)
    _grid_style(ax)
    return _save(fig, "kpi_dashboard")


# --------------------------------------------------------------------------------------
# 28. План внедрения политики
# --------------------------------------------------------------------------------------
def rollout_gantt() -> str:
    fig, ax = plt.subplots(figsize=(9.4, 4.4))
    tasks = [
        ("Утверждение политики и ознакомление сотрудников", 0, 1, NAVY),
        ("Правило 100 % обращений через Итилиум", 0, 2, BLUE),
        ("Каталог сервисов: инвентаризация и паспорта", 0, 4, BLUE),
        ("Запуск процесса управления изменениями (RFC)", 1, 2, TEAL),
        ("Технический совет по изменениям", 1, 1, TEAL),
        ("Реестр административных УЗ, наведение порядка в доступах", 1, 3, TEAL),
        ("Восстановление актуальности сетевых схем и IP-плана", 2, 3, GREEN),
        ("Покрытие мониторингом уровней 1–3", 2, 4, GREEN),
        ("Регламент резервного копирования, тестовые восстановления", 3, 3, GREEN),
        ("Учёт оборудования: сверка с сервис-менеджером", 3, 3, AMBER),
        ("Technology Standard (по подразделениям)", 4, 3, AMBER),
        ("Схема дежурств на праздничные периоды", 5, 2, AMBER),
        ("План аварийного восстановления (DRP)", 6, 4, RED),
        ("SLA и KPI отдела", 8, 3, RED),
        ("Первый внутренний аудит соблюдения политики", 10, 2, GREY),
    ]
    for i, (name, start, dur, color) in enumerate(tasks):
        ax.barh(i, dur, left=start, height=0.56, color=color, alpha=0.9,
                edgecolor=WHITE, lw=1.0)
        ax.text(start + dur + 0.12, i, f"{dur} мес.", va="center", fontsize=6.8, color=GREY)
    ax.set_yticks(range(len(tasks)))
    ax.set_yticklabels([t[0] for t in tasks], fontsize=7.0)
    ax.invert_yaxis()
    ax.set_xticks(range(0, 13))
    ax.set_xticklabels([f"М{i}" for i in range(0, 13)], fontsize=7.2)
    ax.set_xlim(0, 13)
    ax.set_xlabel("месяцы с даты утверждения политики", fontsize=8)
    ax.set_title("План-график внедрения Политики (этапы 1–4)", fontsize=9.4, color=NAVY)
    for x, label in ((0, "Этап 1"), (2, "Этап 2"), (5, "Этап 3"), (8, "Этап 4")):
        ax.axvline(x, color="#C9D3DC", lw=1.0, ls=":")
        ax.text(x + 0.1, -0.85, label, fontsize=7.0, color=GREY)
    _grid_style(ax, axis="x")
    return _save(fig, "rollout_gantt")


# --------------------------------------------------------------------------------------
# 29. Матрица замещения (bus-factor)
# --------------------------------------------------------------------------------------
def substitution_matrix() -> str:
    fig, ax = plt.subplots(figsize=(9.2, 3.8))
    areas = ["Виртуализация\nи серверы", "AD / DNS / DHCP", "Exchange", "Файловые\nхранилища",
             "Резервное\nкопирование", "Сеть и firewall", "Wi-Fi", "Телефония",
             "Рабочие места", "Мониторинг"]
    roles = ["Сист. админ. 1", "Сист. админ. 2", "Сетевой инженер", "Рук. 1-й линии", "1-я линия"]
    # 2 — основной ответственный, 1 — резерв, 0 — не участвует
    data = [
        [2, 1, 0, 0, 0],
        [2, 1, 0, 0, 0],
        [1, 2, 0, 0, 0],
        [1, 2, 0, 0, 0],
        [1, 2, 0, 0, 0],
        [0, 0, 2, 0, 0],
        [0, 1, 2, 0, 0],
        [0, 1, 2, 0, 0],
        [0, 0, 0, 2, 1],
        [1, 1, 1, 0, 0],
    ]
    arr = np.array(data)
    cmap = matplotlib.colors.ListedColormap(["#F1F4F7", TEAL_L, BLUE])
    ax.imshow(arr, cmap=cmap, vmin=0, vmax=2, aspect="auto")
    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            v = arr[i, j]
            if v:
                ax.text(j, i, "О" if v == 2 else "Р", ha="center", va="center",
                        fontsize=8.5, color=WHITE if v == 2 else TEAL, weight="bold")
    ax.set_xticks(range(len(roles)))
    ax.set_xticklabels(roles, fontsize=7.4)
    ax.set_yticks(range(len(areas)))
    ax.set_yticklabels(areas, fontsize=7.0)
    ax.set_xticks(np.arange(-0.5, len(roles), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(areas), 1), minor=True)
    ax.grid(which="minor", color=WHITE, lw=2)
    ax.tick_params(which="both", length=0)
    ax.tick_params(axis="y", pad=7)
    ax.set_title("Матрица замещения по областям: О — основной ответственный, Р — резерв\n"
                 "(заполняется руководителем ОТИ, обязательна для каждой области)",
                 fontsize=8.8, color=NAVY, pad=10)
    return _save(fig, "substitution_matrix")


# --------------------------------------------------------------------------------------
# 30. Распределение трудозатрат отдела
# --------------------------------------------------------------------------------------
def workload_split() -> str:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.4, 3.3), gridspec_kw={"width_ratios": [1, 1.1]})
    labels = ["Поддержка\nи обращения", "Плановая\nэксплуатация", "Проекты\nи развитие",
              "Документы\nи отчёты", "Резерв на\nинциденты"]
    current = [52, 24, 10, 4, 10]
    target = [38, 24, 22, 8, 8]
    x = np.arange(len(labels))
    ax1.bar(x - 0.2, current, width=0.38, color=GREY, label="Сейчас (оценка)")
    ax1.bar(x + 0.2, target, width=0.38, color=BLUE, label="Цель после внедрения политики")
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, fontsize=6.4)
    ax1.set_ylabel("% рабочего времени отдела", fontsize=7.6)
    ax1.set_title("Структура трудозатрат ОТИ", fontsize=9.0, color=NAVY)
    ax1.legend(fontsize=7.0, frameon=False)
    _grid_style(ax1)

    channels = ["Итилиум\n(help@)", "Телефон", "Мессенджер", "Лично\n«в коридоре»"]
    now = [55, 15, 18, 12]
    goal = [100, 0, 0, 0]
    x = np.arange(len(channels))
    ax2.bar(x - 0.2, now, width=0.38, color=AMBER, label="Сейчас")
    ax2.bar(x + 0.2, goal, width=0.38, color=GREEN, label="Требование политики")
    ax2.set_xticks(x)
    ax2.set_xticklabels(channels, fontsize=7.0)
    ax2.set_ylabel("% обращений", fontsize=7.6)
    ax2.set_title("Каналы поступления обращений: 100 % через единую точку входа",
                  fontsize=9.0, color=NAVY)
    ax2.legend(fontsize=7.0, frameon=False)
    _grid_style(ax2)
    return _save(fig, "workload_split")


# --------------------------------------------------------------------------------------
# 31. Полномочия руководителя ОТИ
# --------------------------------------------------------------------------------------
def authority_map() -> str:
    fig, ax = _blank_axes(9.4, 5.8)
    ax.text(50, 97, "Полномочия руководителя ОТИ и границы единоличных решений", ha="center",
            fontsize=10, color=NAVY, weight="bold")

    _box(ax, 1, 39, 48, 53, "", fill="#F4FAF9", edge=TEAL, radius=1.6, lw=1.4)
    ax.text(25, 87.5, "Решает самостоятельно", ha="center", fontsize=9.0, color=TEAL, weight="bold")
    own = [
        "Распределение задач и приоритетов внутри отдела",
        "Техническая архитектура и стандарты инфраструктуры",
        "Согласование изменений инфраструктуры",
        "Остановка небезопасного или несогласованного изменения",
        "Требование соблюдения стандартов и документирования",
        "Доступ к любой технической информации по инфраструктуре",
        "Инициирование закупок в рамках бюджета",
        "Выбор подрядчика по техническим критериям",
        "Назначение ответственных и схемы замещения",
        "График дежурств и окна работ",
        "Инициирование разбора инцидентов",
    ]
    y = 82
    for t in own:
        wrapped = _fill(t, 54)
        lines = wrapped.count("\n") + 1
        y -= (lines - 1) * 1.15
        ax.plot([4], [y], marker="o", ms=3, color=TEAL)
        ax.text(6, y, wrapped, ha="left", va="center", fontsize=6.9, color=INK, linespacing=1.3)
        y -= (lines - 1) * 1.15 + 3.6

    _box(ax, 51, 39, 48, 53, "", fill="#FFF8F5", edge=AMBER, radius=1.6, lw=1.4)
    ax.text(75, 87.5, "Не решает единолично", ha="center", fontsize=9.0, color=AMBER, weight="bold")
    shared = [
        "Изменение политик и требований ИБ — отдел ИБ",
        "Предоставление доступа подрядчику — отдел ИБ",
        "Расходы вне утверждённого бюджета — ИТ-директор",
        "Отклонение от Technology Standard — ИТ-директор",
        "Вывод сервиса класса A из эксплуатации — владелец и ИТ-директор",
        "Изменения прикладной части 1С — отдел 1С",
        "Приём/увольнение сотрудников — с ИТ-директором и HR",
        "Выбор поставщика по коммерческим условиям — закупки",
        "Раскрытие информации и обработка ПДн — ИБ и юристы",
    ]
    y = 82
    for t in shared:
        wrapped = _fill(t, 52)
        lines = wrapped.count("\n") + 1
        y -= (lines - 1) * 1.15
        ax.plot([54], [y], marker="o", ms=3, color=AMBER)
        ax.text(56, y, wrapped, ha="left", va="center", fontsize=6.9, color=INK, linespacing=1.3)
        y -= (lines - 1) * 1.15 + 3.6

    _box(ax, 1, 4, 98, 31,
         "Право технического стоп-слова: руководитель ОТИ вправе приостановить любые работы в инфраструктуре, "
         "если они выполняются без согласования, без плана откатa, в запрещённое окно или создают риск для "
         "критичных сервисов и данных. Решение оформляется письменно (заявка/RFC/служебная записка) с указанием "
         "причины и условий возобновления работ и в тот же день доводится до ИТ-директора. "
         "Обратная сторона полномочий — персональная ответственность за работоспособность инфраструктуры, "
         "достоверность отчётности и актуальность документации.",
         fill="#F7FAFC", edge=NAVY, fontsize=7.6, wrap=124, radius=1.4)
    return _save(fig, "authority_map")


# --------------------------------------------------------------------------------------
# 32. Разделение ответственности ОТИ / ИБ
# --------------------------------------------------------------------------------------
def security_split() -> str:
    fig, ax = plt.subplots(figsize=(9.2, 4.2))
    domains = ["Сегментация\nсети", "Межсетевые\nэкраны", "Патч-\nменеджмент",
               "Антивирус /\nEDR", "MFA\nи пароли", "Журналы\nи SIEM",
               "Управление\nдоступом", "Инциденты\nИБ", "Резервные\nкопии",
               "Оценка\nуязвимостей"]
    oti = [70, 65, 85, 60, 55, 50, 60, 30, 80, 40]
    ib = [30, 35, 15, 40, 45, 50, 40, 70, 20, 60]
    x = np.arange(len(domains))
    ax.bar(x, oti, width=0.62, color=BLUE, label="ОТИ — реализация и эксплуатация")
    ax.bar(x, ib, width=0.62, bottom=oti, color=RED, label="ИБ — требования, контроль, решения")
    for i, v in enumerate(oti):
        ax.text(i, v / 2, f"{v}", ha="center", va="center", fontsize=7.2, color=WHITE, weight="bold")
        ax.text(i, v + ib[i] / 2, f"{ib[i]}", ha="center", va="center", fontsize=7.2,
                color=WHITE, weight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(domains, fontsize=6.5)
    ax.set_ylim(0, 118)
    ax.set_ylabel("условная доля участия, %", fontsize=7.8)
    ax.set_title("Разделение ответственности между ОТИ и отделом ИБ по доменам защиты\n"
                 "(схема ориентирована на разграничение роли «кто делает» и «кто требует и проверяет»)",
                 fontsize=9.0, color=NAVY)
    ax.legend(fontsize=7.4, frameon=False, ncol=2, loc="upper center")
    _grid_style(ax)
    return _save(fig, "security_split")


# --------------------------------------------------------------------------------------
# 33. Процесс управления доступом
# --------------------------------------------------------------------------------------
def access_cycle() -> str:
    fig, ax = _blank_axes(9.4, 4.0)
    ax.text(50, 96, "Управление доступом: от заявки до отзыва", ha="center", fontsize=10,
            color=NAVY, weight="bold")
    steps = [
        ("Заявка", "руководитель сотрудника\nв Итилиуме", BLUE, BLUE_L),
        ("Согласование", "владелец ресурса,\nпри необходимости ИБ", TEAL, TEAL_L),
        ("Предоставление", "минимально необходимый\nобъём прав, срок", GREEN, GREEN_L),
        ("Фиксация", "запись в матрице доступа\nи реестре УЗ", GREEN, GREEN_L),
        ("Пересмотр", "ревизия прав:\nкласс A — раз в квартал", AMBER, AMBER_L),
        ("Отзыв", "перемещение, увольнение,\nокончание работ", RED, RED_L),
    ]
    w, gap = 15.0, 1.5
    for i, (t, d, edge, fill) in enumerate(steps):
        x = 0.5 + i * (w + gap)
        _box(ax, x, 42, w, 36, "", fill=fill, edge=edge, radius=1.3)
        ax.text(x + w / 2, 70, t, ha="center", fontsize=7.8, color=edge, weight="bold")
        ax.text(x + w / 2, 56, textwrap.fill(d.replace("\n", " "), 19), ha="center", va="center",
                fontsize=6.3, color=INK, linespacing=1.4)
        if i < len(steps) - 1:
            _arrow(ax, (x + w, 60), (x + w + gap, 60), color=NAVY, lw=1.2, mut=9)

    _box(ax, 1, 6, 48, 30,
         "Типы учётных записей: пользовательская · административная (персональная, только для "
         "администрирования) · сервисная (для служб, без интерактивного входа) · техническая (оборудование) · "
         "аварийная break-glass. Работа под административной учётной записью в повседневных задачах "
         "(почта, интернет, документы) запрещена.",
         fill="#F7FAFC", edge=BLUE, fontsize=7.0, wrap=64, radius=1.3)
    _box(ax, 51, 6, 48, 30,
         "Аварийная (break-glass) учётная запись: единственный общий административный аккаунт, "
         "пароль хранится в отделе ИБ в запечатанном виде. Использование — только при невозможности "
         "штатного доступа, с уведомлением ИБ и руководителя ОТИ и обязательной сменой пароля "
         "в течение 24 часов после применения.",
         fill="#FFF6F6", edge=RED, fontsize=7.2, wrap=64, radius=1.3)
    return _save(fig, "access_cycle")


CHARTS = {
    "org_structure": org_structure,
    "maturity_radar": maturity_radar,
    "support_lines": support_lines,
    "responsibility_scope": responsibility_scope,
    "criticality_pyramid": criticality_pyramid,
    "service_lifecycle": service_lifecycle,
    "request_flow": request_flow,
    "priority_matrix": priority_matrix,
    "escalation_ladder": escalation_ladder,
    "change_flow": change_flow,
    "maintenance_windows": maintenance_windows,
    "change_metrics": change_metrics,
    "capacity_forecast": capacity_forecast,
    "equipment_lifecycle": equipment_lifecycle,
    "refresh_cycle": refresh_cycle,
    "rpo_rto": rpo_rto,
    "backup_scheme": backup_scheme,
    "monitoring_layers": monitoring_layers,
    "availability_chart": availability_chart,
    "incident_flow": incident_flow,
    "duty_schedule": duty_schedule,
    "contractor_access": contractor_access,
    "procurement_flow": procurement_flow,
    "budget_structure": budget_structure,
    "documentation_tree": documentation_tree,
    "reporting_cadence": reporting_cadence,
    "kpi_dashboard": kpi_dashboard,
    "rollout_gantt": rollout_gantt,
    "substitution_matrix": substitution_matrix,
    "workload_split": workload_split,
    "authority_map": authority_map,
    "security_split": security_split,
    "access_cycle": access_cycle,
}


def build_all() -> dict:
    setup_fonts()
    return {name: fn() for name, fn in CHARTS.items()}


if __name__ == "__main__":
    for name, path in build_all().items():
        print(f"{name}: {path}")
