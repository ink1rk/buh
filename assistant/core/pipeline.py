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

from . import audit, db
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
    if not detected and core.personal is not None:
        detected = core.personal.skills.detect_intents(text)
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


def ingest_incoming(core, payload):
    """Somebody wrote to the owner: store it, then prepare reply options."""
    correlation_id = new_id("corr-")
    peer_id = str(payload.get("peer_id"))
    text = (payload.get("text") or "").strip()
    contact = contacts_mod.upsert_from_telegram(
        peer_id, payload.get("peer_name"), payload.get("username"), bus=core.bus)
    conversation = conversations_mod.get_or_create(
        "telegram", peer_id, contact_id=contact.id,
        title=payload.get("peer_name"), bus=core.bus)

    _backfill(conversation, payload.get("history") or [], contact)

    message = conversations_mod.Message(
        conversation_id=conversation.id, text=text, sender_type="CONTACT",
        sender_id=contact.id, external_id=payload.get("message_id"),
        message_type=payload.get("message_type", "TEXT"),
        transcription=payload.get("transcription"),
        ts=payload.get("ts") or time.time())
    message, is_new = conversations_mod.add_message(message, bus=core.bus)
    if not is_new:
        return {"duplicate": True, "conversation_id": conversation.id}

    core.bus.emit(E.TELEGRAM_MESSAGE_RECEIVED,
                  {"peer_id": peer_id, "contact_id": contact.id,
                   "conversation_id": conversation.id, "message_id": message.id,
                   "text": text[:500]},
                  source="telegram", correlation_id=correlation_id)

    context = core.resolver.for_incoming_message(conversation, contact, text,
                                                 correlation_id=correlation_id)
    options, summary = core.communication.suggest_replies(context)
    suggestion_id = _store_suggestion(conversation, contact, message, options, summary)
    core.bus.emit(E.REPLY_SUGGESTION_CREATED,
                  {"suggestion_id": suggestion_id, "contact_id": contact.id,
                   "options": options}, source="communication",
                  correlation_id=correlation_id)

    severity = "high" if contact.importance >= 0.7 else "medium"
    core.notifications.notify(
        "message.incoming", contact.display_name, body=text[:900], severity=severity,
        metadata={"kind": "incoming_message", "suggestion_id": suggestion_id,
                  "contact_id": contact.id, "conversation_id": conversation.id,
                  "peer_id": peer_id, "options": options,
                  "context_summary": summary or (conversation.summary or ""),
                  "source": f"telegram:{peer_id}"},
        correlation_id=correlation_id)

    core.enricher.on_message(conversation, contact, message, from_owner=False)
    return {"suggestion_id": suggestion_id, "contact_id": contact.id,
            "conversation_id": conversation.id, "options": options,
            "correlation_id": correlation_id}


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

    action = core.actions.request(
        "send.telegram.message",
        {"peer_id": suggestion["peer_id"], "text": body, "as_user": True},
        source="telegram", requested_by=f"user:{actor}",
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
        core.bus.emit(E.TELEGRAM_MESSAGE_SENT,
                      {"peer_id": suggestion["peer_id"], "action_id": action.id,
                       "text": body[:300]}, source="telegram",
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
    return {"id": row["id"], "conversation_id": row["conversation_id"],
            "contact_id": row["contact_id"],
            "contact_name": contact.display_name if contact else "?",
            "peer_id": conversation.external_id if conversation else None,
            "options": options, "context_summary": row["context_summary"],
            "status": row["status"], "created_at": row["created_at"]}
