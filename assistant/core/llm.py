#!/usr/bin/env python3
"""LLM provider abstraction.

Business logic asks for a provider by role ("private", "quality"), never for a
concrete SDK. Two providers exist today — a local Ollama and the Cursor gateway
— and adding OpenAI or Anthropic later means adding a class here.

structured_output() is the important part: when the result feeds code rather
than a human, free-form text is a bug. The model is asked for JSON, the answer
is parsed, validated against a Pydantic model, and repaired once before failing.
"""
import json
import re

import httpx
from pydantic import BaseModel, ValidationError

from .config import config


class LLMError(RuntimeError):
    pass


class LLMProvider:
    name = "base"
    supports_private = False

    def generate(self, messages, temperature=0.4, max_tokens=900, **kwargs):
        raise NotImplementedError

    def stream(self, messages, **kwargs):
        """Default streaming: one chunk. Real streaming is provider-specific."""
        yield self.generate(messages, **kwargs)

    def structured_output(self, messages, schema: type[BaseModel], retries=1, **kwargs):
        instruction = (
            "Ответ строго в формате JSON по схеме, без markdown, без пояснений, "
            "без ```-блоков. Схема:\n"
            + json.dumps(schema.model_json_schema(), ensure_ascii=False))
        convo = list(messages) + [{"role": "system", "content": instruction}]
        last_error = None
        for attempt in range(retries + 1):
            raw = self.generate(convo, **kwargs)
            try:
                return schema.model_validate(_extract_json(raw))
            except (ValueError, ValidationError) as e:
                last_error = e
                convo = list(messages) + [
                    {"role": "system", "content": instruction},
                    {"role": "assistant", "content": raw[:2000]},
                    {"role": "user", "content":
                        f"Это невалидно ({str(e)[:300]}). Верни ТОЛЬКО корректный JSON."}]
        raise LLMError(f"structured output invalid: {last_error}")

    def health(self):
        raise NotImplementedError


def _extract_json(raw):
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    # Models like to wrap JSON in prose; take the outermost object or array.
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if 0 <= start < end:
            try:
                return json.loads(text[start:end + 1])
            except ValueError:
                continue
    raise ValueError("no JSON found in model output")


class LocalProvider(LLMProvider):
    """Ollama on the same machine: private data never leaves the server."""
    name = "local"
    supports_private = True

    def __init__(self, cfg=None):
        self.cfg = cfg or config.llm

    def generate(self, messages, temperature=0.4, max_tokens=900, **kwargs):
        payload = {"model": self.cfg.local_model, "messages": messages, "stream": False,
                   "options": {"temperature": temperature, "num_predict": max_tokens}}
        with httpx.Client(timeout=self.cfg.timeout, trust_env=False) as client:
            response = client.post(f"{self.cfg.local_url}/api/chat", json=payload)
            response.raise_for_status()
            return (response.json().get("message") or {}).get("content", "").strip()

    def health(self):
        with httpx.Client(timeout=10, trust_env=False) as client:
            response = client.get(f"{self.cfg.local_url}/api/tags")
            response.raise_for_status()
            models = [m.get("name") for m in response.json().get("models", [])]
        return {"models": len(models), "model": self.cfg.local_model}


class GatewayProvider(LLMProvider):
    """OpenAI-compatible Cursor gateway: better reasoning, non-private data only."""
    name = "cursor"
    supports_private = False

    def __init__(self, cfg=None):
        self.cfg = cfg or config.llm

    def generate(self, messages, temperature=0.4, max_tokens=1200, **kwargs):
        payload = {"model": self.cfg.gateway_model, "messages": messages,
                   "temperature": temperature, "max_tokens": max_tokens}
        headers = {"Authorization": f"Bearer {self.cfg.gateway_key}"}
        with httpx.Client(timeout=self.cfg.timeout, trust_env=False) as client:
            response = client.post(f"{self.cfg.gateway_url}/chat/completions",
                                   json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        return (data["choices"][0]["message"]["content"] or "").strip()

    def health(self):
        with httpx.Client(timeout=15, trust_env=False) as client:
            response = client.get(f"{self.cfg.gateway_url}/models",
                                  headers={"Authorization": f"Bearer {self.cfg.gateway_key}"})
            response.raise_for_status()
        return {"model": self.cfg.gateway_model}


class LLMRegistry:
    """Picks a provider by role and falls back when one is down."""

    def __init__(self, providers=None, default=None, private=None):
        self.providers = {p.name: p for p in (providers or [LocalProvider(), GatewayProvider()])}
        self.default = default or config.llm.default_provider
        self.private = private or config.llm.private_provider

    def get(self, name=None, private=False):
        if private:
            return self.providers[self.private]
        return self.providers.get(name or self.default) or next(iter(self.providers.values()))

    def generate(self, messages, provider=None, private=False, fallback=True, **kwargs):
        chosen = self.get(provider, private)
        try:
            return chosen.generate(messages, **kwargs), chosen.name
        except Exception as primary_error:
            if not fallback or private:
                raise
            for name, candidate in self.providers.items():
                if name == chosen.name:
                    continue
                try:
                    return candidate.generate(messages, **kwargs), name
                except Exception:
                    continue
            raise primary_error

    def structured_output(self, messages, schema, provider=None, private=True, **kwargs):
        return self.get(provider, private).structured_output(messages, schema, **kwargs)
