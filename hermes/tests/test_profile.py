"""Профиль владельца помещается в USER.md и попадает в системный промпт Hermes."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DELIMITER = "\n§\n"
USER_CHAR_LIMIT = 1375


def test_user_profile_fits_the_memory_budget():
    raw = (ROOT / "memories" / "USER.md").read_text(encoding="utf-8")
    entries = [entry.strip() for entry in raw.split(DELIMITER) if entry.strip()]
    assert raw.strip() == DELIMITER.join(entries)
    assert len(raw.strip()) <= USER_CHAR_LIMIT
    assert max(len(entry) for entry in entries) <= USER_CHAR_LIMIT
    text = "\n".join(entries)
    assert "Кирилл" in text
    assert "ITMS" in text and "NetAtlas" in text
    assert "не соглашайся со мной автоматически" in text.lower()
    assert "велосипед" in text and "вино" in text
    assert "delegate_task" in text and "Cursor" in text
