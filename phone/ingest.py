#!/usr/bin/env python3
"""Приём данных: выгрузка Здоровья, Health Auto Export, базы Apple.

Формат приходит таким, каким его отдал источник, а не таким, каким нам
удобно. Поэтому здесь всё разбирается терпимо — время в трёх видах, числа
строками и объектами `{"qty": …}`, метрики под именами HealthKit и
приложения, — и ни одна кривая строка не роняет пакет целиком.

Источник не помнит, что уже отправлял. Дедупликация по `external_id` —
единственное, что отличает повтор от нового события, поэтому ключ строится
всегда, даже если его не прислали.
"""
import datetime
import hashlib
import re
import time

from . import metrics, store
from .config import config

CALL_DIRECTIONS = {
    "in": "incoming", "incoming": "incoming", "received": "incoming",
    "входящий": "incoming", "входящие": "incoming",
    "out": "outgoing", "outgoing": "outgoing", "dialed": "outgoing",
    "outbound": "outgoing", "исходящий": "outgoing",
}

CALL_STATUSES = {
    "answered": "answered", "completed": "answered", "connected": "answered",
    "missed": "missed", "no answer": "missed", "noanswer": "missed",
    "пропущенный": "missed", "пропущен": "missed",
    "declined": "declined", "rejected": "declined", "отклонён": "declined",
    "voicemail": "voicemail", "автоответчик": "voicemail",
}

MESSAGE_APPS = {"imessage", "sms", "whatsapp", "telegram", "signal", "mail", "other"}

ISO_CLEAN = re.compile(r"\s+(?=[+-]\d{2}:?\d{2}$)")


def parse_time(value, default=None):
    """Эпоха, ISO 8601 или «2026-09-21 08:30:00 +0300» — всё это время."""
    if value is None or value == "":
        return default if default is not None else time.time()
    if isinstance(value, (int, float)):
        seconds = float(value)
        # Ярлыки иногда отдают миллисекунды: 2026 год в секундах — 1.7e9.
        return seconds / 1000 if seconds > 1e11 else seconds
    text = str(value).strip()
    if re.fullmatch(r"-?\d+(\.\d+)?", text):
        return parse_time(float(text))
    candidate = ISO_CLEAN.sub("", text.replace("Z", "+00:00"))
    for parse in (datetime.datetime.fromisoformat,
                  lambda s: datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S"),
                  lambda s: datetime.datetime.strptime(s, "%d.%m.%Y %H:%M"),
                  lambda s: datetime.datetime.strptime(s, "%Y-%m-%d")):
        try:
            parsed = parse(candidate)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=config.tz)
        return parsed.timestamp()
    raise ValueError(f"непонятное время: {value!r}")


def parse_number(value, default=None):
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        # Health Auto Export пишет величину объектом: {"qty": 5.2, "units": "km"}.
        for key in ("qty", "value", "Avg", "avg", "sum", "total"):
            if value.get(key) is not None:
                return parse_number(value[key], default)
        return default
    if isinstance(value, (list, tuple)):
        return parse_number(value[0], default) if value else default
    text = str(value).strip().replace(",", ".")
    match = re.search(r"-?\d+(\.\d+)?", text)
    return float(match.group()) if match else default


def normalize_number(raw):
    """+7 (999) 123-45-67, 89991234567, 8 999 … — один и тот же человек."""
    digits = re.sub(r"\D", "", str(raw or ""))
    if not digits:
        return ""
    if len(digits) == 11 and digits[0] in "78":
        digits = "7" + digits[1:]
    return "+" + digits if len(digits) >= 10 else str(raw).strip()


def fingerprint(*parts):
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha1(raw.encode()).hexdigest()[:20]


def _first(item, *keys):
    """Первое осмысленное значение из тех имён, под которыми его шлют."""
    for key in keys:
        value = parse_number(item.get(key))
        if value is not None:
            return value
    return None


def _external_id(item, kind, *parts):
    for key in ("external_id", "id", "uuid", "identifier"):
        value = item.get(key)
        if value:
            return f"{kind}:{value}"
    return f"{kind}:{fingerprint(*parts)}"


REJECTED_SHOWN = 20
BATCH = 2000


class Sink:
    """Копит разобранные записи и отдаёт их в базу пачками.

    Живой пакет с телефона — десятки строк, выгрузка «Здоровья» за пять лет —
    миллионы. Одна дорога для обоих возможна только если писать пачками:
    построчная запись превращает импорт в часы.
    """

    def __init__(self, save, size=BATCH):
        self._save = save
        self._size = size
        self._rows = []
        self.new = 0
        self.duplicates = 0
        self.rejected = []
        self.rejected_count = 0

    def add(self, row):
        self._rows.append(row)
        if len(self._rows) >= self._size:
            self.flush()

    def reject(self, index, reason):
        self.rejected_count += 1
        if len(self.rejected) < REJECTED_SHOWN:
            self.rejected.append({"index": index, "reason": str(reason)})

    def flush(self):
        if not self._rows:
            return
        saved = self._save(self._rows)
        self.new += saved
        self.duplicates += len(self._rows) - saved
        self._rows = []

    def report(self):
        self.flush()
        out = {"new": self.new, "duplicates": self.duplicates,
               "rejected": self.rejected}
        if self.rejected_count > len(self.rejected):
            out["rejected_count"] = self.rejected_count
        return out


# --- звонки --------------------------------------------------------------
def ingest_calls(items, device_id=None):
    sink = Sink(store.save_calls)
    for index, item in enumerate(items or []):
        try:
            started = parse_time(item.get("started_at") or item.get("start")
                                 or item.get("date") or item.get("ts"))
            duration = parse_number(item.get("duration") or item.get("duration_sec"), 0) or 0
            if str(item.get("duration_unit", "")).startswith("min"):
                duration *= 60
            direction = CALL_DIRECTIONS.get(
                str(item.get("direction", "incoming")).strip().lower(), "incoming")
            status = CALL_STATUSES.get(
                str(item.get("status") or item.get("result") or "").strip().lower())
            if status is None:
                # Входящий нулевой длины — это пропущенный, что бы телефон
                # ни написал в поле статуса.
                status = "answered" if duration > 0 else (
                    "missed" if direction == "incoming" else "declined")
            number = normalize_number(item.get("peer_number") or item.get("number")
                                      or item.get("phone"))
            call = {
                "external_id": _external_id(item, "call", direction, number,
                                            round(started), round(duration)),
                "direction": direction,
                "status": status,
                "peer_name": (item.get("peer_name") or item.get("name") or "").strip(),
                "peer_number": number,
                "app": (item.get("app") or "phone").strip().lower(),
                "started_at": started,
                "duration": duration,
                "note": (item.get("note") or "").strip()[:500],
                "device_id": device_id,
            }
        except (ValueError, TypeError) as e:
            sink.reject(index, e)
            continue
        sink.add(call)
    return sink.report()


# --- сообщения -----------------------------------------------------------
def ingest_messages(items, device_id=None):
    sink = Sink(store.save_messages)
    for index, item in enumerate(items or []):
        try:
            ts = parse_time(item.get("ts") or item.get("date") or item.get("time"))
            text = str(item.get("text") or item.get("body") or "")
            direction = CALL_DIRECTIONS.get(
                str(item.get("direction", "incoming")).strip().lower(), "incoming")
            app = (item.get("app") or "imessage").strip().lower()
            number = normalize_number(item.get("peer_number") or item.get("number")
                                      or item.get("sender"))
            message = {
                "external_id": _external_id(item, "msg", app, direction, number,
                                            round(ts), len(text)),
                "app": app if app in MESSAGE_APPS else "other",
                "direction": direction,
                "peer_name": (item.get("peer_name") or item.get("name") or "").strip(),
                "peer_number": number,
                # Текст переписки — самое чувствительное, что есть в телефоне.
                # По умолчанию от сообщения остаётся только форма: кто, когда,
                # сколько написал.
                "chars": int(parse_number(item.get("chars"), len(text)) or 0),
                "attachments": int(parse_number(item.get("attachments"), 0) or 0),
                "preview": text[:config.preview_chars] if config.store_text else "",
                "ts": ts,
                "device_id": device_id,
            }
        except (ValueError, TypeError) as e:
            sink.reject(index, e)
            continue
        sink.add(message)
    return sink.report()


# --- здоровье ------------------------------------------------------------
# Health Auto Export кладёт в одну точку сразу несколько величин: ночь — это
# «сколько всего», «сколько глубокого», «сколько REM»; пульс за час — среднее,
# минимум и максимум. Разворачиваем в отдельные замеры, иначе от ночи
# останется одно число и стадии сна пропадут.
COMPOUND = {
    "sleep": {"asleep": "sleep", "totalSleep": "sleep", "inBed": "sleep_in_bed",
              "core": "sleep_core", "deep": "sleep_deep", "rem": "sleep_rem",
              "awake": "sleep_awake"},
    "heart_rate": {"Avg": "heart_rate", "avg": "heart_rate",
                   "Min": "heart_rate_min", "Max": "heart_rate_max"},
    "resting_hr": {"Avg": "resting_hr", "Min": "resting_hr", "Max": "resting_hr"},
    "walking_hr": {"Avg": "walking_hr"},
    "blood_pressure": {"systolic": "blood_pressure_systolic",
                       "diastolic": "blood_pressure_diastolic"},
    "blood_glucose": {"Avg": "blood_glucose", "qty": "blood_glucose"},
}


def _expand(name, unit, point):
    """Одна точка приложения — один или несколько наших замеров."""
    if not isinstance(point, dict):
        return []
    metric = metrics.canonical(name)
    plain = {k: v for k, v in point.items() if not isinstance(v, (dict, list))}
    parts = COMPOUND.get(metric)
    if parts:
        out = []
        for field, target in parts.items():
            if point.get(field) in (None, ""):
                continue
            out.append({**plain, "metric": target, "unit": unit,
                        "value": point[field]})
        if out:
            # Сон приходит окном «лёг — встал», а величины в нём — часами.
            for item in out:
                if point.get("sleepStart"):
                    item.setdefault("started_at", point["sleepStart"])
                if point.get("sleepEnd"):
                    item.setdefault("ended_at", point["sleepEnd"])
            return out
    return [{**plain, "metric": name, "unit": unit}]


def flatten_health(payload):
    """Health Auto Export отдаёт метрику пачкой; ярлык — по одному замеру."""
    if isinstance(payload, dict):
        data = payload.get("data", payload)
        groups = data.get("metrics") if isinstance(data, dict) else None
        if groups is None:
            return [payload]
        flat = []
        for group in groups:
            name = group.get("name") or group.get("metric")
            unit = group.get("units") or group.get("unit") or ""
            for point in group.get("data") or []:
                flat.extend(_expand(name, unit, point))
        return flat
    return list(payload or [])


def ingest_health(payload, device_id=None):
    sink = Sink(store.save_samples)
    for index, item in enumerate(flatten_health(payload)):
        try:
            metric = metrics.canonical(item.get("metric") or item.get("name")
                                       or item.get("type"))
            if not metric:
                raise ValueError("метрика без имени")
            started = parse_time(item.get("started_at") or item.get("start")
                                 or item.get("startDate") or item.get("sleepStart")
                                 or item.get("date") or item.get("ts"))
            ended = parse_time(item.get("ended_at") or item.get("end")
                               or item.get("endDate") or item.get("sleepEnd")
                               or "", started)
            raw = item.get("value")
            if raw is None:
                raw = item.get("qty", item.get("quantity"))
            value = parse_number(raw)
            if value is None:
                raise ValueError("замер без значения")
            # Сон приходит и часами, и интервалом «лёг — встал».
            unit = item.get("unit") or item.get("units") or ""
            if metric.startswith("sleep") and not unit and ended > started + 60:
                value, unit = (ended - started) / 3600, "ч"
            value, unit = metrics.normalize(metric, value, unit)
            sample = {
                "external_id": _external_id(item, "smp", metric, round(started),
                                            round(value, 4)),
                "metric": metric,
                "value": value,
                "unit": unit,
                "started_at": started,
                "ended_at": ended,
                "source": (item.get("source") or "").strip(),
                "device_id": device_id,
            }
        except (ValueError, TypeError) as e:
            sink.reject(index, e)
            continue
        sink.add(sample)
    return sink.report()


def _duration_minutes(item, started, ended):
    """Длительность в минутах, чем бы её ни прислали.

    Apple пишет минуты, Health Auto Export — секунды, и различить их по
    самому числу нельзя. Зато есть окно «начало — конец»: из двух прочтений
    верно то, что на него похоже.
    """
    span = max(ended - started, 0)
    value = parse_number(item.get("duration"))
    if value is None:
        return span / 60
    unit = str(item.get("duration_unit") or item.get("durationUnit") or "").lower()
    if unit.startswith("s") or unit in ("сек", "с"):
        return value / 60
    if unit.startswith("h") or unit in ("ч", "час"):
        return value * 60
    if unit.startswith("m") or unit in ("мин",):
        return value
    if span > 0:
        return value / 60 if abs(value - span) < abs(value * 60 - span) else value
    return value / 60 if value > 600 else value


def ingest_workouts(items, device_id=None):
    sink = Sink(store.save_workouts)
    for index, item in enumerate(items or []):
        try:
            started = parse_time(item.get("started_at") or item.get("start")
                                 or item.get("startDate") or item.get("date"))
            ended = parse_time(item.get("ended_at") or item.get("end")
                               or item.get("endDate") or "", started)
            duration = _duration_minutes(item, started, ended)
            workout = {
                "external_id": _external_id(item, "wrk", round(started),
                                            round(duration, 2)),
                "kind": (item.get("kind") or item.get("type") or item.get("name")
                         or item.get("workoutActivityType") or "").strip(),
                "started_at": started,
                "ended_at": ended,
                "duration": duration,
                "energy": _first(item, "energy", "active_energy", "calories",
                                 "activeEnergyBurned", "activeEnergy",
                                 "totalEnergy", "totalEnergyBurned"),
                "distance": _first(item, "distance", "totalDistance",
                                   "walkingAndRunningDistance", "cyclingDistance",
                                   "swimmingDistance"),
                "avg_hr": _first(item, "avg_hr", "average_heart_rate", "avgHeartRate",
                                 "averageHeartRate"),
                "max_hr": _first(item, "max_hr", "max_heart_rate", "maxHeartRate"),
                "source": (item.get("source") or "").strip(),
                "device_id": device_id,
            }
        except (ValueError, TypeError) as e:
            sink.reject(index, e)
            continue
        sink.add(workout)
    return sink.report()


def ingest_state(state, device_id):
    battery = parse_number((state or {}).get("battery"))
    if battery is not None and battery <= 1:
        battery *= 100                      # ярлык отдаёт долю, человек ждёт проценты
    store.save_state(device_id, {
        "battery": battery,
        "charging": (state or {}).get("charging"),
        "focus": (state or {}).get("focus"),
        "place": (state or {}).get("place") or (state or {}).get("location"),
        "network": (state or {}).get("network"),
        "extra": {k: v for k, v in (state or {}).items()
                  if k not in ("battery", "charging", "focus", "place",
                               "location", "network")},
    })
    return {"saved": True}


# --- всё разом -----------------------------------------------------------
def ingest_batch(payload, device_id=None):
    """Один запрос ярлыка — один пакет со всем, что накопилось.

    Понимает и наш формат (`{"calls": [...], "health": [...]}`), и формат
    Health Auto Export (`{"data": {"metrics": [...], "workouts": [...]}}`),
    чтобы приложение можно было направить на мост без прослойки.
    """
    payload = payload or {}
    nested = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    sections = (
        ("calls", payload.get("calls"), ingest_calls),
        ("messages", payload.get("messages"), ingest_messages),
        ("health", payload.get("health") if "health" in payload
         else (payload if nested.get("metrics") else None), ingest_health),
        ("workouts", payload.get("workouts") if "workouts" in payload
         else nested.get("workouts"), ingest_workouts),
    )

    result = {}
    for name, section, handler in sections:
        if section is None:
            continue
        result[name] = handler(section, device_id)
    if payload.get("state") and device_id:
        result["state"] = ingest_state(payload["state"], device_id)
    if device_id:
        store.touch_device(device_id)
    result["accepted"] = sum(section.get("new", 0) for section in result.values()
                             if isinstance(section, dict))
    return result
