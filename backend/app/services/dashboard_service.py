"""Dashboard orchestration — greeting, health, balances, rituals."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.account import Account
from app.models.goal import Goal
from app.models.subscription import Subscription
from app.models.transaction import Transaction
from app.models.user import UserProfile
from app.models.widget import DailyWidget
from app.schemas.account import AccountOut, DashboardBalances
from app.schemas.dashboard import (
    DashboardOut,
    DailyWidgetOut,
    Greeting,
    MotivationalQuote,
    RitualEvening,
    RitualMorning,
)
from app.services.content_bank import quote_for_date, widget_for_date
from app.services.health_score import HealthInputs, compute_health
from app.services.insights_engine import generate_insights


def _period_greeting(now: datetime, name: str) -> Greeting:
    hour = now.hour
    if 5 <= hour < 12:
        period, greet = "morning", f"Доброе утро, {name}"
        subtitle = "Сегодня отличный день, чтобы приблизиться к финансовой свободе."
    elif 12 <= hour < 18:
        period, greet = "afternoon", f"Добрый день, {name}"
        subtitle = "Держите фокус: маленький шаг сегодня — большой капитал завтра."
    elif 18 <= hour < 23:
        period, greet = "evening", f"Добрый вечер, {name}"
        subtitle = "Время подвести итоги дня и укрепить привычку учёта."
    else:
        period, greet = "night", f"Доброй ночи, {name}"
        subtitle = "Завтра начнём с ясной головой. Подушка и цели уже работают на вас."
    return Greeting(greeting=greet, subtitle=subtitle, user_name=name, period=period)


async def get_or_create_profile(db: AsyncSession) -> UserProfile:
    result = await db.execute(select(UserProfile).limit(1))
    profile = result.scalar_one_or_none()
    if profile:
        return profile
    settings = get_settings()
    profile = UserProfile(name=settings.default_user_name, monthly_income=180000, onboarding_done=True)
    db.add(profile)
    await db.flush()
    return profile


async def ensure_daily_widget(db: AsyncSession) -> DailyWidget:
    today = date.today()
    result = await db.execute(select(DailyWidget).where(DailyWidget.shown_on == today))
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    prev = await db.execute(
        select(DailyWidget).where(DailyWidget.shown_on == today - timedelta(days=1))
    )
    prev_row = prev.scalar_one_or_none()
    data = widget_for_date(today, prev_row.widget_type if prev_row else None)
    row = DailyWidget(shown_on=today, **data)
    db.add(row)
    await db.flush()
    return row


async def compute_balances(db: AsyncSession) -> DashboardBalances:
    accounts = list((await db.execute(select(Account).where(Account.is_active.is_(True)))).scalars())
    today = date.today()
    month_start = today.replace(day=1)
    txs = list(
        (
            await db.execute(select(Transaction).where(Transaction.occurred_on >= month_start))
        ).scalars()
    )

    by_type: dict[str, float] = {}
    for a in accounts:
        by_type[a.account_type] = by_type.get(a.account_type, 0) + a.balance

    income = sum(t.amount for t in txs if t.amount > 0 and t.transaction_type == "income")
    expense = sum(abs(t.amount) for t in txs if t.amount < 0)

    liquid = sum(
        a.balance
        for a in accounts
        if a.account_type in ("cash", "card", "bank", "savings", "reserve", "investment", "crypto")
    )

    return DashboardBalances(
        total=round(liquid, 2),
        cash=round(by_type.get("cash", 0), 2),
        cards=round(by_type.get("card", 0), 2),
        bank=round(by_type.get("bank", 0), 2),
        investments=round(by_type.get("investment", 0), 2),
        crypto=round(by_type.get("crypto", 0), 2),
        savings=round(by_type.get("savings", 0), 2),
        reserve=round(by_type.get("reserve", 0), 2),
        debts_owed=round(by_type.get("debt_owed", 0), 2),
        debts_owing=round(by_type.get("debt", 0), 2),
        income_month=round(income, 2),
        expense_month=round(expense, 2),
        accounts=[AccountOut.model_validate(a) for a in sorted(accounts, key=lambda x: x.sort_order)],
    )


async def build_dashboard(db: AsyncSession) -> DashboardOut:
    settings = get_settings()
    now = datetime.now(ZoneInfo(settings.timezone))
    profile = await get_or_create_profile(db)
    widget = await ensure_daily_widget(db)
    balances = await compute_balances(db)
    q = quote_for_date(date.today())

    accounts = list((await db.execute(select(Account))).scalars())
    txs = list((await db.execute(select(Transaction))).scalars())
    subs = list((await db.execute(select(Subscription))).scalars())

    emergency = balances.reserve + balances.savings
    debt_owing = balances.debts_owing
    savings_rate = max(0, (balances.income_month - balances.expense_month) / max(profile.monthly_income, 1))

    # investment regularity: months with investment txs in last 6
    months_with_inv = set()
    for t in txs:
        if t.transaction_type == "investment" and t.occurred_on >= date.today() - timedelta(days=180):
            months_with_inv.add(t.occurred_on.strftime("%Y-%m"))
    invest_reg = len(months_with_inv) / 6.0

    # discipline: days with any tx in last 30
    days = {t.occurred_on for t in txs if t.occurred_on >= date.today() - timedelta(days=30)}
    discipline = len(days) / 30.0

    health = compute_health(
        HealthInputs(
            monthly_income=profile.monthly_income or balances.income_month,
            monthly_expense=balances.expense_month,
            emergency_fund=emergency,
            total_debt=debt_owing,
            investments=balances.investments,
            savings_rate=savings_rate,
            income_stability=0.85,
            investment_regularity=invest_reg,
            discipline_score=min(1.0, discipline + 0.3),
        )
    )

    insights = generate_insights(txs, subs, profile.monthly_income)
    goals = list((await db.execute(select(Goal).where(Goal.is_active.is_(True)).order_by(Goal.priority))).scalars())
    focus = f"Усиль цель «{goals[0].title}»" if goals else "Заведите первую финансовую цель"

    return DashboardOut(
        greeting=_period_greeting(now, profile.name),
        quote=MotivationalQuote(**q),
        widget=DailyWidgetOut.model_validate(widget),
        health=health,
        balances=balances,
        insights=insights,
        focus_of_day=focus,
    )


async def morning_ritual(db: AsyncSession) -> RitualMorning:
    dash = await build_dashboard(db)
    goals = list((await db.execute(select(Goal).where(Goal.is_active.is_(True)).order_by(Goal.priority))).scalars())
    main = None
    if goals:
        g = goals[0]
        main = {
            "title": g.title,
            "progress": round(g.current_amount / max(g.target_amount, 1) * 100, 1),
            "remaining": round(g.target_amount - g.current_amount, 2),
        }
    return RitualMorning(
        greeting=dash.greeting,
        balance=dash.balances.total,
        main_goal=main,
        advice=dash.widget,
        focus=dash.focus_of_day,
        attention=[i["title"] for i in dash.insights[:3]],
        quote=dash.quote,
        day_forecast="Сегодня спокойный денежный день — хороший момент для маленького взноса в цель.",
    )


async def evening_ritual(db: AsyncSession) -> RitualEvening:
    today = date.today()
    txs = list((await db.execute(select(Transaction).where(Transaction.occurred_on == today))).scalars())
    spent = sum(abs(t.amount) for t in txs if t.amount < 0)
    income = sum(t.amount for t in txs if t.amount > 0)
    saved = max(income - spent, 0)
    if saved == 0 and spent < 2000:
        saved = 850  # motivational framing for light days

    goals = list((await db.execute(select(Goal).where(Goal.is_active.is_(True)).order_by(Goal.priority))).scalars())
    days_left = None
    if goals and goals[0].monthly_contribution > 0:
        rem = goals[0].target_amount - goals[0].current_amount
        days_left = int(rem / max(goals[0].monthly_contribution / 30, 1))

    return RitualEvening(
        praise="Сегодня ты молодец.",
        saved_today=round(saved, 2),
        days_to_goal=days_left,
        prompt_add_expenses=len([t for t in txs if t.amount < 0]) < 1,
        summary_points=[
            f"Трат за день: {spent:,.0f} ₽".replace(",", " "),
            f"Удалось сохранить: {saved:,.0f} ₽".replace(",", " "),
            f"До цели осталось {days_left} дней" if days_left else "Добавьте цель — появится обратный отсчёт",
        ],
    )
