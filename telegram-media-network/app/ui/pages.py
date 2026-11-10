from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.deps import default_policy
from app.core.models import (
    AdCampaign,
    Channel,
    ClusterMember,
    Episode,
    EvidenceSnapshot,
    FinanceEvent,
    MediaAsset,
    Post,
    PostVersion,
    RankedCandidate,
    RuntimeSetting,
    Series,
    Source,
    Story,
    StoryCluster,
    StoryEvidence,
    User,
)
from app.core.timeutil import ensure_utc, utcnow
from app.media.renderer import write_studio_pack
from app.product.demo_pack import build_pack
from app.product.drafts import materialise_desk
from app.product.insights import funnel, seed_demo_campaigns
from app.product.programs import move_episode, propose_fortnight
from app.product.radar import import_observations
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
        for channel in db.query(Channel).order_by(Channel.id).all():
            waiting = db.query(Post).filter_by(channel_id=channel.id, review_status="NEEDS_REVIEW").count()
            queued = db.query(Post).filter_by(channel_id=channel.id, review_status="SCHEDULED").count()
            themes = db.query(StoryCluster).filter_by(primary_channel_id=channel.id).count()
            fresh = db.query(StoryCluster).filter_by(primary_channel_id=channel.id, list_name="hot").count()
            covered_days = {
                ensure_utc(row.slot_utc).date()
                for row in db.query(Episode).filter_by(channel_id=channel.id)
                if row.slot_utc is not None
            }
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
                    "free_slots": max(0, 14 - len(covered_days)),
                }
            )
        return templates.TemplateResponse(
            request,
            "overview.html",
            {"request": request, "title": "Каналы", "nav": "overview", "policy": policy, "csrf": row.csrf_token, "cards": cards, "user": user},
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
        return templates.TemplateResponse(
            request,
            "review.html",
            {
                "request": request,
                "title": "Редакция",
                "nav": "inbox",
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
def calendar(request: Request, notice: str = ""):
    db = _db(request)
    try:
        ctx = _context(request, db)
        if ctx is None:
            return RedirectResponse("/login", status_code=303)
        user, row, policy = ctx
        from zoneinfo import ZoneInfo

        moscow = ZoneInfo("Europe/Moscow")
        episodes = []
        for episode in db.query(Episode).order_by(Episode.slot_utc).limit(200):
            local = ensure_utc(episode.slot_utc).astimezone(moscow)
            episodes.append(
                {
                    "id": episode.id,
                    "series_id": episode.series_id,
                    "channel_id": episode.channel_id,
                    "status": episode.status,
                    "version": episode.version,
                    "label": local.strftime("%Y-%m-%d %H:%M"),
                }
            )
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
            '<div class="scroll"><table><tr><th>Источник</th><th>Состояние</th><th>Включён</th><th>Интервал</th><th>Ошибки подряд</th><th>Последняя ошибка</th></tr>'
        ]
        for source in db.query(Source).order_by(Source.id):
            lines.append(
                "<tr>"
                f"<td>{html.escape(source.id)}</td>"
                f"<td>{html.escape(source.health)}</td>"
                f"<td>{'да' if source.enabled else 'нет'}</td>"
                f"<td>{source.poll_interval_minutes} мин</td>"
                f"<td>{source.consecutive_failures}</td>"
                f"<td>{html.escape(source.last_error or '—')}</td>"
                "</tr>"
            )
        lines.append("</table></div>")
        note = "Живой опрос выключен, пока SOURCE_MODE не равен live. Состояние offline не означает, что источник проверен."
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
        query = db.query(Post).order_by(Post.id.desc())
        if channel:
            query = query.filter(Post.channel_id == channel)
        lines = ["<table><tr><th>Пост</th><th>Статус</th><th>Канал</th></tr>"]
        for post in query.limit(100):
            lines.append(
                f"<tr><td><a href=\"/review/{post.id}\">{html.escape(post.title)}</a></td>"
                f"<td>{html.escape(post.review_status)}</td><td>{html.escape(post.channel_id)}</td></tr>"
            )
        lines.append("</table>")
        note = "Откройте строку, чтобы увидеть источник, версии и предпросмотр."
        return _simple(request, ctx, "Редакция", "posts", note, "".join(lines))
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
        body = (
            "<ul><li><a href=\"/api/v1/export/config.json\">Конфигурация JSON</a></li>"
            "<li><a href=\"/api/v1/export/audit.csv\">Аудит CSV</a></li>"
            "<li><a href=\"/api/v1/export/audit.json\">Аудит JSON</a></li></ul>"
            f"<ul>{flag_lines}</ul>"
            "<p>Флаги интерфейса не включают сеть и не включают отправку. Секреты в выгрузку не входят.</p>"
            "<p>Рекламный контур остаётся выключенным. Запрос на включение отклоняется.</p>"
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
            rows.append(
                {
                    "title": cluster.title,
                    "channel_id": cluster.primary_channel_id,
                    "list_name": cluster.list_name,
                    "score": None if rank is None else rank.rank_score,
                    "explanation": "" if rank is None else rank.explanation,
                    "post_id": None if post is None else post.id,
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
        write_studio_pack(directory, channels)
        cards = [
            {"channel": channel.title, "template": template_id, "file": f"{channel.id}-{template_id}.jpg"}
            for channel in channels
            for template_id in ("hero", "tool", "advisory", "digest")
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
        materialise_desk(db)
        propose_fortnight(db, moment)
        seed_demo_campaigns(db, moment)
    finally:
        db.close()
    return RedirectResponse("/radar", status_code=303)


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
