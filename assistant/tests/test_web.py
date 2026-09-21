"""Web UI: сводка главного экрана, список подсказок и охрана доступа."""
import pytest

from core import pipeline, security
from domain import commitments as commitments_mod
from domain import contacts as contacts_mod

from test_pipeline import FakeTelegramProvider, core, incoming  # noqa: F401


class Request:
    """Столько от запроса, сколько смотрит охрана."""

    class URL:
        def __init__(self, path):
            self.path = path

    class Client:
        def __init__(self, host):
            self.host = host

    def __init__(self, path="/api/memory", host="192.168.1.50", headers=None,
                 cookies=None, query=None):
        self.url = Request.URL(path)
        self.client = Request.Client(host)
        self.headers = headers or {}
        self.cookies = cookies or {}
        self.query_params = query or {}


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setenv("ASSISTANT_WEB_TOKEN", "s3cret")
    return "s3cret"


# --- охрана доступа -------------------------------------------------------
def test_without_a_token_nothing_is_guarded(monkeypatch):
    monkeypatch.setenv("ASSISTANT_WEB_TOKEN", "")
    assert security.guard(Request()) is None
    assert security.mode()["auth"] == "open"
    assert security.mode()["warning"]


def test_a_stranger_without_the_token_is_refused(token):
    denied = security.guard(Request())
    assert denied is not None and denied.status_code == 401


def test_the_token_opens_the_door(token):
    assert security.guard(Request(headers={"x-assistant-token": token})) is None
    assert security.guard(Request(cookies={"assistant_token": token})) is None
    assert security.guard(Request(query={"token": token})) is None


def test_a_wrong_token_is_refused(token):
    assert security.guard(Request(headers={"x-assistant-token": "nope"})) is not None


def test_the_machine_itself_needs_no_token(token):
    """Бот и tg-user ходят по петле — им незачем хранить секрет."""
    for host in ("127.0.0.1", "::1"):
        assert security.guard(Request(host=host)) is None


def test_the_interface_shell_stays_open(token):
    """В статике данных нет: она сама спросит токен и проверит его."""
    for path in ("/", "/ui/", "/ui/app.js", "/openapi.json"):
        assert security.guard(Request(path=path)) is None


def test_data_paths_are_closed_even_when_the_shell_is_open(token):
    for path in ("/api/memory", "/api/contacts", "/chat", "/news"):
        assert security.guard(Request(path=path)) is not None


# --- сводка и подсказки ---------------------------------------------------
def test_overview_counts_what_needs_attention(core):  # noqa: F811
    contact = contacts_mod.upsert_from_telegram("991", "Иван")
    commitments_mod.create("прислать конфиг", direction="I_OWE",
                           counterparty_id=contact.id)
    commitments_mod.create("пришлёт договор", direction="THEY_OWE",
                           counterparty_id=contact.id)
    pipeline.ingest_incoming(core, incoming())

    from core.api import api_overview
    data = api_overview()

    assert data["attention"]["suggestions"] == 1
    assert data["attention"]["i_owe"] == 1
    assert data["attention"]["waiting"] == 1
    assert data["greeting"] and data["assistant"]
    assert [c["counterparty_name"] for c in data["i_owe"]] == ["Иван"]
    assert data["system"]["integrations"]


def test_overview_survives_an_empty_system(core):  # noqa: F811
    from core.api import api_overview
    data = api_overview()
    assert data["attention"] == {"suggestions": 0, "approvals": 0, "i_owe": 0,
                                 "waiting": 0, "overdue": 0}
    assert data["suggestions"] == [] and data["i_owe"] == []


def test_suggestions_list_shows_only_undecided(core):  # noqa: F811
    first = pipeline.ingest_incoming(core, {**incoming(), "message_id": "m-1"})
    second = pipeline.ingest_incoming(core, {**incoming(text="ещё вопрос"),
                                             "message_id": "m-2"})
    pipeline.ignore_suggestion(second["suggestion_id"])

    listed = pipeline.list_suggestions("NEW")
    assert [item["id"] for item in listed] == [first["suggestion_id"]]
    assert listed[0]["contact_name"] and listed[0]["options"]
