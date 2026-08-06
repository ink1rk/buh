"""AI Coach — one bite-sized challenge per day."""

from __future__ import annotations

import hashlib
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.coach import DailyChallenge

CHALLENGES = [
    ("save", "Без кофе навынос", "Сегодня попробуй не покупать кофе вне дома. Разницу переведи в цель."),
    ("save", "День без доставки", "Откажись от доставки еды сегодня — приготовь дома или возьми с собой."),
    ("save", "Отложи 300 ₽", "Прямо сейчас переведи 300 ₽ на накопительный счёт. Мелочь, но привычка важнее суммы."),
    ("declutter", "Продай ненужное", "Найди одну вещь, которой не пользовался 3 месяца, и выстави на продажу."),
    ("debt", "Погаси маленький долг", "Закрой самый маленький из открытых долгов сегодня — психологически это мощно."),
    ("invest", "Одна инвестиция", "Сделай один взнос в инвестиции — даже небольшой. Регулярность важнее суммы."),
    ("awareness", "Аудит подписок", "Открой список подписок и отмени хотя бы одну, которой не пользовался 60 дней."),
    ("awareness", "День без импульса", "Перед любой незапланированной покупкой сегодня — подожди 10 минут."),
    ("planning", "Обнови главную цель", "Проверь прогресс по главной цели и, если нужно, увеличь ежемесячный взнос."),
    ("negotiate", "Спроси скидку", "Попробуй попросить скидку или кэшбек хотя бы в одном месте сегодня."),
]


def _index(d: date, modulus: int) -> int:
    seed = int(hashlib.md5(("coach-" + d.isoformat()).encode()).hexdigest(), 16)
    return seed % modulus


def challenge_for_date(d: date) -> tuple[str, str, str]:
    category, title, body = CHALLENGES[_index(d, len(CHALLENGES))]
    return category, title, body


async def ensure_today_challenge(db: AsyncSession) -> DailyChallenge:
    today = date.today()
    row = (
        await db.execute(select(DailyChallenge).where(DailyChallenge.challenge_date == today))
    ).scalar_one_or_none()
    if row:
        return row
    category, title, body = challenge_for_date(today)
    row = DailyChallenge(challenge_date=today, title=title, body=body, category=category)
    db.add(row)
    await db.flush()
    return row
