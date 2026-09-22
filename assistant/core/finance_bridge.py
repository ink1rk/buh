"""Мост в финансовое приложение: письма про деньги и общий календарь.

Почта и CalDAV живут в ассистенте, бюджет и платежи — в финансах. Владельцу
это один вопрос: что будет с деньгами. Письмо-счёт становится событием
календаря там, а предстоящие платежи оттуда попадают в расписание здесь.
"""
from __future__ import annotations

import datetime

import httpx

from .config import config
from providers.calendar import Event
from providers.email import extract_amount, extract_due_date


def _client():
    return httpx.Client(timeout=8, trust_env=False)


def push_mail(letter: dict) -> dict | None:
    """Отдать финансовому приложению письмо про деньги. None — нечего отдавать."""
    blob = f"{letter.get('subject') or ''}\n{letter.get('text') or ''}"
    amount = extract_amount(blob)
    when = extract_due_date(blob)
    if when is None and letter.get("ts"):
        when = datetime.datetime.fromtimestamp(letter["ts"], config.tz).date()
    payload = {
        "message_id": letter.get("message_id") or "",
        "sender": letter.get("address") or "",
        "subject": letter.get("subject") or "",
        "text": (letter.get("text") or "")[:2000],
        "amount": amount,
        "event_date": when.isoformat() if when else None,
    }
    with _client() as client:
        response = client.post(f"{config.finance_api}/ingest/mail", json=payload)
        response.raise_for_status()
        return response.json()


def finance_schedule(days=14) -> list[Event]:
    """Платежи из финансового календаря — тем же типом, что и встречи CalDAV."""
    try:
        with _client() as client:
            rows = client.get(f"{config.finance_api}/calendar").json()
    except Exception as e:
        print(f"finance calendar unavailable: {type(e).__name__}: {e}")
        return []
    if not isinstance(rows, list):
        return []
    now = datetime.datetime.now(config.tz)
    edge = now.date() + datetime.timedelta(days=days)
    events = []
    for row in rows:
        try:
            day = datetime.date.fromisoformat(str(row.get("event_date") or "")[:10])
        except ValueError:
            continue
        if day > edge or row.get("is_completed"):
            continue
        amount = float(row.get("amount") or 0)
        title = row.get("title") or "платёж"
        summary = f"{title} · {int(amount):,} ₽".replace(",", " ") if amount else title
        start = datetime.datetime.combine(day, datetime.time.min, tzinfo=config.tz)
        events.append(Event(
            uid=f"finance:{row.get('id')}",
            summary=summary,
            start=start,
            end=start + datetime.timedelta(days=1),
            all_day=True,
            description=row.get("notes") or "",
            calendar="финансы",
            account="finance",
        ))
    return events


def finance_snapshot() -> dict:
    """То, что ассистенту нужно сказать о деньгах, одним запросом."""
    out = {}
    try:
        with _client() as client:
            dash = client.get(f"{config.finance_api}/dashboard").json()
            out["net_worth"] = dash.get("net_worth")
            out["income"] = (dash.get("balances") or {}).get("income_month")
            out["expense"] = (dash.get("balances") or {}).get("expense_month")
            out["budget"] = dash.get("budget") or {}
            try:
                out["goals"] = client.get(f"{config.finance_api}/goals").json()
            except Exception:
                out["goals"] = []
            try:
                out["calendar"] = client.get(f"{config.finance_api}/calendar").json()
            except Exception:
                out["calendar"] = []
    except Exception as e:
        out["error"] = str(e)
    return out
