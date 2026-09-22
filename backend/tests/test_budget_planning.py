"""План расходов должен быть тем, что человек задал, а не фактом месяца."""

from __future__ import annotations

from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction


@pytest.mark.asyncio
async def test_budget_starts_as_a_suggestion_from_history(client: AsyncClient):
    plan = (await client.get("/api/v1/budget")).json()

    assert plan["has_plan"] is False
    assert plan["months_observed"] >= 1
    slugs = {row["category"] for row in plan["suggestions"]}
    assert "groceries" in slugs
    assert "cafe" in slugs
    assert "investments" not in slugs
    groceries = next(row for row in plan["suggestions"] if row["category"] == "groceries")
    assert groceries["proposed_limit"] > 0
    assert groceries["name"] == "продукты"


@pytest.mark.asyncio
async def test_saving_a_plan_makes_it_the_declared_budget(client: AsyncClient):
    saved = (
        await client.put(
            "/api/v1/budget",
            json={
                "monthly_income": 80_000,
                "envelopes": [
                    {"category": "groceries", "monthly_limit": 10_000},
                    {"category": "cafe", "monthly_limit": 2_000},
                ],
            },
        )
    ).json()

    assert saved["has_plan"] is True
    assert saved["monthly_income"] == 80_000
    assert saved["totals"]["planned"] == 12_000
    assert {row["category"] for row in saved["envelopes"]} == {"groceries", "cafe"}

    dash = (await client.get("/api/v1/dashboard")).json()
    assert dash["budget"]["has_plan"] is True
    assert dash["budget"]["planned"] == 12_000
    profile = (await client.get("/api/v1/profile")).json()
    assert profile["monthly_income"] == 80_000


@pytest.mark.asyncio
async def test_seed_uses_year_average_not_this_month_alone(client: AsyncClient, seeded_db: AsyncSession):
    seeded_db.add(
        Transaction(
            amount=-12_000,
            category="groceries",
            description="Продукты прошлым летом",
            transaction_type="expense",
            occurred_on=date(date.today().year, 1, 15)
            if date.today().month != 1
            else date(date.today().year - 1, 6, 15),
            source="test",
        )
    )
    await seeded_db.commit()

    seeded = (await client.post("/api/v1/budget/seed")).json()
    assert seeded["has_plan"] is True
    groceries = next(row for row in seeded["envelopes"] if row["category"] == "groceries")
    # Два месяца с продуктами, среднее меньше январских 12 000.
    assert groceries["monthly_limit"] < 12_000
    assert groceries["average_last_12m"] > 0

    again = (await client.post("/api/v1/budget/seed")).json()
    first_id = next(row for row in seeded["envelopes"] if row["category"] == "groceries")["id"]
    same_id = next(row for row in again["envelopes"] if row["category"] == "groceries")["id"]
    assert first_id == same_id, "без replace повтор не должен переписывать план"


@pytest.mark.asyncio
async def test_a_goal_can_be_added_changed_and_removed(client: AsyncClient):
    created = (
        await client.post(
            "/api/v1/goals",
            json={"title": "Отпуск", "target_amount": 150_000, "monthly_contribution": 15_000},
        )
    ).json()
    assert created["title"] == "Отпуск"
    assert created["remaining"] == 150_000

    patched = (await client.patch(f"/api/v1/goals/{created['id']}", json={"current_amount": 30_000})).json()
    assert patched["remaining"] == 120_000

    deleted = await client.delete(f"/api/v1/goals/{created['id']}")
    assert deleted.status_code == 204
    titles = {g["title"] for g in (await client.get("/api/v1/goals")).json()}
    assert "Отпуск" not in titles


@pytest.mark.asyncio
async def test_debts_subscriptions_calendar_and_investments_are_writable(client: AsyncClient):
    debt = (
        await client.post(
            "/api/v1/debts",
            json={"person_name": "Олег", "direction": "i_owe", "amount": 8_000},
        )
    ).json()
    assert debt["remaining"] == 8_000
    await client.patch(f"/api/v1/debts/{debt['id']}", json={"remaining": 3_000})
    assert (await client.delete(f"/api/v1/debts/{debt['id']}")).status_code == 204

    sub = (
        await client.post(
            "/api/v1/subscriptions",
            json={"name": "Кинопоиск", "amount": 399, "category": "subscriptions"},
        )
    ).json()
    await client.patch(f"/api/v1/subscriptions/{sub['id']}", json={"is_active": False})
    assert (await client.delete(f"/api/v1/subscriptions/{sub['id']}")).status_code == 204

    event = (
        await client.post(
            "/api/v1/calendar",
            json={"title": "Ипотека", "event_date": "2026-10-05", "amount": 42_000, "event_type": "credit"},
        )
    ).json()
    await client.patch(f"/api/v1/calendar/{event['id']}", json={"amount": 41_000})
    assert (await client.delete(f"/api/v1/calendar/{event['id']}")).status_code == 204

    holding = (
        await client.post(
            "/api/v1/investments",
            json={"name": "ВТБ фонд", "asset_class": "etf", "value": 50_000, "cost_basis": 48_000},
        )
    ).json()
    assert holding["gain_pct"] == 0
    patched = (await client.patch(f"/api/v1/investments/{holding['id']}", json={"value": 55_000})).json()
    assert patched["gain_pct"] > 0
    assert (await client.delete(f"/api/v1/investments/{holding['id']}")).status_code == 204


@pytest.mark.asyncio
async def test_without_envelopes_dashboard_still_does_not_invent_a_budget(client: AsyncClient, seeded_db):
    from app.services.reset import clean_slate

    await clean_slate(seeded_db)
    await seeded_db.commit()
    await client.post("/api/v1/transactions", json={"amount": -26_000, "description": "Продукты"})

    dash = (await client.get("/api/v1/dashboard")).json()
    assert dash["budget"]["has_plan"] is False
    assert not [a for a in dash["proactive_alerts"] if a["category"] == "budget_pace"]
