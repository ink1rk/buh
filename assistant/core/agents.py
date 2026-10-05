#!/usr/bin/env python3
"""Agents.

An agent turns a Context into an answer and, optionally, into action requests.
It never touches an external API: it returns ActionRequest objects and the core
decides whether they may run.

Two agents exist so far. PersonalAgent is the generalist that keeps the old
skills (news, weather, finance, briefing) working; CommunicationAgent handles
everything about people — incoming messages, suggested replies, commitments.
"""
from dataclasses import dataclass, field

from pydantic import BaseModel, Field


@dataclass
class ActionRequest:
    type: str
    parameters: dict = field(default_factory=dict)
    reason: str = ""
    user_confirmed: bool = False


@dataclass
class AgentResult:
    text: str = ""
    actions: list = field(default_factory=list)      # list[ActionRequest]
    data: dict = field(default_factory=dict)
    agent: str = ""
    provider: str = ""

    def as_dict(self):
        return {"text": self.text, "agent": self.agent, "provider": self.provider,
                "data": self.data,
                "actions": [{"type": a.type, "parameters": a.parameters,
                             "reason": a.reason} for a in self.actions]}


class Agent:
    name = "base"
    description = ""
    supported_intents: tuple = ()

    def can_handle(self, context):
        if not self.supported_intents:
            return False
        return any(intent in self.supported_intents for intent in context.intents)

    def handle(self, context):
        raise NotImplementedError


class AgentRegistry:
    """Routes by intent, with one explicit fallback — no silent guessing."""

    def __init__(self, agents=None, fallback=None):
        self.agents = list(agents or [])
        self.fallback = fallback

    def register(self, agent, fallback=False):
        self.agents.append(agent)
        if fallback:
            self.fallback = agent
        return agent

    def select(self, context):
        for agent in self.agents:
            if agent.can_handle(context):
                return agent
        return self.fallback

    def describe(self):
        return [{"name": a.name, "description": a.description,
                 "intents": list(a.supported_intents)} for a in self.agents]


# --- structured outputs shared by agents ---------------------------------
class IntentResult(BaseModel):
    intent: str = Field(description="машинное имя намерения")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    parameters: dict = Field(default_factory=dict)


class ReplyOptions(BaseModel):
    context_summary: str = Field(default="", description="одно предложение о ситуации")
    options: list[str] = Field(default_factory=list, description="2-3 варианта ответа")


class MemoryCandidate(BaseModel):
    type: str = Field(description="FACT|PREFERENCE|EVENT|RELATION|PROCEDURE")
    content: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    about: str = Field(default="owner", description="owner | contact")


class MemoryExtraction(BaseModel):
    memories: list[MemoryCandidate] = Field(default_factory=list)
    tasks: list[str] = Field(default_factory=list)


class CommitmentCandidate(BaseModel):
    description: str
    # Кто исполнитель — единственный вопрос, на который модель отвечает надёжно.
    # Сторона обязательства (I_OWE/THEY_OWE) выводится из этого поля в коде.
    who_acts: str = Field(default="owner",
                          description="owner | counterparty — кто должен выполнить")
    due_hint: str = Field(default="", description="срок словами, как в тексте")
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)

    def direction(self):
        return "THEY_OWE" if self.who_acts.strip().lower().startswith("counter") \
            else "I_OWE"


class CommitmentExtraction(BaseModel):
    commitments: list[CommitmentCandidate] = Field(default_factory=list)


class ConversationSummary(BaseModel):
    summary: str = ""
    title: str = ""
    decisions: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
