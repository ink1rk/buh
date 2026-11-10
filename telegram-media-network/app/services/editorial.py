from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.core.audit import add_audit
from app.core.models import (
    Channel,
    Classification,
    MediaAsset,
    Post,
    PostVersion,
    ScoreEvent,
    Source,
    SourceItem,
    Story,
    StoryAlias,
    StoryEvidence,
    StoryLink,
)
from app.core.redact import redact_obj
from app.core.timeutil import utcnow
from app.media.renderer import render_card
from app.pipeline.caption import build_caption, caption_hash, safe_links, validate_caption
from app.pipeline.dedup import cluster_id, identity_keys, repo_identity, title_similarity
from app.pipeline.editor import post_type_for
from app.pipeline.llm import compose_draft
from app.pipeline.rank import score_item
from app.pipeline.route import route_item
from app.pipeline.schema_check import schema_errors
from app.pipeline.types import SourceItemIn
from app.pipeline.urlsec import canonicalize


@dataclass
class IngestResult:
    story_id: int | None
    post_id: int | None
    status: str
    blocked_reason: str = ""
    score: int | None = None
    band: str = ""
    cluster: str = ""
    duplicate: bool = False
    public_text: str = ""
    warnings: list[str] = field(default_factory=list)
    channel_id: str = ""


def _mark_packaged_fixture(item: SourceItemIn) -> None:
    title = item.title.lower()
    blob = f"{item.title}\n{item.untrusted_text}".upper()
    if item.synthetic or "NEVER_PUBLISH" in blob or "NEVER PUBLISH" in blob:
        item.synthetic = True
    if "учебная фикстура" in title or "не реальная новость" in title:
        item.synthetic = True


def _ensure_source(session: Session, item: SourceItemIn) -> Source:
    row = session.get(Source, item.source_id)
    if row is None:
        row = Source(
            id=item.source_id,
            kind="manual",
            adapter="manual",
            enabled=True,
            health="ok",
            tos_note="manual or fixture",
        )
        session.add(row)
        session.flush()
    return row


def _store_source_item(session: Session, item: SourceItemIn) -> SourceItem:
    raw = redact_obj(item.contract())
    row = SourceItem(
        source_id=item.source_id,
        external_id=item.source_external_id[:300],
        discovered_utc=item.discovered_at,
        published_utc=item.published_at,
        raw_hash=item.raw_sha256,
        raw_json=raw,
        fetched_utc=utcnow(),
    )
    session.add(row)
    session.flush()
    return row


def _hash_post(title: str, body: str, channel_id: str, version: int) -> str:
    return hashlib.sha256(f"{channel_id}|{version}|{title}|{body}".encode()).hexdigest()


def refresh_card(post: Post, channel: Channel, directory: Path) -> MediaAsset:
    return _write_media(post, channel, directory)


def _write_media(post: Post, channel: Channel, directory: Path) -> MediaAsset:
    theme = channel.theme_json or {}
    primary = theme.get("primary") or "#1c2434"
    accent = theme.get("accent") or "#d7e2ea"
    template = post.post_type if post.post_type in {"news", "tool", "security"} else (theme.get("template") or "news")
    cve = ""
    for token in post.title.split():
        if token.startswith("CVE-"):
            cve = token.strip(":,.")
    source_label = ""
    for link in post.source_links_json or []:
        host = urlsplit(str(link)).hostname or ""
        if host:
            source_label = host
            break
    rendered = render_card(
        channel_title=channel.title,
        primary=primary,
        accent=accent,
        template=template,
        title=post.title,
        kicker=template.upper(),
        footer=channel.title,
        cve=cve,
        source_label=source_label,
    )
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"post-{post.id}-v{post.draft_version}.jpg"
    path = directory / filename
    partial = directory / f".{filename}.partial"
    try:
        partial.write_bytes(rendered.jpeg)
        os.replace(partial, path)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    asset = MediaAsset(
        post_id=post.id,
        kind="card",
        file_path=filename,
        rights_basis=rendered.rights_basis,
        sha256=rendered.sha256,
        width=rendered.width,
        height=rendered.height,
        byte_size=rendered.byte_size,
        status="ready",
        render_version="card-v1",
        draft_version=post.draft_version,
        content_hash=post.final_hash,
    )
    return asset


def ingest_source_item(
    session: Session,
    item: SourceItemIn,
    *,
    render: bool = True,
    media_dir: Path | None = None,
    pilot: bool = True,
    llm_mode: str = "mock",
    llm_client=None,
) -> IngestResult:
    _mark_packaged_fixture(item)
    source = _ensure_source(session, item)
    if source.robots_blocked or source.tos_blocked or not source.enabled:
        return IngestResult(None, None, "BLOCKED_SOURCE", blocked_reason=source.last_error or "source_disabled")
    canon = canonicalize(item.canonical_url or item.source_url)
    if not canon.ok:
        return IngestResult(None, None, "QUARANTINED", blocked_reason=canon.reason or "bad_url")
    item.canonical_url = canon.url
    errors = schema_errors("source_item.schema.json", item.contract())
    if errors:
        return IngestResult(None, None, "QUARANTINED", blocked_reason="schema:" + "; ".join(errors[:3]))

    keys = identity_keys(item)
    existing_alias = session.query(StoryAlias).filter(StoryAlias.alias.in_(keys)).first()
    stored = (
        session.query(SourceItem)
        .filter_by(source_id=item.source_id, external_id=item.source_external_id[:300], raw_hash=item.raw_sha256)
        .one_or_none()
    )
    if stored is None:
        stored = _store_source_item(session, item)
    if existing_alias is not None:
        session.add(StoryLink(story_id=existing_alias.story_id, source_item_id=stored.id, relation="duplicate"))
        session.commit()
        story = session.get(Story, existing_alias.story_id)
        return IngestResult(
            story.id if story else existing_alias.story_id,
            None,
            "DUPLICATE",
            duplicate=True,
            cluster=story.cluster_id if story else "",
            channel_id=story.primary_channel_id if story else "",
        )

    decision = route_item(item)
    scored = score_item(item, decision.confidence)
    started = time.perf_counter()
    drafted = compose_draft(item, decision.primary, mode=llm_mode, client=llm_client)
    if llm_mode == "local":
        add_audit(
            session,
            actor="editor",
            action="llm_draft",
            entity="source_item",
            entity_id=item.source_external_id[:80],
            result="fallback" if "llm_fallback" in drafted.warnings else "draft",
            payload={
                "model": getattr(llm_client, "model", ""),
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                "source_external_id": item.source_external_id[:80],
                "error": getattr(llm_client, "last_error", ""),
            },
        )
    status = "NEEDS_REVIEW"
    if drafted.blocked:
        status = "QUARANTINED"
    elif item.archived or scored.total < 60:
        status = "ARCHIVED"
    story = Story(
        canonical_url=canon.url,
        canonical_hash=hashlib.sha256(canon.url.encode()).hexdigest(),
        cluster_id=cluster_id(item),
        repo_identity=repo_identity(item),
        published_utc=item.published_at,
        discovered_utc=item.discovered_at,
        title=item.title[:400],
        summary=(drafted.public_text or item.title)[:500],
        status=status,
        provenance_json={
            "source_id": item.source_id,
            "external_id": item.source_external_id,
            "keys": keys,
            "backfill": bool(item.archived),
            "date_added": item.date_added or "",
        },
        primary_channel_id=decision.primary,
        score_total=scored.total,
        score_band="blocked" if drafted.blocked else scored.band,
        hard_block_reason=drafted.reason,
        content_kind=item.content_kind,
        license_state=item.license_state,
        license_spdx=item.license_spdx or "",
        is_preprint=item.is_preprint,
        source_id=item.source_id,
        synthetic=item.synthetic,
    )
    session.add(story)
    session.flush()
    for key in keys:
        session.add(StoryAlias(alias=key, story_id=story.id))
    for fact in item.facts:
        if fact.evidence_url.startswith("https://"):
            session.add(
                StoryEvidence(
                    story_id=story.id,
                    claim_id=fact.id,
                    source_item_id=stored.id,
                    statement=fact.statement[:400],
                    evidence_excerpt=fact.evidence_excerpt[:160],
                    evidence_url=fact.evidence_url,
                    verified_at=None,
                    status="extracted",
                )
            )
    session.add(
        Classification(
            story_id=story.id,
            channel_id=decision.primary,
            confidence=int(decision.confidence * 100),
            reason=decision.reason,
            is_primary=True,
        )
    )
    for alternative in decision.alternatives:
        if alternative != decision.primary:
            session.add(
                Classification(
                    story_id=story.id,
                    channel_id=alternative,
                    confidence=40,
                    reason="Вторичная тема без отдельного поста.",
                    is_primary=False,
                )
            )
    session.add(
        ScoreEvent(
            story_id=story.id,
            rubric_version=scored.rubric_version,
            per_axis_scores=scored.axes,
            penalties=scored.penalties,
            total=scored.total,
            source_data={"channel_fit": decision.confidence, "reason": decision.reason},
            created_at=utcnow(),
        )
    )
    session.add(StoryLink(story_id=story.id, source_item_id=stored.id, relation="origin"))
    _mark_near_duplicate(session, story)
    post_id = None
    public = drafted.public_text
    if status == "NEEDS_REVIEW" and drafted.draft is not None:
        draft_errors = schema_errors("post_draft.schema.json", drafted.draft)
        if draft_errors:
            story.status = "QUARANTINED"
            story.hard_block_reason = "draft_schema:" + "; ".join(draft_errors[:3])
            status = story.status
        else:
            post = _create_post(session, story, drafted.draft, item)
            post_id = post.id
            public = post.body
            if render:
                channel = session.get(Channel, post.channel_id)
                if channel is not None:
                    session.add(_write_media(post, channel, media_dir or Path("var/media")))
    session.commit()
    return IngestResult(
        story.id,
        post_id,
        status,
        blocked_reason=story.hard_block_reason,
        score=scored.total,
        band=story.score_band,
        cluster=story.cluster_id,
        public_text=public,
        warnings=drafted.warnings,
        channel_id=decision.primary,
    )


def _mark_near_duplicate(session: Session, story: Story) -> None:
    others = session.query(Story).filter(Story.id != story.id).order_by(Story.id.desc()).limit(200).all()
    for other in others:
        if other.cluster_id == story.cluster_id:
            continue
        if title_similarity(story.title, other.title) >= 0.85:
            story.near_duplicate_of = other.id
            return


def _create_post(session: Session, story: Story, draft: dict, item: SourceItemIn) -> Post:
    channel_id = draft["channel_id"]
    title = draft["title"]
    body = draft["body"]
    links = safe_links(draft["source_links"])
    hashtags = draft.get("suggested_hashtags") or []
    caption = build_caption(title, body, links, hashtags)
    ok, problem = validate_caption(caption, body)
    warnings = list(draft.get("warnings") or [])
    if not ok:
        warnings.append(problem)
    security = "security_advisory" in (draft.get("flags") or []) or item.cve_id or channel_id == "cyber"
    channel = session.get(Channel, channel_id)
    approvals = 2 if security or (channel and channel.require_second_human) else 1
    post = Post(
        story_id=story.id,
        channel_id=channel_id,
        post_type=draft["post_type"] or post_type_for(item, channel_id),
        title=title,
        body=body,
        alt_text=draft.get("alt_text") or "",
        draft_version=1,
        review_status="NEEDS_REVIEW",
        final_hash=_hash_post(title, body, channel_id, 1),
        flags_json=list(draft.get("flags") or []),
        warnings_json=warnings,
        source_links_json=links,
        claim_ids_json=list(draft.get("claim_ids") or []),
        requires_review=True,
        approvals_required=approvals,
        approver_ids_json=[],
        publish_intent_id=secrets.token_hex(8),
        caption=caption,
        caption_hash=caption_hash(caption),
        synthetic=item.synthetic,
        hashtags_json=hashtags,
    )
    session.add(post)
    session.flush()
    session.add(
        PostVersion(
            post_id=post.id,
            version=1,
            title=title,
            body=body,
            channel_id=channel_id,
            final_hash=post.final_hash,
            created_at=utcnow(),
        )
    )
    return post


def story_detail(session: Session, story_id: int) -> dict:
    story = session.get(Story, story_id)
    if story is None:
        return {}
    evidence = session.query(StoryEvidence).filter_by(story_id=story.id).all()
    scores = session.query(ScoreEvent).filter_by(story_id=story.id).all()
    posts = session.query(Post).filter_by(story_id=story.id).all()
    classes = session.query(Classification).filter_by(story_id=story.id).all()
    return {
        "id": story.id,
        "title": story.title,
        "status": story.status,
        "score": story.score_total,
        "band": story.score_band,
        "hard_block_reason": story.hard_block_reason,
        "channel_id": story.primary_channel_id,
        "cluster_id": story.cluster_id,
        "canonical_url": story.canonical_url,
        "published_utc": story.published_utc.isoformat() if story.published_utc else None,
        "discovered_utc": story.discovered_utc.isoformat(),
        "license_state": story.license_state,
        "is_preprint": story.is_preprint,
        "near_duplicate_of": story.near_duplicate_of,
        "facts": [
            {
                "id": row.claim_id,
                "statement": row.statement,
                "evidence_url": row.evidence_url,
                "evidence_excerpt": row.evidence_excerpt,
                "status": row.status,
            }
            for row in evidence
        ],
        "scores": [
            {"total": row.total, "axes": row.per_axis_scores, "penalties": row.penalties, "rubric": row.rubric_version}
            for row in scores
        ],
        "classifications": [
            {"channel_id": row.channel_id, "primary": row.is_primary, "reason": row.reason, "confidence": row.confidence}
            for row in classes
        ],
        "posts": [post.id for post in posts],
    }


def dumps_story(session: Session, story_id: int) -> str:
    return json.dumps(story_detail(session, story_id), ensure_ascii=False)
