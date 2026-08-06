"""Purchase Happiness Index — rate now, get asked later, AI learns what you tend to regret."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.happiness import PurchaseRating
from app.schemas.happiness import HappinessInsight


async def create_rating(
    db: AsyncSession,
    item: str,
    price: float,
    category: str,
    initial_rating: int | None,
    transaction_id: int | None = None,
) -> PurchaseRating:
    row = PurchaseRating(
        transaction_id=transaction_id,
        item=item,
        price=price,
        category=category,
        initial_rating=initial_rating,
        follow_up_on=date.today() + timedelta(days=30),
    )
    db.add(row)
    await db.flush()
    return row


async def pending_followups(db: AsyncSession) -> list[PurchaseRating]:
    today = date.today()
    rows = (
        await db.execute(
            select(PurchaseRating).where(
                PurchaseRating.followed_up.is_(False),
                PurchaseRating.follow_up_on <= today,
            )
        )
    ).scalars()
    return list(rows)


async def submit_followup(db: AsyncSession, rating_id: int, score: int) -> PurchaseRating | None:
    row = await db.get(PurchaseRating, rating_id)
    if not row:
        return None
    row.followup_rating = score
    row.followed_up = True
    await db.flush()
    return row


def build_category_insights(ratings: list[PurchaseRating]) -> list[HappinessInsight]:
    by_cat: dict[str, list[int]] = defaultdict(list)
    for r in ratings:
        score = r.followup_rating if r.followup_rating is not None else r.initial_rating
        if score is not None:
            by_cat[r.category].append(score)

    out: list[HappinessInsight] = []
    for cat, scores in by_cat.items():
        avg = sum(scores) / len(scores)
        if avg >= 4:
            verdict = f"«{cat}» — обычно удачные покупки. Смело инвестируйте туда время на выбор."
        elif avg <= 2.5:
            verdict = f"«{cat}» — часто разочаровывает. Прежде чем покупать снова — подождите 48 часов."
        else:
            verdict = f"«{cat}» — неоднозначно. Оценивайте каждую покупку отдельно."
        out.append(HappinessInsight(category=cat, avg_rating=round(avg, 1), count=len(scores), verdict=verdict))
    return sorted(out, key=lambda x: x.avg_rating)
