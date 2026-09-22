"""Dashboard orchestration — greeting, health, balances, rituals."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.account import Account
from app.models.calendar import CalendarEvent
from app.models.debt import Debt
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
    LivingScreenLine,
    MotivationalQuote,
    RitualEvening,
    RitualMorning,
)
from app.services.coach_engine import ensure_today_challenge
from app.services.content_bank import quote_for_date, widget_for_date
from app.services.health_score import HealthInputs, compute_health
from app.services.insights_engine import generate_insights
from app.services.net_worth_service import build_net_worth
from app.services.ledger import is_income, spending
from app.services.proactive_engine import detect_behavior_patterns, generate_proactive_alerts


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

    # Income: only real inflows. Expense: consumption only — investments/savings/debt
    # moves are capital allocation, not lifestyle burn (critical for health score).
    income = sum(t.amount for t in txs if is_income(t))
    expense = sum(abs(t.amount) for t in spending(txs))

    liquid = sum(
        a.balance
        for a in accounts
        if a.account_type in ("cash", "card", "bank", "savings", "reserve", "investment", "crypto")
    )

    debt_rows = list((await db.execute(select(Debt).where(Debt.is_active.is_(True)))).scalars())
    debts_owed = sum(d.remaining for d in debt_rows if d.direction == "owed_to_me")
    debts_owing = sum(d.remaining for d in debt_rows if d.direction == "i_owe")

    return DashboardBalances(
        total=round(liquid, 2),
        cash=round(by_type.get("cash", 0), 2),
        cards=round(by_type.get("card", 0), 2),
        bank=round(by_type.get("bank", 0), 2),
        investments=round(by_type.get("investment", 0), 2),
        crypto=round(by_type.get("crypto", 0), 2),
        savings=round(by_type.get("savings", 0), 2),
        reserve=round(by_type.get("reserve", 0), 2),
        debts_owed=round(debts_owed, 2),
        debts_owing=round(debts_owing, 2),
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
    # Делить на объявленный в профиле доход нельзя: пока он не заполнен, в
    # делителе оказывался один рубль, и норма сбережений выходила в
    # 4 220 969%. Доход месяца известен из операций, а норма больше единицы не
    # бывает.
    income = profile.monthly_income or balances.income_month
    savings_rate = (
        min(1.0, max(0.0, (income - balances.expense_month) / income)) if income else 0.0
    )

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

    behavior_patterns = detect_behavior_patterns(txs)
    insights = behavior_patterns + generate_insights(txs, subs, profile.monthly_income)
    goals = list((await db.execute(select(Goal).where(Goal.is_active.is_(True)).order_by(Goal.priority))).scalars())
    focus = f"Усиль цель «{goals[0].title}»" if goals else "Заведите первую финансовую цель"

    events = list((await db.execute(select(CalendarEvent))).scalars())
    net_worth = await build_net_worth(db)

    # streak: consecutive days (walking backwards from today) with at least one logged transaction
    logged_days = {t.occurred_on for t in txs}
    streak = 0
    cursor = date.today()
    while cursor in logged_days:
        streak += 1
        cursor -= timedelta(days=1)

    # Бюджетом расходы этого же месяца быть не могут: тогда сравнение сводится
    # к «потрачено 100% того, что потрачено», и подсказка про перерасход
    # появляется всегда. Пока бюджет не из чего вывести, её не показываем.
    proactive_alerts = generate_proactive_alerts(
        txs, subs, events, profile.monthly_income,
        profile.monthly_income * 0.75 if profile.monthly_income else 0,
    )

    challenge_row = await ensure_today_challenge(db)
    daily_challenge = {
        "id": challenge_row.id,
        "title": challenge_row.title,
        "body": challenge_row.body,
        "category": challenge_row.category,
        "is_completed": challenge_row.is_completed,
    }

    avg_goal_probability = round(sum(g.probability for g in goals) / len(goals) * 100, 0) if goals else None

    living_screen: list[LivingScreenLine] = [
        LivingScreenLine(icon="sun", text=_period_greeting(now, profile.name).greeting, tone="neutral"),
    ]
    nw_pct = (net_worth.delta.month / max(abs(net_worth.current - net_worth.delta.month), 1)) * 100
    living_screen.append(
        LivingScreenLine(
            icon="trending-up" if net_worth.delta.month >= 0 else "trending-down",
            text=f"Чистый капитал {'вырос' if net_worth.delta.month >= 0 else 'снизился'} на {abs(nw_pct):.1f}% за месяц",
            tone="positive" if net_worth.delta.month >= 0 else "warning",
        )
    )
    if goals:
        top_goal = goals[0]
        remaining = max(top_goal.target_amount - top_goal.current_amount, 0)
        living_screen.append(
            LivingScreenLine(icon="target", text=f"До «{top_goal.title}» осталось накопить {remaining:,.0f} ₽".replace(",", " "), tone="neutral")
        )
    if streak >= 3:
        living_screen.append(LivingScreenLine(icon="flame", text=f"Уже {streak} дней подряд ведёшь учёт", tone="positive"))
    living_screen.append(LivingScreenLine(icon="lightbulb", text=widget.title + ": " + widget.body[:80], tone="neutral"))
    upcoming = [e for e in events if date.today() <= e.event_date <= date.today() + timedelta(days=3) and e.amount > 0]
    if upcoming:
        e = upcoming[0]
        living_screen.append(LivingScreenLine(icon="alert-triangle", text=f"Через {(e.event_date - date.today()).days} дн. платёж «{e.title}» на {e.amount:,.0f} ₽".replace(",", " "), tone="warning"))
    if avg_goal_probability is not None:
        living_screen.append(LivingScreenLine(icon="bar-chart", text=f"Вероятность достижения целей — {avg_goal_probability:.0f}%", tone="neutral"))
    living_screen.append(LivingScreenLine(icon="heart", text="Отличная работа. Продолжай в том же духе.", tone="positive"))

    return DashboardOut(
        greeting=_period_greeting(now, profile.name),
        quote=MotivationalQuote(**q),
        widget=DailyWidgetOut.model_validate(widget),
        health=health,
        balances=balances,
        insights=insights,
        focus_of_day=focus,
        net_worth=net_worth.current,
        net_worth_delta_today=net_worth.delta.today,
        net_worth_delta_month=net_worth.delta.month,
        net_worth_delta_year=net_worth.delta.year,
        streak_days=streak,
        living_screen=living_screen,
        daily_challenge=daily_challenge,
        proactive_alerts=proactive_alerts,
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
