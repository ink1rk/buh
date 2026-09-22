#!/usr/bin/env python3
"""Полная выгрузка «Здоровья»: вся история, все метрики, один файл.

iPhone умеет отдать всё, что о вас знает Health: «Здоровье» → фото профиля →
«Экспортировать медданные» → `export.zip`. Внутри — XML со всеми замерами за
все годы, кольцами активности и тренировками. Это единственный официальный
способ получить данные целиком, без выбора «каких метрик вам не жалко».

Файл большой: у человека с часами это гигабайт-полтора и миллионы записей.
Поэтому читается он потоком — элемент разобрали, значение отдали, память
освободили, — а пишется пачками.
"""
import calendar
import os
import re
import zipfile
from xml.etree import ElementTree

from .. import ingest, metrics

# Стадии сна приходят не числом, а словом. Глубокий сон — это ещё и сон
# вообще, поэтому стадия даёт два замера: свой и общий.
SLEEP_STAGES = {
    "InBed": ("sleep_in_bed",),
    "Asleep": ("sleep",),
    "AsleepUnspecified": ("sleep",),
    "AsleepCore": ("sleep_core", "sleep"),
    "AsleepDeep": ("sleep_deep", "sleep"),
    "AsleepREM": ("sleep_rem", "sleep"),
    "Awake": ("sleep_awake",),
}

# Что Apple считает итогом дня: кольца. Хранятся отдельно от замеров, иначе
# дневная сумма удвоится — кольцо движения это те же активные калории.
RINGS = (
    ("activeEnergyBurned", "ring_move", "activeEnergyBurnedUnit"),
    ("activeEnergyBurnedGoal", "ring_move_goal", "activeEnergyBurnedUnit"),
    ("appleExerciseTime", "ring_exercise", None),
    ("appleExerciseTimeGoal", "ring_exercise_goal", None),
    ("appleStandHours", "ring_stand", None),
    ("appleStandHoursGoal", "ring_stand_goal", None),
    ("appleMoveTime", "move_minutes", None),
)

WORKOUT_STATS = {
    "ActiveEnergyBurned": ("energy", "sum"),
    "DistanceWalkingRunning": ("distance", "sum"),
    "DistanceCycling": ("distance", "sum"),
    "DistanceSwimming": ("distance", "sum"),
    "HeartRate": ("avg_hr", "average"),
}

CHUNK = 5000


def find_xml(path):
    """Путь к файлу выгрузки: в архиве, в папке или прямо файлом."""
    if os.path.isdir(path):
        for root, _dirs, files in os.walk(path):
            for name in files:
                if name.lower().endswith(".xml") and "cda" not in name.lower():
                    return os.path.join(root, name)
        raise FileNotFoundError(f"в папке {path} нет XML выгрузки")
    return path


def open_stream(path):
    """Файл выгрузки как поток байтов. Архив не распаковывается на диск."""
    path = find_xml(path)
    if zipfile.is_zipfile(path):
        archive = zipfile.ZipFile(path)
        names = [i for i in archive.infolist()
                 if i.filename.lower().endswith(".xml")
                 and "cda" not in i.filename.lower()]
        if not names:
            raise ValueError("в архиве нет файла выгрузки")
        # В русской локали файл называется «экспорт.xml», в английской —
        # «export.xml»; общего у них только то, что он самый большой.
        chosen = max(names, key=lambda i: i.file_size)
        return archive.open(chosen), archive
    return open(path, "rb"), None


_TS = re.compile(r"^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2}) ([+-])(\d{2}):?(\d{2})$")


def parse_ts(text):
    """«2026-09-21 08:30:00 +0300» → эпоха. Вызывается миллионы раз."""
    if not text:
        return None
    match = _TS.match(text)
    if not match:
        return ingest.parse_time(text)
    year, month, day, hour, minute, second, sign, oh, om = match.groups()
    utc = calendar.timegm((int(year), int(month), int(day),
                           int(hour), int(minute), int(second), 0, 0, 0))
    offset = int(oh) * 3600 + int(om) * 60
    return float(utc - offset if sign == "+" else utc + offset)


def _sleep_metrics(value):
    if not value:
        return ()
    stage = value.replace("HKCategoryValueSleepAnalysis", "")
    return SLEEP_STAGES.get(stage, ("sleep",))


def _record(attrib):
    """Одна запись выгрузки — ноль, один или два наших замера."""
    kind = attrib.get("type") or ""
    started = parse_ts(attrib.get("startDate"))
    if started is None:
        return []
    ended = parse_ts(attrib.get("endDate")) or started
    source = attrib.get("sourceName") or ""
    raw = attrib.get("value")

    if "SleepAnalysis" in kind:
        hours = max(ended - started, 0) / 3600
        return [{"metric": name, "value": hours, "unit": "ч",
                 "started_at": started, "ended_at": ended, "source": source}
                for name in _sleep_metrics(raw)]

    if kind.startswith("HKCategoryTypeIdentifier"):
        metric = metrics.canonical(kind)
        if "AppleStandHour" in kind:
            if raw and "Stood" not in raw:
                return []
            value, unit = 1.0, "ч"
        elif "MindfulSession" in kind:
            metric, value, unit = "mindful_minutes", max(ended - started, 0) / 60, "мин"
        else:
            # Событие без числа — считаем его единицей: за день их сложат.
            value, unit = ingest.parse_number(raw, 1.0), ""
        return [{"metric": metric, "value": value, "unit": unit,
                 "started_at": started, "ended_at": ended, "source": source}]

    value = ingest.parse_number(raw)
    if value is None:
        return []
    return [{"metric": kind, "value": value, "unit": attrib.get("unit") or "",
             "started_at": started, "ended_at": ended, "source": source}]


def _workout(element):
    started = parse_ts(element.attrib.get("startDate"))
    if started is None:
        return None
    ended = parse_ts(element.attrib.get("endDate")) or started
    workout = {
        "kind": (element.attrib.get("workoutActivityType") or "")
                .replace("HKWorkoutActivityType", ""),
        "started_at": started,
        "ended_at": ended,
        "duration": ingest.parse_number(element.attrib.get("duration")),
        "duration_unit": element.attrib.get("durationUnit") or "min",
        "energy": ingest.parse_number(element.attrib.get("totalEnergyBurned")),
        "distance": ingest.parse_number(element.attrib.get("totalDistance")),
        "source": element.attrib.get("sourceName") or "",
    }
    # С iOS 16 итоги тренировки лежат не в атрибутах, а в дочерних элементах.
    for stat in element.findall("WorkoutStatistics"):
        kind = (stat.attrib.get("type") or "").replace("HKQuantityTypeIdentifier", "")
        known = WORKOUT_STATS.get(kind)
        if not known:
            continue
        field, attr = known
        value = ingest.parse_number(stat.attrib.get(attr))
        if value is not None and workout.get(field) is None:
            workout[field] = value
        if kind == "HeartRate":
            workout["max_hr"] = ingest.parse_number(stat.attrib.get("maximum"))
    return workout


def _summary(attrib):
    day = attrib.get("dateComponents")
    if not day:
        return []
    started = ingest.parse_time(day)
    out = []
    for source_attr, metric, unit_attr in RINGS:
        value = ingest.parse_number(attrib.get(source_attr))
        if value is None:
            continue
        out.append({"metric": metric, "value": value,
                    "unit": attrib.get(unit_attr or "", "") or "",
                    "started_at": started, "ended_at": started + 86399,
                    "source": "Кольца активности"})
    return out


def read(path, since=None):
    """Поток `("health"|"workout", запись)` из выгрузки, по одной за раз."""
    stream, archive = open_stream(path)
    try:
        context = ElementTree.iterparse(stream, events=("start", "end"))
        _event, root = next(context)
        for event, element in context:
            if event != "end":
                continue
            tag = element.tag
            if tag == "Record":
                for sample in _record(element.attrib):
                    if since is None or sample["started_at"] >= since:
                        yield "health", sample
            elif tag == "Workout":
                workout = _workout(element)
                if workout and (since is None or workout["started_at"] >= since):
                    yield "workout", workout
            elif tag == "ActivitySummary":
                for sample in _summary(element.attrib):
                    if since is None or sample["started_at"] >= since:
                        yield "health", sample
            else:
                continue
            element.clear()
            root.clear()
    finally:
        stream.close()
        if archive is not None:
            archive.close()


def _merge(total, part):
    total["new"] += part.get("new", 0)
    total["duplicates"] += part.get("duplicates", 0)
    rejected = part.get("rejected") or []
    total["rejected"] = (total["rejected"] + rejected)[:ingest.REJECTED_SHOWN]
    total["rejected_count"] = total.get("rejected_count", 0) + part.get(
        "rejected_count", len(rejected))
    return total


def import_export(path, device_id=None, since=None, chunk=CHUNK, progress=None):
    """Залить выгрузку в базу моста. Повторный импорт того же файла безвреден.

    Записи дедуплицируются по метрике, времени и значению, поэтому выгрузку
    можно делать раз в полгода и заливать поверх: новое доедет, старое не
    удвоится.
    """
    report = {"health": {"new": 0, "duplicates": 0, "rejected": []},
              "workouts": {"new": 0, "duplicates": 0, "rejected": []},
              "read": 0}
    health, workouts = [], []

    def flush(force=False):
        if health and (force or len(health) >= chunk):
            _merge(report["health"], ingest.ingest_health(list(health), device_id))
            health.clear()
        if workouts and (force or len(workouts) >= chunk):
            _merge(report["workouts"], ingest.ingest_workouts(list(workouts), device_id))
            workouts.clear()

    for kind, item in read(path, since=since):
        (health if kind == "health" else workouts).append(item)
        report["read"] += 1
        flush()
        if progress and report["read"] % 100000 == 0:
            progress(report["read"])
    flush(force=True)
    return report
