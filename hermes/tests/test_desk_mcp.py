"""MCP стола говорит на initialize Hermes и не показывает пароль."""
import json
import os
from pathlib import Path

from phone.mcp import client_meta

from desk_mcp.envfile import load_env_file
from desk_mcp.servers import build


class Box:
    def __init__(self, account="yandex"):
        self.account = type("Account", (), {"name": account, "user": "kirill@yandex.ru",
                                             "password": "secret"})()

    def check(self):
        return True

    def list_folders(self):
        return ["INBOX", "Кирилл"]

    def recent(self, folder=None, limit=15):
        return {"account": self.account.name, "folder": folder or "INBOX", "letters": [
            {"name": "Анна", "address": "anna@example.com", "subject": "договор",
             "date": "Mon, 5 Oct 2026 10:00:00 +0300"}]}

    def frequent_senders(self, folder=None, sample=200):
        return {"account": self.account.name, "folder": folder or "INBOX", "sampled": 2,
                "senders": [{"address": "noreply@github.com", "name": "GitHub", "count": 6}]}

    def create_folder(self, name):
        return {"account": self.account.name, "folder": name, "created": True}

    def create_sender_folders(self, folder=None, sample=200, min_count=5, max_folders=10):
        return {"account": self.account.name, "folder": "INBOX", "sampled": 2,
                "min_count": min_count, "senders": [
                    {"address": "noreply@github.com", "name": "GitHub", "count": 6}],
                "created": [{"folder": "github.com", "address": "noreply@github.com",
                             "name": "GitHub", "count": 6}],
                "already": []}


def ask(server, method, params=None, version="2025-11-25"):
    body = {"jsonrpc": "2.0", "id": 1, "method": method,
            "params": {"_meta": client_meta(version), **(params or {})}}
    reply = server.handle(body, transport="stdio")
    assert reply.body.get("error") is None, reply.body
    return reply.body["result"]


def test_hermes_initialize_is_answered_in_its_version():
    server = build("yandex", mailbox_for=lambda name: Box(name))
    reply = server.handle(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                    "clientInfo": {"name": "hermes", "version": "1"}}},
        transport="stdio")
    result = reply.body["result"]
    assert result["protocolVersion"] == "2025-11-25"
    assert result["serverInfo"]["name"] == "desk-yandex"
    names = [item["name"] for item in ask(server, "tools/list")["tools"]]
    assert "yandex_create_sender_folders" in names
    assert "yandex_folders" in names


def test_create_sender_folders_is_a_write_and_hides_the_password():
    server = build("gmail", mailbox_for=lambda name: Box("gmail"))
    tools = {item["name"]: item for item in ask(server, "tools/list")["tools"]}
    assert tools["gmail_folders"]["annotations"]["readOnlyHint"] is True
    assert tools["gmail_create_sender_folders"]["annotations"]["readOnlyHint"] is False

    result = ask(server, "tools/call", {
        "name": "gmail_create_sender_folders", "arguments": {"min_count": 5}})
    blob = json.dumps(result, ensure_ascii=False)
    assert "github.com" in blob
    assert "secret" not in blob
    assert result["isError"] is False


def test_missing_mailbox_is_an_error_the_model_can_read():
    def missing(name):
        from phone.mcp import ToolError
        raise ToolError(f"ящик {name} не настроен")

    server = build("yandex", mailbox_for=missing)
    reply = server.handle(
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "yandex_folders", "arguments": {}}},
        transport="stdio")
    assert reply.body["result"]["isError"] is True
    assert "не настроен" in reply.body["result"]["content"][0]["text"]


def test_calendar_says_when_google_is_absent():
    server = build("calendar", calendar_clients=lambda: [])
    result = ask(server, "tools/call", {"name": "calendar_status", "arguments": {}})
    assert "Google" in result["content"][0]["text"]
    assert result["structuredContent"]["google"] is False


def test_notes_stay_inside_the_vault(tmp_path):
    from desk import cli
    import os
    os.environ["OBSIDIAN_VAULT_PATH"] = str(tmp_path)
    server = build("notes", notes=cli)
    result = ask(server, "tools/call", {"name": "notes_write", "arguments": {
        "title": "Встреча", "body": "взять выписку"}})
    path = Path(result["structuredContent"]["path"])
    assert path.is_relative_to(tmp_path)
    found = ask(server, "tools/call", {"name": "notes_search", "arguments": {
        "query": "выписку"}})
    assert found["structuredContent"]["hits"]


def test_env_file_does_not_override_or_echo(tmp_path, monkeypatch):
    secret = tmp_path / "assistant.env"
    secret.write_text("MAIL_YANDEX_PASSWORD=secret\nALREADY=from-file\n# comment\n",
                      encoding="utf-8")
    monkeypatch.setenv("ALREADY", "kept")
    monkeypatch.delenv("MAIL_YANDEX_PASSWORD", raising=False)
    assert load_env_file(str(secret)) == 1
    assert os.environ["ALREADY"] == "kept"
    assert os.environ["MAIL_YANDEX_PASSWORD"] == "secret"
    monkeypatch.delenv("MAIL_YANDEX_PASSWORD")


def test_voice_speaks_through_its_own_server():
    server = build("voice", voice=lambda text: {"ok": True, "path": "/tmp/x.mp3", "voice": text})
    result = ask(server, "tools/call", {"name": "voice_speak", "arguments": {"text": "привет"}})
    assert result["structuredContent"]["voice"] == "привет"


def test_telegram_tool_refuses_a_remote_host(monkeypatch):
    monkeypatch.setenv("TG_USER_URL", "http://example.com")
    server = build("telegram")
    reply = server.handle(
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
         "params": {"name": "telegram_unread", "arguments": {}}},
        transport="stdio")
    assert reply.body["result"]["isError"] is True
    assert "этой машине" in reply.body["result"]["content"][0]["text"]


def test_repo_config_registers_the_desk_servers_and_not_finance():
    text = Path(__file__).resolve().parents[1].joinpath("config.yaml").read_text(encoding="utf-8")
    assert "\nmcp_servers:\n" in text
    for name in ("yandex:", "gmail:", "calendar:", "notes:", "telegram:", "voice:", "phone:"):
        assert f"\n  {name}\n" in text
    assert '["-m", "desk_mcp", "yandex"]' in text
    assert '["-m", "phone", "--stdio"]' in text
    assert "app.mcp.server" not in text
    assert "url:" not in text.split("mcp_servers:", 1)[1]
