import re

from mcp_common.errors import IntegrationError

_EMAIL = re.compile(r"^[^@\s<>\"']+@[^@\s<>\"']+\.[^@\s<>\"']+$")
_GUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def clamp_limit(value: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise IntegrationError("limit должен быть целым числом") from exc
    if number < 1:
        raise IntegrationError("limit должен быть больше 0")
    return min(number, maximum)


def mailbox(value: str) -> str:
    text = value.strip()
    if _GUID.fullmatch(text):
        return text
    if not text or len(text) > 320 or not _EMAIL.fullmatch(text):
        raise IntegrationError("Нужен email ящика или GUID пользователя")
    return text


def plain_text(value: str, field: str, maximum: int) -> str:
    text = value.strip()
    if not text:
        raise IntegrationError(f"Пустое поле {field}")
    if len(text) > maximum:
        raise IntegrationError(f"{field} длиннее {maximum} символов")
    if any(ord(ch) < 32 and ch not in "\n\r\t" for ch in text):
        raise IntegrationError(f"Некорректное поле {field}")
    return text
