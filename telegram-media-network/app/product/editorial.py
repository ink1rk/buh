"""Channel passports, formats, claims, and quality gates. Mock LLM only."""

from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.models import Channel, ChannelEditorialProfile, ClaimEvidence, EditorialClaim, Post, Story
from app.core.timeutil import utcnow

FORMATS = (
    "breaking_news",
    "practical_tool",
    "explainer",
    "release_delta",
    "security_brief",
    "curated_digest",
    "comparison_or_guide",
)

_INJECTION = re.compile(r"ignore previous|system prompt|you are now|publish:\s*true|срочно опубликуй", re.I)
_LICENSE_CLAIM = re.compile(r"\b(mit|apache|open source|opensource|свободн|бесплатн)\b", re.I)

PROFILES: dict[str, dict] = {
    "ai_news": {
        "audience": "люди, которые следят за AI без желания покупать хайп",
        "promise": "Что произошло в AI и почему это важно",
        "rubrics": ["релиз", "бенчмарк с первоисточником", "исследование", "регуляторное событие"],
        "avoid": ["революция без проверки", "мы проверили без отчёта"],
        "formats": ["breaking_news", "explainer", "curated_digest"],
    },
    "ai_tools": {
        "audience": "практики, которым нужен инструмент и его предел",
        "promise": "Практическая польза и реальные ограничения",
        "rubrics": ["инструмент дня", "сравнение", "сценарий применения"],
        "avoid": ["выдуманная цена", "выдуманная доступность"],
        "formats": ["practical_tool", "comparison_or_guide", "explainer"],
    },
    "github": {
        "audience": "инженеры, которым нужен проверяемый репозиторий",
        "promise": "Полезные проверяемые репозитории",
        "rubrics": ["repo review", "обновление", "подборка"],
        "avoid": ["OSS/MIT без лицензии"],
        "formats": ["practical_tool", "release_delta", "curated_digest"],
    },
    "cyber": {
        "audience": "админы и ИБ, которым нужен риск и действие",
        "promise": "Понять риск и защитные действия",
        "rubrics": ["CVE", "KEV", "патчи", "hardening"],
        "avoid": ["алармизм", "непроверенные scope/CVSS", "инструкция атаки"],
        "formats": ["security_brief", "breaking_news", "explainer"],
    },
    "infra": {
        "audience": "эксплуатация инфраструктуры",
        "promise": "Улучшить эксплуатацию инфраструктуры",
        "rubrics": ["инцидент-разбор", "релиз", "практики"],
        "avoid": ["универсальные опасные команды"],
        "formats": ["breaking_news", "explainer", "curated_digest"],
    },
    "homelab": {
        "audience": "домашняя инфраструктура",
        "promise": "Осмысленно развивать домашнюю инфраструктуру",
        "rubrics": ["self-hosted", "NAS", "Proxmox", "обзоры"],
        "avoid": ["выдуманное железо"],
        "formats": ["practical_tool", "explainer", "curated_digest"],
    },
    "dev": {
        "audience": "разработчики, которым нужно сократить рутину",
        "promise": "Сократить рутину разработчика",
        "rubrics": ["workflow", "release", "автоматизация"],
        "avoid": ["неподтверждённые ускорения"],
        "formats": ["practical_tool", "release_delta", "comparison_or_guide"],
    },
    "future": {
        "audience": "читатели науки без хайпа",
        "promise": "Наука и технологии без хайпа",
        "rubrics": ["исследование", "прототип", "объяснение"],
        "avoid": ["препринт как установленный факт"],
        "formats": ["explainer", "breaking_news", "curated_digest"],
    },
}

PASSPORT_EXTRAS = {
    "ai_news": {"tone": "спокойный фактический", "frequency": "ежедневно", "link_format": "источник в конце"},
    "ai_tools": {"tone": "практический", "frequency": "ежедневно", "link_format": "ссылка на карточку инструмента"},
    "github": {"tone": "инженерный", "frequency": "ежедневно", "link_format": "репозиторий и тег"},
    "cyber": {"tone": "осторожный", "frequency": "по факту риска", "link_format": "бюллетень / CVE"},
    "infra": {"tone": "эксплуатационный", "frequency": "по релизам", "link_format": "changelog вендора"},
    "homelab": {"tone": "прикладной", "frequency": "еженедельно", "link_format": "документация проекта"},
    "dev": {"tone": "лаконичный", "frequency": "ежедневно", "link_format": "репозиторий или changelog"},
    "future": {"tone": "сдержанный научный", "frequency": "еженедельно", "link_format": "DOI / arXiv"},
}


def ensure_profiles(session: Session) -> None:
    for channel in session.query(Channel).all():
        spec = PROFILES.get(channel.id, PROFILES["dev"])
        extra = PASSPORT_EXTRAS.get(channel.id, PASSPORT_EXTRAS["dev"])
        row = session.get(ChannelEditorialProfile, channel.id)
        created = row is None
        if row is None:
            row = ChannelEditorialProfile(channel_id=channel.id)
            session.add(row)
        if created or not row.promise:
            row.audience = spec["audience"]
            row.promise = spec["promise"]
            row.rubrics_json = spec["rubrics"]
            row.avoid_json = spec["avoid"]
            row.voice = channel.voice
            row.formats_json = spec["formats"]
            row.evidence_rules_json = {"primary_required": channel.id in {"cyber", "ai_news", "future"}}
            row.palette_json = channel.theme_json or {}
            row.tone = extra["tone"]
            row.frequency = extra["frequency"]
            row.link_format = extra["link_format"]
            row.stopwords_json = spec["avoid"]
            row.risks_json = spec["avoid"]
            row.length_chars = 900
            row.updated_at = utcnow()


def format_for(channel_id: str, angle: str, session: Session | None = None) -> str:
    mapping = {"news": 0, "value": 1, "apply": 2, "digest": 2}
    formats = list(PROFILES.get(channel_id, PROFILES["dev"])["formats"])
    if session is not None:
        row = session.get(ChannelEditorialProfile, channel_id)
        if row is not None and row.formats_json:
            formats = list(row.formats_json)
    return formats[mapping.get(angle, 0) % len(formats)]


def write_format(channel_id: str, format_id: str, title: str, fact: str, url: str, *, preprint: bool = False) -> dict:
    clean = _INJECTION.sub("", fact or "").strip() or "Источник не передал проверяемого утверждения."
    profile = PROFILES.get(channel_id, PROFILES["dev"])
    if format_id == "breaking_news":
        hook = f"{profile['promise']}."
        body = f"{hook} {clean} Что изменилось: в учебном источнике появилась эта запись. Практический вывод — проверить ссылку, не добавляя цифр. Ограничение: это DEMO, не новость дня. {url}"
    elif format_id == "practical_tool":
        body = (
            f"Зачем это человеку из аудитории «{profile['audience']}»: {clean} "
            "Как смотреть: только по указанной ссылке, без выдуманной установки. "
            "Ограничение: цена, доступность и лицензия не утверждаются, если их нет в источнике. "
            f"{url}"
        )
    elif format_id == "explainer":
        note = "Препринт не равен рецензии. " if preprint else ""
        body = (
            f"{note}Контекст: {clean} Что из этого следует: источник описывает лабораторный или учебный случай. "
            "Чего нет: независимого подтверждения и полевого измерения. "
            f"{url}"
        )
    elif format_id == "release_delta":
        body = (
            f"Что изменилось в учебной записи релиза: {clean} "
            "Лицензия в карточке не подтверждена, вывод о праве использования не делается. "
            f"Сравнение тегов возможно только если оба тега есть в источнике. {url}"
        )
    elif format_id == "security_brief":
        body = (
            f"Учебная запись каталога, не сводка по всем установкам. {clean} "
            "Защитные действия только те, что переданы в карточке. Оценка критичности из источника не добавляется. "
            "Инструкций по эксплуатации уязвимости нет. "
            f"{url}"
        )
    elif format_id == "curated_digest":
        body = (
            f"Подборка для канала: {clean} "
            "В одном дайджесте должны быть независимые сюжеты; этот черновик — учебный слот на одну тему. "
            f"{url}"
        )
    else:
        body = (
            f"Сравнение без псевдотеста: {clean} "
            "Критерии только из источника. Ускорения и победы над другими инструментами не выдумываются. "
            f"{url}"
        )
    return {
        "format_id": format_id,
        "title": title[:120],
        "body": body[:900],
        "prompt_version": "editorial-v3",
        "requires_review": True,
        "uncertain_claims": True,
        "channel_id": channel_id,
    }


def quality_gate(session: Session, post: Post, story: Story | None) -> dict:
    blocking: list[str] = []
    hints: list[str] = []
    blob = f"{post.title}\n{post.body}\n{post.caption}"
    if post.synthetic or (story is not None and story.synthetic) or "NEVER_PUBLISH" in blob.upper():
        blocking.append("synthetic_never_publish")
    if _LICENSE_CLAIM.search(blob) and (story is None or story.license_state in {"unknown", ""}):
        blocking.append("license_claim_without_evidence")
    if re.search(r"CVSS\s*[:=]?\s*\d", blob, re.I):
        blocking.append("cvss_without_source")
    if story is not None and story.is_preprint and "реценз" in blob.lower() and "не равен" not in blob.lower():
        blocking.append("preprint_as_reviewed")
    if not (post.source_links_json or []):
        blocking.append("missing_primary_source")
    claims = session.query(EditorialClaim).filter_by(post_id=post.id, draft_version=post.draft_version).all()
    if any(claim.status in {"unclear", "contradicted", "not_checked", "unreviewed", "conflicted"} and "CVE" in claim.text for claim in claims):
        hints.append("cve_claim_not_verified")
    if any(claim.status in {"conflicted", "contradicted", "expired"} for claim in claims):
        blocking.append("claim_conflict_or_expired")
    if not claims:
        hints.append("claims_not_materialised")
    return {
        "blocking": blocking,
        "hints": hints,
        "publishable": False,
        "reason": "dry-run quality gate never auto-publishes",
        "qa_color": "red" if blocking else "yellow" if hints else "green",
    }


def replace_claims(session: Session, post: Post, fact: str, url: str, now: datetime) -> None:
    old = session.query(EditorialClaim).filter_by(post_id=post.id, draft_version=post.draft_version).all()
    for claim in old:
        session.query(ClaimEvidence).filter_by(claim_row_id=claim.id).delete()
    session.query(EditorialClaim).filter_by(post_id=post.id, draft_version=post.draft_version).delete()
    status = "source_supported" if url else "unreviewed"
    claim = EditorialClaim(
        post_id=post.id,
        draft_version=post.draft_version,
        claim_id="f1",
        text=fact[:400],
        status=status,
        evidence_url=url,
        origin_kind="source_claim",
        checked_at=None,
        method="",
        actor="",
        excerpt=fact[:240],
    )
    session.add(claim)
    session.flush()
    if url:
        session.add(
            ClaimEvidence(
                claim_row_id=claim.id,
                url=url,
                excerpt=fact[:240],
                method="source_extract",
                snapshot_utc=now,
            )
        )
