"""Demo seed for a vivid first-run experience."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from random import Random

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.achievement import Achievement, UserAchievement
from app.models.calendar import CalendarEvent
from app.models.debt import Debt
from app.models.goal import Goal
from app.models.insight import Insight
from app.models.investment import InvestmentHolding
from app.models.memory import AIMemory
from app.models.subscription import Subscription
from app.models.transaction import Transaction
from app.models.user import UserProfile


ACHIEVEMENTS = [
    ("first_investment", "Первая инвестиция", "Сделан первый инвестиционный взнос", "trending-up", "invest", 20),
    ("streak_100", "100 дней учёта", "Ведёте учёт 100 дней подряд", "calendar", "discipline", 50),
    ("week_clean", "Неделя без лишнего", "7 дней без импульсивных трат", "sparkles", "discipline", 15),
    ("cushion_100k", "Подушка 100 000", "Резерв достиг 100 000 ₽", "shield", "safety", 25),
    ("first_million", "Первый миллион", "Капитал пересёк 1 000 000 ₽", "crown", "wealth", 100),
    ("debt_closed", "Долг закрыт", "Полностью погасили долг", "check-circle", "debt", 30),
    ("no_overspend_10", "10 месяцев без перерасхода", "Дисциплина уровня профи", "award", "discipline", 80),
    ("fi_path", "Финансовая независимость", "Капитал ≥ 25× годовых расходов", "rocket", "freedom", 200),
]


async def seed_if_empty(db: AsyncSession) -> bool:
    count = await db.scalar(select(func.count()).select_from(UserProfile))
    if count and count > 0:
        return False

    profile = UserProfile(
        name="Кирилл",
        monthly_income=220000,
        currency="RUB",
        theme="auto",
        city="Москва",
        dreams="Квартира у моря, финансовая свобода к 40, путешествие в Японию",
        fears="Потерять доход и остаться без подушки",
        habits_notes="Любит кофе навынос, часто заказывает доставку по пятницам",
        onboarding_done=True,
        avatar_emoji="✨",
    )
    db.add(profile)

    accounts = [
        Account(name="Наличные", account_type="cash", balance=18500, color="#34d399", icon="banknote", sort_order=1),
        Account(name="Тинькофф Black", account_type="card", balance=142300, color="#60a5fa", icon="credit-card", sort_order=2),
        Account(name="Сбер накопительный", account_type="bank", balance=89000, color="#38bdf8", icon="landmark", sort_order=3),
        Account(name="Брокерский счёт", account_type="investment", balance=486000, color="#22d3ee", icon="line-chart", sort_order=4),
        Account(name="Крипто", account_type="crypto", balance=67500, color="#a78bfa", icon="bitcoin", sort_order=5),
        Account(name="На мечту", account_type="savings", balance=120000, color="#fbbf24", icon="piggy-bank", sort_order=6),
        Account(name="Подушка", account_type="reserve", balance=310000, color="#f59e0b", icon="shield", sort_order=7),
    ]
    db.add_all(accounts)

    goals = [
        Goal(title="Поездка в Японию", description="Токио + Киото, 14 дней", target_amount=450000, current_amount=120000, monthly_contribution=25000, deadline=date.today() + timedelta(days=300), icon="plane", color="#60a5fa", category="travel", priority=1, probability=0.78),
        Goal(title="Первый взнос на квартиру", description="20% от студии", target_amount=2500000, current_amount=486000, monthly_contribution=60000, deadline=date.today() + timedelta(days=900), icon="home", color="#a78bfa", category="apartment", priority=2, probability=0.55),
        Goal(title="Подушка 6 месяцев", description="Резерв на жизнь", target_amount=600000, current_amount=310000, monthly_contribution=30000, deadline=date.today() + timedelta(days=240), icon="shield", color="#fbbf24", category="emergency", priority=1, probability=0.82),
        Goal(title="MacBook Pro", description="Рабочий инструмент", target_amount=280000, current_amount=90000, monthly_contribution=20000, deadline=date.today() + timedelta(days=180), icon="laptop", color="#818cf8", category="gadget", priority=3, probability=0.7),
    ]
    db.add_all(goals)

    debts = [
        Debt(person_name="Андрей", direction="owed_to_me", amount=12000, remaining=12000, due_date=date.today() + timedelta(days=20), return_probability=0.9, notes="Обед + билеты"),
        Debt(person_name="Саша", direction="i_owe", amount=3000, remaining=3000, due_date=date.today() + timedelta(days=7), return_probability=1.0, notes="Кофе и такси"),
    ]
    db.add_all(debts)

    today = date.today()
    subs = [
        Subscription(name="Spotify", amount=169, next_billing_date=today + timedelta(days=12), category="music", icon="music", last_used_date=today - timedelta(days=1)),
        Subscription(name="YouTube Premium", amount=299, next_billing_date=today + timedelta(days=5), category="video", icon="youtube", last_used_date=today - timedelta(days=2)),
        Subscription(name="Netflix", amount=999, next_billing_date=today + timedelta(days=18), category="video", icon="tv", last_used_date=today - timedelta(days=70), unused_days_threshold=60),
        Subscription(name="ChatGPT Plus", amount=1900, next_billing_date=today + timedelta(days=9), category="ai", icon="bot", last_used_date=today),
        Subscription(name="VPN", amount=299, next_billing_date=today + timedelta(days=22), category="tools", icon="shield", last_used_date=today - timedelta(days=3)),
        Subscription(name="iCloud+", amount=149, next_billing_date=today + timedelta(days=15), category="cloud", icon="cloud", last_used_date=today),
    ]
    db.add_all(subs)

    holdings = [
        InvestmentHolding(name="FXUS", ticker="FXUS", asset_class="etf", value=210000, cost_basis=180000, expected_return=0.12, risk_score=0.55),
        InvestmentHolding(name="ОФЗ", ticker="OFZ", asset_class="bonds", value=160000, cost_basis=158000, expected_return=0.11, risk_score=0.2),
        InvestmentHolding(name="BTC", ticker="BTC", asset_class="crypto", value=67500, cost_basis=52000, expected_return=0.2, risk_score=0.85),
        InvestmentHolding(name="Вклад", ticker="DEPOSIT", asset_class="cash", value=89000, cost_basis=89000, expected_return=0.16, risk_score=0.05),
    ]
    db.add_all(holdings)

    events = [
        CalendarEvent(title="Зарплата", event_type="salary", amount=220000, event_date=today + timedelta(days=9), recurrence="monthly", color="#4ade80"),
        CalendarEvent(title="Аренда", event_type="utilities", amount=65000, event_date=today + timedelta(days=3), recurrence="monthly", color="#f87171"),
        CalendarEvent(title="Netflix", event_type="subscription", amount=999, event_date=today + timedelta(days=18), recurrence="monthly", color="#c084fc"),
        CalendarEvent(title="День рождения мамы", event_type="birthday", amount=8000, event_date=today + timedelta(days=27), recurrence="yearly", color="#fbbf24"),
        CalendarEvent(title="Налог самозанятого", event_type="tax", amount=12000, event_date=today + timedelta(days=40), recurrence="monthly", color="#fb923c"),
    ]
    db.add_all(events)

    rng = Random(42)
    merchants = [
        ("Пятёрочка", "groceries", -1200),
        ("Кофе Portable", "cafe", -450),
        ("Яндекс Go", "transport", -380),
        ("Ресторан", "restaurants", -3200),
        ("Wildberries", "gadgets", -5600),
        ("Аптека", "health", -890),
        ("Доставка", "restaurants", -1500),
    ]
    txs: list[Transaction] = []
    for i in range(75):
        d = today - timedelta(days=rng.randint(0, 89))
        m_name, cat, base = merchants[rng.randint(0, len(merchants) - 1)]
        amount = base * rng.uniform(0.7, 1.4)
        txs.append(
            Transaction(
                amount=round(amount, 2),
                category=cat,
                description=m_name,
                merchant=m_name,
                transaction_type="expense",
                occurred_on=d,
                source="seed",
                account_id=2,
            )
        )
    # incomes
    for months_ago in range(3):
        d = (today.replace(day=10) - timedelta(days=30 * months_ago))
        txs.append(
            Transaction(
                amount=220000,
                category="salary",
                description="Зарплата",
                merchant="Работодатель",
                transaction_type="income",
                occurred_on=d,
                source="seed",
                account_id=2,
            )
        )
    txs.append(
        Transaction(
            amount=-25000,
            category="investments",
            description="Купил акции",
            merchant="Брокер",
            transaction_type="investment",
            occurred_on=today - timedelta(days=5),
            source="seed",
        )
    )
    txs.append(
        Transaction(
            amount=-10000,
            category="savings",
            description="Пополнил вклад",
            merchant="Сбер",
            transaction_type="savings",
            occurred_on=today - timedelta(days=2),
            source="seed",
        )
    )
    db.add_all(txs)

    for code, title, desc, icon, cat, pts in ACHIEVEMENTS:
        db.add(Achievement(code=code, title=title, description=desc, icon=icon, category=cat, points=pts))
    await db.flush()

    # unlock a couple
    ach = list((await db.execute(select(Achievement))).scalars())
    for a in ach:
        if a.code in ("first_investment", "cushion_100k", "week_clean"):
            db.add(UserAchievement(achievement_id=a.id, unlocked_at=datetime.now(timezone.utc)))

    db.add_all(
        [
            AIMemory(key="dream_japan", content="Мечтает о поездке в Японию", memory_type="goal", importance=0.9, tags="travel"),
            AIMemory(key="fear_income_loss", content="Боится потери дохода без подушки", memory_type="fear", importance=0.8, tags="risk"),
            AIMemory(key="habit_coffee", content="Часто покупает кофе навынос", memory_type="habit", importance=0.6, tags="cafe"),
            AIMemory(key="salary", content="Зарплата около 220000 ₽ в месяц, приходит около 10 числа", memory_type="fact", importance=0.95, tags="income"),
        ]
    )

    db.add(
        Insight(
            title="Рестораны выросли",
            body="В этом месяце рестораны и доставка заметно выше обычного.",
            insight_type="warning",
            severity="warning",
            category="restaurants",
            shown_on=today,
            meta_json=json.dumps({"growth_pct": 40}),
        )
    )

    await db.flush()
    return True
