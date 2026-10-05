#!/usr/bin/env python3
"""Справочник метрик здоровья.

Apple называет одну и ту же вещь по-разному в зависимости от того, чем её
выгружают: `HKQuantityTypeIdentifierStepCount` из HealthKit, `step_count` из
Health Auto Export, «Шаги» из ярлыка. Здесь всё это сводится к одному ключу,
единице и способу сложить день.

Незнакомая метрика не отбрасывается: телефон присылает то, что у него есть,
а не то, что мы предусмотрели. Она просто хранится как есть.
"""

# Как складывать значения за день:
#   sum  — шаги, калории, минуты (набегает за сутки)
#   avg  — пульс, HRV, сатурация (мгновенные замеры)
#   last — вес, VO2max (последнее известное)
#   max  — часы стояния (кольцо Watch, накопительный счётчик)
META = {
    "steps": ("Шаги", "шт", "sum", "high"),
    "distance": ("Пройдено", "км", "sum", "high"),
    "active_energy": ("Активные калории", "ккал", "sum", "high"),
    "basal_energy": ("Калории покоя", "ккал", "sum", None),
    "exercise_minutes": ("Тренировка", "мин", "sum", "high"),
    "stand_hours": ("Часы стояния", "ч", "max", "high"),
    "flights_climbed": ("Этажи", "шт", "sum", "high"),
    "sleep": ("Сон", "ч", "sum", "high"),
    "sleep_deep": ("Глубокий сон", "ч", "sum", "high"),
    "sleep_rem": ("REM-сон", "ч", "sum", "high"),
    "heart_rate": ("Пульс", "уд/мин", "avg", None),
    "resting_hr": ("Пульс покоя", "уд/мин", "avg", "low"),
    "walking_hr": ("Пульс при ходьбе", "уд/мин", "avg", "low"),
    "hrv": ("Вариабельность пульса", "мс", "avg", "high"),
    "vo2max": ("VO2max", "мл/кг/мин", "last", "high"),
    "respiratory_rate": ("Частота дыхания", "вдох/мин", "avg", None),
    "blood_oxygen": ("Кислород в крови", "%", "avg", "high"),
    "body_temperature": ("Температура", "°C", "avg", None),
    "weight": ("Вес", "кг", "last", None),
    "mindful_minutes": ("Осознанность", "мин", "sum", "high"),
    "screen_time": ("Экранное время", "мин", "sum", "low"),
    "pickups": ("Взятий телефона", "шт", "sum", "low"),
    "noise_level": ("Уровень шума", "дБ", "avg", "low"),
}

# Границы правдоподобия для одного замера. Это не медицинская норма, а защита
# от мусора: норма у нас считается медианой по собственным дням владельца, и
# один замер «999999999 шагов» или «-500 уд/мин» сдвигает её так, что все
# отклонения после этого считаются от вымысла.
LIMITS = {
    "steps": (0, 200_000),
    "distance": (0, 500),
    "active_energy": (0, 20_000),
    "basal_energy": (0, 20_000),
    "exercise_minutes": (0, 1440),
    "stand_hours": (0, 24),
    "flights_climbed": (0, 1000),
    "sleep": (0, 24),
    "sleep_deep": (0, 24),
    "sleep_rem": (0, 24),
    "heart_rate": (20, 260),
    "resting_hr": (20, 150),
    "walking_hr": (30, 220),
    "hrv": (1, 500),
    "vo2max": (5, 100),
    "respiratory_rate": (3, 60),
    "blood_oxygen": (50, 100),
    "body_temperature": (30, 45),
    "weight": (20, 400),
    "mindful_minutes": (0, 1440),
    "screen_time": (0, 1440),
    "pickups": (0, 5000),
    "noise_level": (0, 140),
}

ALIASES = {
    "stepcount": "steps", "step_count": "steps", "шаги": "steps",
    "distancewalkingrunning": "distance", "walking_running_distance": "distance",
    "distance_walking_running": "distance",
    "activeenergyburned": "active_energy", "active_energy_burned": "active_energy",
    "basalenergyburned": "basal_energy", "basal_energy_burned": "basal_energy",
    "appleexercisetime": "exercise_minutes", "apple_exercise_time": "exercise_minutes",
    "exercise_time": "exercise_minutes",
    "applestandhour": "stand_hours", "apple_stand_hour": "stand_hours",
    "stand_time": "stand_hours", "applestandtime": "stand_hours",
    "flightsclimbed": "flights_climbed",
    "sleepanalysis": "sleep", "sleep_analysis": "sleep", "sleep_asleep": "sleep",
    "asleep": "sleep", "сон": "sleep",
    "sleep_deep_core": "sleep_deep", "asleep_deep": "sleep_deep",
    "asleep_rem": "sleep_rem",
    "heartrate": "heart_rate", "пульс": "heart_rate",
    "restingheartrate": "resting_hr", "resting_heart_rate": "resting_hr",
    "walkingheartrateaverage": "walking_hr", "walking_heart_rate_average": "walking_hr",
    "heartratevariabilitysdnn": "hrv", "heart_rate_variability": "hrv",
    "heart_rate_variability_sdnn": "hrv",
    "vo2max": "vo2max", "vo2_max": "vo2max",
    "respiratoryrate": "respiratory_rate",
    "oxygensaturation": "blood_oxygen", "oxygen_saturation": "blood_oxygen",
    "blood_oxygen_saturation": "blood_oxygen",
    "bodytemperature": "body_temperature", "body_temperature": "body_temperature",
    "bodymass": "weight", "body_mass": "weight", "вес": "weight",
    "mindfulsession": "mindful_minutes", "mindful_session": "mindful_minutes",
    "mindful_minutes": "mindful_minutes",
    "screentime": "screen_time", "screen_time": "screen_time",
    "environmentalaudioexposure": "noise_level",
}

# Единицы, которые Apple отдаёт не в том, в чём удобно считать.
CONVERSIONS = {
    ("sleep", "min"): 1 / 60, ("sleep", "s"): 1 / 3600, ("sleep", "sec"): 1 / 3600,
    ("sleep_deep", "min"): 1 / 60, ("sleep_rem", "min"): 1 / 60,
    ("distance", "m"): 1 / 1000, ("distance", "mi"): 1.609344,
    ("exercise_minutes", "s"): 1 / 60,
    ("mindful_minutes", "s"): 1 / 60,
    ("screen_time", "h"): 60, ("screen_time", "s"): 1 / 60,
    ("weight", "g"): 1 / 1000, ("weight", "lb"): 0.45359237,
    ("stand_hours", "min"): 1 / 60,
}


def canonical(name):
    """`HKQuantityTypeIdentifierStepCount`, `step_count`, «Шаги» → `steps`."""
    key = (name or "").strip()
    if not key:
        return ""
    for prefix in ("HKQuantityTypeIdentifier", "HKCategoryTypeIdentifier"):
        if key.startswith(prefix):
            key = key[len(prefix):]
    key = key.strip().lower().replace(" ", "_").replace("-", "_")
    if key in META:
        return key
    return ALIASES.get(key, ALIASES.get(key.replace("_", ""), key))


def normalize(metric, value, unit=""):
    """Значение в той единице, в которой метрика хранится и показывается."""
    if value is None:
        return None, unit
    unit = (unit or "").strip().lower()
    unit = {"count": "шт", "kcal": "ккал", "cal": "ккал", "bpm": "уд/мин",
            "ms": "мс", "%": "%", "km": "км", "kg": "кг", "hr": "ч",
            "hours": "ч", "minutes": "мин", "count/min": "вдох/мин"}.get(unit, unit)
    factor = CONVERSIONS.get((metric, unit))
    if factor:
        value = value * factor
        unit = ""
    known = META.get(metric)
    if known:
        return value, known[1]
    return value, unit


def label(metric):
    known = META.get(metric)
    return known[0] if known else metric


def unit(metric):
    known = META.get(metric)
    return known[1] if known else ""


def how(metric):
    """Как складывать значения за день: sum | avg | last | max."""
    known = META.get(metric)
    return known[2] if known else "sum"


def direction(metric):
    """Куда лучше: `high`, `low` или неважно."""
    known = META.get(metric)
    return known[3] if known else None


def plausible(metric, value):
    """Похоже ли значение на эту метрику вообще."""
    low, high = LIMITS.get(metric, (float("-inf"), float("inf")))
    return low <= value <= high


def aggregate(metric, values):
    values = [v for v in values if v is not None]
    if not values:
        return None
    rule = how(metric)
    if rule == "avg":
        return sum(values) / len(values)
    if rule == "last":
        return values[-1]
    if rule == "max":
        return max(values)
    return sum(values)
