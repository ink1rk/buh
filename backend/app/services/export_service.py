"""Export / import user data."""

from __future__ import annotations

import csv
import io
import json
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.debt import Debt
from app.models.goal import Goal
from app.models.transaction import Transaction


async def export_json(db: AsyncSession) -> dict[str, Any]:
    accounts = [ _row(a) for a in (await db.execute(select(Account))).scalars() ]
    txs = [ _row(t) for t in (await db.execute(select(Transaction))).scalars() ]
    goals = [ _row(g) for g in (await db.execute(select(Goal))).scalars() ]
    debts = [ _row(d) for d in (await db.execute(select(Debt))).scalars() ]
    return {
        "exported_on": date.today().isoformat(),
        "accounts": accounts,
        "transactions": txs,
        "goals": goals,
        "debts": debts,
    }


def _row(obj: Any) -> dict[str, Any]:
    data = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        if hasattr(val, "isoformat"):
            val = val.isoformat()
        data[col.name] = val
    return data


async def export_csv(db: AsyncSession) -> str:
    txs = list((await db.execute(select(Transaction).order_by(Transaction.occurred_on.desc()))).scalars())
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=["id", "occurred_on", "amount", "category", "description", "merchant", "transaction_type"],
    )
    writer.writeheader()
    for t in txs:
        writer.writerow(
            {
                "id": t.id,
                "occurred_on": t.occurred_on.isoformat(),
                "amount": t.amount,
                "category": t.category,
                "description": t.description,
                "merchant": t.merchant,
                "transaction_type": t.transaction_type,
            }
        )
    return buf.getvalue()


async def export_excel_bytes(db: AsyncSession) -> bytes:
    import pandas as pd

    payload = await export_json(db)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for sheet, rows in payload.items():
            if sheet == "exported_on":
                continue
            pd.DataFrame(rows).to_excel(writer, sheet_name=sheet[:31], index=False)
    return buf.getvalue()
