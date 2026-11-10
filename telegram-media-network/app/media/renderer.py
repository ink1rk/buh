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
    overflow: str = ""


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


def fit_headline(text: str, max_width: int, max_lines: int, max_size: int = 46, min_size: int = 22) -> tuple[list[str], int, bool, str]:
    visible = filter_text(_font(FONT_BOLD, max_size), text).strip()
    size = max_size
    while size >= min_size:
        font = _font(FONT_BOLD, size)
        lines = wrap_text(visible, font, max_width)
        drawn = " ".join(lines)
        if len(lines) <= max_lines and drawn == visible:
            return lines, size, True, ""
        size -= 2
    font = _font(FONT_BOLD, min_size)
    lines = wrap_text(visible, font, max_width)
    if len(lines) <= max_lines and " ".join(lines) == visible:
        return lines, min_size, True, ""
    clipped = lines[:max_lines]
    return clipped, min_size, False, "headline_overflow"


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


def choose_rights(remote: bytes | None, rights_basis: str | None, allow_remote: bool, card: RenderedCard) -> tuple[RenderedCard, str]:
    """Unknown or forbidden remote art never replaces the house layout."""
    if rights_basis in {None, "", "unknown", "no_reuse"}:
        return card, "own_typographic_template"
    return resolve_media(remote, rights_basis, allow_remote, card)


def render_network_card(
    *,
    channel_id: str,
    channel_title: str,
    primary: str,
    accent: str,
    template_id: str,
    title: str,
    subtitle: str = "",
    source_label: str = "",
    cve: str = "",
    digest_lines: list[str] | None = None,
    demo: bool = True,
) -> RenderedCard:
    """Five house layouts. They are covers, not screenshots and not paragraphs."""
    template_id = {"hero": "lead", "advisory": "security"}.get(template_id, template_id)
    background = hex_rgb(primary)
    accent_rgb = hex_rgb(accent)
    image = Image.new("RGB", (CARD_W, CARD_H), background)
    draw = ImageDraw.Draw(image)
    if template_id == "deep-dive":
        draw.rectangle((0, 0, 420, CARD_H), fill=_mix(background, accent_rgb))
    _motif(draw, channel_id, accent_rgb)
    brand = _font(FONT_BOLD, 28)
    small = _font(FONT_REGULAR, 22)
    draw.text((64, 36), filter_text(brand, channel_title)[:32], font=brand, fill=(255, 255, 255))
    label = {
        "lead": "НОВОСТЬ",
        "hero": "НОВОСТЬ",
        "tool": "ИНСТРУМЕНТ",
        "security": "ЗАПИСЬ",
        "advisory": "ЗАПИСЬ",
        "digest": "ПОДБОРКА",
        "deep-dive": "РАЗБОР",
        "review": "ОБЗОР",
    }.get(template_id, "МАТЕРИАЛ")
    draw.text((64, 78), label, font=small, fill=(236, 239, 244))
    if demo:
        draw.text((1040, 36), "DEMO", font=small, fill=accent_rgb)
    draw.text((1040, 68), "СВОЙ МАКЕТ", font=_font(FONT_REGULAR, 16), fill=(220, 224, 230))
    max_width = 760 if template_id == "tool" else 1100
    lines, font_size, fits_title, overflow = fit_headline(title, max_width, 2)
    title_font = _font(FONT_BOLD, font_size)
    y = 150
    if template_id in {"advisory", "security"} and cve:
        draw.rounded_rectangle((64, 140, 640, 210), radius=8, outline=accent_rgb, width=3)
        draw.text((80, 152), filter_text(_font(FONT_BOLD, 32), cve)[:28], font=_font(FONT_BOLD, 32), fill=accent_rgb)
        y = 230
    if template_id == "tool":
        draw.rectangle((860, 150, 1216, 520), fill=_mix(background, accent_rgb))
        for box in ((900, 190), (980, 280), (900, 370)):
            draw.rectangle((box[0], box[1], box[0] + 160, box[1] + 48), outline=accent_rgb, width=3)
        draw.text((900, 470), "схема, не скриншот", font=small, fill=(255, 255, 255))
    if template_id in {"hero", "lead"}:
        draw.ellipse((980, 160, 1220, 400), outline=accent_rgb, width=8)
        draw.ellipse((1040, 220, 1160, 340), fill=accent_rgb)
    if template_id == "review":
        draw.rectangle((64, 430, 620, 600), outline=accent_rgb, width=3)
        draw.rectangle((660, 430, 1216, 600), outline=accent_rgb, width=3)
        draw.text((84, 450), "источник", font=small, fill=accent_rgb)
        draw.text((680, 450), "ограничение", font=small, fill=accent_rgb)
        draw.text((84, 500), filter_text(small, subtitle or "факт из карточки")[:28], font=small, fill=(255, 255, 255))
        draw.text((680, 500), "не подтверждено источником", font=small, fill=(255, 255, 255))
    if template_id == "digest":
        y = 150
        lines = []
        source_items = digest_lines or [title]
        for index, item in enumerate(source_items[:5]):
            top = 150 + index * 90
            draw.rectangle((64, top, 1216, top + 72), outline=accent_rgb, width=2)
            snippet = filter_text(small, item)[:70]
            draw.text((84, top + 22), snippet, font=small, fill=(255, 255, 255))
        bottom = 150 + min(5, len(source_items)) * 90
        payload = _save(image)
        items = digest_lines or [filter_text(small, title).strip()]
        overflow = "" if items else "headline_overflow"
        layout = CardLayout(fits=not overflow, lines=items, bottom=bottom, font_size=22, overflow=overflow)
        return RenderedCard(payload, layout, hashlib.sha256(payload).hexdigest(), "own_typographic_template")
    if template_id == "deep-dive":
        facts = (digest_lines or [subtitle or "факт из источника", "ограничение не выдумано", "ссылка обязательна"])[:3]
        for index, item in enumerate(facts):
            top = 430 + index * 48
            draw.ellipse((64, top + 8, 80, top + 24), fill=accent_rgb)
            draw.text((96, top), filter_text(small, item)[:42], font=small, fill=(255, 255, 255))
    for line in lines:
        draw.text((64, y), line, font=title_font, fill=(255, 255, 255))
        y += 58
    if subtitle:
        draw.text((64, min(y + 8, 520)), filter_text(small, subtitle)[:80], font=small, fill=(230, 234, 238))
    draw.line((64, 620, 1216, 620), fill=(255, 255, 255), width=2)
    footer = source_label or channel_title
    if template_id in {"advisory", "security"}:
        footer = "CVSS нет в источнике" if not source_label else source_label
    draw.text((64, 648), filter_text(small, footer)[:80], font=small, fill=(236, 239, 244))
    if overflow:
        draw.text((64, 580), "заголовок не поместился", font=small, fill=(255, 180, 160))
    payload = _save(image)
    fits = bool(lines) and fits_title and not overflow
    layout = CardLayout(fits=fits, lines=lines, bottom=y, font_size=font_size, overflow=overflow)
    return RenderedCard(payload, layout, hashlib.sha256(payload).hexdigest(), "own_typographic_template")


def _save(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85, optimize=True)
    return buffer.getvalue()


def _mix(base: tuple[int, int, int], accent: tuple[int, int, int]) -> tuple[int, int, int]:
    mixed = [int(base[index] * 0.72 + accent[index] * 0.28) for index in range(3)]
    return mixed[0], mixed[1], mixed[2]


def _motif(draw: ImageDraw.ImageDraw, channel_id: str, accent: tuple[int, int, int]) -> None:
    if channel_id == "ai_news":
        draw.polygon([(0, 0), (420, 0), (300, 120), (0, 120)], fill=accent)
    elif channel_id == "ai_tools":
        for left in (40, 110, 180):
            draw.rounded_rectangle((left, 18, left + 52, 70), radius=12, outline=accent, width=3)
    elif channel_id == "github":
        draw.line((24, 24, 24, 110), fill=accent, width=4)
        draw.line((24, 24, 110, 24), fill=accent, width=4)
        draw.line((1180, 24, 1256, 24), fill=accent, width=4)
        draw.line((1256, 24, 1256, 110), fill=accent, width=4)
    elif channel_id == "cyber":
        for top in (16, 36, 56):
            draw.line((0, top, 1280, top), fill=accent, width=2)
    elif channel_id == "infra":
        for x in range(20, 300, 28):
            for y in range(16, 100, 28):
                draw.ellipse((x, y, x + 8, y + 8), fill=accent)
    elif channel_id == "homelab":
        draw.polygon([(1080, 100), (1150, 40), (1220, 100)], outline=accent)
        draw.rectangle((1100, 100, 1200, 140), outline=accent, width=3)
    elif channel_id == "dev":
        draw.rectangle((0, 0, 18, CARD_H), fill=accent)
    else:
        draw.arc((1080, -40, 1320, 200), 20, 200, fill=accent, width=10)


NETWORK_TEMPLATES = ("lead", "tool", "security", "digest", "deep-dive")
STUDIO_PURPOSES = ("news", "review", "tool", "security", "digest", "deep-dive")
RATIOS = {"16:9": (1280, 720), "1:1": (1080, 1080), "4:5": (1080, 1350)}
PURPOSE_TO_TEMPLATE = {
    "news": "lead",
    "review": "review",
    "tool": "tool",
    "security": "security",
    "digest": "digest",
    "deep-dive": "deep-dive",
}


def write_studio_pack(directory: Path, channels: list) -> list[Path]:
    """40 house covers: eight brands by five layouts. Files are local JPEGs, not fetched art."""
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for channel in channels:
        theme = getattr(channel, "theme_json", None) or {}
        for template_id in NETWORK_TEMPLATES:
            digest = (
                [f"DEMO: пункт {index} · {channel.title}" for index in range(1, 4)]
                if template_id in {"digest", "deep-dive"}
                else None
            )
            card = render_network_card(
                channel_id=channel.id,
                channel_title=channel.title,
                primary=str(theme.get("primary") or "#1c2434"),
                accent=str(theme.get("accent") or "#d7e2ea"),
                template_id=template_id,
                title=f"DEMO: {channel.title}",
                subtitle="учебный макет",
                source_label="example.com/demo",
                cve="CVE-2026-990099" if template_id == "security" and channel.id == "cyber" else "",
                digest_lines=digest,
                demo=True,
            )
            path = directory / f"{channel.id}-{template_id}.jpg"
            path.write_bytes(card.jpeg)
            written.append(path)
    return written


def render_studio_card(
    *,
    channel_id: str,
    channel_title: str,
    primary: str,
    accent: str,
    purpose: str,
    title: str,
    ratio: str = "16:9",
    theme: str = "dark",
    subtitle: str = "",
    source_label: str = "",
    cve: str = "",
    digest_lines: list[str] | None = None,
    demo: bool = True,
) -> RenderedCard:
    """One layout engine. Ratio only changes canvas; composition stays the purpose."""
    width, height = RATIOS.get(ratio, (CARD_W, CARD_H))
    template_id = PURPOSE_TO_TEMPLATE.get(purpose, purpose)
    card = render_network_card(
        channel_id=channel_id,
        channel_title=channel_title,
        primary="#f4f1ea" if theme == "light" else primary,
        accent=accent,
        template_id=template_id,
        title=title,
        subtitle=subtitle,
        source_label=source_label,
        cve=cve,
        digest_lines=digest_lines,
        demo=demo,
    )
    if (width, height) == (CARD_W, CARD_H):
        return card
    with Image.open(io.BytesIO(card.jpeg)) as image:
        scaled = image.resize((width, height))
        payload = _save(scaled)
    layout = CardLayout(
        fits=card.layout.fits,
        lines=card.layout.lines,
        bottom=int(card.layout.bottom * height / CARD_H),
        font_size=card.layout.font_size,
        width=width,
        height=height,
        overflow=card.layout.overflow,
    )
    return RenderedCard(payload, layout, hashlib.sha256(payload).hexdigest(), "own_typographic_template", width, height)


def write_studio_pack_v3(directory: Path, channels: list) -> list[Path]:
    """48 distinct 16:9 covers: eight brands by six purposes."""
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    titles = {
        "news": "DEMO: короткое событие без выдуманных цифр",
        "review": "DEMO: разбор ограничений по первоисточнику",
        "tool": "DEMO: сценарий применения и чего нет в карточке",
        "security": "DEMO: учебная запись каталога, не сводка",
        "digest": "DEMO: три независимых пункта подборки",
        "deep-dive": "DEMO: метод, неизвестное, ссылка на источник",
    }
    for channel in channels:
        theme = getattr(channel, "theme_json", None) or {}
        for purpose in STUDIO_PURPOSES:
            digest = [f"DEMO: {channel.title} пункт {index}" for index in range(1, 4)] if purpose in {"digest", "deep-dive"} else None
            card = render_studio_card(
                channel_id=channel.id,
                channel_title=channel.title,
                primary=str(theme.get("primary") or "#1c2434"),
                accent=str(theme.get("accent") or "#d7e2ea"),
                purpose=purpose,
                title=titles[purpose],
                subtitle=f"{channel.title} · {purpose}",
                source_label="example.com/demo",
                cve="CVE-2026-990099" if purpose == "security" and channel.id == "cyber" else "",
                digest_lines=digest,
                demo=True,
            )
            path = directory / f"{channel.id}-{purpose}.jpg"
            path.write_bytes(card.jpeg)
            written.append(path)
    return written


def resolve_media(remote: bytes | None, rights_basis: str | None, allow_remote: bool, card: RenderedCard) -> tuple[RenderedCard, str]:
    if remote and allow_remote and rights_basis == "licensed_reuse":
        inspection = inspect_image(remote)
        if inspection.ok:
            digest = hashlib.sha256(remote).hexdigest()
            copied = RenderedCard(remote, card.layout, digest, "licensed_reuse", inspection.width, inspection.height)
            return copied, "licensed_reuse"
    return card, "own_typographic_template"
