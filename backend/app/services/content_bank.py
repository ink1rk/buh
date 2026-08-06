"""Curated daily content: quotes, tips, facts, cognitive biases."""

from __future__ import annotations

import hashlib
from datetime import date

WIDGET_TYPES = [
    "tip",
    "thought",
    "fact",
    "bias",
    "invest",
    "save",
    "negotiate",
    "career",
    "income",
]

QUOTES = [
    {"text": "Не богат тот, кто много зарабатывает. Богат тот, кто умеет сохранять.", "author": "Народная мудрость", "theme": "saving"},
    {"text": "Каждый вложенный сегодня рубль — это сотрудник, который будет работать на тебя завтра.", "author": "Personal Finance AI", "theme": "invest"},
    {"text": "Правило №1: никогда не теряй деньги. Правило №2: никогда не забывай правило №1.", "author": "Уоррен Баффетт", "theme": "invest"},
    {"text": "Сложный процент — восьмое чудо света. Тот, кто понимает его — зарабатывает. Кто не понимает — платит.", "author": "Альберт Эйнштейн (приписывается)", "theme": "invest"},
    {"text": "Богатство — это то, что остаётся, когда ты перестаёшь работать.", "author": "Роберт Кийосаки", "theme": "freedom"},
    {"text": "Риск возникает, когда вы не знаете, что делаете.", "author": "Уоррен Баффетт", "theme": "risk"},
    {"text": "Живите ниже своих возможностей — и возможности вырастут.", "author": "Морган Хаузел", "theme": "saving"},
    {"text": "Удача любит подготовленных — и диверсифицированных.", "author": "Нассим Талеб", "theme": "risk"},
    {"text": "Покажите мне стимулы — и я покажу вам результат.", "author": "Чарли Мангер", "theme": "behavior"},
    {"text": "Большинство людей переоценивают то, что могут сделать за год, и недооценивают — за десять.", "author": "Билл Гейтс / Джеймс Клир", "theme": "habits"},
    {"text": "Диверсификация — защита от неведения.", "author": "Уоррен Баффетт", "theme": "invest"},
    {"text": "Сначала заплати себе.", "author": "Джордж Клейсон", "theme": "saving"},
    {"text": "Боль — это информация. Убыток без анализа — просто ошибка.", "author": "Рэй Далио", "theme": "learn"},
    {"text": "Привычки — это проценты, которые капитализируются каждый день.", "author": "Джеймс Клир", "theme": "habits"},
    {"text": "Финансовая свобода — это не сумма на счёте. Это количество дней, которые вы можете прожить без дохода.", "author": "Морган Хаузел", "theme": "freedom"},
    {"text": "Не ставьте всё на чёрное — даже если оно красиво блестит.", "author": "Personal Finance AI", "theme": "risk"},
    {"text": "Цена импульсивной покупки — не только деньги, но и отложенная мечта.", "author": "Personal Finance AI", "theme": "behavior"},
    {"text": "Подушка безопасности — это спокойный сон, переведённый в рубли.", "author": "Personal Finance AI", "theme": "emergency"},
]

WIDGETS = [
    {"widget_type": "tip", "title": "Совет дня", "body": "Переведи 10% дохода на накопительный счёт в день зарплаты — до того, как успеешь их потратить.", "author": "", "source": "pay-yourself-first"},
    {"widget_type": "thought", "title": "Умная мысль", "body": "Деньги — это инструмент свободы выбора. Каждая трата либо приближает к свободе, либо отдаляет.", "author": "", "source": "philosophy"},
    {"widget_type": "fact", "title": "Интересный факт", "body": "Если откладывать 15 000 ₽ в месяц под 12% годовых, через 10 лет у вас будет около 3,5 млн ₽.", "author": "", "source": "compound"},
    {"widget_type": "bias", "title": "Ошибка мышления", "body": "Эффект невозвратных затрат: вы держитесь за плохое вложение, потому что «уже вложили». Отпускайте прошлое — смотрите на будущее.", "author": "", "source": "sunk-cost"},
    {"widget_type": "invest", "title": "Совет по инвестициям", "body": "Ребалансируйте портфель раз в квартал. Это заставляет продавать дорогое и покупать дешёвое — без эмоций.", "author": "", "source": "rebalance"},
    {"widget_type": "save", "title": "Совет по экономии", "body": "Перед подпиской включите «тест на 30 дней»: если не вспомнили о сервисе за месяц — он вам не нужен.", "author": "", "source": "subscriptions"},
    {"widget_type": "negotiate", "title": "Совет по переговорам", "body": "Называйте сумму первой в переговорах о зарплате только если хорошо знаете рынок. Иначе пусть говорит работодатель.", "author": "", "source": "salary"},
    {"widget_type": "career", "title": "Совет по карьере", "body": "Самая высокая доходность — инвестиции в навыки, которые сложно автоматизировать: переговоры, системное мышление, доверие.", "author": "", "source": "skills"},
    {"widget_type": "income", "title": "Рост доходов", "body": "Создайте «меню услуг»: 3 продукта, которые можете продавать параллельно основной работе. Даже 1 клиент в месяц меняет траекторию.", "author": "", "source": "side-income"},
    {"widget_type": "tip", "title": "Совет дня", "body": "Используйте правило 24 часов для покупок дороже 5 000 ₽. Импульс проходит — решение становится яснее.", "author": "", "source": "cooling"},
    {"widget_type": "fact", "title": "Интересный факт", "body": "Средний человек тратит на доставку еды сумму, сопоставимую с месячным взносом в хороший инвестиционный портфель.", "author": "", "source": "delivery"},
    {"widget_type": "bias", "title": "Ошибка мышления", "body": "Ментальный учёт: «бонус — это бесплатные деньги». Нет. Это тоже ваши деньги — с тем же правом на цель.", "author": "", "source": "mental-accounting"},
    {"widget_type": "invest", "title": "Совет по инвестициям", "body": "Не гонитесь за доходностью выше инфляции + разумный риск. Сначала защита капитала, потом рост.", "author": "", "source": "capital"},
    {"widget_type": "save", "title": "Совет по экономии", "body": "Автоматизируйте платежи по целям. Воля — плохой CFO. Система — отличный.", "author": "", "source": "automation"},
    {"widget_type": "thought", "title": "Умная мысль", "body": "Финансовая дисциплина — это не ограничение. Это дизайн будущей свободы.", "author": "", "source": "discipline"},
    {"widget_type": "negotiate", "title": "Совет по переговорам", "body": "Всегда имейте BATNA — лучшую альтернативу соглашению. Без неё вы торгуетесь из слабости.", "author": "Фишер / Ури", "source": "batna"},
    {"widget_type": "career", "title": "Совет по карьере", "body": "Раз в квартал обновляйте CV и LinkedIn — даже если не ищете работу. Рынок должен знать вашу цену.", "author": "", "source": "market"},
    {"widget_type": "income", "title": "Рост доходов", "body": "Попросите обратную связь у руководителя: «Какой навык на +20% к моей ценности для команды?» — и закройте этот разрыв.", "author": "", "source": "feedback"},
]


def _day_index(d: date, modulus: int) -> int:
    seed = int(hashlib.md5(d.isoformat().encode()).hexdigest(), 16)
    return seed % modulus


def quote_for_date(d: date) -> dict:
    return QUOTES[_day_index(d, len(QUOTES))]


def widget_for_date(d: date, previous_type: str | None = None) -> dict:
    idx = _day_index(d, len(WIDGETS))
    widget = WIDGETS[idx]
    if previous_type and widget["widget_type"] == previous_type:
        widget = WIDGETS[(idx + 1) % len(WIDGETS)]
    return widget
