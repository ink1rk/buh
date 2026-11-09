from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from app.core.config import ROOT


@lru_cache(maxsize=8)
def _validator(name: str) -> Draft202012Validator:
    path = ROOT / "schemas" / name
    schema = json.loads(path.read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())


def schema_errors(name: str, payload: dict) -> list[str]:
    return sorted(error.message for error in _validator(name).iter_errors(payload))


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
