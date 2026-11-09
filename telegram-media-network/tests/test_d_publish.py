from __future__ import annotations

import io
from datetime import timedelta

import httpx
from app.core.models import Alert, Channel, PublishedMessage, PublishingOutbox
from app.core.security import Policy
from app.media.renderer import inspect_image, render_card, resolve_media
from app.pipeline.caption import build_caption, preview_html, safe_links, telegram_length, validate_caption
from app.publishing.telegram import AmbiguousTimeout, ScriptedTransport, SpyTransport, TgResult
from app.services.accounts import AuthError
from app.services.dispatch import dispatch_outbox, publish_preview_or_send, recover_inflight
from app.services.moderation import schedule_post
from PIL import Image
from tests.factories import NOW
from tests.support import approved_post


def _jpeg() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), (10, 20, 30)).save(buffer, format="JPEG")
    return buffer.getvalue()


def _card(title: str):
    return render_card(
        channel_title="GitHub Находки",
        primary="#12344D",
        accent="#F2C14E",
        template="tool",
        title=title,
        kicker="ИНСТРУМЕНТ",
        footer="GitHub Находки",
    )


def test_d01_long_russian_title_and_emoji_fit():
    title = (
        "Очень длинный заголовок про локальный запуск служебных задач "
        "в домашней лаборатории без облака и без лишних обещаний"
    )
    rendered = _card(title + " 🚀")
    with Image.open(io.BytesIO(rendered.jpeg)) as image:
        assert image.size == (1280, 720)
        assert image.format == "JPEG"
        assert not image.getexif()
    assert rendered.layout.fits is True
    assert rendered.layout.bottom <= 600
    caption = build_caption(title + " 🚀", "Короткий текст для подписи, в котором эмодзи остаётся.", ["https://github.com/acme/widget"])
    assert "🚀" in caption
    assert telegram_length("🚀") == 2


def test_d02_remote_image_without_rights_falls_back():
    card = _card("Локальная карточка без чужого изображения")
    remote = _jpeg()
    chosen, basis = resolve_media(remote, "unknown", True, card)
    assert basis == "own_typographic_template"
    assert chosen.sha256 == card.sha256
    licensed, licensed_basis = resolve_media(remote, "licensed_reuse", True, card)
    assert licensed_basis == "licensed_reuse"
    denied, denied_basis = resolve_media(remote, "licensed_reuse", False, card)
    assert denied_basis == "own_typographic_template"


def test_d03_malformed_images_are_rejected():
    assert inspect_image(b"this is not an image").reason == "malformed"
    assert inspect_image(b"<svg><script>alert(1)</script></svg>").reason == "svg_or_script"
    huge = io.BytesIO()
    Image.new("RGB", (3000, 2000), (0, 0, 0)).save(huge, format="PNG")
    assert inspect_image(huge.getvalue()).reason == "dimensions"
    assert _card("Процесс продолжает работу").jpeg


def test_d04_caption_over_1024_is_not_sent(db):
    post, owner, editor = approved_post(db)
    del owner
    long_caption = "я" * 1100
    assert telegram_length(long_caption) > 1024
    ok, problem = validate_caption(long_caption, post.body)
    assert ok is False
    assert "1024" in problem
    post.caption = long_caption
    db.commit()
    try:
        schedule_post(db, post, editor, due=NOW, confirmed=True, now=NOW)
        scheduled = True
    except AuthError as exc:
        scheduled = False
        assert exc.status == 422
    assert scheduled is False
    assert db.query(PublishingOutbox).count() == 0


def test_d05_script_and_links_are_escaped():
    html = preview_html("Заголовок", "<script>alert(1)</script>", "card.jpg", "карточка")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    kept = safe_links(
        [
            "javascript:alert(1)",
            "http://127.0.0.1/admin",
            "https://169.254.169.254/latest",
            "https://github.com/acme/widget",
        ]
    )
    assert kept == ["https://github.com/acme/widget"]


def test_d06_dry_run_makes_no_telegram_call(db, monkeypatch):
    post, owner, _editor = approved_post(db)
    spy = SpyTransport()

    def forbid_post(*_args, **_kwargs):
        raise AssertionError("httpx post")

    monkeypatch.setattr(httpx.Client, "post", forbid_post)
    result = publish_preview_or_send(db, post, owner, Policy(True, False, True, False), spy, confirmed=True, now=NOW)
    assert result["mode"] == "dry_run"
    assert result["preview"] is True
    assert spy.calls == []


def test_d07_publish_disabled(db):
    post, owner, _editor = approved_post(db)
    spy = SpyTransport()
    try:
        publish_preview_or_send(db, post, owner, Policy(False, False, False, False), spy, confirmed=True, now=NOW)
        denied = False
    except AuthError as exc:
        denied = exc.status == 403 and exc.detail == "publish disabled"
    assert denied is True
    assert spy.calls == []


def test_d08_channel_publish_disabled(db):
    post, owner, _editor = approved_post(db)
    channel = db.get(Channel, post.channel_id)
    channel.publish_enabled = False
    db.commit()
    spy = SpyTransport()
    try:
        publish_preview_or_send(db, post, owner, Policy(False, True, False, False), spy, confirmed=True, now=NOW)
        denied = False
    except AuthError as exc:
        denied = exc.status == 403 and exc.detail == "channel disabled"
    assert denied is True
    assert spy.calls == []


def _scheduled(db):
    post, owner, editor = approved_post(db)
    outbox = schedule_post(db, post, editor, due=NOW, confirmed=True, now=NOW)
    return post, owner, outbox


def test_d09_mock_200_stores_message(db):
    post, _owner, outbox = _scheduled(db)
    transport = ScriptedTransport([TgResult(200, message_id="555")])
    result = dispatch_outbox(db, outbox, transport, now=NOW)
    saved = db.query(PublishedMessage).one()
    assert result["message_id"] == "555"
    assert saved.telegram_message_id == "555"
    assert saved.published_utc == NOW
    assert saved.caption_hash == post.caption_hash
    assert len(transport.calls) == 1


def test_d10_mock_401_pauses_and_alerts(db):
    post, _owner, outbox = _scheduled(db)
    transport = ScriptedTransport([TgResult(401, description="unauthorized")])
    result = dispatch_outbox(db, outbox, transport, now=NOW)
    channel = db.get(Channel, post.channel_id)
    assert result["state"] == "paused"
    assert channel.paused is True
    assert db.query(Alert).filter_by(channel_id=channel.id).count() == 1
    again = dispatch_outbox(db, outbox, transport, now=NOW)
    assert again["state"] == "paused"
    assert len(transport.calls) == 1


def test_d11_retry_after_is_exact(db):
    _post, _owner, outbox = _scheduled(db)
    transport = ScriptedTransport([TgResult(429, retry_after=17)])
    result = dispatch_outbox(db, outbox, transport, now=NOW)
    db.refresh(outbox)
    assert result["delay"] == 17
    assert outbox.due_utc == NOW + timedelta(seconds=17)
    assert outbox.state == "retryable_failed"


def test_d12_timeout_needs_reconciliation(db):
    _post, _owner, outbox = _scheduled(db)
    transport = ScriptedTransport([AmbiguousTimeout("timeout")])
    result = dispatch_outbox(db, outbox, transport, now=NOW)
    db.refresh(outbox)
    assert result["state"] == "needs_reconciliation"
    assert outbox.request_sent is True
    again = dispatch_outbox(db, outbox, transport, now=NOW + timedelta(minutes=5))
    assert again.get("calls") == 0
    assert len(transport.calls) == 1
    assert db.query(PublishedMessage).count() == 0


def test_d13_crash_before_commit_does_not_resend(db):
    _post, _owner, outbox = _scheduled(db)
    transport = ScriptedTransport([TgResult(200, message_id="777")])
    result = dispatch_outbox(db, outbox, transport, now=NOW, crash_before_commit=True)
    assert result["crashed"] is True
    db.refresh(outbox)
    assert outbox.state == "sending"
    assert outbox.request_sent is True
    moved = recover_inflight(db, NOW + timedelta(minutes=5))
    db.refresh(outbox)
    assert moved == 1
    assert outbox.state == "needs_reconciliation"
    again = dispatch_outbox(db, outbox, transport, now=NOW + timedelta(minutes=6))
    assert len(transport.calls) == 1
    assert db.query(PublishedMessage).count() == 0
    assert again["state"] == "needs_reconciliation"
