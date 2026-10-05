"""Команды, которыми Hermes пользуется вместо самописного ядра.

Почта и календарь уже живут в ассистенте, финансы — в своём API, заметки —
в vault Obsidian. Здесь только узкий вызов: JSON на stdout, без догадок.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def vault_path() -> Path:
    raw = os.environ.get("OBSIDIAN_VAULT_PATH", "").strip()
    return Path(raw).expanduser() if raw else ROOT / "vault"


def _get(url: str, timeout: float = 20) -> dict | list:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def _assistant(path: str) -> dict | list:
    base = os.environ.get("ASSISTANT_URL", "http://127.0.0.1:8800").rstrip("/")
    return _get(f"{base}{path}")


def _tg(path: str) -> dict | list:
    base = os.environ.get("TG_USER_URL", "http://127.0.0.1:8810").rstrip("/")
    return _get(f"{base}{path}")


def modules() -> dict:
    return {
        "modules": [
            {"name": "mail", "via": "assistant /api/mail"},
            {"name": "calendar", "via": "assistant /api/calendar"},
            {"name": "obsidian", "via": str(vault_path())},
            {"name": "browser", "via": "hermes toolset browser"},
            {"name": "telegram", "via": "hermes gateway + tg-user"},
            {"name": "voice", "via": "edge"},
        ]
    }


def mail() -> dict:
    status = _assistant("/api/mail")
    return status if isinstance(status, dict) else {"mail": status}


def calendar(days: int = 14) -> dict:
    data = _assistant(f"/api/calendar?days={days}")
    return data if isinstance(data, dict) else {"events": data}


def telegram_unread() -> dict:
    data = _tg("/unread")
    return data if isinstance(data, dict) else {"unread": data}


def _slug(title: str) -> str:
    cleaned = re.sub(r"[^\w\-]+", "-", title.strip(), flags=re.UNICODE)
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    return (cleaned or "заметка")[:80]


def write_note(title: str, body: str, folder: str = "00 Inbox") -> dict:
    """Заметка только внутрь vault. Путь из заголовка наружу не выходит."""
    vault = vault_path().resolve()
    inbox = (vault / folder).resolve()
    if vault not in inbox.parents and inbox != vault:
        raise ValueError("папка заметки вне vault")
    inbox.mkdir(parents=True, exist_ok=True)
    day = datetime.date.today().isoformat()
    path = (inbox / f"{day}-{_slug(title)}.md").resolve()
    if vault not in path.parents:
        raise ValueError("заметка вне vault")
    text = f"---\ntitle: {title.strip()}\ndate: {day}\n---\n\n{body.strip()}\n"
    path.write_text(text, encoding="utf-8")
    return {"path": str(path), "title": title.strip()}


def search_notes(query: str, limit: int = 20) -> dict:
    needle = query.strip().lower()
    vault = vault_path()
    hits = []
    if needle and vault.exists():
        for path in vault.rglob("*.md"):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if needle in text.lower() or needle in path.name.lower():
                hits.append(str(path.relative_to(vault)))
            if len(hits) >= limit:
                break
    return {"query": query, "hits": hits}


def speak(text: str) -> dict:
    """Озвучка через Edge TTS. Ключ не нужен."""
    phrase = text.strip()
    if not phrase:
        return {"ok": False, "error": "пустой текст"}
    voice = os.environ.get("EDGE_TTS_VOICE", "ru-RU-DmitryNeural").strip() or "ru-RU-DmitryNeural"
    out = Path(os.environ.get("VOICE_OUT", "/tmp/hermes-voice.mp3"))
    try:
        import asyncio
        import edge_tts
    except ImportError:
        return {"ok": False, "error": "нет пакета edge-tts"}

    async def _save() -> None:
        await edge_tts.Communicate(phrase, voice).save(str(out))

    try:
        asyncio.run(_save())
    except Exception as exc:
        return {"ok": False, "error": f"edge {type(exc).__name__}"}
    if not out.is_file() or out.stat().st_size == 0:
        return {"ok": False, "error": "edge не записал звук"}
    return {"ok": True, "path": str(out), "bytes": out.stat().st_size, "voice": voice}


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    command = args[0] if args else "modules"
    try:
        if command == "modules":
            result = modules()
        elif command == "mail":
            result = mail()
        elif command == "calendar":
            days = int(args[1]) if len(args) > 1 else 14
            result = calendar(days)
        elif command == "note":
            if len(args) < 3:
                result = {"ok": False, "error": "нужны заголовок и текст"}
            else:
                result = write_note(args[1], args[2], args[3] if len(args) > 3 else "00 Inbox")
        elif command == "search":
            result = search_notes(args[1] if len(args) > 1 else "")
        elif command == "voice":
            result = speak(" ".join(args[1:]))
        elif command == "telegram":
            result = telegram_unread()
        else:
            result = {"ok": False, "error": f"неизвестная команда {command}", **modules()}
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 2
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
