"""AI Purchase Analyzer — the AI acts as a financial director who argues, not agrees.

Per the product brief: when the user says "I want to buy a MacBook", the AI
should not simply approve. It should challenge the decision like a real CFO —
asking why now, what changes, whether alternatives exist, and referencing
what it remembers about the user's recent related wants.
"""

from __future__ import annotations

from app.schemas.ai import PurchaseAnalyzeResponse
from app.services.money_in_days import humanize


def _challenge_questions(item: str, capital_pct: float, months_of_savings: float, related_memory: str) -> list[str]:
    questions = [
        "Почему именно сейчас, а не через месяц?",
        "Что конкретно изменится в жизни после этой покупки?",
        "Можно ли подождать распродажу или сезон скидок?",
        "Есть ли более доступная альтернатива с 80% пользы?",
    ]
    if related_memory:
        questions.append(f"Вы упоминали похожее раньше: «{related_memory}» — это всё ещё актуально или желание изменилось?")
    if months_of_savings > 3:
        questions.append("Вы точно будете пользоваться этим достаточно, чтобы оправдать месяцы накоплений?")
    if capital_pct > 15:
        questions.append("Готовы ли вы временно снизить взносы в цели ради этой покупки?")
    return questions[:5]


def _twin_opinion(item: str, score: int, capital_pct: float) -> str:
    if score < 40:
        return f"Если бы это был мой бюджет — я бы отложил «{item}» минимум на месяц и пересмотрел решение на свежую голову."
    if score < 65:
        return f"На твоём месте я бы сначала закрыл более приоритетную цель, а «{item}» взял бы после — так капитал не проседает."
    return f"Это разумная покупка при текущем капитале. Я бы одобрил «{item}», но зафиксировал бы сумму и не заходил дороже."


def analyze_purchase(
    item: str,
    price: float,
    total_capital: float,
    hourly_rate: float,
    monthly_savings: float,
    main_goal_remaining: float | None,
    related_memory: str = "",
) -> PurchaseAnalyzeResponse:
    life = humanize(price, hourly_rate, monthly_savings, total_capital)

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

    if life.capital_pct > 25:
        recommendation = "Сейчас покупка сильно бьёт по капиталу. Отложите или найдите альтернативу."
        wait_advice = "Обязательно правило 24–72 часа. Рассмотрите рассрочку только без процентов."
        score = 25
    elif life.capital_pct > 10:
        recommendation = "Покупка ощутима. Убедитесь, что подушка ≥ 3 месяцев и цель не страдает."
        wait_advice = "Отложите на 24 часа и сравните 3 альтернативы."
        score = 55
    else:
        recommendation = "Покупка вписывается в капитал. Проверьте, решает ли она реальную задачу."
        wait_advice = "Можно брать после короткой паузы — если всё ещё хочется."
        score = 78

    if life.months_of_savings > 6:
        score = min(score, 40)
        recommendation += " Это больше полугода ваших накоплений."

    return PurchaseAnalyzeResponse(
        item=item,
        price=price,
        capital_pct=life.capital_pct,
        work_hours=life.work_hours,
        life_days=life.life_days,
        months_of_savings=life.months_of_savings,
        coffee_equivalent=life.coffee_equivalent,
        goal_impact=goal_impact,
        alternatives=alternatives,
        wait_advice=wait_advice,
        recommendation=recommendation,
        score=score,
        postpone_available=True,
        challenge_questions=_challenge_questions(item, life.capital_pct, life.months_of_savings, related_memory),
        twin_opinion=_twin_opinion(item, score, life.capital_pct),
        related_memory=related_memory,
    )
