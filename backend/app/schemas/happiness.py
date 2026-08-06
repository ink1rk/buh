from datetime import date

from pydantic import BaseModel

from app.schemas.common import ORMModel


class PurchaseRatingCreate(BaseModel):
    transaction_id: int | None = None
    item: str
    price: float = 0.0
    category: str = "other"
    initial_rating: int | None = None


class FollowUpRating(BaseModel):
    rating: int


class PurchaseRatingOut(ORMModel):
    id: int
    transaction_id: int | None
    item: str
    price: float
    category: str
    initial_rating: int | None
    followup_rating: int | None
    follow_up_on: date | None
    followed_up: bool


class HappinessInsight(BaseModel):
    category: str
    avg_rating: float
    count: int
    verdict: str
