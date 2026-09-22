"""Свои операции: завести, поправить, удалить — вместе с остатком счёта."""

from datetime import date

import pytest
from sqlalchemy import select

from app.models.account import Account
from app.models.connection import BankOperation
from app.models.transaction import Transaction


@pytest.mark.asyncio
async def test_a_typo_in_the_amount_can_be_fixed(client, seeded_db):
    account = (await seeded_db.execute(select(Account))).scalars().first()
    start = account.balance
    made = (await client.post("/api/v1/transactions", json={
        "amount": -5000, "description": "Ошибся нулём",
        "account_id": account.id})).json()

    fixed = await client.patch(f"/api/v1/transactions/{made['id']}",
                               json={"amount": -500})

    assert fixed.status_code == 200 and fixed.json()["amount"] == -500
    await seeded_db.refresh(account)
    assert account.balance == pytest.approx(start - 500), "остаток не поехал следом"


@pytest.mark.asyncio
async def test_a_deleted_operation_gives_the_money_back_to_the_account(client, seeded_db):
    account = (await seeded_db.execute(select(Account))).scalars().first()
    start = account.balance
    made = (await client.post("/api/v1/transactions", json={
        "amount": -1200, "description": "Не моё", "account_id": account.id})).json()

    assert (await client.delete(f"/api/v1/transactions/{made['id']}")).status_code == 200

    await seeded_db.refresh(account)
    assert account.balance == pytest.approx(start)
    assert await seeded_db.get(Transaction, made["id"]) is None


@pytest.mark.asyncio
async def test_deleting_a_row_from_a_statement_lets_it_come_back(client, seeded_db):
    """Иначе повторная загрузка сочтёт её дублем и не вернёт удалённое."""
    made = (await client.post("/api/v1/transactions", json={
        "amount": -440, "description": "Из выписки", "source": "import"})).json()
    seeded_db.add(BankOperation(connection_id=1, fingerprint="f1", amount=-440,
                                occurred_on=date(2026, 1, 2),
                                transaction_id=made["id"]))
    await seeded_db.flush()

    await client.delete(f"/api/v1/transactions/{made['id']}")

    operation = (await seeded_db.execute(select(BankOperation))).scalars().one()
    assert operation.transaction_id is None


@pytest.mark.asyncio
async def test_a_comment_is_kept_with_the_operation(client):
    made = await client.post("/api/v1/transactions", json={
        "amount": -3400, "transaction_type": "expense", "category": "health",
        "description": "Зубной, вторая часть — остальное в марте"})

    assert made.status_code == 200
    assert "вторая часть" in made.json()["description"]


@pytest.mark.asyncio
async def test_operations_can_be_narrowed_to_a_period_and_a_word(client):
    await client.post("/api/v1/transactions", json={
        "amount": -100, "description": "Кофе у дома", "occurred_on": "2026-02-10"})
    await client.post("/api/v1/transactions", json={
        "amount": -200, "description": "Бензин", "occurred_on": "2026-03-15"})

    found = (await client.get("/api/v1/transactions",
                              params={"date_from": "2026-02-01",
                                      "date_to": "2026-02-28"})).json()

    assert [t["description"] for t in found] == ["Кофе у дома"]
    by_word = (await client.get("/api/v1/transactions",
                                params={"search": "бензин"})).json()
    assert [t["description"] for t in by_word] == ["Бензин"], "поиск без учёта регистра"
