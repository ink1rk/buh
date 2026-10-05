"""Хранение доступа к банку: шифруется или не хранится вовсе.

Колонка называется `credentials_encrypted`, и одного её имени достаточно,
чтобы никто больше никогда не проверил, что там лежит. Поэтому проверяем.
"""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.core.security import EncryptionUnavailable, decrypt_text, encrypt_text
from app.models.connection import BankConnection
from app.services.bank_sync import store_credentials

TOKEN = "ozon-access-token-12345"


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setattr(get_settings(), "encryption_key", "unit-test-key")


def test_a_token_does_not_survive_in_readable_form(key):
    connection = BankConnection(provider="ozon", label="Ozon Банк", mode="api")

    store_credentials(connection, TOKEN)

    assert TOKEN not in connection.credentials_encrypted
    assert decrypt_text(connection.credentials_encrypted) == TOKEN


def test_without_a_key_the_token_is_refused_rather_than_stored(monkeypatch):
    """Тихая запись открытым текстом хуже отказа: её никто не заметит."""
    monkeypatch.setattr(get_settings(), "encryption_key", "")
    connection = BankConnection(provider="ozon", label="Ozon Банк", mode="api")

    with pytest.raises(EncryptionUnavailable):
        store_credentials(connection, TOKEN)

    assert not connection.credentials_encrypted


def test_an_empty_token_clears_the_field_without_needing_a_key(monkeypatch):
    """Подключение по выписке доступа не требует, и ключа ему знать незачем."""
    monkeypatch.setattr(get_settings(), "encryption_key", "")
    connection = BankConnection(provider="ozon", label="Ozon Банк", mode="statement")

    store_credentials(connection, "")

    assert connection.credentials_encrypted == ""


def test_the_same_secret_encrypts_differently_each_time(key):
    """Fernet солит каждый раз: одинаковые шифртексты выдавали бы повтор."""
    assert encrypt_text(TOKEN) != encrypt_text(TOKEN)


async def test_the_api_refuses_a_token_it_cannot_protect(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "encryption_key", "")

    answer = await client.post("/api/v1/connections", json={
        "provider": "ozon", "label": "Ozon Банк", "mode": "api",
        "access_token": TOKEN})

    assert answer.status_code == 400
    assert "ENCRYPTION_KEY" in answer.json()["detail"]
