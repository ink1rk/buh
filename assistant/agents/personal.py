#!/usr/bin/env python3
"""Personal agent: the generalist.

It keeps the skills that already worked — news, weather, finance, Telegram
digest, briefings — and answers everything that no specialised agent claims.
The skills themselves stay where they are; the agent receives them as a small
adapter, so the core does not depend on the legacy module and the legacy module
does not depend on the agent.
"""
from core.agents import Agent, AgentResult


class PersonalAgent(Agent):
    name = "personal"
    description = "Общие вопросы, новости, погода, финансы, брифинги"
    supported_intents = ("general", "news", "weather", "finance", "telegram", "trading")

    def __init__(self, llm, skills):
        self.llm = llm
        self.skills = skills

    def can_handle(self, context):
        return True              # fallback agent: claims whatever is left

    def handle(self, context):
        skills = self.skills
        intents = context.intents or skills.detect_intents(context.text)
        private = skills.is_private(intents)
        blocks = skills.context_blocks(intents, context.text)

        system = skills.build_system(channel=context.interface,
                                     brain="local" if private else "cursor")
        memory_block = context.memory_block(6)
        if memory_block:
            system += "\n\nЧТО ТЫ ПОМНИШЬ О ВЛАДЕЛЬЦЕ:\n" + memory_block
        schedule_block = context.schedule_block()
        if schedule_block:
            system += ("\n\nБЛИЖАЙШИЕ ВСТРЕЧИ ВЛАДЕЛЬЦА "
                       f"(сейчас {context.now:%d.%m %H:%M}):\n" + schedule_block)

        messages = [{"role": "system", "content": system}]
        messages += skills.history(context.session)
        user = context.text
        if blocks:
            user = "ДАННЫЕ:\n" + "\n\n".join(b for b in blocks if b) + "\n\nВОПРОС: " + user
        messages.append({"role": "user", "content": user})

        text, provider = self.llm.generate(messages, private=private,
                                           provider=None if private else "cursor")
        return AgentResult(text=text, agent=self.name, provider=provider,
                           data={"intents": intents, "private": private})
