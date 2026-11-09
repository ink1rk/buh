from __future__ import annotations

from app.pipeline.types import RouteDecision, SourceItemIn

CHANNEL_IDS = ("ai_news", "ai_tools", "github", "cyber", "infra", "homelab", "dev", "future")


def _blob(item: SourceItemIn) -> str:
    topics = " ".join(item.topics + item.categories)
    return f"{item.title} {item.untrusted_text} {topics} {item.source_id} {item.content_kind}".lower()


def route_item(item: SourceItemIn) -> RouteDecision:
    text = _blob(item)
    topics = {topic.lower() for topic in item.topics}

    if item.cve_id or item.source_id == "cisa_kev" or item.content_kind == "advisory":
        alternatives = ["infra"] if "kubernetes" in text or "k8s" in text else []
        return RouteDecision("cyber", alternatives, 0.95, "Официальное уведомление об уязвимости относится к КиберРадару.")

    science = item.source_id == "arxiv_science" or any(cat.lower() in {"cs.ro", "physics"} for cat in item.categories)
    if item.is_preprint and science:
        return RouteDecision("future", ["ai_news"], 0.8, "Препринт вне прикладного AI отнесён к ТехноЗавтра.")
    if item.is_preprint or item.source_id in {"arxiv_ai"}:
        return RouteDecision("ai_news", [], 0.86, "Препринт или исследование AI — основной канал НейроПульс.")

    if topics & {"self-hosted", "homelab", "proxmox"} or any(word in text for word in ("self-hosted", "homelab", "proxmox", "truenas")):
        return RouteDecision("homelab", [], 0.9, "Практический self-hosted материал ближе аудитории HomeLab.")

    if item.source_id == "pypi_updates" or item.content_kind == "package":
        return RouteDecision("dev", ["github"], 0.84, "Пакетный релиз — сценарий разработчика, канал DevPulse.")

    if item.source_id in {"kubernetes", "cloudflare_changelog"}:
        return RouteDecision("infra", ["dev"], 0.88, "Инфраструктурный changelog относится к ИнфраХаб.")

    if "llm" in topics and item.content_kind == "release" and "model" in text:
        return RouteDecision("ai_news", ["ai_tools"], 0.84, "Релиз модели — новость, а не обзор инструмента.")
    if "llm" in topics or (item.source_id == "huggingface" and item.content_kind != "news"):
        primary = "ai_news" if item.content_kind == "research" else "ai_tools"
        return RouteDecision(primary, [], 0.82, "Материал про LLM-инструмент назначен одному основному каналу.")

    if "devtools" in topics or "ci" in topics:
        return RouteDecision("dev", ["github"], 0.86, "Инструмент разработки назначен в DevPulse.")
    if "security-tool" in topics or "security" in topics:
        return RouteDecision("cyber", [], 0.7, "Security-tool не публикуется автоматически и идёт в КиберРадар на разбор.")
    if "docker" in topics:
        primary = "homelab" if "self-hosted" in text else "infra"
        return RouteDecision(primary, [], 0.75, "Docker-проект назначен одному каналу по контексту применения.")

    if item.content_kind in {"repo", "release"} or item.source_id in {"github_search", "github_releases"}:
        return RouteDecision("github", [], 0.84, "Репозиторий или релиз без более узкой темы — GitHub Находки.")

    if item.source_id == "huggingface":
        return RouteDecision("ai_news", ["ai_tools"], 0.8, "Карточка Hugging Face по умолчанию идёт в НейроПульс.")

    return RouteDecision("dev", [], 0.55, "Нет узкого правила — оставлен один основной канал DevPulse для ручного переноса.")
