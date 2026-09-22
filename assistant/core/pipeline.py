#!/usr/bin/env python3
"""The message pipeline shared by every interface.

Telegram, the HTTP API and (later) the Web UI all enter here, so a request
follows the same path regardless of where it came from:

    message → context → intent → agent → response
                                   ↓
                            action request → permission → action engine

Voice is not a separate path: audio is transcribed before this point and the
answer is always text.
"""
import json
import time

from domain import contacts as contacts_mod
from domain import conversations as conversations_mod

from . import audit, channels, db, intents as intents_mod
from .config import config
from .events import E, new_id

BOT_PLATFORM = "telegram:bot"          # the owner's own dialogue with the assistant


def handle_message(core, text, session="default", interface="telegram",
                   correlation_id=None, intents=None, message_type="TEXT",
                   transcription=None):
    """Owner's message → context → agent → text answer."""
    correlation_id = correlation_id or new_id("corr-")
    core.bus.emit(E.MESSAGE_RECEIVED,
                  {"session": session, "interface": interface,
                   "type": message_type, "text": text[:500]},
                  source=interface, correlation_id=correlation_id)

    conversation = conversations_mod.get_or_create(
        BOT_PLATFORM, session, title="Диалог с ассистентом", bus=core.bus)
    owner = _owner_contact()
    message = conversations_mod.Message(
        conversation_id=conversation.id, text=text, sender_type="OWNER",
        sender_id=owner.id if owner else None, message_type=message_type,
        transcription=transcription, ts=time.time())
    conversations_mod.add_message(message, bus=core.bus)

    detected = list(intents or [])
    if not detected:
        skills = core.personal.skills if core.personal is not None else None
        detected = intents_mod.detect(text, skills)
    core.bus.emit(E.INTENT_DETECTED, {"intents": detected, "text": text[:200]},
                  source="core", correlation_id=correlation_id)

    context = core.resolver.resolve(text=text, interface=interface, session=session,
                                    conversation=conversation, contact=owner,
                                    correlation_id=correlation_id, intents=detected)
    agent = core.agents.select(context)
    if agent is None:
        return {"reply": "Пока не умею это обрабатывать.", "agent": None,
                "correlation_id": correlation_id}

    result = agent.handle(context)
    core.bus.emit(E.RESPONSE_GENERATED,
                  {"agent": result.agent, "provider": result.provider,
                   "chars": len(result.text or "")},
                  source="core", correlation_id=correlation_id)

    requested = []
    for request in result.actions:
        action = core.actions.request(
            request.type, request.parameters, source=interface,
            requested_by="agent:" + result.agent, correlation_id=correlation_id,
            context={"user_confirmed": request.user_confirmed})
        requested.append(action.as_dict())

    assistant_message = conversations_mod.Message(
        conversation_id=conversation.id, text=result.text or "",
        sender_type="ASSISTANT", message_type="TEXT", ts=time.time())
    conversations_mod.add_message(assistant_message)

    if core.enricher and owner is not None:
        core.enricher.on_message(conversation, owner, message, from_owner=True)

    return {"reply": result.text, "agent": result.agent, "provider": result.provider,
            "intents": detected, "data": result.data, "actions": requested,
            "correlation_id": correlation_id}


def telegram_ingest_allowed():
    """Чужие чаты в Telegram больше не разбираем: владелец их и так видит."""
    return bool(config.telegram.ingest_incoming)


def ingest_incoming(core, payload, channel="telegram"):
    """Somebody wrote to the owner: store it, then prepare reply options.

    Один путь для всех каналов: письмо и сообщение в Telegram отличаются только
    тем, как из них достаётся человек и чем отправляется ответ.
    """
    channel = channels.get(channel) if isinstance(channel, str) else channel
    if channel.name == "telegram" and not telegram_ingest_allowed():
        return {"disabled": True, "channel": "telegram",
                "reason": "сбор сообщений Telegram выключен"}
    correlation_id = new_id("corr-")
    peer_id = channel.conversation_key(payload)
    text = (payload.get("text") or "").strip()
    subject = (payload.get("subject") or "").strip()
    contact = channel.resolve_contact(payload, core.bus)
    conversation = conversations_mod.get_or_create(
        channel.platform, peer_id, contact_id=contact.id,
        title=channel.title(payload), bus=core.bus)

    _backfill(conversation, payload.get("history") or [], contact)

    metadata = {}
    if subject:
        metadata["subject"] = subject
    if payload.get("account"):
        metadata["account"] = payload["account"]

    message = conversations_mod.Message(
        conversation_id=conversation.id, text=text, sender_type="CONTACT",
        sender_id=contact.id, external_id=payload.get("message_id"),
        message_type=payload.get("message_type", "TEXT"),
        transcription=payload.get("transcription"),
        ts=payload.get("ts") or time.time(), metadata=metadata)
    message, is_new = conversations_mod.add_message(message, bus=core.bus)
    if not is_new:
        return {"duplicate": True, "conversation_id": conversation.id}

    core.bus.emit(channel.received_event,
                  {"peer_id": peer_id, "contact_id": contact.id,
                   "conversation_id": conversation.id, "message_id": message.id,
                   "subject": subject, "text": text[:500]},
                  source=channel.source, correlation_id=correlation_id)

    # Тема письма — часть сообщения: без неё модель не понимает, о чём речь.
    for_model = f"Тема: {subject}\n\n{text}" if subject else text
    context = core.resolver.for_incoming_message(conversation, contact, for_model,
                                                 correlation_id=correlation_id)
    options, summary = core.communication.suggest_replies(context)
    suggestion_id = _store_suggestion(conversation, contact, message, options, summary)
    core.bus.emit(E.REPLY_SUGGESTION_CREATED,
                  {"suggestion_id": suggestion_id, "contact_id": contact.id,
                   "options": options}, source="communication",
                  correlation_id=correlation_id)

    severity = "high" if contact.importance >= 0.7 else "medium"
    core.notifications.notify(
        "message.incoming", contact.display_name,
        body=(f"{subject}\n{text}" if subject else text)[:900], severity=severity,
        metadata={"kind": channel.notification_kind, "channel": channel.name,
                  "suggestion_id": suggestion_id, "subject": subject,
                  "contact_id": contact.id, "conversation_id": conversation.id,
                  "peer_id": peer_id, "options": options,
                  "context_summary": summary or (conversation.summary or ""),
                  "source": f"{channel.name}:{peer_id}"},
        correlation_id=correlation_id)

    core.enricher.on_message(conversation, contact, message, from_owner=False)
    return {"suggestion_id": suggestion_id, "contact_id": contact.id,
            "conversation_id": conversation.id, "options": options,
            "channel": channel.name, "correlation_id": correlation_id}


def send_reply(core, suggestion_id, index=None, text=None, actor="owner"):
    """Owner picked an option (or wrote his own): one confirmed action."""
    suggestion = get_suggestion(suggestion_id)
    if suggestion is None:
        return {"error": "подсказка не найдена"}
    body = (text or "").strip()
    if not body:
        options = suggestion["options"]
        if index is None or index < 0 or index >= len(options):
            return {"error": "нет такого варианта"}
        body = options[index]

    channel = channels.for_platform(suggestion.get("platform"))
    action = core.actions.request(
        channel.action_type, channel.send_parameters(suggestion, body),
        source=channel.source, requested_by=f"user:{actor}",
        idempotency_key=f"reply:{suggestion_id}:{index if text is None else 'custom'}",
        context={"user_confirmed": True})

    if action.status == "SUCCESS":
        conversation = conversations_mod.get(suggestion["conversation_id"])
        if conversation:
            conversations_mod.add_message(conversations_mod.Message(
                conversation_id=conversation.id, text=body, sender_type="OWNER",
                message_type="TEXT", ts=time.time(),
                metadata={"via": "suggestion", "action_id": action.id}))
        db.execute("UPDATE reply_suggestions SET status='SENT', chosen_index=?,"
                   " sent_text=?, decided_at=? WHERE id=?",
                   (index if text is None else -1, body, time.time(), suggestion_id))
        core.bus.emit(channel.sent_event,
                      {"peer_id": suggestion["peer_id"], "action_id": action.id,
                       "text": body[:300]}, source=channel.source,
                      correlation_id=action.correlation_id)
    audit.record("reply.sent" if action.status == "SUCCESS" else "reply.failed",
                 actor=actor, correlation_id=action.correlation_id,
                 entity_type="suggestion", entity_id=suggestion_id,
                 details={"status": action.status, "text": body[:300],
                          "error": action.error})
    return {"status": action.status, "action_id": action.id, "text": body,
            "contact": suggestion["contact_name"], "error": action.error}


def ignore_suggestion(suggestion_id, actor="owner"):
    db.execute("UPDATE reply_suggestions SET status='IGNORED', decided_at=? WHERE id=?",
               (time.time(), suggestion_id))
    audit.record("reply.ignored", actor=actor, entity_type="suggestion",
                 entity_id=suggestion_id)
    return {"status": "IGNORED"}


# -- helpers --------------------------------------------------------------
def _owner_contact():
    owner = contacts_mod.owner()
    if owner is None:
        from .config import config
        owner = contacts_mod.Contact(
            display_name=config.owner_name or "Владелец", is_owner=True,
            telegram_ids=[str(config.telegram.owner_id)] if config.telegram.owner_id else [],
            importance=1.0, relationship_type="UNKNOWN",
            relationship_source="USER_EXPLICIT")
        contacts_mod.save(owner)
    return owner


def _backfill(conversation, history, contact):
    """First sight of a dialogue: keep the history we were handed."""
    if not history or conversations_mod.messages(conversation.id, limit=1):
        return
    owner = _owner_contact()
    for item in history:
        text = (item.get("text") or "").strip()
        if not text:
            continue
        from_owner = bool(item.get("me"))
        conversations_mod.add_message(conversations_mod.Message(
            conversation_id=conversation.id, text=text,
            sender_type="OWNER" if from_owner else "CONTACT",
            sender_id=(owner.id if from_owner else contact.id),
            external_id=item.get("id"), ts=item.get("ts") or time.time(),
            metadata={"backfill": True}))


def _store_suggestion(conversation, contact, message, options, summary):
    suggestion_id = new_id("sug-")
    db.execute(
        """INSERT INTO reply_suggestions(id, conversation_id, message_id, contact_id,
            options, context_summary, status, created_at)
           VALUES(?,?,?,?,?,?,'NEW',?)""",
        (suggestion_id, conversation.id, message.id, contact.id,
         json.dumps(options, ensure_ascii=False), summary or "", time.time()))
    return suggestion_id


def list_suggestions(status="NEW", limit=30):
    """Неразобранные подсказки — то, что ждёт решения владельца."""
    if status:
        rows = db.query("SELECT id FROM reply_suggestions WHERE status=?"
                        " ORDER BY created_at DESC LIMIT ?", (status, limit))
    else:
        rows = db.query("SELECT id FROM reply_suggestions ORDER BY created_at DESC"
                        " LIMIT ?", (limit,))
    found = [get_suggestion(row["id"]) for row in rows]
    return [item for item in found if item]


def get_suggestion(suggestion_id):
    row = db.one("SELECT * FROM reply_suggestions WHERE id=?", (suggestion_id,))
    if row is None:
        return None
    conversation = conversations_mod.get(row["conversation_id"])
    contact = contacts_mod.get(row["contact_id"]) if row["contact_id"] else None
    try:
        options = json.loads(row["options"] or "[]")
    except ValueError:
        options = []
    # Ответ письмом должен попасть в ту же ветку, поэтому нужны тема, ящик и
    # идентификатор исходного письма — всё это лежит на самом сообщении.
    source = conversations_mod.get_message(row["message_id"]) if row["message_id"] \
        else None
    extra = (source.metadata or {}) if source else {}
    platform = conversation.platform if conversation else "telegram"
    return {"id": row["id"], "conversation_id": row["conversation_id"],
            "contact_id": row["contact_id"],
            "contact_name": contact.display_name if contact else "?",
            "peer_id": conversation.external_id if conversation else None,
            "platform": platform, "channel": channels.for_platform(platform).name,
            "subject": extra.get("subject", ""), "account": extra.get("account"),
            "external_message_id": source.external_id if source else None,
            "options": options, "context_summary": row["context_summary"],
            "status": row["status"], "created_at": row["created_at"]}
