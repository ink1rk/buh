"""Logical model aliases, compatible fallback, and a local spend preflight."""

from __future__ import annotations

from dataclasses import dataclass, field

COMPATIBLE = {
    "assistant-fast": ["assistant-fast", "reasoning-strong"],
    "reasoning-strong": ["reasoning-strong"],
    "research-long": ["research-long", "reasoning-strong"],
    "code-strong": ["code-strong"],
    "critic-independent": ["critic-independent", "reasoning-strong"],
}


@dataclass
class Provider:
    failures: dict[str, str] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    def complete(self, model: str) -> str:
        self.calls.append(model)
        if model in self.failures:
            raise RuntimeError(self.failures[model])
        return f"ok:{model}"


def complete_with_fallback(provider: Provider, alias: str) -> tuple[str, str, list[str]]:
    """Return text, model used, and switch reasons. Does not promise zero overspend."""
    chain = COMPATIBLE[alias]
    reasons: list[str] = []
    last_error = "no model"
    for index, model in enumerate(chain):
        try:
            return provider.complete(model), model, reasons
        except RuntimeError as exc:
            last_error = str(exc)
            if index < len(chain) - 1:
                reasons.append(f"{model} -> {chain[index + 1]}: {last_error}")
    raise RuntimeError(last_error)
