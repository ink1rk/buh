"""Письмо-счёт становится событием календаря, а не второй операцией."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_a_bill_becomes_a_calendar_event(client: AsyncClient):
    created = (
        await client.post(
            "/api/v1/ingest/mail",
            json={
                "message_id": "<bill-1@shop>",
                "sender": "receipt@shop.ru",
                "subject": "Счёт за интернет",
                "text": "К оплате 890 ₽ до 25.10.2026",
                "amount": 890,
                "event_date": "2026-10-25",
            },
        )
    ).json()
    assert created["duplicate"] is False
    assert created["amount"] == 890

    events = (await client.get("/api/v1/calendar")).json()
    bill = next(e for e in events if e["external_id"] == "<bill-1@shop>")
    assert bill["source"] == "mail"
    assert bill["event_type"] == "payment"
    assert bill["event_date"] == "2026-10-25"

    again = (
        await client.post(
            "/api/v1/ingest/mail",
            json={"message_id": "<bill-1@shop>", "subject": "Счёт за интернет",
                  "amount": 890, "event_date": "2026-10-25"},
        )
    ).json()
    assert again["duplicate"] is True
    assert again["id"] == created["id"]


@pytest.mark.asyncio
async def test_the_same_bill_without_message_id_is_not_duplicated(client: AsyncClient):
    payload = {
        "sender": "receipt@shop.ru",
        "subject": "Квитанция ЖКХ",
        "text": "К оплате 1200 ₽",
        "amount": 1200,
        "event_date": "2026-11-01",
    }
    first = (await client.post("/api/v1/ingest/mail", json=payload)).json()
    second = (await client.post("/api/v1/ingest/mail", json=payload)).json()
    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert second["id"] == first["id"]

    events = (await client.get("/api/v1/calendar")).json()
    bills = [e for e in events if e["title"] == "Квитанция ЖКХ"]
    assert len(bills) == 1
    assert bills[0]["event_type"] == "utilities"
