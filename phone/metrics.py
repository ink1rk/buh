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
    # движение
    "steps": ("Шаги", "шт", "sum", "high"),
    "distance": ("Пройдено", "км", "sum", "high"),
    "cycling_distance": ("Велосипед", "км", "sum", "high"),
    "swimming_distance": ("Проплыто", "м", "sum", "high"),
    "wheelchair_distance": ("На коляске", "км", "sum", "high"),
    "downhill_snow_distance": ("Спуск", "км", "sum", None),
    "push_count": ("Толчков", "шт", "sum", "high"),
    "swim_strokes": ("Гребков", "шт", "sum", None),
    "active_energy": ("Активные калории", "ккал", "sum", "high"),
    "basal_energy": ("Калории покоя", "ккал", "sum", None),
    "exercise_minutes": ("Тренировка", "мин", "sum", "high"),
    "move_minutes": ("Минуты движения", "мин", "sum", "high"),
    "stand_hours": ("Часы стояния", "ч", "sum", "high"),
    "stand_minutes": ("Минуты стоя", "мин", "sum", "high"),
    "flights_climbed": ("Этажи", "шт", "sum", "high"),
    "physical_effort": ("Нагрузка", "МЕТ", "avg", None),
    # Кольца — итог дня по мнению самой Apple. Лежат отдельно от замеров:
    # кольцо движения это те же активные калории, и складывать их нельзя.
    "ring_move": ("Кольцо движения", "ккал", "last", "high"),
    "ring_move_goal": ("Цель движения", "ккал", "last", None),
    "ring_exercise": ("Кольцо тренировки", "мин", "last", "high"),
    "ring_exercise_goal": ("Цель тренировки", "мин", "last", None),
    "ring_stand": ("Кольцо стояния", "ч", "last", "high"),
    "ring_stand_goal": ("Цель стояния", "ч", "last", None),
    "time_in_daylight": ("На дневном свету", "мин", "sum", "high"),

    # сон
    "sleep": ("Сон", "ч", "sum", "high"),
    "sleep_in_bed": ("В постели", "ч", "sum", None),
    "sleep_core": ("Основной сон", "ч", "sum", "high"),
    "sleep_deep": ("Глубокий сон", "ч", "sum", "high"),
    "sleep_rem": ("REM-сон", "ч", "sum", "high"),
    "sleep_awake": ("Пробуждения", "ч", "sum", "low"),
    "sleeping_wrist_temperature": ("Температура во сне", "°C", "avg", None),

    # сердце и дыхание
    "heart_rate": ("Пульс", "уд/мин", "avg", None),
    "heart_rate_min": ("Пульс мин", "уд/мин", "avg", None),
    "heart_rate_max": ("Пульс макс", "уд/мин", "avg", None),
    "resting_hr": ("Пульс покоя", "уд/мин", "avg", "low"),
    "walking_hr": ("Пульс при ходьбе", "уд/мин", "avg", "low"),
    "hr_recovery": ("Восстановление пульса", "уд/мин", "avg", "high"),
    "hrv": ("Вариабельность пульса", "мс", "avg", "high"),
    "vo2max": ("VO2max", "мл/кг/мин", "last", "high"),
    "afib_burden": ("Мерцательная аритмия", "%", "avg", "low"),
    "respiratory_rate": ("Частота дыхания", "вдох/мин", "avg", None),
    "blood_oxygen": ("Кислород в крови", "%", "avg", "high"),
    "blood_pressure_systolic": ("Давление верхнее", "мм рт.ст.", "avg", None),
    "blood_pressure_diastolic": ("Давление нижнее", "мм рт.ст.", "avg", None),
    "peak_expiratory_flow": ("Пиковый выдох", "л/мин", "avg", "high"),
    "forced_vital_capacity": ("ЖЕЛ", "л", "avg", "high"),

    # тело
    "weight": ("Вес", "кг", "last", None),
    "height": ("Рост", "см", "last", None),
    "bmi": ("Индекс массы тела", "", "last", None),
    "body_fat": ("Жир", "%", "last", "low"),
    "lean_body_mass": ("Мышечная масса", "кг", "last", "high"),
    "waist": ("Талия", "см", "last", "low"),
    "body_temperature": ("Температура", "°C", "avg", None),
    "blood_glucose": ("Глюкоза", "ммоль/л", "avg", None),

    # еда и вода
    "water": ("Вода", "л", "sum", "high"),
    "dietary_energy": ("Съедено", "ккал", "sum", None),
    "protein": ("Белки", "г", "sum", None),
    "carbs": ("Углеводы", "г", "sum", None),
    "fat": ("Жиры", "г", "sum", None),
    "sugar": ("Сахар", "г", "sum", "low"),
    "fiber": ("Клетчатка", "г", "sum", "high"),
    "sodium": ("Натрий", "мг", "sum", "low"),
    "caffeine": ("Кофеин", "мг", "sum", "low"),
    "alcohol": ("Алкоголь", "доз", "sum", "low"),

    # походка (Apple считает это признаком состояния)
    "walking_speed": ("Скорость ходьбы", "км/ч", "avg", "high"),
    "walking_step_length": ("Длина шага", "см", "avg", "high"),
    "walking_asymmetry": ("Асимметрия ходьбы", "%", "avg", "low"),
    "walking_double_support": ("Двойная опора", "%", "avg", "low"),
    "stair_speed_up": ("Скорость вверх", "м/с", "avg", "high"),
    "stair_speed_down": ("Скорость вниз", "м/с", "avg", "high"),
    "six_minute_walk": ("Тест 6 минут", "м", "last", "high"),
    "running_power": ("Мощность бега", "Вт", "avg", "high"),
    "running_speed": ("Скорость бега", "км/ч", "avg", "high"),
    "running_stride_length": ("Длина шага бега", "м", "avg", "high"),
    "running_vertical_oscillation": ("Вертикальные колебания", "см", "avg", "low"),
    "running_ground_contact": ("Контакт с землёй", "мс", "avg", "low"),

    # голова и уши
    "mindful_minutes": ("Осознанность", "мин", "sum", "high"),
    "noise_level": ("Уровень шума", "дБ", "avg", "low"),
    "headphone_audio": ("Громкость наушников", "дБ", "avg", "low"),

    # телефон (приходит не из HealthKit, а из экранного времени)
    "screen_time": ("Экранное время", "мин", "sum", "low"),
    "pickups": ("Взятий телефона", "шт", "sum", "low"),
    "notifications": ("Уведомлений", "шт", "sum", "low"),
}

ALIASES = {
    "stepcount": "steps", "step_count": "steps", "шаги": "steps",
    "distancewalkingrunning": "distance", "walking_running_distance": "distance",
    "distance_walking_running": "distance", "walk_run_distance": "distance",
    "distancecycling": "cycling_distance", "cycling_distance": "cycling_distance",
    "distanceswimming": "swimming_distance", "swimming_distance": "swimming_distance",
    "distancewheelchair": "wheelchair_distance",
    "distancedownhillsnowsports": "downhill_snow_distance",
    "pushcount": "push_count", "wheelchair_push_count": "push_count",
    "swimmingstrokecount": "swim_strokes", "swim_stroke_count": "swim_strokes",
    "activeenergyburned": "active_energy", "active_energy_burned": "active_energy",
    "basalenergyburned": "basal_energy", "basal_energy_burned": "basal_energy",
    "appleexercisetime": "exercise_minutes", "apple_exercise_time": "exercise_minutes",
    "exercise_time": "exercise_minutes",
    "applemovetime": "move_minutes", "apple_move_time": "move_minutes",
    "applestandhour": "stand_hours", "apple_stand_hour": "stand_hours",
    "applestandtime": "stand_minutes", "apple_stand_time": "stand_minutes",
    "stand_time": "stand_minutes",
    "flightsclimbed": "flights_climbed",
    "physicaleffort": "physical_effort",
    "timeindaylight": "time_in_daylight", "time_in_daylight": "time_in_daylight",

    "sleepanalysis": "sleep", "sleep_analysis": "sleep", "sleep_asleep": "sleep",
    "asleep": "sleep", "сон": "sleep", "total_sleep": "sleep",
    "asleepunspecified": "sleep", "sleep_unspecified": "sleep",
    "inbed": "sleep_in_bed", "in_bed": "sleep_in_bed",
    "asleepcore": "sleep_core", "sleep_core": "sleep_core", "core": "sleep_core",
    "sleep_deep_core": "sleep_deep", "asleep_deep": "sleep_deep",
    "asleepdeep": "sleep_deep", "deep": "sleep_deep",
    "asleep_rem": "sleep_rem", "asleeprem": "sleep_rem", "rem": "sleep_rem",
    "awake": "sleep_awake", "sleep_awake": "sleep_awake",
    "applesleepingwristtemperature": "sleeping_wrist_temperature",
    "apple_sleeping_wrist_temperature": "sleeping_wrist_temperature",

    "heartrate": "heart_rate", "пульс": "heart_rate",
    "restingheartrate": "resting_hr", "resting_heart_rate": "resting_hr",
    "walkingheartrateaverage": "walking_hr", "walking_heart_rate_average": "walking_hr",
    "walking_heart_rate": "walking_hr",
    "heartraterecoveryoneminute": "hr_recovery",
    "heart_rate_recovery_one_minute": "hr_recovery", "cardio_recovery": "hr_recovery",
    "heartratevariabilitysdnn": "hrv", "heart_rate_variability": "hrv",
    "heart_rate_variability_sdnn": "hrv",
    "vo2max": "vo2max", "vo2_max": "vo2max",
    "atrialfibrillationburden": "afib_burden",
    "atrial_fibrillation_burden": "afib_burden",
    "respiratoryrate": "respiratory_rate",
    "oxygensaturation": "blood_oxygen", "oxygen_saturation": "blood_oxygen",
    "blood_oxygen_saturation": "blood_oxygen",
    "bloodpressuresystolic": "blood_pressure_systolic",
    "bloodpressurediastolic": "blood_pressure_diastolic",
    "systolic": "blood_pressure_systolic", "diastolic": "blood_pressure_diastolic",
    "peakexpiratoryflowrate": "peak_expiratory_flow",
    "peak_expiratory_flow_rate": "peak_expiratory_flow",
    "forcedvitalcapacity": "forced_vital_capacity",

    "bodytemperature": "body_temperature", "body_temperature": "body_temperature",
    "bodymass": "weight", "body_mass": "weight", "вес": "weight",
    "bodymassindex": "bmi", "body_mass_index": "bmi",
    "bodyfatpercentage": "body_fat", "body_fat_percentage": "body_fat",
    "leanbodymass": "lean_body_mass",
    "waistcircumference": "waist", "waist_circumference": "waist",
    "bloodglucose": "blood_glucose",

    "dietarywater": "water", "dietary_water": "water", "вода": "water",
    "dietaryenergyconsumed": "dietary_energy", "dietary_energy": "dietary_energy",
    "dietaryprotein": "protein", "dietary_protein": "protein", "protein": "protein",
    "dietarycarbohydrates": "carbs", "carbohydrates": "carbs",
    "dietaryfattotal": "fat", "total_fat": "fat",
    "dietarysugar": "sugar", "dietaryfiber": "fiber", "fiber": "fiber",
    "dietarysodium": "sodium", "sodium": "sodium",
    "dietarycaffeine": "caffeine", "caffeine": "caffeine",
    "numberofalcoholicbeverages": "alcohol", "alcohol_consumption": "alcohol",

    "walkingspeed": "walking_speed", "walkingsteplength": "walking_step_length",
    "walking_step_length": "walking_step_length",
    "walkingasymmetrypercentage": "walking_asymmetry",
    "walking_asymmetry_percentage": "walking_asymmetry",
    "walkingdoublesupportpercentage": "walking_double_support",
    "walking_double_support_percentage": "walking_double_support",
    "stairascentspeed": "stair_speed_up", "stair_speed_up": "stair_speed_up",
    "stairdescentspeed": "stair_speed_down", "stair_speed_down": "stair_speed_down",
    "sixminutewalktestdistance": "six_minute_walk",
    "six_minute_walking_test_distance": "six_minute_walk",
    "runningpower": "running_power", "runningspeed": "running_speed",
    "runningstridelength": "running_stride_length",
    "runningverticaloscillation": "running_vertical_oscillation",
    "runninggroundcontacttime": "running_ground_contact",

    "mindfulsession": "mindful_minutes", "mindful_session": "mindful_minutes",
    "mindful_minutes": "mindful_minutes",
    "environmentalaudioexposure": "noise_level",
    "environmental_audio_exposure": "noise_level",
    "headphoneaudioexposure": "headphone_audio",
    "headphone_audio_exposure": "headphone_audio",

    "screentime": "screen_time", "screen_time": "screen_time",
}

# Единицы, которые Apple отдаёт не в том, в чём удобно считать.
_HOURS = {"min": 1 / 60, "s": 1 / 3600, "sec": 1 / 3600, "мин": 1 / 60}
CONVERSIONS = {
    ("distance", "m"): 1 / 1000, ("distance", "mi"): 1.609344,
    ("cycling_distance", "m"): 1 / 1000, ("cycling_distance", "mi"): 1.609344,
    ("swimming_distance", "км"): 1000, ("swimming_distance", "yd"): 0.9144,
    ("wheelchair_distance", "m"): 1 / 1000,
    ("exercise_minutes", "s"): 1 / 60, ("exercise_minutes", "ч"): 60,
    ("move_minutes", "s"): 1 / 60,
    ("mindful_minutes", "s"): 1 / 60, ("mindful_minutes", "ч"): 60,
    ("stand_minutes", "s"): 1 / 60, ("stand_minutes", "ч"): 60,
    ("time_in_daylight", "s"): 1 / 60, ("time_in_daylight", "ч"): 60,
    ("screen_time", "ч"): 60, ("screen_time", "s"): 1 / 60,
    ("weight", "g"): 1 / 1000, ("weight", "lb"): 0.45359237,
    ("lean_body_mass", "lb"): 0.45359237,
    ("height", "m"): 100, ("height", "in"): 2.54,
    ("waist", "m"): 100, ("waist", "in"): 2.54,
    ("water", "ml"): 1 / 1000, ("water", "fl_oz"): 0.0295735,
    ("walking_speed", "m/s"): 3.6, ("running_speed", "m/s"): 3.6,
    ("walking_step_length", "m"): 100,
    ("running_ground_contact", "s"): 1000,
    ("running_vertical_oscillation", "m"): 100,
}
for _sleep in ("sleep", "sleep_in_bed", "sleep_core", "sleep_deep", "sleep_rem",
               "sleep_awake"):
    for _unit, _factor in _HOURS.items():
        CONVERSIONS[(_sleep, _unit)] = _factor

# Что Apple зовёт «единицей», а человек — нет.
UNIT_NAMES = {
    "count": "шт", "kcal": "ккал", "cal": "ккал", "kj": "ккал", "bpm": "уд/мин",
    "count/min": "вдох/мин", "ms": "мс", "km": "км", "kg": "кг", "cm": "см",
    "hr": "ч", "hours": "ч", "h": "ч", "minutes": "мин", "min": "мин",
    "degc": "°C", "°c": "°C", "mmhg": "мм рт.ст.", "mg/dl": "мг/дл",
    "mmol/l": "ммоль/л", "l": "л", "g": "г", "mg": "мг", "db": "дБ",
    "dbaspl": "дБ", "dbhls": "дБ", "w": "Вт", "m": "м", "mets": "МЕТ",
    "ml/kg·min": "мл/кг/мин", "ml/(kg*min)": "мл/кг/мин",
}


def canonical(name):
    """`HKQuantityTypeIdentifierStepCount`, `step_count`, «Шаги» → `steps`."""
    key = (name or "").strip()
    if not key:
        return ""
    for prefix in ("HKQuantityTypeIdentifier", "HKCategoryTypeIdentifier",
                   "HKCorrelationTypeIdentifier", "HKCharacteristicTypeIdentifier",
                   "HKDataType", "HKCategoryValueSleepAnalysis"):
        if key.startswith(prefix):
            key = key[len(prefix):]
    key = key.strip().lower().replace(" ", "_").replace("-", "_")
    if key in META:
        return key
    return ALIASES.get(key, ALIASES.get(key.replace("_", ""), key))


FAHRENHEIT = ("degf", "°f", "f", "fahrenheit")
TEMPERATURES = ("body_temperature", "sleeping_wrist_temperature")


def normalize(metric, value, unit=""):
    """Значение в той единице, в которой метрика хранится и показывается."""
    if value is None:
        return None, unit
    raw = (unit or "").strip().lower()
    named = UNIT_NAMES.get(raw, raw)
    if metric in TEMPERATURES and raw in FAHRENHEIT:
        return (value - 32) / 1.8, META[metric][1]
    # Сначала пробуем единицу как прислали, потом — её человеческое имя:
    # «m» у Apple это метры, а у нас — уже переведённое «м».
    factor = CONVERSIONS.get((metric, raw), CONVERSIONS.get((metric, named)))
    if factor:
        value = value * factor
    known = META.get(metric)
    if known:
        return value, known[1]
    return value, named


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
