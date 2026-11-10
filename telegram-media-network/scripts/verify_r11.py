#!/usr/bin/env python3
"""R11 verification. Does not send Telegram or call live Ollama."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    commands = [
        [sys.executable, "-m", "pytest", "-q"],
        [sys.executable, "-m", "ruff", "check", "app", "tests"],
        [sys.executable, "-m", "mypy", "app"],
    ]
    for command in commands:
        print("+", " ".join(command), flush=True)
        completed = subprocess.run(command, cwd=ROOT)
        if completed.returncode != 0:
            return completed.returncode
    print("PUBLISH ENABLED? NO. TELEGRAM SEND COUNT? 0. LIVE DATA? NO. REAL REVENUE? UNKNOWN. PRODUCTION READY? NO.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
