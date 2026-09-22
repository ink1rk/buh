"""Чистый лист: выдуманные деньги уходят, свои остаются."""

from datetime import date

import pytest
from sqlalchemy import func, select

from app.models.account import Account
from app.models.connection import BankConnection, BankOperation
from app.models.goal import Goal
from app.models.transaction import Transaction
from app.models.user import UserProfile
from app.services.reset import clean_slate


@pytest.mark.asyncio
async def test_a_clean_slate_removes_the_invented_money(seeded_db):
    before = await seeded_db.scalar(select(func.count()).select_from(Transaction))
    assert before, "фикстура должна что-то положить, иначе тест ни о чём"

    report = await clean_slate(seeded_db)

    assert await seeded_db.scalar(select(func.count()).select_from(Transaction)) == 0
    assert await seeded_db.scalar(select(func.count()).select_from(Account)) == 0
    assert await seeded_db.scalar(select(func.count()).select_from(Goal)) == 0
    assert report["total"] >= before


@pytest.mark.asyncio
async def test_the_bank_connection_survives_but_forgets_what_it_imported(seeded_db):
    """Подключение владелец заводил сам — выписку надо залить заново."""
    seeded_db.add(BankConnection(provider="ozon", label="Ozon", account_id=7,
                                 imported_total=42, status="error",
                                 last_error="что-то было"))
    await seeded_db.flush()

    await clean_slate(seeded_db)

    connection = (await seeded_db.execute(select(BankConnection))).scalars().one()
    assert connection.provider == "ozon"
    assert connection.imported_total == 0 and connection.account_id is None
    assert connection.status == "idle" and connection.last_error == ""


@pytest.mark.asyncio
async def test_imported_operations_go_too_so_a_reupload_is_not_a_duplicate(seeded_db):
    seeded_db.add(BankOperation(connection_id=1, fingerprint="abc", amount=-100,
                                occurred_on=date(2026, 1, 2)))
    await seeded_db.flush()

    await clean_slate(seeded_db)

    assert await seeded_db.scalar(select(func.count()).select_from(BankOperation)) == 0


@pytest.mark.asyncio
async def test_the_profile_keeps_the_person_and_drops_the_character(seeded_db):
    profile = (await seeded_db.execute(select(UserProfile))).scalars().first()
    profile.name, profile.monthly_income = "Кирилл", 220000
    profile.dreams = "Квартира у моря"
    await seeded_db.flush()

    await clean_slate(seeded_db)

    profile = (await seeded_db.execute(select(UserProfile))).scalars().first()
    assert profile.name == "Кирилл", "имя — про человека, а не про демонстрацию"
    assert profile.monthly_income == 0 and profile.dreams == ""


@pytest.mark.asyncio
async def test_an_empty_app_does_not_grade_a_person_it_knows_nothing_about(client, seeded_db):
    """«48 из 100, требует внимания» на пустой базе — вывод из ничего."""
    await clean_slate(seeded_db)
    await seeded_db.commit()

    health = (await client.get("/api/v1/dashboard")).json()["health"]

    assert health["known"] is False
    assert health["score"] == 0 and "не о чем судить" in health["label"]


@pytest.mark.asyncio
async def test_savings_rate_survives_a_profile_without_declared_income(client, seeded_db):
    """Сброс обнуляет доход в профиле, а норма сбережений делилась на него.

    В делителе оказывался один рубль, и загруженная выписка давала «норму
    сбережений 4 220 969%» — число, которое выглядит как поломка.
    """
    await clean_slate(seeded_db)
    await seeded_db.commit()
    await client.post("/api/v1/transactions", json={
        "amount": 52173, "description": "Заработная плата",
        "transaction_type": "income"})
    await client.post("/api/v1/transactions", json={
        "amount": -9800, "description": "Продукты"})

    health = (await client.get("/api/v1/dashboard")).json()["health"]
    savings = next(f for f in health["factors"] if f["name"] == "Сбережения")

    assert savings["explanation"] == "Норма сбережений: 81%."


@pytest.mark.asyncio
async def test_one_real_operation_is_enough_to_start_grading(client, seeded_db):
    await clean_slate(seeded_db)
    await seeded_db.commit()
    await client.post("/api/v1/transactions", json={
        "amount": -2500, "description": "Продукты"})

    health = (await client.get("/api/v1/dashboard")).json()["health"]

    assert health["known"] is True
