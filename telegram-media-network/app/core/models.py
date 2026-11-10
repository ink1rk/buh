from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.timeutil import utcnow


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return utcnow()


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    mfa_secret: Mapped[str | None] = mapped_column(String(128), nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    user: Mapped[User] = relationship()


class MfaChallenge(Base):
    __tablename__ = "mfa_challenges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(80), default="")
    result: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    trace_id: Mapped[str] = mapped_column(String(64), default="")
    payload_redacted: Mapped[dict] = mapped_column(JSON, default=dict)


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    adapter: Mapped[str] = mapped_column(String(80), nullable=False)
    base_url: Mapped[str] = mapped_column(Text, default="")
    poll_interval_minutes: Mapped[int] = mapped_column(Integer, default=60)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tos_note: Mapped[str] = mapped_column(Text, default="")
    health: Mapped[str] = mapped_column(String(40), default="unknown")
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    etag: Mapped[str] = mapped_column(Text, default="")
    last_modified: Mapped[str] = mapped_column(Text, default="")
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    circuit_open: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    robots_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tos_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    policy_json: Mapped[dict] = mapped_column(JSON, default=dict)


class SourceEndpointState(Base):
    """Conditional-request cache for one URL. It is never reused for a different endpoint."""

    __tablename__ = "source_endpoint_states"
    __table_args__ = (UniqueConstraint("source_id", "request_url", name="uq_source_endpoint"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), nullable=False)
    request_url: Mapped[str] = mapped_column(Text, nullable=False)
    etag: Mapped[str] = mapped_column(Text, default="")
    last_modified: Mapped[str] = mapped_column(Text, default="")
    last_status: Mapped[int] = mapped_column(Integer, default=0)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ComponentHeartbeat(Base):
    __tablename__ = "component_heartbeats"

    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    status: Mapped[str] = mapped_column(String(40), default="unknown")
    detail: Mapped[str] = mapped_column(Text, default="")
    beat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SourceItem(Base):
    __tablename__ = "source_items"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", "raw_hash", name="uq_source_item_hash"),
        Index("ix_source_items_source_external", "source_id", "external_id"),
        Index("ix_source_items_fetched", "source_id", "fetched_utc"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(300), nullable=False)
    discovered_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_json: Mapped[dict] = mapped_column(JSON, default=dict)
    fetched_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    publisher_id: Mapped[str] = mapped_column(String(80), default="")
    content_kind: Mapped[str] = mapped_column(String(40), default="news")
    origin_mode: Mapped[str] = mapped_column(String(40), default="demo")
    lab_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Story(Base):
    __tablename__ = "stories"
    __table_args__ = (
        Index("ix_stories_canonical_hash", "canonical_hash"),
        Index("ix_stories_cluster", "cluster_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_url: Mapped[str] = mapped_column(Text, default="")
    canonical_hash: Mapped[str] = mapped_column(String(64), default="")
    cluster_id: Mapped[str] = mapped_column(String(300), default="")
    repo_identity: Mapped[str] = mapped_column(String(300), default="")
    published_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    discovered_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    title: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="INGESTED", index=True)
    provenance_json: Mapped[dict] = mapped_column(JSON, default=dict)
    primary_channel_id: Mapped[str] = mapped_column(String(40), default="")
    score_total: Mapped[int] = mapped_column(Integer, default=0)
    score_band: Mapped[str] = mapped_column(String(40), default="")
    hard_block_reason: Mapped[str] = mapped_column(Text, default="")
    near_duplicate_of: Mapped[int | None] = mapped_column(ForeignKey("stories.id"), nullable=True)
    content_kind: Mapped[str] = mapped_column(String(40), default="news")
    license_state: Mapped[str] = mapped_column(String(40), default="unknown")
    license_spdx: Mapped[str] = mapped_column(String(80), default="")
    is_preprint: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_id: Mapped[str] = mapped_column(String(80), default="")
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class StoryAlias(Base):
    __tablename__ = "story_aliases"

    alias: Mapped[str] = mapped_column(String(300), primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id"), index=True, nullable=False)


class StoryLink(Base):
    __tablename__ = "story_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id"), index=True)
    source_item_id: Mapped[int | None] = mapped_column(ForeignKey("source_items.id"), nullable=True)
    relation: Mapped[str] = mapped_column(String(40), default="duplicate")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class StoryEvidence(Base):
    __tablename__ = "story_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id"), index=True)
    claim_id: Mapped[str] = mapped_column(String(80), nullable=False)
    source_item_id: Mapped[int | None] = mapped_column(ForeignKey("source_items.id"), nullable=True)
    statement: Mapped[str] = mapped_column(Text, default="")
    evidence_excerpt: Mapped[str] = mapped_column(String(200), default="")
    evidence_url: Mapped[str] = mapped_column(Text, default="")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="recorded")


class Classification(Base):
    __tablename__ = "classifications"
    __table_args__ = (UniqueConstraint("story_id", "channel_id", name="uq_story_channel"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id"), index=True)
    channel_id: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str] = mapped_column(Text, default="")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ScoreEvent(Base):
    __tablename__ = "score_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id"), index=True)
    rubric_version: Mapped[str] = mapped_column(String(40), default="rubric-v1")
    per_axis_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    penalties: Mapped[dict] = mapped_column(JSON, default=dict)
    total: Mapped[int] = mapped_column(Integer, default=0)
    source_data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(120), default="")
    username: Mapped[str] = mapped_column(String(120), default="")
    chat_id: Mapped[str] = mapped_column(String(80), default="")
    publish_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    paused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    daily_cap: Mapped[int] = mapped_column(Integer, default=2)
    min_gap_minutes: Mapped[int] = mapped_column(Integer, default=240)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")
    schedule_json: Mapped[list] = mapped_column(JSON, default=list)
    theme_json: Mapped[dict] = mapped_column(JSON, default=dict)
    tags_json: Mapped[list] = mapped_column(JSON, default=list)
    voice: Mapped[str] = mapped_column(Text, default="")
    require_second_human: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    quiet_start: Mapped[str] = mapped_column(String(5), default="22:00")
    quiet_end: Mapped[str] = mapped_column(String(5), default="08:00")


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id"), index=True)
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id"), index=True)
    post_type: Mapped[str] = mapped_column(String(40), default="news")
    title: Mapped[str] = mapped_column(String(200), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    alt_text: Mapped[str] = mapped_column(Text, default="")
    draft_version: Mapped[int] = mapped_column(Integer, default=1)
    review_status: Mapped[str] = mapped_column(String(40), default="NEEDS_REVIEW", index=True)
    final_hash: Mapped[str] = mapped_column(String(64), default="")
    flags_json: Mapped[list] = mapped_column(JSON, default=list)
    warnings_json: Mapped[list] = mapped_column(JSON, default=list)
    source_links_json: Mapped[list] = mapped_column(JSON, default=list)
    claim_ids_json: Mapped[list] = mapped_column(JSON, default=list)
    requires_review: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    approvals_required: Mapped[int] = mapped_column(Integer, default=1)
    approver_ids_json: Mapped[list] = mapped_column(JSON, default=list)
    publish_intent_id: Mapped[str] = mapped_column(String(64), default="")
    caption: Mapped[str] = mapped_column(Text, default="")
    caption_hash: Mapped[str] = mapped_column(String(64), default="")
    sponsored_campaign_id: Mapped[int | None] = mapped_column(ForeignKey("ad_campaigns.id"), nullable=True)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hashtags_json: Mapped[list] = mapped_column(JSON, default=list)
    format_id: Mapped[str] = mapped_column(String(40), default="breaking_news")
    quality_json: Mapped[dict] = mapped_column(JSON, default=dict)
    angle_id: Mapped[str] = mapped_column(String(40), default="")
    brief_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text_hash: Mapped[str] = mapped_column(String(64), default="")
    data_mode: Mapped[str] = mapped_column(String(20), default="demo")
    lab_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class PostVersion(Base):
    __tablename__ = "post_versions"
    __table_args__ = (Index("ix_post_versions_post", "post_id", "version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    channel_id: Mapped[str] = mapped_column(String(40), default="")
    final_hash: Mapped[str] = mapped_column(String(64), default="")
    editor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    body: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MediaAsset(Base):
    __tablename__ = "media_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40), default="card")
    file_path: Mapped[str] = mapped_column(Text, default="")
    rights_basis: Mapped[str] = mapped_column(String(80), default="own_typographic_template")
    sha256: Mapped[str] = mapped_column(String(64), default="")
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    byte_size: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(40), default="ready")
    render_version: Mapped[str] = mapped_column(String(40), default="card-v1")
    draft_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), default="")


class ApprovalEvent(Base):
    __tablename__ = "approval_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="")
    before_hash: Mapped[str] = mapped_column(String(64), default="")
    after_hash: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PublishingOutbox(Base):
    __tablename__ = "publishing_outbox"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_outbox_idempotency"),
        Index("ix_outbox_due", "channel_id", "state", "due_utc"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True)
    channel_id: Mapped[str] = mapped_column(String(40), nullable=False)
    due_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(40), default="scheduled", index=True)
    lease_owner: Mapped[str] = mapped_column(String(80), default="")
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")
    publish_intent_id: Mapped[str] = mapped_column(String(64), default="")
    request_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pending_message_id: Mapped[str] = mapped_column(String(40), default="")
    caption_hash: Mapped[str] = mapped_column(String(64), default="")
    claimed_draft_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    claimed_caption: Mapped[str] = mapped_column(Text, default="")


class PublishedMessage(Base):
    __tablename__ = "published_messages"
    __table_args__ = (
        UniqueConstraint("post_id", "channel_id", name="uq_published_post_channel"),
        UniqueConstraint("channel_id", "telegram_message_id", name="uq_published_channel_message"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), nullable=False)
    channel_id: Mapped[str] = mapped_column(String(40), nullable=False)
    telegram_message_id: Mapped[str] = mapped_column(String(40), nullable=False)
    published_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    telegram_link: Mapped[str] = mapped_column(Text, default="")
    caption_hash: Mapped[str] = mapped_column(String(64), default="")


class CredentialRef(Base):
    __tablename__ = "credentials_refs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service: Mapped[str] = mapped_column(String(80), nullable=False)
    secret_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    created_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    rotated_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AnalyticsDaily(Base):
    __tablename__ = "analytics_daily"
    __table_args__ = (UniqueConstraint("channel_id", "metric_date", name="uq_analytics_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[str] = mapped_column(String(40), nullable=False)
    metric_date: Mapped[str] = mapped_column(String(10), nullable=False)
    subscribers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    posts: Mapped[int] = mapped_column(Integer, default=0)
    clicks_measured: Mapped[int | None] = mapped_column(Integer, nullable=True)
    views_manual: Mapped[int | None] = mapped_column(Integer, nullable=True)
    views_source: Mapped[str] = mapped_column(String(40), default="")
    costs_actual: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AdCampaign(Base):
    __tablename__ = "ad_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    advertiser: Mapped[str] = mapped_column(String(200), default="")
    channel_id: Mapped[str] = mapped_column(String(40), default="")
    price: Mapped[str] = mapped_column(String(40), default="")
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    period: Mapped[str] = mapped_column(String(80), default="")
    marked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    erid: Mapped[str] = mapped_column(String(80), default="")
    legal_status: Mapped[str] = mapped_column(String(40), default="pending")
    approvals_json: Mapped[dict] = mapped_column(JSON, default=dict)
    demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class RuntimeSetting(Base):
    __tablename__ = "runtime_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value_json: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_by: Mapped[str] = mapped_column(String(80), default="")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    severity: Mapped[str] = mapped_column(String(20), default="warning")
    code: Mapped[str] = mapped_column(String(80), index=True)
    message: Mapped[str] = mapped_column(Text, default="")
    channel_id: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("key", "user_id", name="uq_idempotency_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status_code: Mapped[int] = mapped_column(Integer, default=200)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class StoryCluster(Base):
    __tablename__ = "story_clusters"
    __table_args__ = (UniqueConstraint("cluster_key", name="uq_cluster_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cluster_key: Mapped[str] = mapped_column(String(300), nullable=False)
    title: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(40), default="event")
    status: Mapped[str] = mapped_column(String(40), default="open", index=True)
    list_name: Mapped[str] = mapped_column(String(40), default="review")
    primary_channel_id: Mapped[str] = mapped_column(String(40), default="")
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    merge_reason: Mapped[str] = mapped_column(Text, default="")
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), default="event")
    event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_change_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dossier_json: Mapped[dict] = mapped_column(JSON, default=dict)
    score_version: Mapped[str] = mapped_column(String(40), default="radar-v3")
    locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    trend_state: Mapped[str] = mapped_column(String(40), default="unknown")
    trend_delta: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_mode: Mapped[str] = mapped_column(String(20), default="demo")
    program_kind: Mapped[str] = mapped_column(String(40), default="breaking")
    lab_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ClusterMember(Base):
    __tablename__ = "cluster_members"
    __table_args__ = (Index("ix_cluster_members_cluster", "cluster_id", "relation"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("story_clusters.id"), nullable=False)
    story_id: Mapped[int | None] = mapped_column(ForeignKey("stories.id"), nullable=True)
    source_item_id: Mapped[int | None] = mapped_column(ForeignKey("source_items.id"), nullable=True)
    relation: Mapped[str] = mapped_column(String(40), default="member")
    reason: Mapped[str] = mapped_column(Text, default="")


class RankedCandidate(Base):
    __tablename__ = "ranked_candidates"
    __table_args__ = (UniqueConstraint("cluster_id", "channel_id", "model_version", name="uq_rank_latest"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("story_clusters.id"), index=True, nullable=False)
    channel_id: Mapped[str] = mapped_column(String(40), nullable=False)
    model_version: Mapped[str] = mapped_column(String(40), default="radar-v2")
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    dimensions_json: Mapped[dict] = mapped_column(JSON, default=dict)
    penalties_json: Mapped[dict] = mapped_column(JSON, default=dict)
    rank_score: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    explanation: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="ranked")
    trend_state: Mapped[str] = mapped_column(String(40), default="unknown")
    reasons_json: Mapped[list] = mapped_column(JSON, default=list)


class TrendSample(Base):
    __tablename__ = "trend_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_item_id: Mapped[int] = mapped_column(ForeignKey("source_items.id"), index=True, nullable=False)
    snapshot_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider: Mapped[str] = mapped_column(String(80), default="")
    completeness: Mapped[str] = mapped_column(String(40), default="single")


class EvidenceSnapshot(Base):
    __tablename__ = "evidence_snapshots"
    __table_args__ = (Index("ix_evidence_post_version", "post_id", "draft_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), nullable=False)
    draft_version: Mapped[int] = mapped_column(Integer, nullable=False)
    claim_id: Mapped[str] = mapped_column(String(80), default="")
    claim_text: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(Text, default="")
    source_item_id: Mapped[int | None] = mapped_column(ForeignKey("source_items.id"), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_method: Mapped[str] = mapped_column(String(40), default="")
    support_level: Mapped[str] = mapped_column(String(40), default="source_claim")
    excerpt: Mapped[str] = mapped_column(String(200), default="")
    origin_kind: Mapped[str] = mapped_column(String(40), default="source_claim")


class Series(Base):
    __tablename__ = "series"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    allowed_channels: Mapped[list] = mapped_column(JSON, default=list)
    period: Mapped[str] = mapped_column(String(20), default="daily")
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")
    min_items: Mapped[int] = mapped_column(Integer, default=1)
    max_items: Mapped[int] = mapped_column(Integer, default=5)
    style: Mapped[str] = mapped_column(String(40), default="digest")
    rules_json: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Episode(Base):
    __tablename__ = "episodes"
    __table_args__ = (Index("ix_episodes_slot", "channel_id", "slot_utc"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    series_id: Mapped[str] = mapped_column(ForeignKey("series.id"), nullable=False)
    channel_id: Mapped[str] = mapped_column(String(40), nullable=False)
    slot_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="proposed")
    item_refs: Mapped[list] = mapped_column(JSON, default=list)
    draft_post_id: Mapped[int | None] = mapped_column(ForeignKey("posts.id"), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    origin: Mapped[str] = mapped_column(String(40), default="propose")
    format_id: Mapped[str] = mapped_column(String(40), default="")
    program_kind: Mapped[str] = mapped_column(String(40), default="breaking")
    vacancy_reason: Mapped[str] = mapped_column(Text, default="")
    lab_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class EditorialFeedback(Base):
    __tablename__ = "editorial_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True, nullable=False)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    rating: Mapped[str] = mapped_column(String(40), default="")
    labels_json: Mapped[list] = mapped_column(JSON, default=list)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AudienceMetric(Base):
    __tablename__ = "audience_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[str] = mapped_column(String(40), nullable=False)
    message_id: Mapped[str] = mapped_column(String(40), default="")
    period_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    measurement_source: Mapped[str] = mapped_column(String(40), default="manual")
    verified_by: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("ad_campaigns.id"), index=True, nullable=False)
    channel_id: Mapped[str] = mapped_column(String(40), default="")
    slot_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="planned")
    demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Creative(Base):
    __tablename__ = "creatives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("ad_campaigns.id"), index=True, nullable=False)
    body: Mapped[str] = mapped_column(Text, default="")
    disclosure_status: Mapped[str] = mapped_column(String(40), default="pending")
    demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Placement(Base):
    __tablename__ = "placements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), nullable=False)
    creative_id: Mapped[int] = mapped_column(ForeignKey("creatives.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="planned")
    demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ChannelEditorialProfile(Base):
    __tablename__ = "channel_editorial_profiles"

    channel_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    audience: Mapped[str] = mapped_column(Text, default="")
    promise: Mapped[str] = mapped_column(Text, default="")
    rubrics_json: Mapped[list] = mapped_column(JSON, default=list)
    avoid_json: Mapped[list] = mapped_column(JSON, default=list)
    voice: Mapped[str] = mapped_column(Text, default="")
    formats_json: Mapped[list] = mapped_column(JSON, default=list)
    evidence_rules_json: Mapped[dict] = mapped_column(JSON, default=dict)
    palette_json: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    tone: Mapped[str] = mapped_column(Text, default="")
    length_chars: Mapped[int] = mapped_column(Integer, default=900)
    frequency: Mapped[str] = mapped_column(Text, default="")
    stopwords_json: Mapped[list] = mapped_column(JSON, default=list)
    link_format: Mapped[str] = mapped_column(Text, default="")
    risks_json: Mapped[list] = mapped_column(JSON, default=list)


class EditorialClaim(Base):
    __tablename__ = "editorial_claims"
    __table_args__ = (Index("ix_claims_post_version", "post_id", "draft_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), nullable=False)
    draft_version: Mapped[int] = mapped_column(Integer, nullable=False)
    claim_id: Mapped[str] = mapped_column(String(80), nullable=False)
    text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="not_checked")
    evidence_url: Mapped[str] = mapped_column(Text, default="")
    reviewer: Mapped[str] = mapped_column(String(80), default="")
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    origin_kind: Mapped[str] = mapped_column(String(40), default="source_claim")
    method: Mapped[str] = mapped_column(String(80), default="")
    actor: Mapped[str] = mapped_column(String(80), default="")
    cluster_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    excerpt: Mapped[str] = mapped_column(String(240), default="")
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StoryRelation(Base):
    __tablename__ = "story_relations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    left_cluster_id: Mapped[int] = mapped_column(ForeignKey("story_clusters.id"), nullable=False)
    right_cluster_id: Mapped[int] = mapped_column(ForeignKey("story_clusters.id"), nullable=False)
    relation: Mapped[str] = mapped_column(String(40), default="merge_candidate")
    reason: Mapped[str] = mapped_column(Text, default="")
    actor: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MetricDefinition(Base):
    __tablename__ = "metric_definitions"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    title: Mapped[str] = mapped_column(String(160), default="")
    unit: Mapped[str] = mapped_column(String(40), default="count")
    formula: Mapped[str] = mapped_column(Text, default="")
    source_type: Mapped[str] = mapped_column(String(40), default="derived")


class MetricObservation(Base):
    __tablename__ = "metric_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    metric_id: Mapped[str] = mapped_column(ForeignKey("metric_definitions.id"), nullable=False)
    channel_id: Mapped[str] = mapped_column(String(40), default="")
    period_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_type: Mapped[str] = mapped_column(String(40), default="unknown")
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    evidence_ref: Mapped[str] = mapped_column(Text, default="")
    demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    unit: Mapped[str] = mapped_column(String(40), default="count")
    interval: Mapped[str] = mapped_column(String(40), default="snapshot")
    actor: Mapped[str] = mapped_column(String(80), default="")


class ExperimentPlan(Base):
    __tablename__ = "experiment_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    hypothesis: Mapped[str] = mapped_column(Text, default="")
    expected_metric: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(40), default="NOT_STARTED")
    actual: Mapped[str] = mapped_column(Text, default="н/д")
    decision: Mapped[str] = mapped_column(Text, default="")
    demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    segment: Mapped[str] = mapped_column(String(80), default="")
    format_id: Mapped[str] = mapped_column(String(40), default="")
    period: Mapped[str] = mapped_column(String(80), default="")
    control: Mapped[str] = mapped_column(Text, default="")
    confidence_note: Mapped[str] = mapped_column(Text, default="")


class SalesLead(Base):
    __tablename__ = "sales_leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    advertiser: Mapped[str] = mapped_column(String(200), default="")
    segment: Mapped[str] = mapped_column(String(80), default="")
    stage: Mapped[str] = mapped_column(String(40), default="lead")
    channel_id: Mapped[str] = mapped_column(String(40), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    owner: Mapped[str] = mapped_column(String(80), default="")
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    offer_version: Mapped[int] = mapped_column(Integer, default=1)
    history_json: Mapped[list] = mapped_column(JSON, default=list)
    lab_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class RateCard(Base):
    __tablename__ = "rate_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(160), default="")
    package: Mapped[str] = mapped_column(String(40), default="single")
    price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    status: Mapped[str] = mapped_column(String(40), default="draft")
    demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    channels_json: Mapped[list] = mapped_column(JSON, default=list)
    materials_count: Mapped[int] = mapped_column(Integer, default=1)


class ExpenseRecord(Base):
    __tablename__ = "expense_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), default="infra")
    amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    note: Mapped[str] = mapped_column(Text, default="")
    demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    period_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class FinanceEvent(Base):
    __tablename__ = "finance_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("ad_campaigns.id"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="planned")
    amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    note: Mapped[str] = mapped_column(Text, default="")
    demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PublisherIdentity(Base):
    __tablename__ = "publisher_identities"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    title: Mapped[str] = mapped_column(String(160), default="")
    kind: Mapped[str] = mapped_column(String(40), default="origin")
    trust: Mapped[int] = mapped_column(Integer, default=8)


class SourceSnapshot(Base):
    __tablename__ = "source_snapshots"
    __table_args__ = (Index("ix_source_snapshots_item", "source_item_id", "raw_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_item_id: Mapped[int] = mapped_column(ForeignKey("source_items.id"), nullable=False)
    raw_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    body: Mapped[dict] = mapped_column(JSON, default=dict)
    discovered_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    claimed_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    canonical_url: Mapped[str] = mapped_column(Text, default="")
    origin_mode: Mapped[str] = mapped_column(String(40), default="demo")


class EventRelation(Base):
    __tablename__ = "event_relations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    left_cluster_id: Mapped[int] = mapped_column(ForeignKey("story_clusters.id"), nullable=False)
    right_cluster_id: Mapped[int] = mapped_column(ForeignKey("story_clusters.id"), nullable=False)
    relation: Mapped[str] = mapped_column(String(40), default="related")
    reason: Mapped[str] = mapped_column(Text, default="")
    actor: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class StoryDossier(Base):
    __tablename__ = "story_dossiers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("story_clusters.id"), unique=True, nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="")
    timeline_json: Mapped[list] = mapped_column(JSON, default=list)
    entities_json: Mapped[list] = mapped_column(JSON, default=list)
    contradictions_json: Mapped[list] = mapped_column(JSON, default=list)
    unknowns_json: Mapped[list] = mapped_column(JSON, default=list)
    why_json: Mapped[dict] = mapped_column(JSON, default=dict)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    license_note: Mapped[str] = mapped_column(Text, default="")
    data_mode: Mapped[str] = mapped_column(String(20), default="demo")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class EntityMention(Base):
    __tablename__ = "entity_mentions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("story_clusters.id"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), default="product")
    name: Mapped[str] = mapped_column(String(200), default="")
    version: Mapped[str] = mapped_column(String(80), default="")
    note: Mapped[str] = mapped_column(Text, default="")


class ClaimEvidence(Base):
    __tablename__ = "claim_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_row_id: Mapped[int] = mapped_column(ForeignKey("editorial_claims.id"), index=True, nullable=False)
    source_item_id: Mapped[int | None] = mapped_column(ForeignKey("source_items.id"), nullable=True)
    url: Mapped[str] = mapped_column(Text, default="")
    excerpt: Mapped[str] = mapped_column(String(240), default="")
    publisher_id: Mapped[str] = mapped_column(String(80), default="")
    snapshot_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    method: Mapped[str] = mapped_column(String(80), default="")
    actor: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class EditorialBrief(Base):
    __tablename__ = "editorial_briefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("story_clusters.id"), index=True, nullable=False)
    channel_id: Mapped[str] = mapped_column(String(40), default="")
    angle_id: Mapped[str] = mapped_column(String(40), default="news")
    format_id: Mapped[str] = mapped_column(String(40), default="breaking_news")
    prompt_version: Mapped[str] = mapped_column(String(40), default="editorial-v4")
    notes: Mapped[str] = mapped_column(Text, default="")
    actor: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class EditorialVariant(Base):
    __tablename__ = "editorial_variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brief_id: Mapped[int] = mapped_column(ForeignKey("editorial_briefs.id"), index=True, nullable=False)
    post_id: Mapped[int | None] = mapped_column(ForeignKey("posts.id"), nullable=True)
    angle_id: Mapped[str] = mapped_column(String(40), default="")
    title: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    text_hash: Mapped[str] = mapped_column(String(64), default="")
    prompt_version: Mapped[str] = mapped_column(String(40), default="")
    agent_role: Mapped[str] = mapped_column(String(40), default="editor")
    model_config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    claim_ids_json: Mapped[list] = mapped_column(JSON, default=list)
    qa_json: Mapped[dict] = mapped_column(JSON, default=dict)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class VisualPreset(Base):
    __tablename__ = "visual_presets"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    channel_id: Mapped[str] = mapped_column(String(40), default="")
    purpose: Mapped[str] = mapped_column(String(40), default="news")
    ratio: Mapped[str] = mapped_column(String(16), default="16:9")
    theme: Mapped[str] = mapped_column(String(16), default="dark")
    palette_json: Mapped[dict] = mapped_column(JSON, default=dict)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_workflow_idempotency"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    story_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cluster_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channel_id: Mapped[str] = mapped_column(String(40), default="")
    trace_id: Mapped[str] = mapped_column(String(64), default="")
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    stage: Mapped[str] = mapped_column(String(40), default="ingest")
    status: Mapped[str] = mapped_column(String(40), default="running", index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    last_error: Mapped[str] = mapped_column(Text, default="")
    retry_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    editorial_ready: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    delivery_allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    lab_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class WorkflowStep(Base):
    __tablename__ = "workflow_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("workflow_runs.id"), index=True, nullable=False)
    stage: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="ok")
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class EditorialTask(Base):
    __tablename__ = "editorial_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), default="research")
    cluster_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channel_id: Mapped[str] = mapped_column(String(40), default="")
    title: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="open")
    assignee: Mapped[str] = mapped_column(String(80), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MetricProvenance(Base):
    __tablename__ = "metric_provenance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    observation_id: Mapped[int] = mapped_column(ForeignKey("metric_observations.id"), index=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), default="unknown")
    evidence: Mapped[str] = mapped_column(Text, default="")
    actor: Mapped[str] = mapped_column(String(80), default="")
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class CommercialOffer(Base):
    __tablename__ = "commercial_offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("sales_leads.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(40), default="draft")
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_kind: Mapped[str] = mapped_column(String(40), default="proposal")
    notes: Mapped[str] = mapped_column(Text, default="")
    demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    history_json: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    lab_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class CommercialLineItem(Base):
    __tablename__ = "commercial_line_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("commercial_offers.id"), index=True, nullable=False)
    package: Mapped[str] = mapped_column(String(40), default="single")
    channel_id: Mapped[str] = mapped_column(String(40), default="")
    materials_count: Mapped[int] = mapped_column(Integer, default=1)
    slot_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="proposed")


class LabRun(Base):
    __tablename__ = "lab_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(160), default="offline-30d")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    through_day: Mapped[int] = mapped_column(Integer, default=30)
    status: Mapped[str] = mapped_column(String(40), default="ready")
    report_json: Mapped[dict] = mapped_column(JSON, default=dict)
    data_mode: Mapped[str] = mapped_column(String(20), default="demo")


class ChannelPlanSettings(Base):
    __tablename__ = "channel_plan_settings"

    channel_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    daily_cap: Mapped[int] = mapped_column(Integer, default=2)
    quiet_start: Mapped[str] = mapped_column(String(5), default="22:00")
    quiet_end: Mapped[str] = mapped_column(String(5), default="08:00")
    mix_fresh_pct: Mapped[int] = mapped_column(Integer, default=70)
    min_gap_minutes: Mapped[int] = mapped_column(Integer, default=240)
    blackout_dates_json: Mapped[list] = mapped_column(JSON, default=list)
    theme_days_json: Mapped[list] = mapped_column(JSON, default=list)
    reserve_slots: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ScoreRevision(Base):
    __tablename__ = "score_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("story_clusters.id"), index=True, nullable=False)
    channel_id: Mapped[str] = mapped_column(String(40), default="")
    formula_version: Mapped[str] = mapped_column(String(40), default="rank-v4")
    weights_json: Mapped[dict] = mapped_column(JSON, default=dict)
    dimensions_json: Mapped[dict] = mapped_column(JSON, default=dict)
    total: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
