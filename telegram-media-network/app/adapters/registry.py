from __future__ import annotations

from app.adapters.cisa import CisaKevAdapter
from app.adapters.github import GitHubReleasesAdapter, GitHubSearchAdapter
from app.adapters.hackernews import HackerNewsAdapter
from app.adapters.huggingface import HuggingFaceAdapter
from app.adapters.rssfeed import ArxivAdapter, CloudflareChangelogAdapter, KubernetesBlogAdapter, PyPIAdapter

ADAPTER_TYPES = (
    GitHubSearchAdapter,
    GitHubReleasesAdapter,
    HuggingFaceAdapter,
    HackerNewsAdapter,
    ArxivAdapter,
    CisaKevAdapter,
    KubernetesBlogAdapter,
    PyPIAdapter,
    CloudflareChangelogAdapter,
)


def adapter_names() -> list[str]:
    return [cls.__name__ for cls in ADAPTER_TYPES]
