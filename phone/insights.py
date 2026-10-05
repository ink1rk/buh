#!/usr/bin/env python3
"""Осмысление того, что прислал телефон.

Сырые замеры ассистенту бесполезны: «8 231 шаг» ничего не значит без «обычно
у тебя 11 тысяч». Поэтому всё здесь считается относительно нормы самого
человека за последние две недели, а не относительно рекомендаций ВОЗ.

Модуль ничего не знает ни о HTTP, ни об MCP: на входе — база, на выходе —
словари и человеческие формулировки.
"""
import datetime
import statistics
import time

from . import metrics, store
from .config import config

# Метрики, которые показываются в сводке дня, и в каком порядке.
DAILY = ("sleep", "steps", "active_energy", "exercise_minutes", "resting_hr",
         "hrv", "stand_hours", "distance", "screen_time", "weight")

# Отклонение от собственной нормы, после которого об этом стоит сказать
# вслух, и насколько это срочно. Пороги разные: сон на пятую часть меньше —
# это заметно, а пульс покоя выше на восемь процентов — это «ты заболеваешь».
ANOMALIES = {
    "sleep": (-0.2, "medium"),
    "resting_hr": (0.08, "high"),
    "hrv": (-0.25, "medium"),
    "steps": (-0.5, "low"),
    "screen_time": (0.5, "low"),
}


def day_bounds(day=None):
    """Границы суток в часовом поясе владельца, а не в UTC."""
    if day is None:
        today = datetime.datetime.now(config.tz).date()
    elif isinstance(day, str):
        today = datetime.date.fromisoformat(day)
    elif isinstance(day, datetime.datetime):
        today = day.astimezone(config.tz).date()
    else:
        today = day
    start = datetime.datetime.combine(today, datetime.time.min, tzinfo=config.tz)
    return start.timestamp(), (start + datetime.timedelta(days=1)).timestamp()


def day_of(ts):
    return datetime.datetime.fromtimestamp(ts, config.tz).date().isoformat()


def _sample_day(sample):
    """Сон принадлежит утру, а не вечеру: ночь с 20-го на 21-е — это 21-е."""
    anchor = (sample.get("ended_at") if sample["metric"].startswith("sleep")
              else sample["started_at"])
    return day_of(anchor or sample["started_at"])


def daily_values(metric, days=14, until=None):
    """{'2026-09-21': 8231.0, …} — по одному числу на день."""
    end = until if until is not None else time.time()
    start = end - days * 86400
    first_day = day_of(start)
    buckets = {}
    # Сон начинается вчера, а считается сегодняшним: выбираем с запасом в
    # сутки и отбрасываем лишнее уже по дню, которому замер принадлежит.
    for sample in store.samples(metric=metric, since=start - 86400, until=end + 86400):
        day = _sample_day(sample)
        if day < first_day:
            continue
        buckets.setdefault(day, []).append(sample["value"])
    return {day: metrics.aggregate(metric, values)
            for day, values in sorted(buckets.items())}


def baseline(metric, days=None, until=None, skip_today=True):
    """Норма — медиана по прошлым дням: один марафон не должен её задрать."""
    days = days or config.baseline_days
    values = daily_values(metric, days=days + 1, until=until)
    if skip_today:
        values.pop(day_of(until or time.time()), None)
    numbers = [v for v in values.values() if v is not None]
    return statistics.median(numbers) if numbers else None


def metric_today(metric, day=None):
    start, end = day_bounds(day)
    samples = [s for s in store.samples(metric=metric, since=start - 86400, until=end)
               if _sample_day(s) == day_of(start)]
    return metrics.aggregate(metric, [s["value"] for s in samples])


def health_today(day=None):
    """Каждая метрика дня рядом со своей нормой — без нормы это просто число."""
    start, _ = day_bounds(day)
    out = {}
    for metric in DAILY:
        value = metric_today(metric, day)
        norm = baseline(metric, until=start + 86399)
        if value is None and norm is None:
            continue
        delta = None
        if value is not None and norm:
            delta = round((value - norm) / norm * 100)
        out[metric] = {
            "label": metrics.label(metric),
            "unit": metrics.unit(metric),
            "value": None if value is None else round(value, 2),
            "baseline": None if norm is None else round(norm, 2),
            "delta_pct": delta,
        }
    return out


def anomalies(day=None):
    """Что сегодня выбивается из собственной нормы настолько, что это важно."""
    start, _ = day_bounds(day)
    found = []
    for metric, (threshold, severity) in ANOMALIES.items():
        value = metric_today(metric, day)
        norm = baseline(metric, until=start + 86399)
        if value is None or not norm:
            continue
        delta = (value - norm) / norm
        triggered = delta <= threshold if threshold < 0 else delta >= threshold
        if not triggered:
            continue
        label = metrics.label(metric)
        unit = metrics.unit(metric)
        found.append({
            "kind": "health",
            "metric": metric,
            "severity": severity,
            "title": f"{label}: {round(value, 1)} {unit}".strip(),
            "detail": f"обычно около {round(norm, 1)} {unit}".strip()
                      + f" ({delta:+.0%})",
            "value": round(value, 2),
            "baseline": round(norm, 2),
        })
    return found


# --- связь ---------------------------------------------------------------
def _peer_key(item):
    return item.get("peer_number") or (item.get("peer_name") or "").lower() or "?"


def communication(day=None):
    start, end = day_bounds(day)
    calls = store.calls(since=start, until=end)
    messages = store.messages(since=start, until=end)
    talk = sum(c["duration"] for c in calls if c["status"] == "answered")
    return {
        "calls": {
            "incoming": sum(1 for c in calls if c["direction"] == "incoming"),
            "outgoing": sum(1 for c in calls if c["direction"] == "outgoing"),
            "missed": sum(1 for c in calls if c["status"] == "missed"),
            "talk_minutes": round(talk / 60, 1),
            "people": len({_peer_key(c) for c in calls}),
        },
        "messages": {
            "incoming": sum(1 for m in messages if m["direction"] == "incoming"),
            "outgoing": sum(1 for m in messages if m["direction"] == "outgoing"),
            "people": len({_peer_key(m) for m in messages}),
            "apps": sorted({m["app"] for m in messages}),
        },
    }


def waiting_for_reply(hours=48, now=None):
    """Кому телефон должен ответ: последнее слово за собеседником.

    Пропущенный звонок — такое же незакрытое дело, как непрочитанное
    сообщение, поэтому звонки и переписка считаются вместе по человеку.
    """
    now = now or time.time()
    since = now - hours * 3600
    events = []
    for call in store.calls(since=since, until=now + 1):
        events.append({"kind": "call", "ts": call["started_at"],
                       "direction": call["direction"], "status": call["status"],
                       "name": call["peer_name"], "number": call["peer_number"],
                       "key": _peer_key(call)})
    for message in store.messages(since=since, until=now + 1):
        events.append({"kind": "message", "ts": message["ts"],
                       "direction": message["direction"], "status": "",
                       "name": message["peer_name"], "number": message["peer_number"],
                       "key": _peer_key(message)})

    latest = {}
    for event in sorted(events, key=lambda e: e["ts"]):
        latest[event["key"]] = event

    grace = config.reply_grace_minutes * 60
    pending = []
    for event in latest.values():
        if event["direction"] != "incoming":
            continue
        if event["kind"] == "call" and event["status"] == "answered":
            continue
        if now - event["ts"] < grace:
            continue                      # человек мог ответить минуту назад
        pending.append({
            "kind": "waiting",
            "severity": "medium",
            "who": event["name"] or event["number"] or "неизвестный номер",
            "number": event["number"],
            "what": "пропущенный звонок" if event["kind"] == "call"
                    else "сообщение без ответа",
            "since": event["ts"],
            "hours_ago": round((now - event["ts"]) / 3600, 1),
        })
    return sorted(pending, key=lambda item: item["since"])


# --- состояние моста -----------------------------------------------------
def bridge_state(now=None):
    now = now or time.time()
    devices = store.devices()
    last = store.last_sync_at()
    silent_after = config.silence_hours * 3600
    return {
        "devices": [{**d, "silent_hours": None if not d["last_seen_at"]
                     else round((now - d["last_seen_at"]) / 3600, 1)}
                    for d in devices],
        "last_sync_at": last,
        "silent": bool(devices) and (last is None or now - last > silent_after),
        "state": store.states(),
        "pending_outbox": len(store.outbox("NEW", limit=100)),
    }


def problems(now=None):
    """Не про здоровье, а про сам мост: молчащее устройство и севший телефон."""
    now = now or time.time()
    state = bridge_state(now)
    out = []
    if not state["devices"]:
        out.append({"kind": "bridge", "severity": "medium",
                    "title": "Телефон не подключён",
                    "detail": "ни одно устройство не поставлено на учёт"})
    elif state["silent"]:
        last = state["last_sync_at"]
        ago = "никогда" if not last else f"{round((now - last) / 3600, 1)} ч назад"
        out.append({"kind": "bridge", "severity": "medium",
                    "title": "Телефон молчит",
                    "detail": f"последняя синхронизация: {ago}"})
    for item in state["state"]:
        battery = item.get("battery")
        if battery is not None and battery <= 15 and not item.get("charging"):
            out.append({"kind": "battery", "severity": "low",
                        "title": f"Батарея {round(battery)}%",
                        "detail": "телефон скоро выключится и перестанет присылать данные"})
    return out


# --- сводки --------------------------------------------------------------
def today(day=None, now=None):
    """Всё про сегодня одним словарём — то, что ассистент спрашивает чаще всего."""
    now = now or time.time()
    start, end = day_bounds(day)
    return {
        "day": day_of(start),
        "generated_at": now,
        "health": health_today(day),
        "workouts": [
            {"kind": w["kind"], "minutes": round(w["duration"] or 0),
             "energy": w["energy"], "distance": w["distance"],
             "avg_hr": w["avg_hr"], "started_at": w["started_at"]}
            for w in store.workouts(since=start, until=end)],
        "communication": communication(day),
        "attention": attention(now=now),
        "bridge": bridge_state(now),
    }


def attention(now=None):
    """Одним списком: и здоровье, и незакрытые разговоры, и сам мост."""
    items = anomalies() + waiting_for_reply(now=now) + problems(now=now)
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(items, key=lambda item: order.get(item.get("severity", "low"), 3))


def series(metric, days=14, until=None):
    """Метрика по дням: цифры, норма и куда всё движется."""
    metric = metrics.canonical(metric)
    values = daily_values(metric, days=days, until=until)
    points = [{"date": day, "value": None if value is None else round(value, 2)}
              for day, value in values.items()]
    numbers = [p["value"] for p in points if p["value"] is not None]
    trend = None
    if len(numbers) >= 4:
        half = len(numbers) // 2
        first, second = numbers[:half], numbers[half:]
        before, after = statistics.mean(first), statistics.mean(second)
        if before:
            change = (after - before) / before
            trend = "растёт" if change > 0.1 else ("падает" if change < -0.1 else "ровно")
    return {
        "metric": metric,
        "label": metrics.label(metric),
        "unit": metrics.unit(metric),
        "points": points,
        "average": round(statistics.mean(numbers), 2) if numbers else None,
        "baseline": baseline(metric, days=days, until=until),
        "trend": trend,
    }


def sleep_nights(nights=7, until=None):
    """Сон интересен вместе с тем, что творилось с сердцем той же ночью."""
    sleep = daily_values("sleep", days=nights, until=until)
    deep = daily_values("sleep_deep", days=nights, until=until)
    rem = daily_values("sleep_rem", days=nights, until=until)
    resting = daily_values("resting_hr", days=nights, until=until)
    hrv = daily_values("hrv", days=nights, until=until)
    out = []
    for day, hours in sleep.items():
        out.append({"date": day, "hours": None if hours is None else round(hours, 2),
                    "deep": _rounded(deep.get(day)), "rem": _rounded(rem.get(day)),
                    "resting_hr": _rounded(resting.get(day)),
                    "hrv": _rounded(hrv.get(day))})
    return out


def _rounded(value, digits=1):
    return None if value is None else round(value, digits)


def digest(day=None, now=None):
    """Короткий человеческий текст — им ассистент открывает утренний брифинг."""
    snapshot = today(day, now=now)
    health = snapshot["health"]
    parts = []

    sleep = health.get("sleep", {}).get("value")
    if sleep:
        hours = int(sleep)
        minutes = int(round((sleep - hours) * 60))
        line = f"Сон {hours} ч {minutes:02d} мин"
        delta = health["sleep"].get("delta_pct")
        if delta is not None and abs(delta) >= 10:
            line += f" ({delta:+d}% к норме)"
        parts.append(line)

    steps = health.get("steps", {}).get("value")
    if steps:
        parts.append(f"{int(steps)} шагов")
    energy = health.get("active_energy", {}).get("value")
    if energy:
        parts.append(f"{int(energy)} ккал")

    calls = snapshot["communication"]["calls"]
    if calls["missed"]:
        parts.append(f"пропущенных звонков: {calls['missed']}")
    waiting = [item for item in snapshot["attention"] if item["kind"] == "waiting"]
    if waiting:
        names = ", ".join(item["who"] for item in waiting[:3])
        parts.append(f"ждут ответа: {names}")

    for item in snapshot["attention"]:
        if item["kind"] in ("health", "bridge"):
            parts.append(f"{item['title']} — {item['detail']}")

    return "; ".join(parts) if parts else "Телефон пока ничего не прислал."
