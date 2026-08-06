"""AI Purchase Analyzer — opportunity cost of big buys."""

from __future__ import annotations

from app.schemas.ai import PurchaseAnalyzeResponse


def analyze_purchase(
    item: str,
    price: float,
    total_capital: float,
    hourly_rate: float,
    monthly_savings: float,
    main_goal_remaining: float | None,
) -> PurchaseAnalyzeResponse:
    capital = max(total_capital, 1.0)
    capital_pct = price / capital * 100
    work_hours = price / max(hourly_rate, 1.0)
    # rough: waking life day ~ 16h productive? use 8h work day equivalent
    life_days = work_hours / 8.0
    months_of_savings = price / max(monthly_savings, 1.0)

    if main_goal_remaining and main_goal_remaining > 0:
        delay_months = price / max(monthly_savings, 1.0)
        goal_impact = f"Покупка отодвинет главную цель примерно на {delay_months:.1f} мес."
    else:
        goal_impact = "Нет активной цели — оцените, не создаёт ли покупка новую зависимость."

    alternatives = [
        f"БУ / refurbished — экономия 20–40% (~{price * 0.7:,.0f} ₽)".replace(",", " "),
        "Подождать распродажу / trade-in / кэшбек-сезон",
        "Аренда или подписка на 1–3 месяца для проверки потребности",
        "Более доступная модель с 80% пользы за 60% цены",
    ]

    if capital_pct > 25:
        recommendation = "Сейчас покупка сильно бьёт по капиталу. Отложите или найдите альтернативу."
        wait_advice = "Обязательно правило 24–72 часа. Рассмотрите рассрочку только без процентов."
        score = 25
    elif capital_pct > 10:
        recommendation = "Покупка ощутима. Убедитесь, что подушка ≥ 3 месяцев и цель не страдает."
        wait_advice = "Отложите на 24 часа и сравните 3 альтернативы."
        score = 55
    else:
        recommendation = "Покупка вписывается в капитал. Проверьте, решает ли она реальную задачу."
        wait_advice = "Можно брать после короткой паузы — если всё ещё хочется."
        score = 78

    if months_of_savings > 6:
        score = min(score, 40)
        recommendation += " Это больше полугода ваших накоплений."

    return PurchaseAnalyzeResponse(
        item=item,
        price=price,
        capital_pct=round(capital_pct, 2),
        work_hours=round(work_hours, 1),
        life_days=round(life_days, 1),
        months_of_savings=round(months_of_savings, 1),
        goal_impact=goal_impact,
        alternatives=alternatives,
        wait_advice=wait_advice,
        recommendation=recommendation,
        score=score,
        postpone_available=True,
    )
