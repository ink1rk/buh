from __future__ import annotations

from datetime import datetime

from app.adapters.base import DiscoverResult, SourceHealth
from app.adapters.parse import FeedError, filter_pypi, parse_feed


class RssAdapter:
    def __init__(
        self,
        source_id: str,
        xml_text: str | None = None,
        *,
        enabled: bool = True,
        mark_preprints: bool = False,
        watched: list[str] | None = None,
        feed_url: str | None = None,
    ) -> None:
        self.source_id = source_id
        self.xml_text = xml_text
        self.enabled = enabled
        self.mark_preprints = mark_preprints
        self.watched = watched
        self.feed_url = feed_url
        self.fetch_attempted = False

    def discover(self, since: datetime | None, limit: int) -> DiscoverResult:
        del since
        if not self.enabled or not self.feed_url and self.xml_text is None:
            return DiscoverResult([], SourceHealth("disabled", "feed not configured"))
        if self.xml_text is None:
            return DiscoverResult([], SourceHealth("skipped", "offline and no fixture"))
        self.fetch_attempted = True
        try:
            items = parse_feed(self.xml_text, self.source_id, mark_preprints=self.mark_preprints)
        except FeedError as exc:
            return DiscoverResult([], SourceHealth("error", str(exc)))
        if self.watched is not None:
            items = filter_pypi(items, self.watched)
        return DiscoverResult(items[:limit], SourceHealth("ok", requests_made=1))

    def validate_source(self) -> SourceHealth:
        if not self.enabled:
            return SourceHealth("disabled", "awaiting an exact official feed url")
        return SourceHealth("ok", "rss")


class ArxivAdapter(RssAdapter):
    def __init__(self, xml_text: str | None = None, source_id: str = "arxiv_ai") -> None:
        super().__init__(source_id, xml_text, mark_preprints=True, feed_url="https://rss.arxiv.org/rss/cs.AI")


class KubernetesBlogAdapter(RssAdapter):
    def __init__(self, xml_text: str | None = None) -> None:
        super().__init__("kubernetes", xml_text, feed_url="https://kubernetes.io/feed.xml")


class PyPIAdapter(RssAdapter):
    def __init__(self, xml_text: str | None = None, watched: list[str] | None = None) -> None:
        super().__init__(
            "pypi_updates",
            xml_text,
            watched=[] if watched is None else watched,
            feed_url="https://pypi.org/rss/updates.xml",
        )


class CloudflareChangelogAdapter(RssAdapter):
    def __init__(self, xml_text: str | None = None, feed_url: str | None = None) -> None:
        super().__init__(
            "cloudflare_changelog",
            xml_text,
            enabled=bool(feed_url),
            feed_url=feed_url,
        )
