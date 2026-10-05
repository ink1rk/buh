"""Модули стола отвечают JSON и не пишут заметки мимо vault."""
import json
from pathlib import Path

import pytest

from desk import cli


def test_modules_lists_the_desk():
    names = [item["name"] for item in cli.modules()["modules"]]
    assert names == ["mail", "calendar", "obsidian", "browser", "telegram", "voice"]


def test_note_lands_in_the_inbox(tmp_path, monkeypatch):
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path))
    saved = cli.write_note("Встреча с банком", "взять выписку")
    path = Path(saved["path"])
    assert path.parent == tmp_path / "00 Inbox"
    assert "взять выписку" in path.read_text(encoding="utf-8")
    found = cli.search_notes("выписку")
    assert found["hits"]


def test_a_note_title_cannot_leave_the_vault(tmp_path, monkeypatch):
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path))
    saved = cli.write_note("../../etc/passwd", "нет")
    assert Path(saved["path"]).is_relative_to(tmp_path)


def test_mail_reads_the_assistant(monkeypatch):
    monkeypatch.setattr(cli, "_assistant", lambda path: {"accounts": ["a"], "path": path})
    assert cli.mail()["path"] == "/api/mail"


def test_voice_without_a_key_does_not_call_the_network(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_VOICE_ID", raising=False)

    def boom(*_a, **_k):
        raise AssertionError("сеть не нужна")

    monkeypatch.setattr(cli.urllib.request, "urlopen", boom)
    result = cli.speak("привет")
    assert result["ok"] is False


def test_cli_prints_json(capsys):
    assert cli.main(["modules"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["modules"]
