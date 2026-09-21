#!/usr/bin/env python3
"""Communication agent: everything about people writing to the owner.

It answers questions about correspondence («кому я должен ответить», «что мы
обсуждали с Иваном») and prepares reply options for an incoming message. It
produces text and action requests; sending is the action engine's job.
"""
import json
import re

from core.agents import Agent, AgentResult, ReplyOptions
from core.config import config
from domain import commitments as commitments_mod
from domain import contacts as contacts_mod
from domain import conversations as conversations_mod

INTENTS = ("communication", "suggest_reply", "who_wrote", "commitments", "contact_info")


class CommunicationAgent(Agent):
    name = "communication"
    description = "Переписка: кто написал, что обсуждали, что кому обещано, ответы"
    supported_intents = INTENTS

    def __init__(self, llm, resolver=None):
        self.llm = llm
        self.resolver = resolver

    # -- reply suggestions ----------------------------------------------
    def suggest_replies(self, context, count=3):
        """2–3 варианта ответа в манере владельца, с опорой на историю."""
        contact = context.contact
        style = (contact.communication_style if contact else {}) or {}
        gender = "мужском" if config.owner_gender == "male" else "женском"
        style_hint = ", ".join(filter(None, [
            f"длина: {style.get('length')}" if style.get("length") else "",
            f"тон: {style.get('formality')}" if style.get("formality") else "",
            f"эмодзи: {style.get('emoji')}" if style.get("emoji") else ""]))

        blocks = [f"Тебе пишет: {contact.display_name if contact else 'неизвестный'}"]
        if contact and contact.relationship_type != "UNKNOWN":
            blocks.append(f"Кто это: {contact.relationship_type.lower()}")
        if context.conversation and context.conversation.summary:
            blocks.append(f"О чём общались раньше: {context.conversation.summary}")
        memory_block = context.memory_block(6)
        if memory_block:
            blocks.append("Что я про него помню:\n" + memory_block)
        commitment_block = context.commitments_block()
        if commitment_block:
            blocks.append(commitment_block)
        history = context.history_block(12)
        if history:
            blocks.append("Последние сообщения (Я — владелец):\n" + history)
        blocks.append(f"Новое сообщение: «{context.text}»")
        if style_hint:
            blocks.append(f"Его манера письма — {style_hint}. Отвечай в тон.")

        system = (
            "Ты готовишь черновики ответов ЗА владельца ассистента: он отправит их "
            f"от своего имени. О себе пиши в {gender} роде. Копируй его манеру из "
            "переписки: длину, тон, обращения. Никаких пояснений и подписей."
        )
        user = ("\n\n".join(blocks) + "\n\nДай ровно "
                f"{count} коротких варианта ответа: 1) согласиться/подтвердить, "
                "2) уточнить или отложить, 3) вежливо отказать. Плюс одно "
                "предложение с описанием ситуации.")
        try:
            parsed = self.llm.structured_output(
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                ReplyOptions, private=True)
            options = [o.strip() for o in parsed.options if o and o.strip()][:count]
            summary = parsed.context_summary.strip()
        except Exception as e:
            print("structured suggestions failed, falling back to plain:", e)
            options, summary = self._plain_suggestions(system, user, count), ""
        return options, summary

    def _plain_suggestions(self, system, user, count):
        """Small local models sometimes refuse JSON; take clean lines instead."""
        raw, _ = self.llm.generate(
            [{"role": "system", "content": system},
             {"role": "user", "content": user + " Выведи варианты построчно, без нумерации."}],
            private=True)
        options = []
        for line in (raw or "").splitlines():
            line = re.sub(r"^\s*(?:вариант\s*)?\d+[\).:\-]?\s*", "", line.strip(),
                          flags=re.IGNORECASE)
            line = re.sub(r"^[-*•]\s*", "", line).strip().strip('"«»')
            if len(line) > 2 and not line.endswith(":"):
                options.append(line[:300])
        return options[:count]

    # -- questions about correspondence ----------------------------------
    def handle(self, context):
        text = (context.text or "").lower()
        if any(word in text for word in ("жду ответ", "от кого я жду", "кто должен мне")):
            return self._waiting(context)
        if any(word in text for word in ("кому ответить", "кому я должен", "что я обещал",
                                         "обязательств", "должен сделать")):
            return self._owed(context)
        if any(word in text for word in ("кто написал", "кто писал", "непрочит",
                                         "что нового в переписк")):
            return self._who_wrote(context)
        return self._about_contact(context)

    def _waiting(self, context):
        items = commitments_mod.waiting_for_reply()
        if not items:
            return AgentResult(text="Сейчас ты никого не ждёшь — всё закрыто.",
                               agent=self.name)
        lines = ["<b>Жду ответа от:</b>"]
        for commitment in items:
            contact = (contacts_mod.get(commitment.counterparty_id)
                       if commitment.counterparty_id else None)
            who = contact.display_name if contact else "неизвестный"
            lines.append(f"• {who} — {commitment.description}")
        return AgentResult(text="\n".join(lines), agent=self.name,
                           data={"commitments": [c.as_dict() for c in items]})

    def _owed(self, context):
        items = commitments_mod.i_owe()
        if not items:
            return AgentResult(text="Незакрытых обещаний нет.", agent=self.name)
        lines = ["<b>Ты обещал:</b>"]
        for commitment in items:
            contact = (contacts_mod.get(commitment.counterparty_id)
                       if commitment.counterparty_id else None)
            who = f" ({contact.display_name})" if contact else ""
            lines.append(f"• {commitment.description}{who}")
        return AgentResult(text="\n".join(lines), agent=self.name,
                           data={"commitments": [c.as_dict() for c in items]})

    def _who_wrote(self, context):
        conversations = conversations_mod.recent(8)
        if not conversations:
            return AgentResult(text="Пока никто не писал.", agent=self.name)
        lines = ["<b>Последние диалоги:</b>"]
        for conversation in conversations:
            contact = (contacts_mod.get(conversation.contact_id)
                       if conversation.contact_id else None)
            who = contact.display_name if contact else (conversation.title or "чат")
            tail = f" — {conversation.summary[:120]}" if conversation.summary else ""
            lines.append(f"• {who}{tail}")
        return AgentResult(text="\n".join(lines), agent=self.name)

    def _about_contact(self, context):
        """«Кто такой Сергей», «что мы обсуждали» — профиль и контекст."""
        name = _extract_name(context.text)
        contact, candidates = (None, [])
        if name:
            contact, candidates = contacts_mod.resolve_one(name)
            if contact is None and len(candidates) > 1:
                options = "\n".join(f"• {c.display_name} — {c.relationship_type.lower()}"
                                    for c, _ in candidates[:4])
                return AgentResult(
                    text=f"Нашла несколько подходящих:\n{options}\n\nКого имеешь в виду?",
                    agent=self.name, data={"ambiguous": True,
                                           "candidates": [c.id for c, _ in candidates]})
        contact = contact or (context.contact if not name else None)
        if contact is None:
            return AgentResult(text="Не поняла, о ком речь — назови имя точнее.",
                               agent=self.name)
        return AgentResult(text=render_profile(contact), agent=self.name,
                           data={"contact": contact.as_dict()})


def _extract_name(text):
    match = re.search(r"(?:кто так(?:ой|ая)|про|о|об|с|напиши|ответь|для)\s+([А-ЯЁA-Z][\w-]+)",
                      text or "")
    if match:
        return match.group(1)
    words = re.findall(r"\b[А-ЯЁ][\w-]{2,}\b", text or "")
    return words[0] if words else None


def render_profile(contact, limit_memories=6):
    """Contact card built from structured data, not from an LLM blob."""
    from domain import episodes as episodes_mod
    from domain import memory as memory_mod

    style = contact.communication_style or {}
    lines = [f"<b>{contact.display_name}</b>"]
    if contact.aliases:
        lines.append(f"<i>также: {', '.join(contact.aliases[:5])}</i>")
    lines.append(f"Отношения: {contact.relationship_type.lower()}"
                 + (" (предположение)" if contact.relationship_source == "LLM_INFERENCE"
                    else ""))
    if contact.last_interaction_at:
        import datetime
        stamp = datetime.datetime.fromtimestamp(contact.last_interaction_at, config.tz)
        lines.append(f"Последний контакт: {stamp.strftime('%d.%m %H:%M')}")
    if style:
        lines.append(f"Стиль общения: {style.get('length', '?')}, "
                     f"{style.get('formality', '?')}, эмодзи {style.get('emoji', '?')}")

    open_items = commitments_mod.open_commitments(counterparty_id=contact.id)
    mine = [c for c in open_items if c.direction == "I_OWE"]
    theirs = [c for c in open_items if c.direction == "THEY_OWE"]
    if mine:
        lines.append("\n<b>Я обещал:</b>\n" + commitments_mod.render(mine, config.tz))
    if theirs:
        lines.append("\n<b>Жду от него:</b>\n" + commitments_mod.render(theirs, config.tz))

    memories = memory_mod.for_entity(contact.id, limit_memories)
    if memories:
        lines.append("\n<b>Помню:</b>\n" + memory_mod.render(memories, limit_memories))

    recent_episodes = episodes_mod.for_contact(contact.id, 2)
    if recent_episodes:
        lines.append("\n<b>Последнее обсуждение:</b>")
        for episode in recent_episodes:
            if episode.summary:
                lines.append(f"• {episode.summary[:250]}")

    conversations = conversations_mod.by_contact(contact.id, 1)
    if conversations and conversations[0].summary:
        lines.append(f"\n<b>Коротко:</b> {conversations[0].summary[:300]}")
    return "\n".join(lines)


def profile_dict(contact):
    """Same profile as structured data — for the API and the future Web UI."""
    from domain import episodes as episodes_mod
    from domain import memory as memory_mod
    return {
        "contact": contact.as_dict(),
        "commitments": [c.as_dict() for c in
                        commitments_mod.open_commitments(counterparty_id=contact.id)],
        "memories": [m.as_dict() for m in memory_mod.for_entity(contact.id, 10)],
        "episodes": [e.as_dict() for e in episodes_mod.for_contact(contact.id, 5)],
        "conversations": [c.as_dict() for c in conversations_mod.by_contact(contact.id, 5)],
    }
