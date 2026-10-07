"""Профиль Hermes говорит с владельцем по-русски, в том числе в меню Telegram."""
from pathlib import Path


def test_menu_language_is_russian():
    text = Path(__file__).resolve().parents[1].joinpath("config.yaml").read_text(encoding="utf-8")
    assert "\ndisplay:\n  language: ru\n" in text


def test_everyday_model_is_grok_and_tools_stay_on_hermes():
    text = Path(__file__).resolve().parents[1].joinpath("config.yaml").read_text(encoding="utf-8")
    assert "default: cursor-grok-4.6-high-fast\n" in text
    assert "context_length: 65536\n" in text
    assert "streaming: false\n" in text
    assert "base_url: http://127.0.0.1:8791/v1\n" in text
    assert "xavier.lan" not in text
    assert "delegation:\n" in text
    assert "model: cursor-grok-4.6-high-fast\n" in text
