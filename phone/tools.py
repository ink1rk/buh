#!/usr/bin/env python3
"""Инструменты и ресурсы MCP поверх данных телефона.

Каждый инструмент возвращает две вещи сразу: короткий текст для модели и
структуру для интерфейса. Модели нужен смысл («спал на два часа меньше
обычного»), интерфейсу — числа, и превращать одно в другое дважды незачем.

Имена намеренно без точек: те же инструменты уходят модели как функции, а
у OpenAI-совместимых схем в имени допустимы только буквы, цифры, `_` и `-`.
"""
import datetime
import time

from . import insights, metrics, store
from .config import config
from .mcp import Server, ToolError, no_arguments

VERSION = "1.0.0"

INSTRUCTIONS = (
    "Мост с iPhone и Apple Watch владельца. Здесь лежат здоровье (сон, пульс, "
    "HRV, шаги, тренировки), журнал звонков и метаданные переписки — кто, когда "
    "и сколько написал, без текста сообщений.\n"
    "Каждое число уже сравнено с собственной нормой человека за последние две "
    "недели: говори об отклонениях, а не о цифрах. Начинай с phone_today или "
    "phone_attention — там всё, что важно прямо сейчас."
)

READ_ONLY = {"readOnlyHint": True, "openWorldHint": False}

server = Server("jarvis-phone", VERSION, INSTRUCTIONS)


def _number(value, unit=""):
    if value is None:
        return "нет данных"
    shown = int(value) if abs(value - round(value)) < 0.05 else round(value, 1)
    return f"{shown} {unit}".strip()


def _hours(value):
    if value is None:
        return "нет данных"
    return f"{int(value)} ч {int(round((value - int(value)) * 60)):02d} мин"


def _when(ts):
    """У звонка важно время, а не только дата: «в 9 утра» — это другой разговор."""
    return datetime.datetime.fromtimestamp(ts, config.tz).strftime("%d.%m %H:%M")


# --- сводки --------------------------------------------------------------
@server.tool(
    "phone_today",
    "Сводка дня с телефона: здоровье против собственной нормы, звонки, "
    "переписка, тренировки и то, что требует внимания.",
    {"type": "object",
     "properties": {"day": {"type": "string",
                            "description": "день в формате ГГГГ-ММ-ДД; по умолчанию сегодня"}},
     "additionalProperties": False},
    title="Что с телефоном сегодня", annotations=READ_ONLY)
def phone_today(day=None):
    snapshot = insights.today(day)
    return {"text": insights.digest(day), "data": snapshot}


@server.tool(
    "phone_attention",
    "Что требует внимания: отклонения здоровья от нормы, пропущенные звонки и "
    "сообщения без ответа, проблемы самого моста.",
    no_arguments(), title="Требует внимания", annotations=READ_ONLY)
def phone_attention():
    items = insights.attention()
    if not items:
        return {"text": "Ничего не требует внимания.", "data": {"items": []}}
    return {"text": "\n".join(_attention_line(item) for item in items),
            "data": {"items": items}}


def _attention_line(item):
    if item["kind"] == "waiting":
        return f"— {item['who']}: {item['what']} ({item['hours_ago']} ч назад)"
    detail = item.get("detail")
    return f"— {item['title']}: {detail}" if detail else f"— {item['title']}"


@server.tool(
    "phone_health",
    "Одна метрика здоровья по дням: значения, среднее, норма и тренд. "
    "Ключи: sleep, steps, resting_hr, hrv, active_energy, exercise_minutes, "
    "weight, screen_time и другие из Здоровья Apple.",
    {"type": "object",
     "properties": {
         "metric": {"type": "string", "description": "например sleep или resting_hr"},
         "days": {"type": "integer", "minimum": 1, "maximum": 180, "default": 14},
     },
     "required": ["metric"], "additionalProperties": False},
    title="Метрика здоровья", annotations=READ_ONLY)
def phone_health(metric, days=14):
    data = insights.series(metric, days=int(days))
    if not data["points"]:
        known = ", ".join(store.metrics()[:12]) or "пока ничего не пришло"
        raise ToolError(f"по метрике «{metric}» данных нет. Есть: {known}")
    unit = data["unit"]
    text = (f"{data['label']}: в среднем {_number(data['average'], unit)}"
            f" за {len(data['points'])} дн., норма {_number(data['baseline'], unit)}")
    if data["trend"]:
        text += f", тренд {data['trend']}"
    return {"text": text, "data": data}


@server.tool(
    "phone_sleep",
    "Сон за последние ночи вместе с пульсом покоя и вариабельностью той же ночи.",
    {"type": "object",
     "properties": {"nights": {"type": "integer", "minimum": 1, "maximum": 60,
                               "default": 7}},
     "additionalProperties": False},
    title="Сон", annotations=READ_ONLY)
def phone_sleep(nights=7):
    rows = insights.sleep_nights(int(nights))
    if not rows:
        raise ToolError("данных о сне нет: Apple Watch не синхронизировались")
    lines = [f"{row['date']}: {_hours(row['hours'])}"
             + (f", пульс покоя {_number(row['resting_hr'])}" if row["resting_hr"] else "")
             + (f", HRV {_number(row['hrv'])} мс" if row["hrv"] else "")
             for row in rows]
    return {"text": "\n".join(lines), "data": {"nights": rows}}


@server.tool(
    "phone_calls",
    "Журнал звонков: кто, когда, сколько говорили, что пропущено.",
    {"type": "object",
     "properties": {
         "hours": {"type": "integer", "minimum": 1, "maximum": 720, "default": 24},
         "only_missed": {"type": "boolean", "default": False},
         "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
     },
     "additionalProperties": False},
    title="Звонки", annotations=READ_ONLY)
def phone_calls(hours=24, only_missed=False, limit=50):
    since = time.time() - int(hours) * 3600
    rows = store.calls(since=since, limit=int(limit))
    if only_missed:
        rows = [row for row in rows if row["status"] == "missed"]
    if not rows:
        return {"text": f"Звонков за {hours} ч нет.", "data": {"calls": []}}
    lines = []
    for row in rows:
        who = row["peer_name"] or row["peer_number"] or "неизвестный номер"
        when = _when(row["started_at"])
        if row["status"] == "missed":
            lines.append(f"{when} {who} — пропущенный")
        else:
            direction = "входящий" if row["direction"] == "incoming" else "исходящий"
            lines.append(f"{when} {who} — {direction},"
                         f" {round(row['duration'] / 60, 1)} мин")
    return {"text": "\n".join(lines), "data": {"calls": rows}}


@server.tool(
    "phone_messages",
    "Метаданные переписки: кто и сколько писал. Текст сообщений мост не хранит.",
    {"type": "object",
     "properties": {
         "hours": {"type": "integer", "minimum": 1, "maximum": 720, "default": 24},
         "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 100},
     },
     "additionalProperties": False},
    title="Переписка", annotations=READ_ONLY)
def phone_messages(hours=24, limit=100):
    since = time.time() - int(hours) * 3600
    rows = store.messages(since=since, limit=int(limit))
    by_peer = {}
    for row in rows:
        who = row["peer_name"] or row["peer_number"] or "неизвестный номер"
        stats = by_peer.setdefault(who, {"who": who, "app": row["app"],
                                         "incoming": 0, "outgoing": 0, "last": 0})
        stats[row["direction"]] = stats.get(row["direction"], 0) + 1
        stats["last"] = max(stats["last"], row["ts"])
    people = sorted(by_peer.values(), key=lambda item: -item["last"])
    if not people:
        return {"text": f"Сообщений за {hours} ч нет.", "data": {"people": []}}
    lines = [f"{item['who']} ({item['app']}): получено {item['incoming']},"
             f" отправлено {item['outgoing']}" for item in people]
    return {"text": "\n".join(lines), "data": {"people": people, "total": len(rows)}}


@server.tool(
    "phone_workouts",
    "Тренировки с Apple Watch за последние дни.",
    {"type": "object",
     "properties": {"days": {"type": "integer", "minimum": 1, "maximum": 90,
                             "default": 7}},
     "additionalProperties": False},
    title="Тренировки", annotations=READ_ONLY)
def phone_workouts(days=7):
    since = time.time() - int(days) * 86400
    rows = store.workouts(since=since)
    if not rows:
        return {"text": f"Тренировок за {days} дн. нет.", "data": {"workouts": []}}
    lines = [f"{_when(row['started_at'])}: {row['kind'] or 'тренировка'},"
             f" {_number(row['duration'], 'мин')}"
             + (f", {_number(row['energy'], 'ккал')}" if row["energy"] else "")
             for row in rows]
    return {"text": "\n".join(lines), "data": {"workouts": rows}}


@server.tool(
    "phone_devices",
    "Состояние моста: какие устройства на учёте, когда синхронизировались, "
    "заряд и режим фокусирования.",
    no_arguments(), title="Устройства", annotations=READ_ONLY)
def phone_devices():
    state = insights.bridge_state()
    if not state["devices"]:
        return {"text": "Ни одно устройство не подключено.", "data": state}
    lines = []
    for device in state["devices"]:
        silent = device["silent_hours"]
        seen = "ни разу" if silent is None else f"{silent} ч назад"
        lines.append(f"{device['name']} ({device['kind']}): синхронизация {seen}")
    for item in state["state"]:
        if item.get("battery") is not None:
            lines.append(f"заряд {round(item['battery'])}%"
                         + (", заряжается" if item["charging"] else "")
                         + (f", фокус «{item['focus']}»" if item.get("focus") else ""))
    return {"text": "\n".join(lines), "data": state}


# --- обратная связь ------------------------------------------------------
@server.tool(
    "phone_push",
    "Положить задание для телефона: показать уведомление, напомнить или "
    "запустить ярлык. Телефон заберёт его при следующей синхронизации — "
    "мгновенной доставки у моста нет.",
    {"type": "object",
     "properties": {
         "kind": {"type": "string", "enum": ["notify", "reminder", "shortcut"],
                  "default": "notify"},
         "text": {"type": "string", "description": "текст уведомления или имя ярлыка"},
         "target": {"type": "string",
                    "description": "id устройства; пусто — любое устройство"},
     },
     "required": ["text"], "additionalProperties": False},
    title="Отправить на телефон",
    annotations={"readOnlyHint": False, "destructiveHint": False, "openWorldHint": True})
def phone_push(text, kind="notify", target=""):
    if not (text or "").strip():
        raise ToolError("пустой текст")
    if target and store.device(target) is None:
        raise ToolError(f"устройства {target} нет")
    item = store.push_outbox(kind, {"text": text.strip()}, target=target)
    return {"text": f"Задание «{kind}» поставлено в очередь телефона.", "data": item}


# --- ресурсы -------------------------------------------------------------
@server.resource("phone://today", "Сегодня",
                 "Полная сводка дня: здоровье, связь, тренировки, внимание.")
def resource_today():
    return insights.today()


@server.resource("phone://attention", "Требует внимания",
                 "Отклонения здоровья, незакрытые разговоры, состояние моста.")
def resource_attention():
    return {"items": insights.attention()}


@server.resource("phone://devices", "Устройства",
                 "Устройства на учёте, последняя синхронизация и состояние.")
def resource_devices():
    return insights.bridge_state()


@server.resource("phone://metrics", "Метрики",
                 "Какие метрики здоровья телефон реально присылает.",
                 mime_type="application/json")
def resource_metrics():
    return {"metrics": [{"key": key, "label": metrics.label(key),
                         "unit": metrics.unit(key)} for key in store.metrics()]}
