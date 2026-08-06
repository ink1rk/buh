from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.advisor import chat_with_advisor
from app.ai.memory_store import memory_store
from app.core.database import get_db
from app.models.calendar import CalendarEvent
from app.models.goal import Goal
from app.models.subscription import Subscription
from app.models.transaction import Transaction
from app.schemas.ai import (
    ChatRequest,
    ChatResponse,
    PostponePurchaseRequest,
    PurchaseAnalyzeRequest,
)
from app.services.dashboard_service import compute_balances, get_or_create_profile
from app.services.purchase_analyzer import analyze_purchase

router = APIRouter(prefix="/ai", tags=["ai"])


async def _context(db: AsyncSession) -> dict:
    balances = await compute_balances(db)
    txs = list((await db.execute(select(Transaction))).scalars())
    month_start = date.today().replace(day=1)
    expenses = [t for t in txs if t.occurred_on >= month_start and t.amount < 0]
    by_cat: dict[str, float] = {}
    for t in expenses:
        by_cat[t.category] = by_cat.get(t.category, 0) + abs(t.amount)
    top = max(by_cat.items(), key=lambda x: x[1]) if by_cat else ("other", 0)
    subs = list((await db.execute(select(Subscription).where(Subscription.is_active.is_(True)))).scalars())
    return {
        "balance": balances.total,
        "income_month": balances.income_month,
        "expense_month": balances.expense_month,
        "top_category": top[0],
        "top_category_sum": top[1],
        "subscriptions_total": sum(s.amount for s in subs),
    }


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, db: AsyncSession = Depends(get_db)):
    ctx = await _context(db)
    memories = await memory_store.recall(db, payload.message, limit=5)
    result = await chat_with_advisor(payload.message, payload.history, ctx, memories)
    # store notable preferences lightly
    if any(w in payload.message.lower() for w in ("хочу", "мечтаю", "боюсь", "цель")):
        await memory_store.remember(
            db,
            key=f"chat-{date.today().isoformat()}",
            content=payload.message[:500],
            memory_type="conversation",
            importance=0.55,
        )
    return result


@router.post("/purchase/analyze")
async def purchase_analyze(payload: PurchaseAnalyzeRequest, db: AsyncSession = Depends(get_db)):
    balances = await compute_balances(db)
    profile = await get_or_create_profile(db)
    hourly = (profile.monthly_income or 180000) / 160
    monthly_savings = max(balances.income_month - balances.expense_month, profile.monthly_income * 0.15)
    goals = list((await db.execute(select(Goal).where(Goal.is_active.is_(True)).order_by(Goal.priority))).scalars())
    remaining = (goals[0].target_amount - goals[0].current_amount) if goals else None
    return analyze_purchase(
        payload.item,
        payload.price,
        balances.total,
        hourly,
        monthly_savings,
        remaining,
    )


@router.post("/purchase/postpone")
async def postpone_purchase(payload: PostponePurchaseRequest, db: AsyncSession = Depends(get_db)):
    remind_at = datetime.now() + timedelta(hours=payload.hours)
    event = CalendarEvent(
        title=f"Напоминание: {payload.item}",
        event_type="reminder",
        amount=payload.price,
        event_date=remind_at.date(),
        color="#fbbf24",
        notes=f"Отложено на {payload.hours}ч. Пересмотрите покупку осознанно.",
        reminder_days_before=0,
    )
    db.add(event)
    await memory_store.remember(
        db,
        key=f"postpone-{payload.item}",
        content=f"Отложил покупку {payload.item} за {payload.price} до {remind_at.isoformat()}",
        memory_type="habit",
        importance=0.7,
    )
    await db.flush()
    return {"ok": True, "remind_on": event.event_date.isoformat(), "event_id": event.id}


@router.get("/memories")
async def list_memories(db: AsyncSession = Depends(get_db)):
    rows = await memory_store.list_all(db)
    return [
        {
            "id": m.id,
            "key": m.key,
            "content": m.content,
            "memory_type": m.memory_type,
            "importance": m.importance,
        }
        for m in rows
    ]
