"""Deterministic editorial variants. The model output is never a fact source."""

from __future__ import annotations

import hashlib
import re

from sqlalchemy.orm import Session

from app.core.models import (
    EditorialBrief,
    EditorialVariant,
    EvidenceSnapshot,
    Post,
    PostVersion,
    RankedCandidate,
    Story,
    StoryCluster,
    StoryEvidence,
)
from app.core.timeutil import utcnow
from app.pipeline.caption import build_caption
from app.product.editorial import format_for, quality_gate, replace_claims, write_format
from app.product.radar import MODEL, _primary_story

PROMPT_VERSION = "editorial-v4"
ANGLES = ("news", "value", "apply")
_INJECTION = re.compile(r"ignore previous|system prompt|you are now|publish:\s*true", re.I)

_OPENINGS = {
    "ai_news": {
        "news": "Что произошло по учебному источнику",
        "value": "Чем эта заметка отличается от прошлого описания",
        "apply": "Что можно проверить по ссылке, не делая выводов сверх текста",
    },
    "ai_tools": {
        "news": "Что делает учебный инструмент",
        "value": "Кому это может пригодиться, если описание источника верно",
        "apply": "Как смотреть карточку: только по указанной ссылке",
    },
    "github": {
        "news": "Назначение учебного репозитория",
        "value": "Практическая ценность, которую источник прямо назвал",
        "apply": "Лицензия в карточке не подтверждена, вывод о праве использования не делается",
    },
    "cyber": {
        "news": "Учебная запись каталога, не сводка по всем установкам",
        "value": "Кого источник называет в этой записи",
        "apply": "Защитные действия только те, что переданы в карточке",
    },
    "infra": {
        "news": "Что изменилось в учебном материале по эксплуатации",
        "value": "Где это может пригодиться и какой риск источник не закрыл",
        "apply": "Применять только после проверки своей среды",
    },
    "homelab": {
        "news": "Зачем учебный материал дома",
        "value": "Что источник говорит об установке",
        "apply": "Ограничения по железу не выдуманы: их нет, если источник молчит",
    },
    "dev": {
        "news": "Сценарий для инженера по учебному источнику",
        "value": "Минимальный принцип, без непроверенной команды",
        "apply": "Команды запуска в текст не добавляются",
    },
    "future": {
        "news": "Что показывает учебный материал",
        "value": "Уровень проверки: препринт не равен рецензии",
        "apply": "Чего источник не доказал, то не утверждается",
    },
}


def build_variant(channel_id: str, angle: str, title: str, fact: str, url: str, *, preprint: bool = False) -> dict:
    format_id = format_for(channel_id, angle)
    payload = write_format(channel_id, format_id, title, fact, url, preprint=preprint)
    opening = _OPENINGS.get(channel_id, _OPENINGS["dev"])[angle]
    extra = ""
    if preprint and "препринт не равен рецензии" not in payload["body"]:
        extra += " Уровень проверки: препринт не равен рецензии."
    if channel_id == "github" and "не подтверждена" not in payload["body"]:
        extra += " Лицензия в карточке не подтверждена, вывод о праве использования не делается."
    if channel_id == "cyber" and "не сводка по всем установкам" not in payload["body"]:
        extra += " Учебная запись каталога, не сводка по всем установкам."
    payload["body"] = (payload["body"] + extra)[:900]
    payload["angle"] = angle
    payload["opening"] = opening
    payload["prompt_version"] = PROMPT_VERSION
    return payload


def materialise_desk(session: Session, *, per_channel: int = 3) -> int:
    """Create synthetic review posts for the strongest primary cluster of each channel."""
    made = 0
    channels = sorted({row.primary_channel_id for row in session.query(StoryCluster) if row.primary_channel_id})
    for channel_id in channels:
        ranked = (
            session.query(RankedCandidate)
            .join(StoryCluster, StoryCluster.id == RankedCandidate.cluster_id)
            .filter(
                RankedCandidate.channel_id == channel_id,
                RankedCandidate.model_version == MODEL,
                StoryCluster.primary_channel_id == channel_id,
            )
            .order_by(RankedCandidate.rank_score.desc(), RankedCandidate.id)
            .all()
        )
        taken = session.query(Post).filter_by(channel_id=channel_id).count()
        if taken >= per_channel:
            continue
        for story in _priority_stories(session, channel_id):
            if taken >= per_channel:
                break
            if session.query(Post).filter_by(story_id=story.id, channel_id=channel_id).first():
                continue
            _create_post(session, story, channel_id, angle=ANGLES[taken % len(ANGLES)])
            taken += 1
            made += 1
        for candidate in ranked:
            if taken >= per_channel:
                break
            cluster = session.get(StoryCluster, candidate.cluster_id)
            ranked_story = _primary_story(session, cluster) if cluster else None
            if ranked_story is None:
                continue
            if session.query(Post).filter_by(story_id=ranked_story.id, channel_id=channel_id).first():
                continue
            _create_post(session, ranked_story, channel_id, angle=ANGLES[taken % len(ANGLES)])
            taken += 1
            made += 1
    session.commit()
    return made


def _priority_stories(session: Session, channel_id: str) -> list[Story]:
    rows: list[Story] = []
    if channel_id == "future":
        rows.extend(session.query(Story).filter_by(primary_channel_id="future", is_preprint=True).all())
    if channel_id == "cyber":
        rows.extend(session.query(Story).filter(Story.title.contains("CVE-2026-990099")).all())
    if channel_id == "github":
        rows.extend(session.query(Story).filter(Story.repo_identity == "acme/demo-runner").order_by(Story.id).all())
    return rows


def variants_for(session: Session, post: Post) -> list[dict]:
    story = session.get(Story, post.story_id)
    fact = story.summary if story else post.body
    url = (post.source_links_json or ["https://example.com/demo"])[0]
    preprint = bool(story.is_preprint) if story is not None else False
    return [build_variant(post.channel_id, angle, post.title, fact, url, preprint=preprint) for angle in ANGLES]


def fallback_from_invalid(channel_id: str, title: str) -> dict:
    return {
        "angle": "news",
        "title": title[:120] or "Черновик без модели",
        "body": "Локальная модель не вернула проверяемый JSON. Текст не отправлен в очередь публикации и требует редактора.",
        "prompt_version": PROMPT_VERSION,
        "requires_review": True,
        "uncertain_claims": True,
        "llm_fallback": True,
        "channel_id": channel_id,
    }


def _create_post(session: Session, story: Story, channel_id: str, angle: str = "news") -> Post:
    evidence = session.query(StoryEvidence).filter_by(story_id=story.id).all()
    fact = evidence[0].statement if evidence else story.summary
    url = evidence[0].evidence_url if evidence else story.canonical_url
    news = build_variant(channel_id, angle, story.title, fact, url, preprint=story.is_preprint)
    security = channel_id == "cyber" or story.content_kind == "advisory"
    caption = build_caption(news["title"], news["body"], [url] if url else [], ["#demo"])
    digest = hashlib.sha256(f"{channel_id}|1|{news['title']}|{news['body']}".encode()).hexdigest()
    post = Post(
        story_id=story.id,
        channel_id=channel_id,
        post_type="security" if security else "news",
        title=news["title"][:200],
        body=news["body"],
        draft_version=1,
        review_status="NEEDS_REVIEW",
        final_hash=digest,
        flags_json=["demo", "never_publish", "uncertain_claims"],
        warnings_json=["DEMO", "NEVER_PUBLISH"],
        source_links_json=[url] if url else [],
        claim_ids_json=["f1"],
        requires_review=True,
        approvals_required=2 if security else 1,
        caption=caption,
        caption_hash=hashlib.sha256(caption.encode()).hexdigest(),
        synthetic=True,
        hashtags_json=["#demo"],
        format_id=news.get("format_id") or "breaking_news",
        quality_json={},
        angle_id=angle,
        text_hash=digest,
        data_mode="demo",
    )
    session.add(post)
    session.flush()
    for index, angle in enumerate(ANGLES, start=1):
        variant = build_variant(channel_id, angle, story.title, fact, url, preprint=story.is_preprint)
        session.add(
            PostVersion(
                post_id=post.id,
                version=index,
                title=variant["title"],
                body=variant["body"],
                channel_id=channel_id,
                final_hash=hashlib.sha256(variant["body"].encode()).hexdigest(),
            )
        )
        session.add(
            EvidenceSnapshot(
                post_id=post.id,
                draft_version=index,
                claim_id="f1",
                claim_text=fact[:400],
                source_url=url,
                published_at=story.published_utc,
                observed_at=story.discovered_utc,
                verified_at=None,
                verification_method="",
                support_level="source_supported",
                excerpt=fact[:160],
                origin_kind="source_claim",
            )
        )
    replace_claims(session, post, fact, url, utcnow())
    post.quality_json = quality_gate(session, post, story)
    _store_brief(session, post, story, fact, url)
    return post


def create_angles(session: Session, post: Post, actor: str = "editor") -> list[dict]:
    """Two to four structurally different drafts from one brief. Not a first-sentence swap."""
    variants = variants_for(session, post)
    story = session.get(Story, post.story_id)
    cluster = None
    if story is not None:
        cluster = session.query(StoryCluster).filter_by(cluster_key=story.cluster_id).one_or_none()
    brief = EditorialBrief(
        cluster_id=cluster.id if cluster else 0,
        channel_id=post.channel_id,
        angle_id="multi",
        format_id=post.format_id,
        prompt_version=PROMPT_VERSION,
        notes="детерминированный генератор, не LLM",
        actor=actor,
    )
    if cluster is None:
        return variants
    session.add(brief)
    session.flush()
    post.brief_id = brief.id
    stored = []
    for item in variants:
        digest = hashlib.sha256(item["body"].encode()).hexdigest()
        row = EditorialVariant(
            brief_id=brief.id,
            post_id=post.id,
            angle_id=item["angle"],
            title=item["title"],
            body=item["body"],
            text_hash=digest,
            prompt_version=PROMPT_VERSION,
            agent_role="editor",
            model_config_json={"mode": "mock", "prompt_version": PROMPT_VERSION},
            claim_ids_json=list(post.claim_ids_json or ["f1"]),
            qa_json={"requires_review": True},
            duration_ms=0,
            cost=None,
        )
        session.add(row)
        stored.append(item)
    session.flush()
    return stored


def _store_brief(session: Session, post: Post, story: Story, fact: str, url: str) -> None:
    cluster = session.query(StoryCluster).filter_by(cluster_key=story.cluster_id).one_or_none()
    if cluster is None:
        return
    brief = EditorialBrief(
        cluster_id=cluster.id,
        channel_id=post.channel_id,
        angle_id=post.angle_id or "news",
        format_id=post.format_id,
        prompt_version=PROMPT_VERSION,
        notes="учебный brief DEMO",
        actor="desk",
    )
    session.add(brief)
    session.flush()
    post.brief_id = brief.id
    for angle in ANGLES:
        variant = build_variant(post.channel_id, angle, story.title, fact, url, preprint=story.is_preprint)
        session.add(
            EditorialVariant(
                brief_id=brief.id,
                post_id=post.id,
                angle_id=angle,
                title=variant["title"],
                body=variant["body"],
                text_hash=hashlib.sha256(variant["body"].encode()).hexdigest(),
                prompt_version=PROMPT_VERSION,
                agent_role="editor",
                model_config_json={"mode": "mock"},
                claim_ids_json=["f1"],
                qa_json=post.quality_json or {},
                duration_ms=0,
                cost=None,
            )
        )
