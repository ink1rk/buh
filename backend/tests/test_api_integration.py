"""API integration tests against isolated in-memory DB."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_dashboard_living_and_net_worth(client: AsyncClient):
    r = await client.get("/api/v1/dashboard")
    assert r.status_code == 200
    data = r.json()
    assert "living_screen" in data and len(data["living_screen"]) >= 3
    assert data["daily_challenge"] and data["daily_challenge"]["id"]
    assert data["net_worth"] > 0
    # Expected NW from fixture:
    # liquid 100k+10k+200k+150k+50k = 510k + car 500k + owed 12k - i_owe 5k = 1_017_000
    assert abs(data["net_worth"] - 1_017_000) < 1
    # Expense must be consumption only (3000+800), not investments/savings
    assert abs(data["balances"]["expense_month"] - 3_800) < 1
    assert abs(data["balances"]["debts_owing"] - 5_000) < 1
    assert abs(data["balances"]["debts_owed"] - 12_000) < 1
    assert 0 <= data["health"]["score"] <= 100


@pytest.mark.asyncio
async def test_networth_and_capital_map(client: AsyncClient):
    r = await client.get("/api/v1/networth")
    assert r.status_code == 200
    nw = r.json()
    assert abs(nw["current"] - 1_017_000) < 1
    assert nw["capital_map"]["total_debts"] == 5_000
    labels = {s["label"] for s in nw["capital_map"]["slices"]}
    assert "Деньги" in labels
    assert "Автомобиль" in labels or "Инвестиции" in labels


@pytest.mark.asyncio
async def test_quick_input_and_chat(client: AsyncClient):
    r = await client.post("/api/v1/transactions/quick", json={"text": "-450 кофе"})
    assert r.status_code == 200
    body = r.json()
    assert body["parsed"]["amount"] == -450
    assert body["parsed"]["category"] == "cafe"

    chat = await client.post("/api/v1/ai/chat", json={"message": "Куда ушли деньги?"})
    assert chat.status_code == 200
    reply = chat.json()["reply"].lower()
    assert len(reply) > 30
    # Lifestyle spend, not capital allocation
    assert "groceries" in reply or "cafe" in reply or "продукт" in reply or "кофе" in reply or "пятёр" in reply


@pytest.mark.asyncio
async def test_purchase_analyzer_uses_net_worth(client: AsyncClient):
    r = await client.post(
        "/api/v1/ai/purchase/analyze",
        json={"item": "MacBook", "price": 101_700},
    )
    assert r.status_code == 200
    data = r.json()
    # 101700 / 1017000 = 10%
    assert abs(data["capital_pct"] - 10.0) < 0.2
    assert data["challenge_questions"]
    assert data["twin_opinion"]
    assert data["coffee_equivalent"] > 0


@pytest.mark.asyncio
async def test_habits_risks_timeline_coach(client: AsyncClient):
    habits = (await client.get("/api/v1/habits")).json()
    assert 0 <= habits["overall"] <= 100
    imp = next(s for s in habits["scores"] if s["key"] == "impulsiveness")
    assert imp["score"] >= 20

    risks = (await client.get("/api/v1/risks")).json()
    assert len(risks["items"]) == 6

    timeline = (await client.get("/api/v1/timeline")).json()
    assert len(timeline) >= 1

    coach = (await client.get("/api/v1/coach/today")).json()
    assert coach["id"]
    done = await client.post(f"/api/v1/coach/{coach['id']}/complete")
    assert done.status_code == 200
    assert done.json()["is_completed"] is True


@pytest.mark.asyncio
async def test_analytics_cashflow_conserved(client: AsyncClient):
    r = await client.get("/api/v1/analytics/bundle")
    assert r.status_code == 200
    cf = r.json()["cashflow"]
    nodes = {n["id"]: n["amount"] for n in cf["nodes"]}
    out = sum(l["value"] for l in cf["links"] if l["source"] == "distribute")
    assert abs(nodes["income"] - out) < 0.05


@pytest.mark.asyncio
async def test_subscriptions_unused_and_export(client: AsyncClient):
    subs = (await client.get("/api/v1/subscriptions")).json()
    assert any(s["unused_warning"] for s in subs)

    js = await client.get("/api/v1/export/json")
    assert js.status_code == 200
    assert "transactions" in js.json()

    csv = await client.get("/api/v1/export/csv")
    assert csv.status_code == 200
    assert "amount" in csv.text


@pytest.mark.asyncio
async def test_goals_math(client: AsyncClient):
    goals = (await client.get("/api/v1/goals")).json()
    assert goals
    g = goals[0]
    assert abs(g["remaining"] - (g["target_amount"] - g["current_amount"])) < 0.01
    assert abs(g["progress_pct"] - (g["current_amount"] / g["target_amount"] * 100)) < 0.2
