"""Synthetic DEMO observations. They are not news and must not be published."""

from __future__ import annotations

CHANNELS = ("ai_news", "ai_tools", "github", "cyber", "infra", "homelab", "dev", "future")

SHARED_URL = "https://example.com/demo/shared-local-model-note"
SHARED_TITLE = "DEMO: учебная заметка об одном и том же локальном запуске"


def _row(
    channel: str,
    number: int,
    *,
    title: str,
    url: str,
    source_id: str,
    summary: str,
    cve: str = "",
    repo: str = "",
    tag: str = "",
    arxiv: str = "",
    stars: int | None = None,
    days_old: int = 1,
) -> dict:
    return {
        "channel_id": channel,
        "external_id": f"demo:{channel}:{number:02d}",
        "title": title,
        "url": url,
        "source_id": source_id,
        "summary": summary,
        "cve": cve,
        "repo": repo,
        "tag": tag,
        "arxiv": arxiv,
        "stars": stars,
        "days_old": days_old,
        "synthetic": True,
    }


def build_pack() -> list[dict]:
    """160 observations: 20 for each channel. Three of them describe one shared event."""
    rows: list[dict] = []
    for channel in CHANNELS:
        for number in range(1, 21):
            source = _source_for(channel, number)
            title = f"DEMO: {channel} материал {number} для редакционной очереди"
            url = f"https://example.com/demo/{channel}/{number}"
            summary = f"Учебный источник описывает сценарий {number} для канала {channel}. Это не измерение и не новость дня."
            cve = ""
            repo = ""
            tag = ""
            arxiv = ""
            stars = None
            days = 1 if number < 15 else 40
            if channel == "ai_news" and number == 1:
                title = SHARED_TITLE
                url = SHARED_URL
                source = "huggingface"
                summary = "Учебная карточка: один и тот же локальный запуск описан в трёх демо-источниках."
            elif channel == "github" and number in {2, 3}:
                tag = "v1.2.0" if number == 2 else "v1.3.0"
                repo = "acme/demo-runner"
                title = f"DEMO: demo-runner {tag} для локальной служебной задачи"
                url = f"https://example.com/demo/acme/demo-runner/{tag}"
                source = "github_releases"
                summary = f"Учебный репозиторий acme/demo-runner отметил тег {tag}. Лицензия в этой карточке не указана."
            elif channel == "github" and number == 4:
                stars = 120
                repo = "acme/demo-stars"
                title = "DEMO: репозиторий со одним снимком звёзд"
                url = "https://example.com/demo/acme/demo-stars"
                source = "github_search"
                summary = "Зафиксировано одно число 120. Это не динамика и не рост."
            elif channel == "cyber" and number == 1:
                cve = "CVE-2026-990099"
                title = "DEMO: CVE-2026-990099 учебная запись каталога"
                url = "https://example.com/demo/cve-2026-990099"
                source = "cisa_kev"
                summary = "Учебная запись каталога для Demo Catalog App. Запись не описывает все установки."
                days = 2
            elif channel == "future" and number == 1:
                arxiv = "2601.09999"
                title = "DEMO: препринт 2601.09999 о лабораторном макете"
                url = "https://example.com/demo/arxiv/2601.09999"
                source = "arxiv_science"
                summary = "Учебный препринт. Рецензии в карточке нет."
            rows.append(
                _row(
                    channel,
                    number,
                    title=title,
                    url=url,
                    source_id=source,
                    summary=summary,
                    cve=cve,
                    repo=repo,
                    tag=tag,
                    arxiv=arxiv,
                    stars=stars,
                    days_old=days,
                )
            )
    rows.append(
        _row(
            "ai_news",
            21,
            title=SHARED_TITLE,
            url=SHARED_URL,
            source_id="hackernews",
            summary="Тот же учебный запуск, второй демо-источник. Популярность не доказана.",
        )
    )
    rows.append(
        _row(
            "ai_news",
            22,
            title=SHARED_TITLE,
            url=SHARED_URL,
            source_id="github_search",
            summary="Тот же учебный запуск, третий демо-источник. Это не отдельная тема.",
        )
    )
    return rows


def _source_for(channel: str, number: int) -> str:
    table = {
        "ai_news": "huggingface",
        "ai_tools": "github_search",
        "github": "github_search",
        "cyber": "cisa_kev",
        "infra": "kubernetes",
        "homelab": "github_releases",
        "dev": "pypi_updates",
        "future": "arxiv_science",
    }
    if number % 5 == 0:
        return "hackernews"
    return table[channel]
