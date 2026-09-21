#!/usr/bin/env python3
"""Core HTTP API (/api/*).

Mounted into the existing FastAPI application — one backend, not two. The old
endpoints keep working; everything new lives behind /api and is shared by the
Telegram bot, the future Web UI and any other interface.
"""
from fastapi import APIRouter, Body

from domain import commitments as commitments_mod
from domain import contacts as contacts_mod
from domain import conversations as conversations_mod
from domain import episodes as episodes_mod
from domain import memory as memory_mod

from . import audit, pipeline
from .bootstrap import get_core

router = APIRouter(prefix="/api")


# --- chat & actions ------------------------------------------------------
@router.post("/chat")
def api_chat(payload: dict = Body(...)):
    core = get_core()
    return pipeline.handle_message(
        core, payload.get("text", ""), session=payload.get("session", "default"),
        interface=payload.get("interface", "api"),
        message_type=payload.get("message_type", "TEXT"),
        transcription=payload.get("transcription"))


@router.post("/actions")
def api_action_request(payload: dict = Body(...)):
    core = get_core()
    action = core.actions.request(
        payload.get("type", ""), payload.get("parameters") or {},
        source=payload.get("source", "api"),
        requested_by=payload.get("requested_by", "user:owner"),
        idempotency_key=payload.get("idempotency_key"),
        context={"user_confirmed": bool(payload.get("user_confirmed"))})
    return action.as_dict()


@router.get("/actions")
def api_actions(status: str = None, limit: int = 50):
    core = get_core()
    return {"actions": [a.as_dict() for a in core.actions.list(status, limit)]}


@router.get("/actions/{action_id}")
def api_action(action_id: str):
    action = get_core().actions.get(action_id)
    return action.as_dict() if action else {"error": "не найдено"}


@router.post("/actions/{action_id}/approve")
def api_action_approve(action_id: str, payload: dict = Body(default={})):
    try:
        action = get_core().actions.approve(action_id, payload.get("actor", "owner"))
    except LookupError as e:
        return {"error": str(e)}
    return action.as_dict()


@router.post("/actions/{action_id}/cancel")
def api_action_cancel(action_id: str, payload: dict = Body(default={})):
    try:
        action = get_core().actions.cancel(action_id, payload.get("actor", "owner"))
    except LookupError as e:
        return {"error": str(e)}
    return action.as_dict()


# --- notifications -------------------------------------------------------
@router.get("/notifications")
def api_notifications(limit: int = 30):
    return {"notifications": get_core().notifications.history(limit)}


@router.get("/notifications/pending")
def api_notifications_pending(channel: str = "telegram", limit: int = 10):
    return {"items": get_core().notifications.pending(channel, limit)}


@router.post("/notifications/delivered")
def api_notifications_delivered(payload: dict = Body(...)):
    return {"sent": get_core().notifications.mark_sent(payload.get("ids") or [])}


@router.get("/notifications/digest")
def api_notifications_digest(limit: int = 20):
    return {"items": get_core().notifications.digest(limit)}


# --- suggested replies ---------------------------------------------------
@router.post("/ingest/telegram")
def api_ingest_telegram(payload: dict = Body(...)):
    """tg-user pushes incoming messages here."""
    return pipeline.ingest_incoming(get_core(), payload)


@router.get("/mail")
def api_mail():
    """Настроенные ящики и итог последнего опроса."""
    from .config import config

    from providers.email import sender_lists

    core = get_core()
    return {"enabled": config.email.enabled,
            "poll_seconds": config.email.poll_seconds,
            "accounts": [{"name": a.name, "address": a.address} for a
                         in config.email.accounts],
            "last": core.mail.last, **sender_lists()}


@router.post("/mail/check")
def api_mail_check():
    """Забрать почту сейчас, не дожидаясь очередного опроса."""
    from .config import config

    if not config.email.enabled:
        return {"error": "почта не настроена"}
    return get_core().mail.poll_once()


@router.post("/mail/sender")
def api_mail_sender(body: dict = Body(...)):
    """Отбор роботов не безошибочен — владелец правит его сам, и правка живёт."""
    from providers.email import mark_sender

    address = (body.get("address") or "").strip().lower()
    robot = bool(body.get("robot", True))
    if not address:
        return {"error": "нужен адрес"}
    result = mark_sender(address, robot)
    audit.record("email.sender.robot" if robot else "email.sender.person",
                 actor="owner", entity_type="email", entity_id=address)
    return result


@router.get("/suggestions")
def api_suggestions(status: str = "NEW", limit: int = 30):
    return {"suggestions": pipeline.list_suggestions(status or None, limit)}


@router.get("/suggestions/{suggestion_id}")
def api_suggestion(suggestion_id: str):
    return pipeline.get_suggestion(suggestion_id) or {"error": "не найдено"}


@router.post("/suggestions/{suggestion_id}/send")
def api_suggestion_send(suggestion_id: str, payload: dict = Body(default={})):
    index = payload.get("index")
    return pipeline.send_reply(get_core(), suggestion_id,
                               index=None if index is None else int(index),
                               text=payload.get("text"))


@router.post("/suggestions/{suggestion_id}/ignore")
def api_suggestion_ignore(suggestion_id: str):
    return pipeline.ignore_suggestion(suggestion_id)


# --- memory --------------------------------------------------------------
@router.get("/memory")
def api_memory(type: str = None, entity_id: str = None, status: str = "ACTIVE",
               limit: int = 100):
    items = memory_mod.list_memories(type_=type, entity_id=entity_id, status=status,
                                     limit=limit)
    return {"memories": [m.as_dict() for m in items]}


@router.post("/memory")
def api_memory_create(payload: dict = Body(...)):
    memory, outcome = memory_mod.remember(
        payload.get("content", ""), type_=payload.get("type", "FACT"),
        source=payload.get("source", "USER_EXPLICIT"),
        entity_id=payload.get("entity_id"),
        confidence=float(payload.get("confidence", 0.9)),
        importance=float(payload.get("importance", 0.6)),
        bus=get_core().bus)
    return {"outcome": outcome, "memory": memory.as_dict() if memory else None}


@router.post("/memory/search")
def api_memory_search(payload: dict = Body(...)):
    found = memory_mod.search(payload.get("query", ""),
                              entity_id=payload.get("entity_id"),
                              limit=int(payload.get("limit", 10)))
    return {"results": [{**m.as_dict(), "score": score} for m, score in found]}


@router.get("/memory/{memory_id}")
def api_memory_get(memory_id: str):
    memory = memory_mod.get(memory_id)
    return memory.as_dict() if memory else {"error": "не найдено"}


@router.patch("/memory/{memory_id}")
def api_memory_patch(memory_id: str, payload: dict = Body(...)):
    memory = memory_mod.update(memory_id, **payload)
    return memory.as_dict() if memory else {"error": "не найдено"}


@router.delete("/memory/{memory_id}")
def api_memory_delete(memory_id: str):
    return {"deleted": memory_mod.delete(memory_id, bus=get_core().bus)}


# --- contacts ------------------------------------------------------------
@router.get("/contacts")
def api_contacts(limit: int = 200):
    return {"contacts": [c.as_dict() for c in contacts_mod.all_contacts(limit)]}


@router.get("/contacts/resolve")
def api_contacts_resolve(q: str):
    contact, candidates = contacts_mod.resolve_one(q)
    return {"resolved": contact.as_dict() if contact else None,
            "ambiguous": contact is None and len(candidates) > 1,
            "candidates": [{**c.as_dict(), "score": s} for c, s in candidates]}


@router.get("/contacts/{contact_id}")
def api_contact(contact_id: str):
    contact = contacts_mod.get(contact_id)
    return contact.as_dict() if contact else {"error": "не найдено"}


@router.get("/contacts/{contact_id}/context")
def api_contact_context(contact_id: str):
    from agents.communication import profile_dict
    contact = contacts_mod.get(contact_id)
    return profile_dict(contact) if contact else {"error": "не найдено"}


@router.patch("/contacts/{contact_id}")
def api_contact_patch(contact_id: str, payload: dict = Body(...)):
    contact = contacts_mod.get(contact_id)
    if contact is None:
        return {"error": "не найдено"}
    for field in ("display_name", "notes", "relationship_type", "importance",
                  "aliases", "emails", "phones"):
        if field in payload:
            setattr(contact, field, payload[field])
    if "relationship_type" in payload:
        contact.relationship_source = "USER_EXPLICIT"
    return contacts_mod.save(contact).as_dict()


@router.delete("/contacts/{contact_id}")
def api_contact_delete(contact_id: str):
    return {"deleted": contacts_mod.delete(contact_id)}


# --- conversations -------------------------------------------------------
@router.get("/conversations")
def api_conversations(limit: int = 30):
    items = []
    for conversation in conversations_mod.recent(limit):
        contact = (contacts_mod.get(conversation.contact_id)
                   if conversation.contact_id else None)
        items.append({**conversation.as_dict(),
                      "contact_name": contact.display_name if contact else None})
    return {"conversations": items}


@router.get("/conversations/{conversation_id}")
def api_conversation(conversation_id: str):
    conversation = conversations_mod.get(conversation_id)
    if conversation is None:
        return {"error": "не найдено"}
    return {**conversation.as_dict(),
            "episodes": [e.as_dict() for e in
                         episodes_mod.for_conversation(conversation_id, 5)]}


@router.get("/conversations/{conversation_id}/messages")
def api_conversation_messages(conversation_id: str, limit: int = 50):
    return {"messages": [m.as_dict()
                         for m in conversations_mod.messages(conversation_id, limit)]}


@router.delete("/conversations/{conversation_id}")
def api_conversation_delete(conversation_id: str):
    return {"deleted": conversations_mod.delete(conversation_id)}


# --- commitments ---------------------------------------------------------
@router.get("/commitments")
def api_commitments(status: str = None, limit: int = 100):
    items = commitments_mod.all_commitments(status, limit)
    out = []
    for commitment in items:
        contact = (contacts_mod.get(commitment.counterparty_id)
                   if commitment.counterparty_id else None)
        out.append({**commitment.as_dict(),
                    "counterparty_name": contact.display_name if contact else None})
    return {"commitments": out}


@router.patch("/commitments/{commitment_id}")
def api_commitment_patch(commitment_id: str, payload: dict = Body(...)):
    core = get_core()
    status = (payload.get("status") or "").upper()
    if status == "DONE":
        commitment = commitments_mod.complete(commitment_id, bus=core.bus)
    elif status == "CANCELLED":
        commitment = commitments_mod.cancel(commitment_id)
    else:
        commitment = commitments_mod.get(commitment_id)
        if commitment and payload.get("description"):
            commitment.description = payload["description"]
            commitments_mod.save(commitment)
    return commitment.as_dict() if commitment else {"error": "не найдено"}


# --- episodes, activity, integrations, health ----------------------------
@router.get("/episodes")
def api_episodes(conversation_id: str = None, contact_id: str = None, limit: int = 20):
    if conversation_id:
        items = episodes_mod.for_conversation(conversation_id, limit)
    elif contact_id:
        items = episodes_mod.for_contact(contact_id, limit)
    else:
        items = []
    return {"episodes": [e.as_dict() for e in items]}


@router.get("/activity")
def api_activity(limit: int = 50, correlation_id: str = None):
    return {"activity": audit.timeline(limit=limit, correlation_id=correlation_id)}


@router.get("/integrations")
def api_integrations(refresh: bool = False):
    core = get_core()
    return {"integrations": core.integrations.check() if refresh
            else core.integrations.status()}


@router.get("/permissions")
def api_permissions():
    return get_core().permissions.describe()


@router.post("/permissions/override")
def api_permissions_override(payload: dict = Body(...)):
    core = get_core()
    action_type, decision = payload.get("action_type"), payload.get("decision")
    if not action_type:
        return {"error": "нужен action_type"}
    if decision:
        core.permissions.set_override(action_type, decision)
    else:
        core.permissions.clear_override(action_type)
    return core.permissions.describe()


@router.get("/health")
def api_health():
    return get_core().health()


def _greeting(hour):
    if hour < 5:
        return "Доброй ночи"
    if hour < 12:
        return "Доброе утро"
    if hour < 18:
        return "Добрый день"
    return "Добрый вечер"


@router.get("/overview")
def api_overview():
    """Всё для главного экрана одним запросом — чтобы не собирать его из пяти."""
    import datetime

    from .config import config

    core = get_core()
    now = datetime.datetime.now(config.tz)
    owner = contacts_mod.owner()

    suggestions = pipeline.list_suggestions("NEW", 5)
    approvals = [a.as_dict() for a in core.actions.list("WAITING_APPROVAL", 5)]
    mine = commitments_mod.i_owe(20)
    theirs = commitments_mod.waiting_for_reply(20)
    overdue = [c for c in mine + theirs if c.status == "OVERDUE"]

    def with_names(items):
        out = []
        for commitment in items[:5]:
            contact = (contacts_mod.get(commitment.counterparty_id)
                       if commitment.counterparty_id else None)
            out.append({**commitment.as_dict(),
                        "counterparty_name": contact.display_name if contact else None})
        return out

    integrations = core.integrations.status()
    broken = [i["name"] for i in integrations if i["status"] == "ERROR"]

    return {
        "greeting": _greeting(now.hour),
        "owner": (owner.display_name if owner else config.owner_name) or "",
        "assistant": config.assistant_name,
        "now": now.isoformat(),
        "response_mode": config.response_mode,
        "attention": {"suggestions": len(pipeline.list_suggestions("NEW", 100)),
                      "approvals": len(core.actions.list("WAITING_APPROVAL", 100)),
                      "i_owe": len(mine), "waiting": len(theirs),
                      "overdue": len(overdue)},
        "suggestions": suggestions,
        "approvals": approvals,
        "i_owe": with_names(mine),
        "waiting": with_names(theirs),
        "system": {"ok": not broken, "broken": broken,
                   "integrations": [{"name": i["name"], "status": i["status"],
                                     "detail": i["detail"]} for i in integrations]},
    }
