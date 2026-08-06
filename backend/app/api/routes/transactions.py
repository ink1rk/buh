from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.account import Account
from app.models.transaction import Transaction
from app.schemas.transaction import (
    QuickInputRequest,
    QuickInputResult,
    TransactionCreate,
    TransactionOut,
)
from app.services.quick_input import parse_quick_input

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("", response_model=list[TransactionOut])
async def list_transactions(
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(select(Transaction).order_by(Transaction.occurred_on.desc()).limit(limit))
    ).scalars()
    return list(rows)


@router.post("", response_model=TransactionOut)
async def create_transaction(payload: TransactionCreate, db: AsyncSession = Depends(get_db)):
    data = payload.model_dump()
    if data.get("occurred_on") is None:
        data["occurred_on"] = date.today()
    row = Transaction(**data)
    db.add(row)
    if payload.account_id:
        acc = await db.get(Account, payload.account_id)
        if acc:
            acc.balance += payload.amount
    await db.flush()
    return row


@router.post("/quick", response_model=QuickInputResult)
async def quick_input(payload: QuickInputRequest, db: AsyncSession = Depends(get_db)):
    draft, confidence, explanation = parse_quick_input(payload.text)
    # auto-apply high confidence
    tx = None
    needs = confidence < 0.85
    if not needs:
        data = draft.model_dump()
        if data.get("occurred_on") is None:
            data["occurred_on"] = date.today()
        # pick default card account
        acc = (
            await db.execute(select(Account).where(Account.account_type == "card").limit(1))
        ).scalar_one_or_none()
        if acc:
            data["account_id"] = acc.id
            acc.balance += draft.amount
        tx = Transaction(**data)
        db.add(tx)
        await db.flush()
    return QuickInputResult(
        parsed=draft,
        confidence=confidence,
        explanation=explanation,
        transaction=TransactionOut.model_validate(tx) if tx else None,
        needs_confirmation=needs,
    )
