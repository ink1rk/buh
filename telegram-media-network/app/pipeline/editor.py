from __future__ import annotations

import hashlib
import re

from app.pipeline.rank import LICENSE_CLAIM_RE
from app.pipeline.types import DraftResult, Fact, SourceItemIn

INJECTION_RE = re.compile(
    r"ignore\s+(all\s+|any\s+)?(previous|prior)\s+instructions"
    r"|you\s+are\s+now"
    r"|telegram_bot_token"
    r"|system\s+prompt"
    r"|publish\s*:\s*true"
    r"|disregard\s+(all\s+)?previous",
    re.I,
)
ATTACK_RE = re.compile(
    r"attack\s+instructions"
    r"|proof[- ]of[- ]concept"
    r"|\bpayload\b"
    r"|reverse\s+shell"
    r"|\bmetasploit\b"
    r"|shellcode"
    r"|шелл[- ]код"
    r"|инструкци[яи]\s+по\s+эксплуатац"
    r"|эксплойт",
    re.I,
)
BENCHMARK_RE = re.compile(
    r"превосходит|outperform|beats\s+gpt|\bsota\b|state-of-the-art|бенчмарк|benchmark|gpt-\d|\bclaude\b",
    re.I,
)
EXTRAORDINARY_RE = re.compile(r"доказал[иа]?|прорыв|agi\s+достиг|квантовое\s+превосходство", re.I)
TOKEN_RE = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{20,}\b|\bgh[pousr]_[A-Za-z0-9]{20,}\b|\bsk-[A-Za-z0-9]{10,}\b")

CHANNEL_AUDIENCE = {
    "ai_news": "тем, кто следит за релизами моделей и отделяет анонс от проверенного результата.",
    "ai_tools": "тем, кто выбирает прикладной инструмент и хочет понять ограничения до установки.",
    "github": "тем, кто ищет конкретный репозиторий с понятным назначением и проверяемой лицензией.",
    "cyber": "администраторам, которым нужно сверить продукт и применить защитную рекомендацию источника.",
    "infra": "инженерам эксплуатации, которые оценивают применимость изменения, а не только факт релиза.",
    "homelab": "тем, кто собирает домашнюю лабораторию и сверяет требования до изменений на своём стенде.",
    "dev": "разработчикам, которым важны версия, сценарий и совместимость инструмента.",
    "future": "читателям, которые хотят понять статус исследования без маркетинговых выводов.",
}
HASHTAGS = {
    "ai_news": ["#нейросети", "#модели"],
    "ai_tools": ["#ai", "#инструменты"],
    "github": ["#github"],
    "cyber": ["#безопасность", "#патч"],
    "infra": ["#инфраструктура", "#linux"],
    "homelab": ["#homelab", "#selfhosted"],
    "dev": ["#devtools", "#разработка"],
    "future": ["#наука", "#технологии"],
}
CHANNEL_TEMPLATE = {
    "ai_news": "news",
    "ai_tools": "tool",
    "github": "tool",
    "cyber": "security",
    "infra": "news",
    "homelab": "tool",
    "dev": "tool",
    "future": "news",
}


def contains_attack(text: str) -> bool:
    return bool(ATTACK_RE.search(text or ""))


def contains_injection(text: str) -> bool:
    return bool(INJECTION_RE.search(text or ""))


def _fact_problem(fact: Fact, item: SourceItemIn) -> str | None:
    blob = f"{fact.statement}\n{fact.evidence_excerpt}"
    if TOKEN_RE.search(blob):
        return "secret_material"
    if contains_injection(blob):
        return "prompt_injection"
    if contains_attack(blob):
        return "attack_instructions"
    if BENCHMARK_RE.search(blob):
        return "unsupported_benchmark"
    if item.license_state != "explicit_open_source" and LICENSE_CLAIM_RE.search(blob):
        return "unsupported_license"
    return None


def safe_facts(item: SourceItemIn) -> tuple[list[Fact], list[str]]:
    kept: list[Fact] = []
    warnings: list[str] = []
    for fact in item.facts:
        problem = _fact_problem(fact, item)
        if problem:
            warnings.append(problem)
            continue
        statement = fact.statement.strip()
        if EXTRAORDINARY_RE.search(statement):
            warnings.append("extraordinary_claim_removed")
            statement = EXTRAORDINARY_RE.sub("", statement).strip(" .;-")
            if len(statement) < 3:
                continue
        kept.append(
            Fact(
                id=fact.id,
                statement=statement[:400],
                evidence_url=fact.evidence_url,
                evidence_excerpt=fact.evidence_excerpt[:160],
            )
        )
    return kept, list(dict.fromkeys(warnings))


def post_type_for(item: SourceItemIn, channel_id: str) -> str:
    if item.cve_id or item.content_kind == "advisory" or CHANNEL_TEMPLATE.get(channel_id) == "security":
        return "security"
    if CHANNEL_TEMPLATE.get(channel_id) == "tool" or item.content_kind in {"repo", "release", "package"}:
        return "tool"
    return "news"


def _title(item: SourceItemIn) -> str:
    title = TOKEN_RE.sub("", item.title).strip()
    if contains_injection(title) or contains_attack(title) or BENCHMARK_RE.search(title):
        title = "Технический материал"
    title = re.sub(r"\s+", " ", title)
    if len(title) < 10:
        title = f"{title} — заметка редакции".strip()
    return title[:100]


_LEADS = (
    "Суть по первоисточнику:",
    "Что можно проверить по ссылке:",
    "Редакция оставляет только подтверждаемое:",
    "Практический смысл материала:",
)


def _body(item: SourceItemIn, facts: list[Fact], channel_id: str) -> str:
    fact_text = " ".join(fact.statement.strip().rstrip(".") + "." for fact in facts)
    lead = _LEADS[int(hashlib.sha256(item.source_external_id.encode()).hexdigest(), 16) % len(_LEADS)]
    limits: list[str] = []
    if item.is_preprint:
        limits.append("Это препринт: текст не выдаёт результат за рецензированный или доказанный вывод.")
    if item.license_state == "unknown":
        limits.append("Лицензия в источнике не указана, поэтому редакция не делает вывод о праве на повторное использование.")
    elif item.license_state == "explicit_open_source" and item.license_spdx:
        limits.append(f"В первоисточнике указана лицензия {item.license_spdx}.")
    if item.content_kind == "advisory" or item.cve_id:
        limits.append("Здесь только защитная формулировка источника, без инструкций по эксплуатации.")
    if EXTRAORDINARY_RE.search(item.untrusted_text or ""):
        limits.append("Громкая формулировка источника в текст не перенесена.")
    if not limits:
        limits.append("В текст вошли только утверждения, для которых есть переданные доказательства.")
    audience = CHANNEL_AUDIENCE.get(channel_id, CHANNEL_AUDIENCE["dev"])
    body = f"{lead} {fact_text} Кому полезно: {audience} Ограничения: {' '.join(limits)}"
    body = TOKEN_RE.sub("", body)
    body = re.sub(r"\s+", " ", body).strip()
    return body[:900]


def _hashtags(channel_id: str, item: SourceItemIn) -> list[str]:
    tags = list(HASHTAGS.get(channel_id, ["#технологии"]))
    if channel_id == "github" and item.license_state == "explicit_open_source" and item.license_spdx:
        tags.append("#opensource")
    return tags[:3]


def hard_block_reason(item: SourceItemIn, warnings: list[str], facts: list[Fact]) -> str:
    blob = f"{item.title}\n{item.untrusted_text}\n" + "\n".join(fact.statement for fact in item.facts)
    if item.synthetic or "NEVER_PUBLISH" in blob.upper() or "NEVER PUBLISH" in blob.upper():
        return "synthetic_never_publish"
    if item.link_broken:
        return "broken_link"
    if contains_attack(blob):
        return "attack_instructions"
    if not facts and "prompt_injection" in warnings:
        return "prompt_injection"
    if not facts and ("unsupported_benchmark" in warnings or "unsupported_license" in warnings):
        return "unsupported_claim"
    if not facts:
        return "no_evidence"
    if not any(fact.evidence_url.startswith("https://") for fact in facts):
        return "no_evidence"
    return ""


def draft_post(item: SourceItemIn, channel_id: str, *, pilot: bool = True) -> DraftResult:
    """Deterministic editor. Source text is data. Model verbs like publish are ignored."""
    facts, warnings = safe_facts(item)
    if contains_injection(item.untrusted_text) and "prompt_injection" not in warnings:
        warnings.append("prompt_injection_ignored")
    if item.is_preprint and EXTRAORDINARY_RE.search(item.untrusted_text or ""):
        warnings.append("extraordinary_preprint")
    reason = hard_block_reason(item, warnings, facts)
    if reason:
        return DraftResult(True, reason, warnings, None, "")
    title = _title(item)
    body = _body(item, facts, channel_id)
    links: list[str] = []
    for fact in facts:
        if fact.evidence_url.startswith("https://") and fact.evidence_url not in links:
            links.append(fact.evidence_url)
    if len(links) > 3:
        links = links[:3]
    flags: list[str] = []
    if item.is_preprint:
        flags.append("preprint")
    if item.license_state == "unknown":
        flags.append("license_unknown")
    if item.cve_id or item.content_kind == "advisory":
        flags.append("security_advisory")
    if warnings:
        flags.append("not_verified")
    flags = list(dict.fromkeys(flags))
    human_warnings = [_warning_text(code) for code in warnings]
    draft = {
        "channel_id": channel_id,
        "post_type": post_type_for(item, channel_id),
        "title": title,
        "body": body,
        "claim_ids": [fact.id for fact in facts],
        "source_links": links,
        "flags": flags,
        "warnings": human_warnings,
        "requires_review": True if pilot or flags or warnings else True,
        "suggested_hashtags": _hashtags(channel_id, item),
        "alt_text": f"Карточка: {title}"[:300],
    }
    # publish/approve keys are intentionally absent. A caller cannot promote them.
    return DraftResult(False, "", human_warnings, draft, body)


def _warning_text(code: str) -> str:
    mapping = {
        "prompt_injection": "Инструкция из источника проигнорирована и не влияет на правила.",
        "prompt_injection_ignored": "Инструкция из источника проигнорирована и не влияет на правила.",
        "secret_material": "Строка, похожая на секрет, удалена из материала.",
        "attack_instructions": "Инструкция по атаке не переносится в публикацию.",
        "unsupported_benchmark": "Заявление о бенчмарке не подтверждено и исключено.",
        "unsupported_license": "Заявление о лицензии или бесплатности не подтверждено и исключено.",
        "extraordinary_claim_removed": "Сенсационная формулировка удалена из фактов.",
        "extraordinary_preprint": "Необычное научное заявление оставлено на ручную проверку и помечено как препринт.",
    }
    return mapping.get(code, code)


def license_claim_blocked(text: str, license_state: str) -> bool:
    if license_state == "explicit_open_source":
        return False
    return bool(LICENSE_CLAIM_RE.search(text or ""))


def auto_approve_allowed() -> bool:
    """Auto-approval is outside the MVP. The pilot stays fully manual."""
    return False
