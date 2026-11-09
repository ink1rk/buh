from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Counters:
    values: dict[str, int] = field(default_factory=dict)

    def inc(self, name: str, amount: int = 1) -> None:
        self.values[name] = self.values.get(name, 0) + amount

    def render(self) -> str:
        lines = [f"tmn_{key} {value}" for key, value in sorted(self.values.items())]
        return "\n".join(lines) + ("\n" if lines else "")


COUNTERS = Counters()
