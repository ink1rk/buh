"""AI financial advisor — OpenAI when available, smart local fallback otherwise."""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings
from app.schemas.ai import ChatMessage, ChatResponse

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты — личный финансовый советник премиум-уровня в приложении Personal Finance AI.
Ты думаешь вместе с пользователем: аналитик, мотиватор, психолог и инвестиционный помощник.
Отвечай на русском, конкретно, с цифрами из контекста. Без канцелярита.
Структура: короткий вывод → почему → 2–3 действия.
Не давай юридических/налоговых гарантий. Не подталкивай к рискованным спекуляциям.
"""


def _local_reply(message: str, context: dict[str, Any], memories: list[str]) -> ChatResponse:
    lower = message.lower()
    bal = context.get("balance", 0)
    income = context.get("income_month", 0)
    expense = context.get("expense_month", 0)
    top_cat = context.get("top_category", "прочее")
    top_cat_sum = context.get("top_category_sum", 0)
    subs = context.get("subscriptions_total", 0)

    if "куда ушли" in lower or "куда уходят" in lower:
        reply = (
            f"В этом месяце основной поток ушёл в «{top_cat}» — ≈ {top_cat_sum:,.0f} ₽. "
            f"Всего расходов: {expense:,.0f} ₽ при доходе {income:,.0f} ₽. "
            f"Свободный остаток: {income - expense:,.0f} ₽."
        ).replace(",", " ")
        suggestions = ["Показать категории", "Что оптимизировать?", "Сравнить с прошлым месяцем"]
    elif "перерасход" in lower or "почему" in lower and "расход" in lower:
        gap = expense - income * 0.7
        reply = (
            f"Расходы {expense:,.0f} ₽ — выше комфортной зоны 70% дохода. "
            f"Главный драйвер: {top_cat}. Подписки съедают ≈ {subs:,.0f} ₽/мес."
        ).replace(",", " ")
        suggestions = ["Какие подписки отменить?", "План экономии на неделю", "Анализ кофе/доставки"]
    elif "оптимиз" in lower:
        reply = (
            f"Три быстрых рычага: 1) аудит подписок ({subs:,.0f} ₽), "
            f"2) лимит на {top_cat}, 3) автоперевод 10% дохода в инвестиции в день зарплаты."
        ).replace(",", " ")
        suggestions = ["Создать цель", "Анализ покупки", "Сценарий: потеря дохода"]
    elif "машин" in lower or "купить" in lower:
        reply = (
            f"При балансе {bal:,.0f} ₽ крупная покупка должна пройти через анализатор: "
            f"% капитала, часы работы, удар по цели. Откройте «AI Purchase Analyzer»."
        ).replace(",", " ")
        suggestions = ["Проанализировать покупку", "Отложить на 24 часа", "Альтернативы"]
    elif "зарплат" in lower or "хватит" in lower:
        daily = expense / max(date_days_left(), 1)
        reply = (
            f"Текущий баланс {bal:,.0f} ₽. При среднем burn ≈ {daily:,.0f} ₽/день "
            f"до зарплаты важно не уходить в минус по discretionary."
        ).replace(",", " ")
        suggestions = ["Прогноз месяца", "Вечерний ритуал", "Где срезать"]
    elif "подписк" in lower:
        reply = (
            f"Подписки: ≈ {subs:,.0f} ₽/мес. "
            f"Это {(subs / max(income, 1) * 100):.1f}% дохода. "
            f"Отключите всё, чем не пользовались 60+ дней."
        ).replace(",", " ")
        suggestions = ["Список подписок", "Отменить неиспользуемые"]
    else:
        mem_line = f" Учитываю: {memories[0]}." if memories else ""
        reply = (
            f"Баланс {bal:,.0f} ₽, доход месяца {income:,.0f} ₽, расходы {expense:,.0f} ₽.{mem_line} "
            f"Спросите: «Куда ушли деньги?» или «Что оптимизировать?» — разберём точечно."
        ).replace(",", " ")
        suggestions = ["Куда ушли деньги?", "Финансовое здоровье", "Прогноз до конца года"]

    return ChatResponse(reply=reply, suggestions=suggestions, memories_used=memories[:3])


def date_days_left() -> int:
    from datetime import date
    from calendar import monthrange

    t = date.today()
    return monthrange(t.year, t.month)[1] - t.day + 1


async def chat_with_advisor(
    message: str,
    history: list[ChatMessage],
    context: dict[str, Any],
    memories: list[str],
) -> ChatResponse:
    settings = get_settings()
    if not settings.openai_api_key:
        return _local_reply(message, context, memories)

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
        ctx = (
            f"Контекст: баланс={context.get('balance')}, доход={context.get('income_month')}, "
            f"расход={context.get('expense_month')}, топ-категория={context.get('top_category')}, "
            f"подписки={context.get('subscriptions_total')}. "
            f"Память: {'; '.join(memories) if memories else 'пусто'}."
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT + "\n" + ctx},
            *[{"role": m.role, "content": m.content} for m in history[-8:]],
            {"role": "user", "content": message},
        ]
        resp = await client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            temperature=0.6,
            max_tokens=800,
        )
        reply = resp.choices[0].message.content or "Не удалось получить ответ."
        return ChatResponse(
            reply=reply,
            suggestions=["Что оптимизировать?", "Прогноз месяца", "Анализ крупной покупки"],
            memories_used=memories[:3],
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("OpenAI chat failed, fallback: %s", exc)
        return _local_reply(message, context, memories)
