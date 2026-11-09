from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.pipeline.types import SourceItemIn
from app.pipeline.urlsec import canonicalize


@dataclass(frozen=True)
class GitHubRef:
    owner: str
    name: str
    tag: str | None = None


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def parse_github(url: str) -> GitHubRef | None:
    canon = canonicalize(url)
    if not canon.ok:
        return None
    host = canon.host
    if host != "github.com" and not host.endswith(".github.com"):
        return None
    parts = [part for part in urlsplit(canon.url).path.split("/") if part]
    if len(parts) < 2:
        return None
    owner, name = parts[0], parts[1]
    tag = None
    if len(parts) >= 5 and parts[2] == "releases" and parts[3] == "tag":
        tag = parts[4]
    return GitHubRef(owner=owner, name=name, tag=tag)


def parse_arxiv(url: str) -> tuple[str, str] | None:
    canon = canonicalize(url)
    if not canon.ok or "arxiv.org" not in canon.host:
        return None
    match = re.search(r"((?:[a-z\-]+/\d{7})|(?:\d{4}\.\d{4,5}))(v\d+)?", canon.url, re.I)
    if not match:
        return None
    return match.group(1), match.group(2) or "v1"


def identity_keys(item: SourceItemIn) -> list[str]:
    keys: list[str] = []
    github = parse_github(item.canonical_url or item.source_url)
    tag = item.release_tag or (github.tag if github else None)
    is_release = item.content_kind == "release" or bool(tag and item.content_kind != "repo")
    if item.content_kind == "release" or (github and github.tag and item.content_kind != "repo"):
        is_release = True
    if is_release and tag:
        if item.repo_id:
            keys.append(f"github-release:{item.repo_id}:{tag}")
        if github:
            keys.append(f"github-release:{github.owner}/{github.name}:{tag}".lower())
        return _unique(keys)
    if item.cve_id:
        keys.append(f"cve:{item.cve_id}:{item.date_added or 'na'}")
    arxiv = parse_arxiv(item.source_url) or (parse_arxiv(item.canonical_url) if item.canonical_url else None)
    if arxiv:
        keys.append(f"arxiv:{arxiv[0]}:{arxiv[1]}")
    if item.repo_id and item.content_kind == "repo":
        keys.append(f"github:{item.repo_id}")
    if github and not github.tag:
        keys.append(f"github-repo:{github.owner}/{github.name}".lower())
    if item.source_external_id.startswith("hn:") and not github:
        keys.append(item.source_external_id)
    if not keys:
        canon = canonicalize(item.canonical_url or item.source_url)
        basis = canon.url if canon.ok else item.source_url
        keys.append("article:" + sha256_text(basis)[:32])
    return _unique(keys)


def repo_identity(item: SourceItemIn) -> str:
    github = parse_github(item.canonical_url or item.source_url)
    if github:
        return f"github-repo:{github.owner}/{github.name}".lower()
    if item.repo_id:
        return f"github:{item.repo_id}"
    return ""


def cluster_id(item: SourceItemIn) -> str:
    return identity_keys(item)[0]


def title_tokens(title: str) -> set[str]:
    return set(re.findall(r"[0-9a-zа-яё]+", title.lower()))


def title_similarity(left: str, right: str) -> float:
    a = title_tokens(left)
    b = title_tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _unique(values: list[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return seen
