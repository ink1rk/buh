from __future__ import annotations

import hashlib
import html

CAPTION_HARD_LIMIT = 1024
CAPTION_SOFT_LIMIT = 900


def telegram_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def escape_text(text: str) -> str:
    return html.escape(text or "", quote=True)


def safe_links(links: list[str]) -> list[str]:
    kept: list[str] = []
    for link in links:
        if not link.startswith("https://"):
            continue
        if any(token in link.lower() for token in ("javascript:", "data:", "169.254.169.254", "127.0.0.1")):
            continue
        if link not in kept:
            kept.append(link)
    return kept[:3]


def build_caption(title: str, body: str, links: list[str], hashtags: list[str] | None = None) -> str:
    source = safe_links(links)
    lines = [title.strip(), "", body.strip()]
    if source:
        lines.extend(["", f"Источник: {source[0]}"])
    if hashtags:
        lines.extend(["", " ".join(hashtags[:3])])
    return "\n".join(lines).strip()


def validate_caption(caption: str, body: str | None = None) -> tuple[bool, str]:
    if "<script" in caption.lower():
        return False, "Подпись содержит HTML. Уберите разметку и оставьте обычный текст."
    length = telegram_length(caption)
    if length > CAPTION_HARD_LIMIT:
        return False, f"Подпись занимает {length} символов UTF-16. Сократите текст до {CAPTION_HARD_LIMIT}."
    if body is not None and telegram_length(body) > CAPTION_SOFT_LIMIT:
        return False, f"Текст заметки длиннее внутреннего лимита {CAPTION_SOFT_LIMIT}."
    return True, ""


def caption_hash(caption: str) -> str:
    return hashlib.sha256(caption.encode("utf-8")).hexdigest()


def preview_html(title: str, caption: str, image_name: str, alt_text: str) -> str:
    return (
        "<!doctype html><html lang=\"ru\"><head><meta charset=\"utf-8\">"
        "<title>Предпросмотр</title></head><body>"
        f"<h1>{escape_text(title)}</h1>"
        f"<img alt=\"{escape_text(alt_text)}\" src=\"{escape_text(image_name)}\" width=\"1280\" height=\"720\">"
        f"<pre>{escape_text(caption)}</pre>"
        "</body></html>"
    )
