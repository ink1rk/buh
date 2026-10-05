from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.account import Account
from app.models.connection import BankOperation
from app.models.transaction import Transaction
from app.schemas.transaction import (
    QuickInputRequest,
    QuickInputResult,
    TransactionCreate,
    TransactionOut,
    TransactionUpdate,
)
from app.services.quick_input import parse_quick_input

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("", response_model=list[TransactionOut])
async def list_transactions(
    limit: int = Query(100, le=500),
    date_from: date | None = None,
    date_to: date | None = None,
    category: str = "",
    kind: str = "",
    search: str = "",
    db: AsyncSession = Depends(get_db),
):
    query = select(Transaction)
    if date_from:
        query = query.where(Transaction.occurred_on >= date_from)
    if date_to:
        query = query.where(Transaction.occurred_on <= date_to)
    if category:
        query = query.where(Transaction.category == category)
    if kind:
        query = query.where(Transaction.transaction_type == kind)
    if search:
        like = f"%{search}%"
        query = query.where(Transaction.description.ilike(like)
                            | Transaction.merchant.ilike(like))
    # Внутри дня порядок по номеру: иначе операции одного дня скачут между
    # запросами и список выглядит живущим своей жизнью.
    rows = (await db.execute(query.order_by(Transaction.occurred_on.desc(),
                                            Transaction.id.desc()).limit(limit))).scalars()
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


@router.patch("/{tx_id}", response_model=TransactionOut)
async def update_transaction(tx_id: int, payload: TransactionUpdate,
                             db: AsyncSession = Depends(get_db)):
    """Поправить операцию — вместе с остатком счёта, которого она касалась."""
    row = await db.get(Transaction, tx_id)
    if row is None:
        raise HTTPException(404, "операции нет")

    changes = payload.model_dump(exclude_unset=True)
    await _shift_balance(db, row.account_id, -row.amount)
    for field, value in changes.items():
        setattr(row, field, value)
    await _shift_balance(db, row.account_id, row.amount)
    await db.flush()
    return row


@router.delete("/{tx_id}")
async def delete_transaction(tx_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(Transaction, tx_id)
    if row is None:
        raise HTTPException(404, "операции нет")
    await _shift_balance(db, row.account_id, -row.amount)
    # Операция банка знает про эту транзакцию; без развязки повторная
    # загрузка выписки сочтёт её дублем и не вернёт удалённое.
    await db.execute(update(BankOperation)
                     .where(BankOperation.transaction_id == tx_id)
                     .values(transaction_id=None))
    await db.delete(row)
    await db.flush()
    return {"deleted": tx_id}


async def _shift_balance(db: AsyncSession, account_id: int | None, amount: float):
    if not account_id:
        return
    account = await db.get(Account, account_id)
    if account is not None:
        account.balance += amount


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
