#!/usr/bin/env python3
"""Intent recognition.

Rules first, model second. A question like «что я обещал Ивану» must route to
the communication agent every single time, and a keyword table does that
instantly and predictably; the LLM is only asked when the rules find nothing
and a caller explicitly wants a second opinion.
"""
import re

# Ordered: the first match becomes the primary intent.
RULES = (
    ("commitments", (
        r"что я обещал", r"мои обещани", r"обязательств", r"кому я должен",
        r"что я должен (?:сделать|отправить|прислать)", r"незакрыт",
        r"кому (?:надо|нужно) ответить", r"кому ответить")),
    ("waiting_reply", (
        r"жду ответ", r"от кого я жду", r"кто мне должен", r"кто должен мне",
        r"кто (?:ещё |еще )?не ответил")),
    ("who_wrote", (
        r"кто (?:мне )?(?:написал|писал)", r"что нового в переписк", r"непрочит",
        r"есть что-то срочн", r"кто на связи")),
    ("contact_info", (
        r"кто так(?:ой|ая)", r"что (?:мы|я) .{0,20}обсуждал", r"что я говорил про",
        r"о чём мы говорили", r"о чем мы говорили", r"расскажи про ",
        r"что ты знаешь про ", r"что помнишь про ")),
    ("suggest_reply", (
        r"^ответь ", r"^напиши ", r"^отправь сообщени", r"ответь ему",
        r"ответь ей", r"напиши ему", r"напиши ей")),
    ("memory", (
        r"что ты помнишь", r"что ты знаешь обо мне", r"забудь(?: про)?",
        r"запомни")),
)

COMMUNICATION_INTENTS = ("commitments", "waiting_reply", "who_wrote", "contact_info",
                         "suggest_reply")


def detect(text, skills=None):
    """Communication intents from rules, everything else from the skills."""
    lowered = (text or "").lower()
    found = [name for name, patterns in RULES
             if any(re.search(pattern, lowered) for pattern in patterns)]
    if skills is not None:
        legacy = [i for i in skills.detect_intents(text or "") if i != "general"]
        found += [i for i in legacy if i not in found]
    return found or ["general"]


def is_communication(intents):
    return any(intent in COMMUNICATION_INTENTS for intent in intents)
