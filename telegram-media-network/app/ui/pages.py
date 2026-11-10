from __future__ import annotations

import html
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.deps import default_policy
from app.core.models import (
    AdCampaign,
    Channel,
    ChannelEditorialProfile,
    ClusterMember,
    CommercialOffer,
    EditorialClaim,
    EditorialTask,
    EditorialVariant,
    Episode,
    EvidenceSnapshot,
    ExpenseRecord,
    FinanceEvent,
    MediaAsset,
    Post,
    PostVersion,
    PublishingOutbox,
    RankedCandidate,
    RateCard,
    RuntimeSetting,
    SalesLead,
    Series,
    Source,
    SourceItem,
    Story,
    StoryCluster,
    StoryEvidence,
    User,
    WorkflowRun,
    WorkflowStep,
)
from app.core.timeutil import ensure_utc, utcnow
from app.media.renderer import STUDIO_PURPOSES, write_studio_pack_v3
from app.product.commercial import cancel_offer, create_offer, media_kit, reserve_offer, seed_commercial
from app.product.commercial import forecast as commercial_forecast
from app.product.demo_pack import build_pack
from app.product.drafts import materialise_desk
from app.product.editorial import ensure_profiles
from app.product.growth import board as growth_board
from app.product.growth import ensure_metrics, seed_experiments, snapshot_derived
from app.product.insights import funnel, seed_demo_campaigns
from app.product.intelligence import SOURCE_ROLES
from app.product.planning import lock_episode
from app.product.programs import move_episode, propose_fortnight
from app.product.radar import import_observations, merge_into, split_member
from app.services.accounts import AuthError, load_session, login
from app.services.dispatch import publish_preview_or_send
from app.services.moderation import approve_post, policy_from, reject_post, save_post, schedule_post

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


def _db(request: Request) -> Session:
    return request.app.state.session_factory()


def _context(request: Request, db: Session):
    raw = request.cookies.get("tmn_session")
    row = load_session(db, raw, idle_minutes=request.app.state.settings.session_idle_minutes)
    if row is None:
        return None
    user = db.get(User, row.user_id)
    if user is None:
        return None
    policy = policy_from(db, default_policy(request.app.state.settings))
    return user, row, policy


def _page(request: Request, name: str, **extra):
    db = _db(request)
    try:
        ctx = _context(request, db)
        if ctx is None:
            return RedirectResponse("/login", status_code=303)
        user, row, policy = ctx
        payload = {
            "request": request,
            "title": extra.get("title", "TMN"),
            "nav": extra.get("nav", ""),
            "policy": policy,
            "user": user,
            "csrf": row.csrf_token,
        }
        payload.update(extra)
        return templates.TemplateResponse(request, name, payload)
    finally:
        db.close()


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, error: str = "") -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {"request": request, "error": error})


@router.post("/login")
def login_submit(request: Request, username: str = Form(), password: str = Form()):
    db = _db(request)
    try:
        payload = login(db, username, password, request.app.state.limiter)
    except AuthError as exc:
        return RedirectResponse(f"/login?error={exc.detail}", status_code=303)
    finally:
        db.close()
    if payload.get("mfa_required"):
        return RedirectResponse("/login?error=mfa+required", status_code=303)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie("tmn_session", payload["token"], httponly=True, samesite="lax", path="/")
    return response


@router.post("/logout")
def logout(request: Request):
    db = _db(request)
    try:
        ctx = _context(request, db)
        if ctx is not None:
            _user, row, _policy = ctx
            row.revoked = True
            db.commit()
    finally:
        db.close()
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("tmn_session")
    return response


@router.get("/", response_class=HTMLResponse)
def overview(request: Request):
    db = _db(request)
    try:
        ctx = _context(request, db)
        if ctx is None:
            return RedirectResponse("/login", status_code=303)
        user, row, policy = ctx
        cards = []
        waiting_total = 0
        queued_total = 0
        proposed_total = db.query(Episode).filter(Episode.status.in_(("proposed", "idea"))).count()
        outbox_queued = db.query(PublishingOutbox).filter(PublishingOutbox.state.in_(("scheduled", "sending"))).count()
        for channel in db.query(Channel).order_by(Channel.id).all():
            waiting = db.query(Post).filter_by(channel_id=channel.id, review_status="NEEDS_REVIEW").count()
            queued = db.query(PublishingOutbox).filter(
                PublishingOutbox.channel_id == channel.id,
                PublishingOutbox.state.in_(("scheduled", "sending")),
            ).count()
            themes = db.query(StoryCluster).filter_by(primary_channel_id=channel.id).count()
            fresh = db.query(StoryCluster).filter_by(primary_channel_id=channel.id, list_name="hot").count()
            covered_days = {
                ensure_utc(item.slot_utc).date()
                for item in db.query(Episode).filter_by(channel_id=channel.id)
                if item.slot_utc is not None
            }
            profile = db.get(ChannelEditorialProfile, channel.id)
            waiting_total += waiting
            queued_total += queued
            cards.append(
                {
                    "id": channel.id,
                    "title": channel.title,
                    "category": channel.category,
                    "queued": queued,
                    "waiting": waiting,
                    "publish_enabled": channel.publish_enabled,
                    "health": "локально",
                    "themes": themes,
                    "fresh": fresh,
                    "free_slots": max(0, 28 - len(covered_days)),
                    "promise": profile.promise if profile else channel.voice,
                    "audience": profile.audience if profile else channel.voice,
                    "proposed": db.query(Episode).filter_by(channel_id=channel.id, status="proposed").count(),
                }
            )
        collisions = sum(
            1 for ranked in db.query(RankedCandidate) if (ranked.penalties_json or {}).get("duplicate_across_network")
        )
        fresh_events = db.query(StoryCluster).filter(StoryCluster.list_name.in_(("hot", "review"))).order_by(StoryCluster.id.desc()).limit(5).all()
        tasks = db.query(EditorialTask).filter_by(status="open").order_by(EditorialTask.id.desc()).limit(5).all()
        return templates.TemplateResponse(
            request,
            "overview.html",
            {
                "request": request,
                "title": "Моя смена",
                "nav": "overview",
                "policy": policy,
                "csrf": row.csrf_token,
                "cards": cards,
                "user": user,
                "waiting_total": waiting_total,
                "queued_total": queued_total,
                "proposed_total": proposed_total,
                "outbox_queued": outbox_queued,
                "collisions": collisions,
                "fresh_events": fresh_events,
                "shift_tasks": tasks,
            },
        )
    finally:
        db.close()


@router.get("/inbox", response_class=HTMLResponse)
def inbox(request: Request, channel: str = ""):
    db = _db(request)
    try:
        ctx = _context(request, db)
        if ctx is None:
            return RedirectResponse("/login", status_code=303)
        user, row, policy = ctx
        query = db.query(Story).order_by(Story.id.desc())
        if channel:
            query = query.filter(Story.primary_channel_id == channel)
        rows = []
        for story in query.limit(100):
            post = db.query(Post).filter_by(story_id=story.id).order_by(Post.id.desc()).first()
            rows.append(
                {
                    "title": story.title,
                    "channel": story.primary_channel_id,
                    "score": story.score_total,
                    "status": story.status,
                    "block": story.hard_block_reason,
                    "post_id": post.id if post else None,
                }
            )
        return templates.TemplateResponse(
            request,
            "inbox.html",
            {
                "request": request,
                "title": "Лента",
                "nav": "inbox",
                "policy": policy,
                "csrf": row.csrf_token,
                "rows": rows,
                "channels": db.query(Channel).order_by(Channel.title).all(),
                "selected": channel,
                "user": user,
            },
        )
    finally:
        db.close()


@router.get("/review/{post_id}", response_class=HTMLResponse)
def review(request: Request, post_id: int, notice: str = ""):
    db = _db(request)
    try:
        ctx = _context(request, db)
        if ctx is None:
            return RedirectResponse("/login", status_code=303)
        user, row, policy = ctx
        post = db.get(Post, post_id)
        if post is None:
            raise HTTPException(status_code=404, detail="not found")
        story = db.get(Story, post.story_id)
        facts = db.query(StoryEvidence).filter_by(story_id=story.id).all() if story else []
        from app.core.models import ScoreEvent

        score = db.query(ScoreEvent).filter_by(story_id=story.id).order_by(ScoreEvent.id.desc()).first() if story else None
        image = (
            db.query(MediaAsset)
            .filter_by(
                post_id=post.id,
                kind="card",
                status="ready",
                draft_version=post.draft_version,
                content_hash=post.final_hash,
            )
            .order_by(MediaAsset.id.desc())
            .first()
        )
        cluster = db.query(StoryCluster).filter_by(cluster_key=story.cluster_id).one_or_none() if story else None
        explanation = ""
        if cluster is not None:
            rank = (
                db.query(RankedCandidate)
                .filter_by(cluster_id=cluster.id, channel_id=post.channel_id)
                .order_by(RankedCandidate.id.desc())
                .first()
            )
            explanation = "" if rank is None else rank.explanation
        versions = db.query(PostVersion).filter_by(post_id=post.id).order_by(PostVersion.version).all()
        snapshots = db.query(EvidenceSnapshot).filter_by(post_id=post.id).order_by(EvidenceSnapshot.id).all()
        claims = db.query(EditorialClaim).filter_by(post_id=post.id, draft_version=post.draft_version).all()
        variants = db.query(EditorialVariant).filter_by(post_id=post.id).order_by(EditorialVariant.id).all()
        return templates.TemplateResponse(
            request,
            "review.html",
            {
                "request": request,
                "title": "Редакция",
                "nav": "posts",
                "policy": policy,
                "csrf": row.csrf_token,
                "user": user,
                "post": post,
                "story": story,
                "facts": facts,
                "scores": score,
                "channels": db.query(Channel).order_by(Channel.title).all(),
                "image": image.file_path if image else "",
                "notice": notice,
                "explanation": explanation,
                "versions": versions,
                "snapshots": snapshots,
                "claims": claims,
                "quality": post.quality_json or {},
                "variants": variants,
            },
        )
    finally:
        db.close()


def _review_actor(request: Request):
    db = _db(request)
    ctx = _context(request, db)
    if ctx is None:
        db.close()
        return None
    return db, ctx


@router.post("/review/{post_id}/save")
def review_save(
    request: Request,
    post_id: int,
    csrf_token: str = Form(),
    version: int = Form(),
    title: str = Form(),
    body: str = Form(),
    channel_id: str = Form(),
):
    opened = _review_actor(request)
    if opened is None:
        return RedirectResponse("/login", status_code=303)
    db, (user, row, _policy) = opened
    try:
        if csrf_token != row.csrf_token:
            raise HTTPException(status_code=403, detail="csrf failed")
        post = db.get(Post, post_id)
        save_post(
            db,
            post,
            user,
            title=title,
            body=body,
            channel_id=channel_id,
            expected_version=version,
            media_dir=Path(request.app.state.settings.media_dir),
        )
    finally:
        db.close()
    return RedirectResponse(f"/review/{post_id}", status_code=303)


@router.post("/review/{post_id}/approve")
def review_approve(request: Request, post_id: int, csrf_token: str = Form(), confirm: str = Form(default="")):
    return _review_action(request, post_id, csrf_token, confirm, "approve")


@router.post("/review/{post_id}/reject")
def review_reject(
    request: Request,
    post_id: int,
    csrf_token: str = Form(),
    confirm: str = Form(default=""),
    reason: str = Form(default=""),
):
    return _review_action(request, post_id, csrf_token, confirm, "reject", reason)


@router.post("/review/{post_id}/schedule")
def review_schedule(
    request: Request,
    post_id: int,
    csrf_token: str = Form(),
    confirm: str = Form(default=""),
    due_utc: str = Form(),
):
    return _review_action(request, post_id, csrf_token, confirm, "schedule", due_utc)


@router.post("/review/{post_id}/publish")
def review_publish(request: Request, post_id: int, csrf_token: str = Form(), confirm: str = Form(default="")):
    return _review_action(request, post_id, csrf_token, confirm, "publish")


def _review_action(request: Request, post_id: int, csrf_token: str, confirm: str, action: str, extra: str = ""):
    opened = _review_actor(request)
    if opened is None:
        return RedirectResponse("/login", status_code=303)
    db, (user, row, policy) = opened
    notice = "ok"
    try:
        if csrf_token != row.csrf_token:
            notice = "csrf"
        elif confirm != "yes":
            notice = "нужно подтверждение"
        else:
            post = db.get(Post, post_id)
            try:
                if action == "approve":
                    approve_post(db, post, user, confirmed=True)
                    notice = "Решение записано. Сообщение не отправлено."
                elif action == "reject":
                    reject_post(db, post, user, reason=extra or "отклонено в интерфейсе", confirmed=True)
                    notice = "Материал отклонён."
                elif action == "schedule":
                    due = datetime.fromisoformat(extra)
                    schedule_post(db, post, user, due=due, confirmed=True, now=utcnow())
                    notice = "Слот записан. Сообщение не отправлено."
                elif action == "publish":
                    result = publish_preview_or_send(
                        db, post, user, policy, request.app.state.telegram_transport, confirmed=True
                    )
                    notice = (
                        "Это предпросмотр. Запрос в Telegram не отправлялся."
                        if result.get("mode") == "dry_run"
                        else result.get("state", "ok")
                    )
            except AuthError as exc:
                notice = exc.detail
    finally:
        db.close()
    return RedirectResponse(f"/review/{post_id}?notice={notice}", status_code=303)


@router.get("/calendar", response_class=HTMLResponse)
def calendar(request: Request, notice: str = "", days: int = 28):
    db = _db(request)
    try:
        ctx = _context(request, db)
        if ctx is None:
            return RedirectResponse("/login", status_code=303)
        user, row, policy = ctx
        from zoneinfo import ZoneInfo

        moscow = ZoneInfo("Europe/Moscow")
        horizon = 7 if days == 7 else 28
        start = utcnow().astimezone(moscow).date()
        grid_days = [start + timedelta(days=offset) for offset in range(horizon)]
        episodes = []
        by_key: dict[tuple[str, str], dict] = {}
        for episode in db.query(Episode).order_by(Episode.slot_utc).limit(400):
            local = ensure_utc(episode.slot_utc).astimezone(moscow)
            day_key = local.date().isoformat()
            payload = {
                "id": episode.id,
                "series_id": episode.series_id,
                "channel_id": episode.channel_id,
                "status": episode.status,
                "version": episode.version,
                "locked": episode.locked,
                "program_kind": episode.program_kind,
                "label": local.strftime("%Y-%m-%d %H:%M"),
                "day": day_key,
            }
            episodes.append(payload)
            by_key[(episode.channel_id, day_key)] = payload
        channels = db.query(Channel).order_by(Channel.id).all()
        grid = []
        for channel in channels:
            cells = []
            for day in grid_days:
                found = by_key.get((channel.id, day.isoformat()))
                cells.append({"episode": found, "reason": "" if found else "нет материала"})
            grid.append({"channel": channel.title, "cells": cells})
        drop = utcnow().replace(minute=0, second=0, microsecond=0)
        return templates.TemplateResponse(
            request,
            "calendar.html",
            {
                "request": request,
                "title": "Календарь",
                "nav": "calendar",
                "policy": policy,
                "csrf": row.csrf_token,
                "user": user,
                "episodes": episodes,
                "drop_slot": drop.isoformat(),
                "drop_label": drop.astimezone(moscow).strftime("%Y-%m-%d %H:%M MSK"),
                "notice": notice,
                "days": horizon,
                "day_headers": [day.strftime("%d.%m") for day in grid_days],
                "grid": grid,
            },
        )
    finally:
        db.close()


@router.get("/sources", response_class=HTMLResponse)
def sources(request: Request):
    db = _db(request)
    try:
        ctx = _context(request, db)
        if ctx is None:
            return RedirectResponse("/login", status_code=303)
        lines = [
            '<div class="scroll"><table><tr><th>Источник</th><th>Состояние</th><th>Включён</th><th>Интервал</th><th>Ошибки подряд</th><th>Роль</th><th>Последняя ошибка</th></tr>'
        ]
        for source in db.query(Source).order_by(Source.id):
            role, trust, label = SOURCE_ROLES.get(source.id, ("unknown", 8, "роль не задана"))
            lines.append(
                "<tr>"
                f"<td>{html.escape(source.id)}</td>"
                f"<td>{html.escape(source.health)}</td>"
                f"<td>{'да' if source.enabled else 'нет'}</td>"
                f"<td>{source.poll_interval_minutes} мин</td>"
                f"<td>{source.consecutive_failures}</td>"
                f"<td>{html.escape(label)} · вес {trust} · {html.escape(role)}</td>"
                f"<td>{html.escape(source.last_error or '—')}</td>"
                "</tr>"
            )
        lines.append("</table></div>")
        note = "Живой опрос выключен, пока SOURCE_MODE не равен live. Вес доверия — роль источника, не истина."
        return _simple(request, ctx, "Источники", "sources", note, "".join(lines))
    finally:
        db.close()


@router.get("/posts", response_class=HTMLResponse)
def posts(request: Request, channel: str = ""):
    db = _db(request)
    try:
        ctx = _context(request, db)
        if ctx is None:
            return RedirectResponse("/login", status_code=303)
        user, row, policy = ctx
        query = db.query(Post).order_by(Post.id.desc())
        if channel:
            query = query.filter(Post.channel_id == channel)
        return templates.TemplateResponse(
            request,
            "posts.html",
            {
                "request": request,
                "title": "Редакция",
                "nav": "posts",
                "policy": policy,
                "csrf": row.csrf_token,
                "user": user,
                "posts": query.limit(100).all(),
                "channels": db.query(Channel).order_by(Channel.title).all(),
                "selected": channel,
            },
        )
    finally:
        db.close()


@router.get("/analytics", response_class=HTMLResponse)
def analytics(request: Request):
    db = _db(request)
    try:
        ctx = _context(request, db)
        if ctx is None:
            return RedirectResponse("/login", status_code=303)
        user, row, policy = ctx
        return templates.TemplateResponse(
            request,
            "analytics.html",
            {
                "request": request,
                "title": "Аналитика",
                "nav": "analytics",
                "policy": policy,
                "csrf": row.csrf_token,
                "user": user,
                "report": funnel(db),
                "board": growth_board(db),
            },
        )
    finally:
        db.close()


@router.get("/commercial", response_class=HTMLResponse)
def commercial(request: Request):
    db = _db(request)
    try:
        ctx = _context(request, db)
        if ctx is None:
            return RedirectResponse("/login", status_code=303)
        user, row, policy = ctx
        rows = []
        for campaign in db.query(AdCampaign).order_by(AdCampaign.id):
            actual = db.query(FinanceEvent).filter_by(campaign_id=campaign.id, kind="actual").order_by(FinanceEvent.id.desc()).first()
            rows.append(
                {
                    "advertiser": campaign.advertiser,
                    "channel_id": campaign.channel_id,
                    "demo": campaign.demo,
                    "legal_status": campaign.legal_status,
                    "actual": None if actual is None else actual.amount,
                }
            )
        leads = db.query(SalesLead).order_by(SalesLead.id).all()
        pipeline: dict[str, list] = {name: [] for name in ("lead", "contact", "discussion", "offer", "won", "lost")}
        for lead in leads:
            pipeline.setdefault(lead.stage, []).append(lead)
        offers = db.query(CommercialOffer).order_by(CommercialOffer.id.desc()).all()
        return templates.TemplateResponse(
            request,
            "commercial.html",
            {
                "request": request,
                "title": "Коммерция",
                "nav": "commercial",
                "policy": policy,
                "csrf": row.csrf_token,
                "user": user,
                "campaigns": rows,
                "leads": leads,
                "offers": offers,
                "pipeline": pipeline,
                "rates": db.query(RateCard).order_by(RateCard.id).all(),
                "expenses": db.query(ExpenseRecord).order_by(ExpenseRecord.id).all(),
                "kit": media_kit(db),
                "forecast": commercial_forecast(db),
            },
        )
    finally:
        db.close()


@router.get("/system", response_class=HTMLResponse)
def system(request: Request):
    db = _db(request)
    try:
        ctx = _context(request, db)
        if ctx is None:
            return RedirectResponse("/login", status_code=303)
        user, _row, policy = ctx
        flags = db.query(RuntimeSetting).filter(RuntimeSetting.key.like("FEATURE_%")).order_by(RuntimeSetting.key).all()
        flag_lines = "".join(
            f"<li>{html.escape(item.key)}: {'включён в интерфейсе' if (item.value_json or {}).get('value') else 'выключен'}</li>"
            for item in flags
        )
        from app.product.pilot import status as pilot_status

        matrix = pilot_status()
        body = (
            "<ul><li><a href=\"/api/v1/export/config.json\">Конфигурация JSON</a></li>"
            "<li><a href=\"/api/v1/export/audit.csv\">Аудит CSV</a></li>"
            "<li><a href=\"/api/v1/export/audit.json\">Аудит JSON</a></li></ul>"
            f"<ul>{flag_lines}</ul>"
            "<p>Флаги интерфейса не включают сеть и не включают отправку. Секреты в выгрузку не входят.</p>"
            "<p>Рекламный контур остаётся выключенным. Запрос на включение отклоняется.</p>"
            f"<p>Пилот: {html.escape(matrix['active'])}. Telegram send = {matrix['telegram_send']}. Production ready = нет.</p>"
        )
        note = ""
        if user.role == "OWNER":
            state = "включён" if policy.kill_switch else "выключен"
            note = f"Kill switch {state}. Его видит только OWNER. Эта сборка не отправляет сообщения в Telegram."
        return _simple(request, ctx, "Система", "system", note, body)
    finally:
        db.close()


@router.get("/radar", response_class=HTMLResponse)
def radar_page(request: Request, channel: str = "", status: str = "", q: str = ""):
    db = _db(request)
    try:
        ctx = _context(request, db)
        if ctx is None:
            return RedirectResponse("/login", status_code=303)
        user, row, policy = ctx
        query = db.query(StoryCluster)
        if channel:
            query = query.filter(StoryCluster.primary_channel_id == channel)
        if status:
            query = query.filter(StoryCluster.list_name == status)
        if q:
            query = query.filter(StoryCluster.title.ilike(f"%{q[:80]}%"))
        rows = []
        for cluster in query.order_by(StoryCluster.id).limit(40):
            rank = (
                db.query(RankedCandidate)
                .filter_by(cluster_id=cluster.id, channel_id=cluster.primary_channel_id)
                .order_by(RankedCandidate.id.desc())
                .first()
            )
            member = (
                db.query(ClusterMember)
                .filter_by(cluster_id=cluster.id, relation="member")
                .filter(ClusterMember.story_id.is_not(None))
                .order_by(ClusterMember.id)
                .first()
            )
            post = None
            if member is not None and member.story_id is not None:
                post = db.query(Post).filter_by(story_id=member.story_id, channel_id=cluster.primary_channel_id).first()
            member_row = (
                db.query(ClusterMember)
                .filter_by(cluster_id=cluster.id, relation="member")
                .order_by(ClusterMember.id)
                .first()
            )
            source_id = ""
            if member_row is not None and member_row.source_item_id:
                item = db.get(SourceItem, member_row.source_item_id)
                source_id = item.source_id if item is not None else ""
            trust = SOURCE_ROLES.get(source_id, ("unknown", 8, "роль не задана"))[2]
            rows.append(
                {
                    "id": cluster.id,
                    "title": cluster.title,
                    "channel_id": cluster.primary_channel_id,
                    "list_name": cluster.list_name,
                    "score": None if rank is None else rank.rank_score,
                    "confidence": None if rank is None else rank.confidence,
                    "evidence_state": "" if rank is None else rank.status,
                    "explanation": "" if rank is None else rank.explanation,
                    "post_id": None if post is None else post.id,
                    "member_id": None if member_row is None else member_row.id,
                    "trust": trust,
                    "trend": "н/д" if cluster.trend_state == "unknown" else f"{cluster.trend_state} Δ{cluster.trend_delta}",
                    "reasons": list((rank.reasons_json or [])[:3]) if rank is not None else [],
                    "data_mode": cluster.data_mode or "demo",
                }
            )
        return templates.TemplateResponse(
            request,
            "radar.html",
            {
                "request": request,
                "title": "Радар",
                "nav": "radar",
                "policy": policy,
                "csrf": row.csrf_token,
                "user": user,
                "channels": db.query(Channel).order_by(Channel.title).all(),
                "selected": channel,
                "selected_list": status,
                "lists": ["hot", "review", "evergreen", "backfill", "rejected", "covered"],
                "query": q,
                "rows": rows,
            },
        )
    finally:
        db.close()


@router.get("/studio", response_class=HTMLResponse)
def studio(request: Request):
    db = _db(request)
    try:
        ctx = _context(request, db)
        if ctx is None:
            return RedirectResponse("/login", status_code=303)
        user, row, policy = ctx
        channels = db.query(Channel).order_by(Channel.id).all()
        directory = Path(request.app.state.settings.media_dir)
        write_studio_pack_v3(directory, channels)
        cards = [
            {"channel": channel.title, "template": purpose, "file": f"{channel.id}-{purpose}.jpg"}
            for channel in channels
            for purpose in STUDIO_PURPOSES
        ]
        return templates.TemplateResponse(
            request,
            "studio.html",
            {
                "request": request,
                "title": "Студия",
                "nav": "studio",
                "policy": policy,
                "csrf": row.csrf_token,
                "user": user,
                "cards": cards,
            },
        )
    finally:
        db.close()


@router.get("/programs", response_class=HTMLResponse)
def programs(request: Request):
    db = _db(request)
    try:
        ctx = _context(request, db)
        if ctx is None:
            return RedirectResponse("/login", status_code=303)
        user, row, policy = ctx
        return templates.TemplateResponse(
            request,
            "programs.html",
            {
                "request": request,
                "title": "Программы",
                "nav": "programs",
                "policy": policy,
                "csrf": row.csrf_token,
                "user": user,
                "programs": db.query(Series).order_by(Series.id).all(),
            },
        )
    finally:
        db.close()


@router.post("/demo/load")
def demo_load(request: Request, csrf_token: str = Form()):
    opened = _review_actor(request)
    if opened is None:
        return RedirectResponse("/login", status_code=303)
    db, (user, row, _policy) = opened
    try:
        if csrf_token != row.csrf_token or user.role != "OWNER":
            return RedirectResponse("/", status_code=303)
        moment = utcnow()
        import_observations(db, build_pack(), moment)
        ensure_profiles(db)
        materialise_desk(db)
        propose_fortnight(db, moment)
        seed_demo_campaigns(db, moment)
        seed_commercial(db, moment)
        ensure_metrics(db)
        seed_experiments(db)
        snapshot_derived(db, moment, demo=True)
    finally:
        db.close()
    return RedirectResponse("/radar", status_code=303)


@router.get("/quality", response_class=HTMLResponse)
def quality_page(request: Request):
    db = _db(request)
    try:
        ctx = _context(request, db)
        if ctx is None:
            return RedirectResponse("/login", status_code=303)
        user, row, policy = ctx
        blocking = []
        for post in db.query(Post).order_by(Post.id.desc()).limit(80):
            reasons = (post.quality_json or {}).get("blocking") or []
            if reasons:
                blocking.append({"id": post.id, "title": post.title, "channel_id": post.channel_id, "reasons": ", ".join(reasons)})
        claims = db.query(EditorialClaim).order_by(EditorialClaim.id.desc()).limit(40).all()
        unclear = db.query(EditorialClaim).filter(EditorialClaim.status.in_(("not_checked", "unclear", "contradicted"))).count()
        stale = db.query(MediaAsset).filter_by(status="stale").count()
        return templates.TemplateResponse(
            request,
            "quality.html",
            {
                "request": request,
                "title": "Качество",
                "nav": "quality",
                "policy": policy,
                "csrf": row.csrf_token,
                "user": user,
                "blocking": blocking,
                "claims": claims,
                "unclear": unclear,
                "stale": stale,
            },
        )
    finally:
        db.close()


@router.post("/radar/merge")
def radar_merge_form(
    request: Request,
    csrf_token: str = Form(),
    source_id: int = Form(default=0),
    target_id: int = Form(default=0),
    reason: str = Form(),
    cluster_ids: list[int] = Form(default=[]),
):
    opened = _review_actor(request)
    if opened is None:
        return RedirectResponse("/login", status_code=303)
    db, (user, row, _policy) = opened
    try:
        if csrf_token != row.csrf_token or user.role not in {"OWNER", "EDITOR"}:
            return RedirectResponse("/radar", status_code=303)
        selected = [item for item in cluster_ids if item]
        if len(selected) >= 2:
            target, *rest = selected
            for source in rest:
                merge_into(db, source, target, user.username, reason)
        elif source_id and target_id:
            merge_into(db, source_id, target_id, user.username, reason)
        db.commit()
    except ValueError:
        db.rollback()
    finally:
        db.close()
    return RedirectResponse("/radar", status_code=303)


@router.post("/radar/split")
def radar_split_form(
    request: Request,
    csrf_token: str = Form(),
    cluster_id: int = Form(),
    member_id: int = Form(),
    reason: str = Form(),
):
    opened = _review_actor(request)
    if opened is None:
        return RedirectResponse("/login", status_code=303)
    db, (user, row, _policy) = opened
    try:
        if csrf_token != row.csrf_token or user.role not in {"OWNER", "EDITOR"}:
            return RedirectResponse("/radar", status_code=303)
        split_member(db, cluster_id, member_id, user.username, reason)
        db.commit()
    except ValueError:
        db.rollback()
    finally:
        db.close()
    return RedirectResponse("/radar", status_code=303)


@router.post("/radar/reject")
def radar_reject_form(request: Request, csrf_token: str = Form(), cluster_id: int = Form(), reason: str = Form(default="не подходит")):
    opened = _review_actor(request)
    if opened is None:
        return RedirectResponse("/login", status_code=303)
    db, (user, row, _policy) = opened
    try:
        if csrf_token == row.csrf_token and user.role in {"OWNER", "EDITOR"}:
            cluster = db.get(StoryCluster, cluster_id)
            if cluster is not None:
                cluster.list_name = "rejected"
                cluster.status = "rejected"
                cluster.manual_override = True
                cluster.merge_reason = reason[:500]
                db.commit()
    finally:
        db.close()
    return RedirectResponse("/radar", status_code=303)


@router.get("/dossier/{cluster_id}", response_class=HTMLResponse)
def dossier_page(request: Request, cluster_id: int):
    db = _db(request)
    try:
        ctx = _context(request, db)
        if ctx is None:
            return RedirectResponse("/login", status_code=303)
        user, row, policy = ctx
        cluster = db.get(StoryCluster, cluster_id)
        if cluster is None:
            raise HTTPException(status_code=404, detail="not found")
        from app.product.dossier import dossier_payload

        payload = dossier_payload(db, cluster)
        rank = (
            db.query(RankedCandidate)
            .filter_by(cluster_id=cluster.id, channel_id=cluster.primary_channel_id)
            .order_by(RankedCandidate.id.desc())
            .first()
        )
        member = db.query(ClusterMember).filter_by(cluster_id=cluster.id, relation="member").order_by(ClusterMember.id).first()
        post = db.query(Post).filter_by(channel_id=cluster.primary_channel_id).order_by(Post.id.desc()).first()
        return templates.TemplateResponse(
            request,
            "dossier.html",
            {
                "request": request,
                "title": "Досье",
                "nav": "radar",
                "policy": policy,
                "csrf": row.csrf_token,
                "user": user,
                "cluster": cluster,
                "dossier": payload,
                "rank": rank,
                "member_id": None if member is None else member.id,
                "post_id": None if post is None else post.id,
            },
        )
    finally:
        db.close()


@router.get("/passport/{channel_id}", response_class=HTMLResponse)
def passport_page(request: Request, channel_id: str):
    db = _db(request)
    try:
        ctx = _context(request, db)
        if ctx is None:
            return RedirectResponse("/login", status_code=303)
        user, row, policy = ctx
        profile = db.get(ChannelEditorialProfile, channel_id)
        channel = db.get(Channel, channel_id)
        if channel is None:
            raise HTTPException(status_code=404, detail="not found")
        return templates.TemplateResponse(
            request,
            "passport.html",
            {
                "request": request,
                "title": "Паспорт редакции",
                "nav": "overview",
                "policy": policy,
                "csrf": row.csrf_token,
                "user": user,
                "channel": channel,
                "profile": profile,
            },
        )
    finally:
        db.close()


@router.post("/passport/{channel_id}")
def passport_save(
    request: Request,
    channel_id: str,
    csrf_token: str = Form(),
    audience: str = Form(),
    promise: str = Form(),
    tone: str = Form(default=""),
    frequency: str = Form(default=""),
):
    opened = _review_actor(request)
    if opened is None:
        return RedirectResponse("/login", status_code=303)
    db, (user, row, _policy) = opened
    try:
        if csrf_token == row.csrf_token and user.role in {"OWNER", "EDITOR"}:
            profile = db.get(ChannelEditorialProfile, channel_id)
            if profile is not None:
                profile.audience = audience[:500]
                profile.promise = promise[:500]
                profile.tone = tone[:300]
                profile.frequency = frequency[:200]
                profile.version = int(profile.version or 1) + 1
                db.commit()
    finally:
        db.close()
    return RedirectResponse(f"/passport/{channel_id}", status_code=303)


@router.get("/autopilot", response_class=HTMLResponse)
def autopilot_page(request: Request):
    db = _db(request)
    try:
        ctx = _context(request, db)
        if ctx is None:
            return RedirectResponse("/login", status_code=303)
        user, row, policy = ctx
        from app.product.workflow import board as workflow_board

        panel = workflow_board(db)
        return templates.TemplateResponse(
            request,
            "autopilot.html",
            {
                "request": request,
                "title": "Автопилот",
                "nav": "autopilot",
                "policy": policy,
                "csrf": row.csrf_token,
                "user": user,
                "runs": panel["runs"],
                "tasks": panel["tasks"],
            },
        )
    finally:
        db.close()


@router.get("/autopilot/{run_id}", response_class=HTMLResponse)
def autopilot_lineage(request: Request, run_id: int):
    db = _db(request)
    try:
        ctx = _context(request, db)
        if ctx is None:
            return RedirectResponse("/login", status_code=303)
        user, row, policy = ctx
        run = db.get(WorkflowRun, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="not found")
        from app.product.workflow import lineage as workflow_lineage

        trail = workflow_lineage(db, run)
        steps = db.query(WorkflowStep).filter_by(run_id=run.id).order_by(WorkflowStep.id).all()
        return templates.TemplateResponse(
            request,
            "lineage.html",
            {
                "request": request,
                "title": f"Конвейер {run.id}",
                "nav": "autopilot",
                "policy": policy,
                "csrf": row.csrf_token,
                "user": user,
                "run": run,
                "trail": trail,
                "steps": steps,
            },
        )
    finally:
        db.close()


@router.post("/autopilot/pause")
def autopilot_pause_form(request: Request, csrf_token: str = Form(), run_id: int = Form()):
    opened = _review_actor(request)
    if opened is None:
        return RedirectResponse("/login", status_code=303)
    db, (user, row, _policy) = opened
    try:
        if csrf_token == row.csrf_token and user.role in {"OWNER", "EDITOR"}:
            run = db.get(WorkflowRun, run_id)
            if run is not None:
                from app.product.workflow import pause_run

                pause_run(db, run, user.username)
                db.commit()
    finally:
        db.close()
    return RedirectResponse("/autopilot", status_code=303)


@router.post("/autopilot/resume")
def autopilot_resume_form(request: Request, csrf_token: str = Form(), run_id: int = Form()):
    opened = _review_actor(request)
    if opened is None:
        return RedirectResponse("/login", status_code=303)
    db, (user, row, _policy) = opened
    try:
        if csrf_token == row.csrf_token and user.role in {"OWNER", "EDITOR"}:
            run = db.get(WorkflowRun, run_id)
            if run is not None:
                from app.product.workflow import resume_run

                resume_run(db, run, user.username)
                db.commit()
    finally:
        db.close()
    return RedirectResponse("/autopilot", status_code=303)


@router.post("/commercial/offer")
def commercial_offer_form(
    request: Request,
    csrf_token: str = Form(),
    lead_id: int = Form(),
    title: str = Form(),
    package: str = Form(default="single"),
    channel_id: str = Form(default=""),
):
    opened = _review_actor(request)
    if opened is None:
        return RedirectResponse("/login", status_code=303)
    db, (user, row, _policy) = opened
    try:
        if csrf_token == row.csrf_token and user.role == "OWNER":
            lead = db.get(SalesLead, lead_id)
            if lead is not None:
                create_offer(db, lead, title=title, package=package, channel_id=channel_id, actor=user.username)
                db.commit()
    finally:
        db.close()
    return RedirectResponse("/commercial", status_code=303)


@router.post("/commercial/reserve")
def commercial_reserve_form(
    request: Request,
    csrf_token: str = Form(),
    offer_id: int = Form(),
    slot_utc: str = Form(),
):
    opened = _review_actor(request)
    if opened is None:
        return RedirectResponse("/login", status_code=303)
    db, (user, row, _policy) = opened
    try:
        if csrf_token == row.csrf_token and user.role == "OWNER":
            offer = db.get(CommercialOffer, offer_id)
            if offer is not None:
                reserve_offer(db, offer, datetime.fromisoformat(slot_utc), user.username)
                db.commit()
    finally:
        db.close()
    return RedirectResponse("/commercial", status_code=303)


@router.post("/commercial/cancel")
def commercial_cancel_form(request: Request, csrf_token: str = Form(), offer_id: int = Form()):
    opened = _review_actor(request)
    if opened is None:
        return RedirectResponse("/login", status_code=303)
    db, (user, row, _policy) = opened
    try:
        if csrf_token == row.csrf_token and user.role == "OWNER":
            offer = db.get(CommercialOffer, offer_id)
            if offer is not None:
                cancel_offer(db, offer, user.username)
                db.commit()
    finally:
        db.close()
    return RedirectResponse("/commercial", status_code=303)


@router.get("/lab", response_class=HTMLResponse)
def lab_page(request: Request):
    db = _db(request)
    try:
        ctx = _context(request, db)
        if ctx is None:
            return RedirectResponse("/login", status_code=303)
        user, row, policy = ctx
        from app.product.lab import export_lab

        report = export_lab(db)
        return templates.TemplateResponse(
            request,
            "lab.html",
            {
                "request": request,
                "title": "Лаборатория",
                "nav": "lab",
                "policy": policy,
                "csrf": row.csrf_token,
                "user": user,
                "report": report,
            },
        )
    finally:
        db.close()


@router.post("/lab/load")
def lab_load_form(request: Request, csrf_token: str = Form()):
    opened = _review_actor(request)
    if opened is None:
        return RedirectResponse("/login", status_code=303)
    db, (user, row, _policy) = opened
    try:
        if csrf_token == row.csrf_token and user.role == "OWNER":
            from app.product.lab import load_lab

            load_lab(db, through_day=30, actor=user.username, mode="historical-small")
    finally:
        db.close()
    return RedirectResponse("/lab", status_code=303)


@router.get("/shift", response_class=HTMLResponse)
def shift_page(request: Request):
    db = _db(request)
    try:
        ctx = _context(request, db)
        if ctx is None:
            return RedirectResponse("/login", status_code=303)
        user, row, policy = ctx
        fresh = db.query(StoryCluster).filter(StoryCluster.list_name.in_(("hot", "review"))).order_by(StoryCluster.id.desc()).limit(8).all()
        tasks = db.query(EditorialTask).filter_by(status="open").order_by(EditorialTask.id.desc()).limit(8).all()
        empties = db.query(EditorialTask).filter(EditorialTask.reason.ilike("%слот пуст%")).limit(8).all()
        return templates.TemplateResponse(
            request,
            "shift.html",
            {
                "request": request,
                "title": "Моя смена",
                "nav": "overview",
                "policy": policy,
                "csrf": row.csrf_token,
                "user": user,
                "fresh": fresh,
                "tasks": tasks,
                "empties": empties,
            },
        )
    finally:
        db.close()


@router.post("/calendar/lock")
def calendar_lock_form(request: Request, csrf_token: str = Form(), episode_id: int = Form()):
    opened = _review_actor(request)
    if opened is None:
        return RedirectResponse("/login", status_code=303)
    db, (user, row, _policy) = opened
    try:
        if csrf_token == row.csrf_token and user.role in {"OWNER", "EDITOR"}:
            episode = db.get(Episode, episode_id)
            if episode is not None:
                lock_episode(db, episode, user.username)
    finally:
        db.close()
    return RedirectResponse("/calendar", status_code=303)


@router.post("/calendar/move")
def calendar_move(
    request: Request,
    csrf_token: str = Form(),
    episode_id: int = Form(),
    slot_utc: str = Form(),
    expected_version: int = Form(),
):
    opened = _review_actor(request)
    if opened is None:
        return RedirectResponse("/login", status_code=303)
    db, (user, row, _policy) = opened
    notice = "слот обновлён"
    try:
        if csrf_token != row.csrf_token or user.role not in {"OWNER", "EDITOR"}:
            notice = "нет права"
        else:
            episode = db.get(Episode, episode_id)
            if episode is None:
                notice = "выпуск не найден"
            else:
                try:
                    move_episode(db, episode, datetime.fromisoformat(slot_utc), expected_version)
                except ValueError as exc:
                    notice = str(exc)
    finally:
        db.close()
    return RedirectResponse(f"/calendar?notice={notice}", status_code=303)


@router.get("/media/{name}")
def media(request: Request, name: str):
    db = _db(request)
    try:
        ctx = _context(request, db)
        if ctx is None:
            raise HTTPException(status_code=401, detail="authentication required")
        root = Path(request.app.state.settings.media_dir).resolve()
        path = (root / name).resolve()
        if path.parent != root or not path.is_file():
            raise HTTPException(status_code=404, detail="not found")
        return FileResponse(path)
    finally:
        db.close()


def _simple(request, ctx, heading: str, nav: str, note: str, body: str):
    user, row, policy = ctx
    return templates.TemplateResponse(
        request,
        "simple.html",
        {
            "request": request,
            "title": heading,
            "heading": heading,
            "nav": nav,
            "policy": policy,
            "csrf": row.csrf_token,
            "user": user,
            "note": note,
            "body": body,
        },
    )
