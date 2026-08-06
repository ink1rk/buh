from datetime import date

from pydantic import BaseModel

from app.schemas.common import ORMModel


class DailyChallengeOut(ORMModel):
    id: int
    challenge_date: date
    title: str
    body: str
    category: str
    is_completed: bool
