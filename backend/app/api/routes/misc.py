from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.investment.advisor import advise_portfolio
from app.models.achievement import Achievement, UserAchievement
from app.models.calendar import CalendarEvent
from app.models.debt import Debt
from app.models.investment import InvestmentHolding
from app.models.subscription import Subscription
from app.models.user import UserProfile
from app.ocr.receipt_parser import parse_receipt_bytes
from app.schemas.misc import (
    AchievementOut,
    CalendarEventCreate,
    CalendarEventOut,
    DebtCreate,
    DebtOut,
    InvestmentCreate,
    InvestmentOut,
    SubscriptionCreate,
    SubscriptionOut,
    UserProfileOut,
    UserProfileUpdate,
)
from app.services.dashboard_service import compute_balances, get_or_create_profile
from app.services.export_service import export_csv, export_excel_bytes, export_json
from app.services.reset import clean_slate
from fastapi import File, UploadFile

router = APIRouter(tags=["misc"])


# --- Profile ---
@router.get("/profile", response_model=UserProfileOut)
async def get_profile(db: AsyncSession = Depends(get_db)):
    return await get_or_create_profile(db)


@router.patch("/profile", response_model=UserProfileOut)
async def update_profile(payload: UserProfileUpdate, db: AsyncSession = Depends(get_db)):
    profile = await get_or_create_profile(db)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(profile, k, v)
    await db.flush()
    return profile


@router.post("/profile/clean-slate")
async def profile_clean_slate(confirm: str = "", db: AsyncSession = Depends(get_db)):
    """Стереть всё и начать со своих денег.

    Спрашиваем слово вслух: восстановить стёртое неоткуда, а промахнуться
    мимо кнопки легко.
    """
    if confirm != "стереть":
        raise HTTPException(400, "нужно подтверждение: confirm=стереть")
    return await clean_slate(db)


# --- Debts ---
@router.get("/debts", response_model=list[DebtOut])
async def list_debts(db: AsyncSession = Depends(get_db)):
    rows = list((await db.execute(select(Debt).where(Debt.is_active.is_(True)))).scalars())
    out = []
    for d in rows:
        # simple time value: 12% annual
        days = (d.due_date - date.today()).days if d.due_date else 30
        cost = d.remaining * 0.12 * max(days, 0) / 365
        item = DebtOut.model_validate(d)
        item.time_value_cost = round(cost, 2)
        out.append(item)
    return out


@router.post("/debts", response_model=DebtOut)
async def create_debt(payload: DebtCreate, db: AsyncSession = Depends(get_db)):
    data = payload.model_dump()
    if data.get("remaining") is None:
        data["remaining"] = data["amount"]
    row = Debt(**data)
    db.add(row)
    await db.flush()
    item = DebtOut.model_validate(row)
    item.time_value_cost = 0
    return item


# --- Subscriptions ---
@router.get("/subscriptions", response_model=list[SubscriptionOut])
async def list_subscriptions(db: AsyncSession = Depends(get_db)):
    rows = list((await db.execute(select(Subscription))).scalars())
    out = []
    for s in rows:
        unused_days = (date.today() - s.last_used_date).days if s.last_used_date else 0
        item = SubscriptionOut.model_validate(s)
        item.unused_days = unused_days
        item.unused_warning = bool(s.is_active and unused_days >= s.unused_days_threshold)
        out.append(item)
    return out


@router.post("/subscriptions", response_model=SubscriptionOut)
async def create_subscription(payload: SubscriptionCreate, db: AsyncSession = Depends(get_db)):
    row = Subscription(**payload.model_dump())
    db.add(row)
    await db.flush()
    item = SubscriptionOut.model_validate(row)
    return item


# --- Calendar ---
@router.get("/calendar", response_model=list[CalendarEventOut])
async def list_events(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(CalendarEvent).order_by(CalendarEvent.event_date))).scalars()
    return list(rows)


@router.post("/calendar", response_model=CalendarEventOut)
async def create_event(payload: CalendarEventCreate, db: AsyncSession = Depends(get_db)):
    row = CalendarEvent(**payload.model_dump())
    db.add(row)
    await db.flush()
    return row


# --- Investments ---
@router.get("/investments", response_model=list[InvestmentOut])
async def list_investments(db: AsyncSession = Depends(get_db)):
    rows = list((await db.execute(select(InvestmentHolding))).scalars())
    out = []
    for h in rows:
        item = InvestmentOut.model_validate(h)
        item.gain_pct = round((h.value - h.cost_basis) / max(h.cost_basis, 1) * 100, 2)
        out.append(item)
    return out


@router.post("/investments", response_model=InvestmentOut)
async def create_investment(payload: InvestmentCreate, db: AsyncSession = Depends(get_db)):
    row = InvestmentHolding(**payload.model_dump())
    db.add(row)
    await db.flush()
    item = InvestmentOut.model_validate(row)
    item.gain_pct = 0
    return item


@router.get("/investments/advice")
async def investment_advice(db: AsyncSession = Depends(get_db)):
    holdings = list((await db.execute(select(InvestmentHolding))).scalars())
    balances = await compute_balances(db)
    profile = await get_or_create_profile(db)
    expense = balances.expense_month or profile.monthly_income * 0.6
    months = balances.reserve / max(expense, 1)
    return advise_portfolio(holdings, months)


# --- Achievements ---
@router.get("/achievements", response_model=list[AchievementOut])
async def list_achievements(db: AsyncSession = Depends(get_db)):
    ach = list((await db.execute(select(Achievement))).scalars())
    unlocked = {
        u.achievement_id: u
        for u in (await db.execute(select(UserAchievement))).scalars()
    }
    out = []
    for a in ach:
        u = unlocked.get(a.id)
        out.append(
            AchievementOut(
                id=a.id,
                code=a.code,
                title=a.title,
                description=a.description,
                icon=a.icon,
                category=a.category,
                points=a.points,
                unlocked=u is not None,
                unlocked_at=u.unlocked_at if u else None,
            )
        )
    return out


# --- OCR ---
@router.post("/ocr/receipt")
async def ocr_receipt(file: UploadFile = File(...)):
    data = await file.read()
    return await parse_receipt_bytes(data, file.filename or "receipt.jpg")


# --- Export ---
@router.get("/export/json")
async def export_as_json(db: AsyncSession = Depends(get_db)):
    return await export_json(db)


@router.get("/export/csv")
async def export_as_csv(db: AsyncSession = Depends(get_db)):
    content = await export_csv(db)
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=transactions.csv"},
    )


@router.get("/export/excel")
async def export_as_excel(db: AsyncSession = Depends(get_db)):
    content = await export_excel_bytes(db)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=finance.xlsx"},
    )
