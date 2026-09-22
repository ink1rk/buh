from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.mail_ingest import ingest_mail

router = APIRouter(prefix="/ingest", tags=["ingest"])


class MailIngest(BaseModel):
    message_id: str = ""
    sender: str = ""
    subject: str = ""
    text: str = ""
    amount: float | None = None
    event_date: str | None = None


@router.post("/mail")
async def ingest_mail_letter(payload: MailIngest, db: AsyncSession = Depends(get_db)):
    """Письмо-счёт от ассистента: становится событием календаря, не операцией.

    Операцию из чека не заводим — та же покупка уже есть в выписке, и второй
    раз она раздует расход. Дата и сумма нужны в календаре, чтобы платёж
    не пришёл сюрпризом.
    """
    return await ingest_mail(db, payload.model_dump())
