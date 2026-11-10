from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from xml.etree import ElementTree

import feedparser

from app.core.timeutil import ensure_utc, parse_datetime, utcnow
from app.pipeline.types import Fact, SourceItemIn
from app.pipeline.urlsec import canonicalize

OSS_LICENSES = {
    "MIT",
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "GPL-2.0",
    "GPL-3.0",
    "LGPL-2.1",
    "LGPL-3.0",
    "MPL-2.0",
    "ISC",
    "AGPL-3.0",
    "Unlicense",
    "0BSD",
}


class FeedError(Exception):
    pass


def _sha(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _excerpt(text: str, limit: int = 160) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    return compact[:limit]


def _fact(fid: str, statement: str, url: str, excerpt: str) -> Fact:
    return Fact(id=fid, statement=_excerpt(statement, 400), evidence_url=url, evidence_excerpt=_excerpt(excerpt))


def classify_repo_age(created_at: datetime | None, now: datetime) -> bool:
    if created_at is None:
        return False
    return ensure_utc(now) - ensure_utc(created_at) <= timedelta(days=30)


def parse_github_search(payload: dict, now: datetime | None = None) -> list[SourceItemIn]:
    moment = now or utcnow()
    items: list[SourceItemIn] = []
    for row in payload.get("items", []):
        if row.get("fork") or row.get("archived"):
            continue
        html_url = row.get("html_url") or ""
        if not html_url.startswith("https://"):
            continue
        created = parse_datetime(row.get("created_at"))
        license_info = row.get("license") or {}
        spdx = license_info.get("spdx_id")
        if not spdx or spdx in {"NOASSERTION", "OTHER"}:
            license_state, spdx_value = "unknown", None
        elif spdx in OSS_LICENSES or spdx.startswith(("MIT", "Apache", "BSD", "GPL", "LGPL", "MPL", "ISC")):
            license_state, spdx_value = "explicit_open_source", spdx
        else:
            license_state, spdx_value = "explicit_non_oss", spdx
        description = _excerpt(row.get("description") or row.get("full_name") or "repository", 160)
        full_name = row.get("full_name") or "repository"
        statement = f"Репозиторий {full_name}: {description}"
        items.append(
            SourceItemIn(
                source_id="github_search",
                source_external_id=f"github:{row.get('id')}",
                source_url=html_url,
                canonical_url=canonicalize(html_url).url or html_url,
                title=full_name[:400],
                discovered_at=moment,
                published_at=parse_datetime(row.get("pushed_at")) or created,
                raw_sha256=_sha(f"github:{row.get('id')}:{row.get('pushed_at')}"),
                license_state=license_state,
                facts=[_fact("f1", statement, html_url, description)],
                content_kind="repo",
                license_spdx=spdx_value,
                topics=list(row.get("topics") or []),
                untrusted_text=row.get("description") or "",
                repo_id=str(row.get("id")),
                is_new=classify_repo_age(created, moment),
                practical=bool(description),
                audience=0.7,
            )
        )
    return items


def parse_github_release(repo: dict, release: dict, now: datetime | None = None) -> SourceItemIn:
    moment = now or utcnow()
    tag = str(release.get("tag_name") or "untagged")
    url = str(release.get("html_url") or repo.get("html_url") or "")
    body = _excerpt(release.get("body") or release.get("name") or tag, 160)
    license_info = (repo.get("license") or {})
    spdx = license_info.get("spdx_id")
    if spdx and spdx not in {"NOASSERTION", "OTHER"}:
        license_state, spdx_value = "explicit_open_source", spdx
    else:
        license_state, spdx_value = "unknown", None
    full_name = repo.get("full_name") or "repository"
    statement = f"{full_name} опубликовал релиз {tag}. {body}".strip()
    return SourceItemIn(
        source_id="github_releases",
        source_external_id=f"github-release:{repo.get('id')}:{tag}",
        source_url=url,
        canonical_url=canonicalize(url).url or url,
        title=f"{full_name} {tag}"[:400],
        discovered_at=moment,
        published_at=parse_datetime(release.get("published_at")),
        raw_sha256=_sha(f"release:{repo.get('id')}:{tag}:{release.get('published_at')}"),
        license_state=license_state,
        facts=[
            _fact("f1", statement, url, body or tag),
            _fact("f2", f"Тег релиза: {tag}.", url, tag),
        ],
        content_kind="release",
        license_spdx=spdx_value,
        topics=list(repo.get("topics") or []),
        untrusted_text=release.get("body") or "",
        repo_id=str(repo.get("id")),
        release_tag=tag,
        is_new=True,
        has_changelog=bool(release.get("body")),
        practical=True,
        audience=0.8,
    )


def parse_hn_item(item: dict, now: datetime | None = None) -> SourceItemIn | None:
    moment = now or utcnow()
    if item.get("type") not in {None, "story"}:
        return None
    title = (item.get("title") or "").strip()
    if len(title) < 4:
        return None
    external_url = item.get("url") or f"https://news.ycombinator.com/item?id={item.get('id')}"
    if not str(external_url).startswith("https://"):
        external_url = f"https://news.ycombinator.com/item?id={item.get('id')}"
    preprint = "arxiv.org" in external_url
    published = datetime.fromtimestamp(int(item["time"]), tz=utcnow().tzinfo) if item.get("time") else None
    excerpt = _excerpt(title, 160)
    return SourceItemIn(
        source_id="hackernews",
        source_external_id=f"hn:{item.get('id')}",
        source_url=external_url,
        canonical_url=canonicalize(external_url).url or external_url,
        title=title[:400],
        discovered_at=moment,
        published_at=published,
        raw_sha256=_sha(f"hn:{item.get('id')}:{title}"),
        license_state="not_applicable",
        facts=[_fact("f1", f"Hacker News отметил материал: {excerpt}", external_url, excerpt)],
        content_kind="research" if preprint else "news",
        is_preprint=preprint,
        untrusted_text=title,
        is_new=True,
        practical=False,
        audience=0.6,
        official_publisher=False,
    )


def parse_hf_models(payload: list[dict], now: datetime | None = None) -> list[SourceItemIn]:
    moment = now or utcnow()
    items: list[SourceItemIn] = []
    for row in payload:
        model_id = row.get("id") or row.get("modelId")
        if not model_id:
            continue
        url = f"https://huggingface.co/{model_id}"
        created = parse_datetime(row.get("createdAt") or row.get("created_at"))
        pipeline = row.get("pipeline_tag") or "model"
        excerpt = _excerpt(f"{model_id} pipeline {pipeline}", 160)
        items.append(
            SourceItemIn(
                source_id="huggingface",
                source_external_id=f"hf:{model_id}",
                source_url=url,
                canonical_url=url,
                title=str(model_id)[:400],
                discovered_at=moment,
                published_at=created,
                raw_sha256=_sha(f"hf:{model_id}:{row.get('createdAt')}"),
                license_state="unknown",
                facts=[_fact("f1", f"На Hugging Face появилась карточка {model_id} ({pipeline}).", url, excerpt)],
                content_kind="research" if "text-generation" in str(pipeline) else "repo",
                untrusted_text=str(row.get("cardData") or ""),
                is_new=True,
                topics=["llm"] if "text" in str(pipeline) else [],
                audience=0.75,
            )
        )
    return items


def parse_hf_spaces(payload: list[dict], now: datetime | None = None) -> list[SourceItemIn]:
    moment = now or utcnow()
    items: list[SourceItemIn] = []
    for row in payload:
        space_id = row.get("id") or row.get("modelId")
        if not space_id:
            continue
        url = f"https://huggingface.co/spaces/{space_id}"
        created = parse_datetime(row.get("createdAt") or row.get("created_at"))
        sdk = row.get("sdk") or "space"
        excerpt = _excerpt(f"{space_id} sdk {sdk}", 160)
        items.append(
            SourceItemIn(
                source_id="huggingface",
                source_external_id=f"hf-space:{space_id}",
                source_url=url,
                canonical_url=url,
                title=str(space_id)[:400],
                discovered_at=moment,
                published_at=created,
                raw_sha256=_sha(f"hf-space:{space_id}:{row.get('createdAt')}"),
                license_state="unknown",
                facts=[_fact("f1", f"На Hugging Face появилось пространство {space_id} ({sdk}).", url, excerpt)],
                content_kind="repo",
                untrusted_text=str(row.get("cardData") or ""),
                is_new=True,
                topics=["space"],
                audience=0.7,
            )
        )
    return items


def parse_cisa_kev(payload: dict, now: datetime | None = None) -> list[SourceItemIn]:
    moment = now or utcnow()
    items: list[SourceItemIn] = []
    for row in payload.get("vulnerabilities", []):
        cve = row.get("cveID") or ""
        if not cve.startswith("CVE-"):
            continue
        date_added = str(row.get("dateAdded") or "")
        vendor = row.get("vendorProject") or ""
        product = row.get("product") or ""
        summary = _excerpt(row.get("shortDescription") or "", 160)
        action = _excerpt(row.get("requiredAction") or "", 160)
        url = "https://www.cisa.gov/known-exploited-vulnerabilities-catalog"
        statement = (
            f"Каталог CISA KEV содержит {cve} от {date_added} для {vendor} {product}. "
            "Это запись каталога, не вывод редакции о каждом экземпляре продукта."
        ).strip()
        facts = [_fact("f1", statement, url, summary or cve)]
        if action:
            facts.append(_fact("f2", f"Рекомендация источника: {action}", url, action))
        items.append(
            SourceItemIn(
                source_id="cisa_kev",
                source_external_id=f"cve:{cve}:{date_added}",
                source_url=url,
                canonical_url=url,
                title=f"{cve}: {vendor} {product}".strip()[:400],
                discovered_at=moment,
                published_at=parse_datetime(date_added + "T00:00:00Z") if date_added else None,
                raw_sha256=_sha(f"{cve}:{date_added}:{summary}"),
                license_state="not_applicable",
                facts=facts,
                content_kind="advisory",
                cve_id=cve,
                date_added=date_added,
                cvss=None,
                official_publisher=True,
                untrusted_text=f"{summary}\n{action}",
                is_new=True,
                practical=True,
                has_changelog=False,
                audience=0.9,
            )
        )
    return items


def parse_feed(xml_text: str, source_id: str, *, mark_preprints: bool, now: datetime | None = None) -> list[SourceItemIn]:
    if not (xml_text or "").strip():
        return []
    lowered = xml_text.lower()
    if "<!doctype" in lowered or "<!entity" in lowered:
        raise FeedError("doctype")
    try:
        ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        raise FeedError("malformed") from exc
    parsed = feedparser.parse(xml_text)
    if getattr(parsed, "bozo", False) and not parsed.entries:
        raise FeedError("malformed")
    moment = now or utcnow()
    items: list[SourceItemIn] = []
    for entry in parsed.entries:
        link = entry.get("link") or ""
        title = (entry.get("title") or "").strip()
        if not link.startswith("https://") or len(title) < 4:
            continue
        published = None
        if entry.get("published"):
            published = parse_datetime(entry.get("published"))
        elif entry.get("updated"):
            published = parse_datetime(entry.get("updated"))
        tags = [tag.get("term", "") for tag in entry.get("tags", []) if isinstance(tag, dict)]
        arxiv_id = ""
        version = "v1"
        id_match = re.search(r"((?:\d{4}\.\d{4,5})|(?:[a-z\-]+/\d{7}))(v\d+)?", link + " " + entry.get("id", ""), re.I)
        if id_match:
            arxiv_id = id_match.group(1)
            version = id_match.group(2) or "v1"
        preprint = bool(mark_preprints or "arxiv.org" in link)
        summary = _excerpt(entry.get("summary") or title, 160)
        external = f"arxiv:{arxiv_id}:{version}" if arxiv_id else f"article:{hashlib.sha256(link.encode()).hexdigest()[:16]}"
        kind = "research" if preprint else "news"
        if source_id == "pypi_updates":
            kind = "package"
        statement = title if not preprint else f"Препринт: {title}"
        items.append(
            SourceItemIn(
                source_id=source_id,
                source_external_id=external,
                source_url=link,
                canonical_url=canonicalize(link).url or link,
                title=title[:400],
                discovered_at=moment,
                published_at=published,
                raw_sha256=_sha(external + title),
                license_state="not_applicable" if preprint else "unknown",
                facts=[_fact("f1", statement, link, summary)],
                content_kind=kind,
                is_preprint=preprint,
                untrusted_text=_excerpt(entry.get("summary") or "", 500),
                categories=tags,
                is_new=True,
                official_publisher=source_id in {"kubernetes", "cisa_kev"},
                audience=0.7,
                practical=source_id in {"kubernetes", "pypi_updates"},
            )
        )
    return items


def filter_pypi(items: list[SourceItemIn], watched: list[str]) -> list[SourceItemIn]:
    if not watched:
        return []
    allowed = {name.lower() for name in watched}
    kept = []
    for item in items:
        haystack = (item.title + " " + item.source_url).lower()
        if any(name in haystack for name in allowed):
            kept.append(item)
    return kept
