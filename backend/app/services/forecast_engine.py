"""Forecast and scenario simulation."""

from __future__ import annotations

from calendar import monthrange
from datetime import date
from dateutil.relativedelta import relativedelta

from app.schemas.analytics import ForecastPoint, ForecastResult, ScenarioRequest, ScenarioResult

SCENARIO_META = {
    "quit_job": ("Уволюсь", "Потеря основного дохода — стресс-тест подушки."),
    "lose_income": ("Потеряю доход", "Доход падает до 30% на 6 месяцев."),
    "child": ("Родится ребёнок", "Рост расходов +45 000 ₽/мес."),
    "buy_car": ("Куплю машину", "Разовый платёж + рост расходов на авто."),
    "mortgage": ("Возьму ипотеку", "Ежемесячный платёж и рост активов."),
    "sell_apartment": ("Продам квартиру", "Крупный приток капитала."),
    "raise": ("Повышение зарплаты", "Доход +20%."),
    "currency_shift": ("Смена валюты", "Часть капитала в валюте / инфляция."),
    "relocation": ("Переезд", "Рост расходов на жильё и адаптацию."),
}


def _month_points(
    start_balance: float,
    monthly_net_base: float,
    months: int,
    opt_mult: float = 1.2,
    stress_mult: float = 0.5,
) -> list[ForecastPoint]:
    points: list[ForecastPoint] = []
    bal_o = bal_b = bal_s = start_balance
    d = date.today().replace(day=1)
    for i in range(months):
        d = d + relativedelta(months=1) if i else d
        # simple growth + volatility bands
        bal_o += monthly_net_base * opt_mult * (1.01 ** i)
        bal_b += monthly_net_base * (1.005 ** i)
        bal_s += monthly_net_base * stress_mult
        # floor stress a bit if negative drift
        points.append(
            ForecastPoint(
                date=d.isoformat(),
                optimistic=round(bal_o, 2),
                base=round(bal_b, 2),
                stress=round(bal_s, 2),
            )
        )
    return points


def build_forecast(
    balance: float,
    monthly_income: float,
    monthly_expense: float,
    monthly_invest: float = 0,
) -> ForecastResult:
    net = monthly_income - monthly_expense
    series = _month_points(balance, net, 36)

    # month end expense projection (linear)
    days_left = monthrange(date.today().year, date.today().month)[1] - date.today().day + 1
    daily_burn = monthly_expense / max(monthrange(date.today().year, date.today().month)[1], 1)
    month_end_expense = monthly_expense  # expected full month

    year_end = series[11].base if len(series) > 11 else balance + net * 12

    runway = None
    if monthly_expense > monthly_income and monthly_expense > 0:
        runway = int(balance / (monthly_expense - monthly_income) * 30)

    million_date = None
    retirement_date = None
    for p in series:
        if million_date is None and p.base >= 1_000_000:
            million_date = p.date
        # FI proxy: 25x annual expenses
        if retirement_date is None and p.base >= monthly_expense * 12 * 25:
            retirement_date = p.date

    narrative = (
        f"При текущем темпе чистый поток ≈ {net:,.0f} ₽/мес. "
        f"К концу года баланс в базовом сценарии ≈ {year_end:,.0f} ₽."
    ).replace(",", " ")

    return ForecastResult(
        month_end_expense=round(month_end_expense, 2),
        year_end_balance=round(year_end, 2),
        runway_days=runway,
        million_date=million_date,
        retirement_date=retirement_date,
        series=series,
        narrative=narrative,
    )


def run_scenario(
    req: ScenarioRequest,
    balance: float,
    monthly_income: float,
    monthly_expense: float,
) -> ScenarioResult:
    income, expense = monthly_income, monthly_expense
    bal = balance
    title, summary = SCENARIO_META.get(req.scenario, (req.scenario, "Пользовательский сценарий"))

    recommendations: list[str] = []

    if req.scenario == "quit_job":
        income = 0
        recommendations = ["Увеличьте подушку до 12 месяцев", "Сократите discretionary на 40%", "Активируйте side-income"]
    elif req.scenario == "lose_income":
        income *= 0.3
        recommendations = ["Заморозьте крупные покупки", "Пересмотрите подписки", "Используйте резерв точечно"]
    elif req.scenario == "child":
        expense += 45000
        recommendations = ["Откройте цель «Ребёнок»", "Увеличьте страховку", "Пересмотрите бюджет на 6 месяцев"]
    elif req.scenario == "buy_car":
        price = float(req.params.get("price", 1_500_000))
        bal -= price
        expense += 25000
        recommendations = ["Сравните кредит vs накопления", "Учтите страховку и ТО", "Не трогайте инвестиционный горизонт"]
    elif req.scenario == "mortgage":
        payment = float(req.params.get("payment", 80000))
        expense += payment
        recommendations = ["Держите резерв 6+ месяцев платежа", "Досрочные погашения после подушки", "Фиксируйте ставку осознанно"]
    elif req.scenario == "sell_apartment":
        bal += float(req.params.get("proceeds", 8_000_000))
        recommendations = ["Не держите всё в кэше", "Диверсифицируйте", "Закройте дорогие долги"]
    elif req.scenario == "raise":
        income *= 1.2
        recommendations = ["Половину повышения — в инвестиции", "Не раздувайте lifestyle", "Обновите цели"]
    elif req.scenario == "currency_shift":
        expense *= 1.08
        recommendations = ["Часть резерва в твёрдой валюте/золоте", "Хедж через глобальные ETF", "Пересмотрите бюджет"]
    elif req.scenario == "relocation":
        expense *= 1.35
        income *= float(req.params.get("income_mult", 1.1))
        recommendations = ["Закладывайте 3 месяца адаптации", "Сравните cost of living", "Сохраните remote-доход"]

    net = income - expense
    months = max(6, min(req.months, 120))
    base = _month_points(bal, net, months, 1.0, 1.0)
    # rebuild with proper multipliers
    optimistic = _month_points(bal, net, months, 1.25, 1.25)
    stress = _month_points(bal, net, months, 0.4, 0.4)

    return ScenarioResult(
        scenario=req.scenario,
        title=title,
        optimistic=optimistic,
        base=base,
        stress=stress,
        summary=summary,
        recommendations=recommendations,
    )
