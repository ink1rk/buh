from __future__ import annotations

from datetime import datetime

from app.adapters.base import DiscoverResult, SourceHealth
from app.adapters.parse import parse_hf_models


class HuggingFaceAdapter:
    """Public metadata only. Model weights are never downloaded."""

    source_id = "huggingface"

    def __init__(self, models: list[dict] | None = None, request_cap: int = 6) -> None:
        self.models = models or []
        self.request_cap = request_cap

    def discover(self, since: datetime | None, limit: int) -> DiscoverResult:
        del since
        items = parse_hf_models(self.models[: min(limit, self.request_cap)])
        return DiscoverResult(items, SourceHealth("ok", requests_made=1 if self.models else 0))

    def validate_source(self) -> SourceHealth:
        return SourceHealth("ok", "weights_disabled")

    @staticmethod
    def hub_api_available() -> bool:
        from huggingface_hub import HfApi

        return callable(getattr(HfApi, "list_models", None))
