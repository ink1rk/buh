from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.deps import default_policy
from app.core.models import Channel, MediaAsset, Post, Source, Story, StoryEvidence, User
from app.core.timeutil import utcnow
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
            cards.append(
                {
                    "title": channel.title,
                    "category": channel.category,
                    "queued": queued,
                    "waiting": waiting,
                    "publish_enabled": channel.publish_enabled,
                    "health": "локально",
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
        image = db.query(MediaAsset).filter_by(post_id=post.id).order_by(MediaAsset.id.desc()).first()
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
        save_post(db, post, user, title=title, body=body, channel_id=channel_id, expected_version=version)
        channel = db.get(Channel, post.channel_id)
        if channel is not None:
            from app.services.editorial import refresh_card

            db.add(refresh_card(post, channel, Path(request.app.state.settings.media_dir)))
            db.commit()
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
def calendar(request: Request):
    db = _db(request)
    try:
        ctx = _context(request, db)
        if ctx is None:
            return RedirectResponse("/login", status_code=303)
        lines = ["<table><tr><th>Канал</th><th>Слоты MSK</th><th>Тихие часы</th></tr>"]
        for channel in db.query(Channel).order_by(Channel.id):
            slots = ", ".join(html.escape(str(item)) for item in (channel.schedule_json or []))
            lines.append(
                f"<tr><td>{html.escape(channel.title)}</td><td>{slots}</td>"
                f"<td>{html.escape(channel.quiet_start)}–{html.escape(channel.quiet_end)}</td></tr>"
            )
        lines.append("</table>")
        return _simple(request, ctx, "Календарь", "calendar", "Слоты показаны в Europe/Moscow.", "".join(lines))
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
def posts(request: Request):
    db = _db(request)
    try:
        ctx = _context(request, db)
        if ctx is None:
            return RedirectResponse("/login", status_code=303)
        lines = ["<table><tr><th>Пост</th><th>Статус</th><th>Канал</th></tr>"]
        for post in db.query(Post).order_by(Post.id.desc()).limit(100):
            lines.append(
                f"<tr><td><a href=\"/review/{post.id}\">{html.escape(post.title)}</a></td>"
                f"<td>{html.escape(post.review_status)}</td><td>{html.escape(post.channel_id)}</td></tr>"
            )
        lines.append("</table>")
        return _simple(request, ctx, "Публикации", "posts", "", "".join(lines))
    finally:
        db.close()


@router.get("/analytics", response_class=HTMLResponse)
def analytics(request: Request):
    db = _db(request)
    try:
        ctx = _context(request, db)
        if ctx is None:
            return RedirectResponse("/login", status_code=303)
        return _simple(
            request,
            ctx,
            "Статистика",
            "analytics",
            "Просмотры постов: н/д. Bot API не отдаёт просмотры, и цифра не выдумывается.",
            "<p>Подписчики: н/д, пока нет отдельного разрешения на getChatMemberCount.</p>",
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
        return _simple(
            request,
            ctx,
            "Реклама",
            "commercial",
            "Контур выключен. Без legal approval пост не планируется и не публикуется.",
            "",
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
        body = (
            "<ul><li><a href=\"/api/v1/export/config.json\">Конфигурация JSON</a></li>"
            "<li><a href=\"/api/v1/export/audit.csv\">Аудит CSV</a></li>"
            "<li><a href=\"/api/v1/export/audit.json\">Аудит JSON</a></li></ul>"
            "<p>Секреты в выгрузку не входят. Production не включён.</p>"
        )
        note = ""
        if user.role == "OWNER":
            state = "включён" if policy.kill_switch else "выключен"
            note = f"Kill switch {state}. Его видит только OWNER. Эта сборка не отправляет сообщения в Telegram."
        return _simple(request, ctx, "Система", "system", note, body)
    finally:
        db.close()


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
