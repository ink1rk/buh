"""Профиль Hermes говорит с владельцем по-русски, в том числе в меню Telegram."""
from pathlib import Path


def test_menu_language_is_russian():
    text = Path(__file__).resolve().parents[1].joinpath("config.yaml").read_text(encoding="utf-8")
    assert "\ndisplay:\n  language: ru\n" in text
