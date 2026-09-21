#!/usr/bin/env python3
"""Background enrichment of conversations.

Everything expensive happens here, after the user already got an answer:
memory extraction, commitment detection, conversation summaries and episodes.
A failure in any of it must never affect the chat, so each step is isolated.
"""
import datetime
import re
import threading
import time

from core.agents import CommitmentExtraction, ConversationSummary, MemoryExtraction
from core.config import config
from core.events import E

from . import commitments as commitments_mod
from . import contacts as contacts_mod
from . import conversations as conversations_mod
from . import episodes as episodes_mod
from . import memory as memory_mod

SUMMARY_EVERY = 6            # messages between summary refreshes
SUMMARY_MIN_AGE = 600        # seconds; do not re-summarise a live chat too often

# «Напомни завтра купить молоко» is a task, not a memory.
TASK_RE = re.compile(r"\b(напомни|напоминай|поставь напоминание|заведи задачу)\b",
                     re.IGNORECASE)
TRIVIAL_RE = re.compile(
    r"^\W*(привет|здравствуй|хай|ок|окей|ага|да|нет|спасибо|спс|пока|good|hi|hello|"
    r"ладно|понял|поняла|плюс|\+|\d+)\W*$", re.IGNORECASE)


class Enricher:
    def __init__(self, llm, bus, tasks=None):
        self.llm = llm
        self.bus = bus
        self.tasks = tasks              # optional task sink (Phase 6)
        self._lock = threading.Lock()

    # -- entry points ----------------------------------------------------
    def on_message(self, conversation, contact, message, from_owner=False):
        """Fire-and-forget: the caller has already answered the user."""
        threading.Thread(target=self._safe_process, name="enrich",
                         args=(conversation, contact, message, from_owner),
                         daemon=True).start()

    def _safe_process(self, conversation, contact, message, from_owner):
        for step in (self._extract_memories, self._extract_commitments,
                     self._maybe_summarise, self._update_style):
            try:
                step(conversation, contact, message, from_owner)
            except Exception as e:
                print(f"enrichment step {step.__name__} failed: {type(e).__name__}: {e}")

    # -- steps -----------------------------------------------------------
    def _extract_memories(self, conversation, contact, message, from_owner):
        text = (message.transcription or message.text or "").strip()
        if len(text) < 12 or TRIVIAL_RE.match(text):
            return
        if TASK_RE.search(text):
            # Tasks live in their own domain; memory must not swallow them.
            self.bus.emit("task.candidate.detected",
                          {"text": text, "conversation_id": conversation.id,
                           "message_id": message.id}, source="enrichment")
            if self.tasks:
                self.tasks.add_from_text(text, conversation_id=conversation.id)
            return

        who = "владелец" if from_owner else (contact.display_name if contact else "собеседник")
        system = (
            "Ты извлекаешь из сообщения только то, что стоит помнить долго. "
            "Не запоминай приветствия, болтовню и сиюминутные детали. "
            "Просьбы, обещания и сроки тоже не запоминай: договорённости и задачи "
            "учитываются отдельно, память — только про устойчивое знание. "
            "Типы: FACT (устойчивый факт), PREFERENCE (предпочтение/привычка), "
            "EVENT (состоявшееся или назначенное событие), RELATION (кто кому кто), "
            "PROCEDURE (как принято поступать в повторяющейся ситуации). "
            "Если запоминать нечего — пустой список."
        )
        user = (f"Сообщение от: {who}\nТекст: «{text}»\n\n"
                "Верни память в JSON. about='owner', если факт про владельца, "
                "иначе about='contact'. confidence — насколько это точно сказано, "
                "а не додумано.")
        extraction = self.llm.structured_output(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            MemoryExtraction, private=True)

        source = "USER_MESSAGE" if from_owner else "TELEGRAM"
        for candidate in extraction.memories:
            entity_id = None
            if candidate.about == "contact" and contact:
                entity_id = contact.id
            elif candidate.about == "owner":
                owner = contacts_mod.owner()
                entity_id = owner.id if owner else None
            stored, outcome = memory_mod.remember(
                candidate.content, type_=candidate.type.upper(), source=source,
                source_id=message.id, entity_id=entity_id,
                confidence=candidate.confidence, importance=candidate.importance,
                bus=self.bus)
            self.bus.emit(E.MEMORY_CANDIDATE,
                          {"content": candidate.content, "outcome": outcome,
                           "stored_id": stored.id if stored else None},
                          source="enrichment")
        for task_text in extraction.tasks:
            self.bus.emit("task.candidate.detected",
                          {"text": task_text, "conversation_id": conversation.id},
                          source="enrichment")

    def _extract_commitments(self, conversation, contact, message, from_owner):
        text = (message.transcription or message.text or "").strip()
        if len(text) < 10 or TRIVIAL_RE.match(text):
            return
        if contact is not None and contact.is_owner:
            # Разговор с самим ассистентом: обязательств перед собой не бывает,
            # такие просьбы — это задачи, а не договорённости с человеком.
            return
        history = conversations_mod.as_history(conversation.id, 6)
        rendered = "\n".join(
            ("Я: " if item["from_owner"] else "Он: ") + item["text"][:200]
            for item in history)
        who_wrote = "владелец" if from_owner else "собеседник"
        system = (
            "Ты выделяешь из переписки договорённости: кто и что должен сделать.\n"
            "who_acts='owner' — выполнить должен владелец.\n"
            "who_acts='counterparty' — выполнить должен собеседник.\n"
            "Обязательство возникает и когда человек сам обещает, и когда его прямо "
            "просят: просьба в адрес владельца — это обязательство владельца, "
            "просьба владельца к собеседнику — обязательство собеседника.\n"
            "Вопросы, уточнения и обычный обмен репликами обязательств не создают — "
            "тогда пустой список."
        )
        user = (f"Переписка:\n{rendered}\n\nПоследнее сообщение ({who_wrote}): «{text}»\n\n"
                "Найди обязательства из последнего сообщения. Описывай действие, "
                "а не пересказывай реплику. due_hint — срок словами, как в тексте.")
        extraction = self.llm.structured_output(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            CommitmentExtraction, private=True)
        for candidate in extraction.commitments:
            if candidate.confidence < 0.5:
                continue
            commitments_mod.create(
                candidate.description,
                direction=candidate.direction(),
                counterparty_id=contact.id if contact else None,
                due_at=parse_due(candidate.due_hint),
                conversation_id=conversation.id, source_message_id=message.id,
                confidence=candidate.confidence, bus=self.bus)
        if not from_owner and contact:
            # Their reply closes what we were waiting for.
            commitments_mod.close_on_reply(conversation.id, contact.id, bus=self.bus)

    def _maybe_summarise(self, conversation, contact, message, from_owner):
        fresh = conversation.summary_updated_at or 0
        history = conversations_mod.as_history(conversation.id, 30)
        if len(history) < 3:
            return
        if (time.time() - fresh) < SUMMARY_MIN_AGE and len(history) % SUMMARY_EVERY:
            return
        rendered = "\n".join(("Я: " if item["from_owner"] else "Он: ") + item["text"][:250]
                             for item in history)
        who = contact.display_name if contact else "собеседник"
        system = ("Ты ведёшь краткую карточку переписки. Пиши по-русски, фактически, "
                  "без оценок и без выдумок.")
        user = (f"Переписка с «{who}»:\n{rendered}\n\n"
                "Сделай summary в 2–3 предложениях: о чём речь, чем закончилось, "
                "что осталось открытым. title — тема в 3–5 словах. decisions — принятые "
                "решения. entities — упомянутые объекты (проекты, сервера, компании).")
        result = self.llm.structured_output(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            ConversationSummary, private=True)
        if result.summary:
            conversations_mod.set_summary(conversation.id, result.summary, bus=self.bus)
            episodes_mod.upsert(conversation.id,
                                contact_id=contact.id if contact else None,
                                title=result.title, summary=result.summary,
                                decisions=result.decisions, entities=result.entities,
                                ts=message.ts, bus=self.bus)

    def _update_style(self, conversation, contact, message, from_owner):
        if contact is None or contact.is_owner:
            return
        history = conversations_mod.as_history(conversation.id, 30)
        if len(history) >= 4:
            contacts_mod.update_style(contact, history)


RELATIVE_DAYS = {"сегодня": 0, "завтра": 1, "послезавтра": 2}
WEEKDAYS = {"понедельник": 0, "вторник": 1, "сред": 2, "четверг": 3, "пятниц": 4,
            "суббот": 5, "воскресен": 6}


def parse_due(hint, now=None):
    """Turn «завтра к 14:00» or «в четверг» into a timestamp; None when unclear."""
    text = (hint or "").strip().lower()
    if not text:
        return None
    now = now or datetime.datetime.now(config.tz)
    target = None
    for word, offset in RELATIVE_DAYS.items():
        if word in text:
            target = now + datetime.timedelta(days=offset)
            break
    if target is None:
        for word, weekday in WEEKDAYS.items():
            if word in text:
                ahead = (weekday - now.weekday()) % 7 or 7
                target = now + datetime.timedelta(days=ahead)
                break
    if target is None:
        match = re.search(r"через\s+(\d+)\s*(минут|час|день|дня|дней|недел)", text)
        if match:
            amount = int(match.group(1))
            unit = match.group(2)
            delta = ({"минут": datetime.timedelta(minutes=amount)}.get(unit)
                     or (datetime.timedelta(hours=amount) if unit.startswith("час")
                         else datetime.timedelta(weeks=amount) if unit.startswith("недел")
                         else datetime.timedelta(days=amount)))
            return (now + delta).timestamp()
        match = re.search(r"(\d{1,2})[.\-/](\d{1,2})", text)
        if match:
            day, month = int(match.group(1)), int(match.group(2))
            try:
                target = now.replace(month=month, day=day)
                if target < now:
                    target = target.replace(year=now.year + 1)
            except ValueError:
                target = None
    if target is None:
        return None
    hour_match = re.search(r"(\d{1,2})[:.](\d{2})", text)
    if hour_match:
        target = target.replace(hour=int(hour_match.group(1)),
                                minute=int(hour_match.group(2)))
    elif re.search(r"\bутр", text):
        target = target.replace(hour=10, minute=0)
    elif re.search(r"\bвечер", text):
        target = target.replace(hour=19, minute=0)
    else:
        target = target.replace(hour=12, minute=0)
    return target.replace(second=0, microsecond=0).timestamp()
