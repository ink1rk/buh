from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.account import Account
from app.schemas.account import AccountCreate, AccountOut, AccountUpdate
from app.services.dashboard_service import compute_balances

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountOut])
async def list_accounts(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Account).order_by(Account.sort_order))).scalars()
    return list(rows)


@router.get("/balances")
async def balances(db: AsyncSession = Depends(get_db)):
    return await compute_balances(db)


@router.post("", response_model=AccountOut)
async def create_account(payload: AccountCreate, db: AsyncSession = Depends(get_db)):
    row = Account(**payload.model_dump())
    db.add(row)
    await db.flush()
    return row


@router.patch("/{account_id}", response_model=AccountOut)
async def update_account(account_id: int, payload: AccountUpdate, db: AsyncSession = Depends(get_db)):
    row = await db.get(Account, account_id)
    if not row:
        raise HTTPException(404, "Account not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    await db.flush()
    return row
