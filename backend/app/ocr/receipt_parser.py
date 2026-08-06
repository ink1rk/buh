"""Receipt OCR — Vision API when available, heuristic fallback for demos."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.core.config import get_settings
from app.schemas.ai import OCRResult

logger = logging.getLogger(__name__)


async def parse_receipt_bytes(data: bytes, filename: str = "receipt.jpg") -> OCRResult:
    settings = get_settings()
    if settings.openai_api_key:
        try:
            return await _vision_parse(data, filename)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Vision OCR failed: %s", exc)

    # Demo / offline fallback — extract numbers from filename hints or return template
    text = filename.lower()
    total = None
    m = re.search(r"(\d{3,7})", text)
    if m:
        total = float(m.group(1))

    return OCRResult(
        date=None,
        merchant="Неизвестный магазин",
        total=total,
        items=[
            {"name": "Позиция (уточните)", "price": total or 0, "category": "other"},
        ],
        vat=None,
        discounts=None,
        payment_method=None,
        confidence=0.35,
        needs_confirmation=True,
        conflicts=["Не удалось уверенно распознать чек. Проверьте сумму и магазин."],
        raw_text="OCR offline mode — подключите OPENAI_API_KEY для Vision.",
    )


async def _vision_parse(data: bytes, filename: str) -> OCRResult:
    import base64
    import json

    from openai import AsyncOpenAI

    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
    b64 = base64.b64encode(data).decode()
    ext = filename.rsplit(".", 1)[-1].lower()
    mime = "application/pdf" if ext == "pdf" else f"image/{'jpeg' if ext in ('jpg', 'jpeg') else ext}"

    prompt = (
        "Извлеки данные чека в JSON: date, merchant, total, items[{name,price,category}], "
        "vat, discounts, payment_method, confidence(0-1). Только JSON."
    )
    resp = await client.chat.completions.create(
        model=settings.vision_model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                ],
            }
        ],
        max_tokens=1000,
    )
    raw = resp.choices[0].message.content or "{}"
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    payload: dict[str, Any] = json.loads(raw)
    confidence = float(payload.get("confidence") or 0.7)
    conflicts = []
    if confidence < 0.6:
        conflicts.append("Низкая уверенность распознавания — подтвердите данные.")

    return OCRResult(
        date=payload.get("date"),
        merchant=payload.get("merchant"),
        total=payload.get("total"),
        items=payload.get("items") or [],
        vat=payload.get("vat"),
        discounts=payload.get("discounts"),
        payment_method=payload.get("payment_method"),
        confidence=confidence,
        needs_confirmation=bool(conflicts) or confidence < 0.75,
        conflicts=conflicts,
        raw_text=raw,
    )
