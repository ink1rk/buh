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


def test_voice_uses_edge_without_a_key(monkeypatch, tmp_path):
    import sys
    import types

    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    out = tmp_path / "voice.mp3"
    monkeypatch.setenv("VOICE_OUT", str(out))
    seen = {}

    class _Communicate:
        def __init__(self, text, voice):
            seen["text"] = text
            seen["voice"] = voice

        async def save(self, path):
            Path(path).write_bytes(b"audio")

    monkeypatch.setitem(sys.modules, "edge_tts", types.SimpleNamespace(Communicate=_Communicate))
    result = cli.speak("привет")
    assert result["ok"] is True
    assert result["voice"] == "ru-RU-DmitryNeural"
    assert seen == {"text": "привет", "voice": "ru-RU-DmitryNeural"}
    assert out.read_bytes() == b"audio"


def test_cli_prints_json(capsys):
    assert cli.main(["modules"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["modules"]
