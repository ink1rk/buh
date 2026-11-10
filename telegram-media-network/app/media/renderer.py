from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

FONT_DIR = Path(__file__).resolve().parent / "fonts"
FONT_REGULAR = FONT_DIR / "DejaVuSans.ttf"
FONT_BOLD = FONT_DIR / "DejaVuSans-Bold.ttf"
MAX_PIXELS = 4_000_000
MAX_SIDE_SUM = 10000
MAX_BYTES = 8 * 1024 * 1024
CARD_W = 1280
CARD_H = 720


@dataclass
class ImageInspection:
    ok: bool
    reason: str = ""
    width: int = 0
    height: int = 0


@dataclass
class CardLayout:
    fits: bool
    lines: list[str] = field(default_factory=list)
    bottom: int = 0
    font_size: int = 0
    width: int = CARD_W
    height: int = CARD_H


@dataclass
class RenderedCard:
    jpeg: bytes
    layout: CardLayout
    sha256: str
    rights_basis: str
    width: int = CARD_W
    height: int = CARD_H

    @property
    def byte_size(self) -> int:
        return len(self.jpeg)


def hex_rgb(value: str) -> tuple[int, int, int]:
    raw = value.removeprefix("#")
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size=size)


def _glyph_ok(font: ImageFont.FreeTypeFont, char: str) -> bool:
    if char.isspace():
        return True
    bbox = font.getbbox(char)
    return bbox[2] - bbox[0] > 0


def filter_text(font: ImageFont.FreeTypeFont, text: str) -> str:
    return "".join(char for char in text if _glyph_ok(font, char))


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if font.getlength(trial) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def inspect_image(data: bytes) -> ImageInspection:
    if not data:
        return ImageInspection(False, "empty")
    if len(data) > MAX_BYTES:
        return ImageInspection(False, "too_large")
    prefix = data[:800].lower()
    if prefix.lstrip().startswith(b"<svg") or b"<script" in prefix or data[:4] == b"<svg":
        return ImageInspection(False, "svg_or_script")
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
    except (UnidentifiedImageError, OSError, ValueError):
        return ImageInspection(False, "malformed")
    if width <= 0 or height <= 0:
        return ImageInspection(False, "malformed")
    if width * height > MAX_PIXELS or width + height > MAX_SIDE_SUM:
        return ImageInspection(False, "dimensions")
    ratio = max(width / height, height / width)
    if ratio > 20:
        return ImageInspection(False, "aspect")
    return ImageInspection(True, width=width, height=height)


def render_card(
    *,
    channel_title: str,
    primary: str,
    accent: str,
    template: str,
    title: str,
    kicker: str,
    footer: str,
    cve: str = "",
    source_label: str = "",
) -> RenderedCard:
    background = hex_rgb(primary)
    accent_rgb = hex_rgb(accent)
    image = Image.new("RGB", (CARD_W, CARD_H), background)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 22, CARD_H), fill=accent_rgb)
    draw.rectangle((0, 0, CARD_W, 10), fill=accent_rgb)
    brand_font = _font(FONT_BOLD, 28)
    small_font = _font(FONT_REGULAR, 24)
    probe = _font(FONT_BOLD, 48)
    visible_title = filter_text(probe, title).strip()
    draw.text((64, 42), filter_text(brand_font, channel_title)[:40], font=brand_font, fill=accent_rgb)
    draw.text((980, 46), filter_text(small_font, "СВОЙ МАКЕТ"), font=small_font, fill=accent_rgb)
    kicker_text = kicker
    if template == "security":
        kicker_text = "ОБНОВЛЕНИЕ / УЯЗВИМОСТЬ"
    draw.text((64, 92), filter_text(small_font, kicker_text)[:48], font=small_font, fill=(232, 236, 241))
    y_start = 180
    if template == "security" and cve:
        cve_font = _font(FONT_BOLD, 54)
        draw.text((64, 140), filter_text(cve_font, cve)[:24], font=cve_font, fill=accent_rgb)
        y_start = 230
    font_size = 58
    lines: list[str] = []
    title_font = _font(FONT_BOLD, font_size)
    while font_size >= 28:
        title_font = _font(FONT_BOLD, font_size)
        lines = wrap_text(visible_title, title_font, 1100)
        block = len(lines) * (font_size + 10)
        if len(lines) <= 5 and y_start + block <= 560:
            break
        font_size -= 2
    y = y_start
    for line in lines:
        draw.text((64, y), line, font=title_font, fill=(255, 255, 255))
        y += font_size + 10
    footer_font = _font(FONT_REGULAR, 26)
    draw.line((64, 620, 1216, 620), fill=(255, 255, 255), width=2)
    footer_source = f"{footer} · {source_label}" if source_label else footer
    footer_text = filter_text(footer_font, footer_source)[:80]
    if template == "security":
        footer_text = filter_text(footer_font, "CVSS не добавляется, если его нет в источнике")
    draw.text((64, 648), footer_text, font=footer_font, fill=(236, 239, 244))
    bottom = y
    fits = bool(lines) and bottom <= 600 and all(title_font.getlength(line) <= 1120 for line in lines)
    drawn = " ".join(lines)
    fits = fits and drawn == visible_title
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85, optimize=True)
    payload = buffer.getvalue()
    layout = CardLayout(fits=fits, lines=lines, bottom=bottom, font_size=font_size)
    return RenderedCard(
        jpeg=payload,
        layout=layout,
        sha256=hashlib.sha256(payload).hexdigest(),
        rights_basis="own_typographic_template",
    )


def resolve_media(remote: bytes | None, rights_basis: str | None, allow_remote: bool, card: RenderedCard) -> tuple[RenderedCard, str]:
    if remote and allow_remote and rights_basis == "licensed_reuse":
        inspection = inspect_image(remote)
        if inspection.ok:
            digest = hashlib.sha256(remote).hexdigest()
            copied = RenderedCard(remote, card.layout, digest, "licensed_reuse", inspection.width, inspection.height)
            return copied, "licensed_reuse"
    return card, "own_typographic_template"
