from __future__ import annotations

from pathlib import Path

import yaml
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.models import Channel, CredentialRef, RuntimeSetting, Source
from app.core.timeutil import utcnow


class ConfigError(ValueError):
    pass


# Runtime progress is not part of the YAML document and must survive a reload.
RUNTIME_POLICY_KEYS = ("query_cursor",)


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_channels_document(path: Path) -> dict:
    document = load_yaml(path)
    channels = document.get("channels") or []
    ids = [channel["id"] for channel in channels]
    if len(ids) != 8 or len(set(ids)) != 8:
        raise ConfigError("expected exactly 8 unique channel ids")
    network = document.get("network") or {}
    if network.get("timezone") != "Europe/Moscow":
        raise ConfigError("timezone must be Europe/Moscow")
    for channel in channels:
        if int(channel.get("daily_cap") or 0) < 1:
            raise ConfigError(f"daily cap invalid for {channel.get('id')}")
        if not channel.get("schedule"):
            raise ConfigError(f"schedule missing for {channel.get('id')}")
    return document


def shipped_is_safe(document: dict) -> None:
    network = document["network"]
    if network.get("dry_run") is not True or network.get("publish_enabled") is not False:
        raise ConfigError("shipped network must stay dry-run and unpublished")
    if network.get("global_kill_switch") is not True or network.get("sponsored_enabled") is not False:
        raise ConfigError("shipped network must keep the kill switch on and sponsorship off")
    for channel in document["channels"]:
        if channel.get("publish_enabled") is not False:
            raise ConfigError(f"{channel['id']} publish_enabled must be false")


def load_sources_document(path: Path) -> dict:
    document = load_yaml(path)
    sources = document.get("sources") or []
    if len(sources) < 7:
        raise ConfigError("expected at least 7 sources")
    return document


def bootstrap(session: Session, settings: Settings, config_dir: Path | None = None) -> None:
    directory = config_dir or settings.config_dir
    channels_doc = load_channels_document(directory / "channels.yaml")
    network = channels_doc["network"]
    force_off = network.get("publish_enabled") is not True
    for raw in channels_doc["channels"]:
        row = session.get(Channel, raw["id"])
        if row is None:
            row = Channel(id=raw["id"])
            session.add(row)
        theme = raw.get("theme") or {}
        row.title = raw["title"]
        row.category = raw.get("category") or ""
        row.username = raw.get("username") or ""
        row.chat_id = str(raw.get("chat_id") or "")
        row.publish_enabled = False if force_off else bool(raw.get("publish_enabled"))
        row.daily_cap = int(raw.get("daily_cap") or network.get("default_daily_cap") or 2)
        row.min_gap_minutes = int(network.get("default_min_gap_minutes") or 240)
        row.timezone = network.get("timezone") or "Europe/Moscow"
        row.schedule_json = list(raw.get("schedule") or [])
        row.theme_json = theme
        row.tags_json = list(raw.get("tags") or [])
        row.voice = raw.get("voice") or ""
        row.require_second_human = bool(raw.get("require_second_human") or raw["id"] == "cyber")
        quiet = network.get("quiet_hours") or {}
        row.quiet_start = str(quiet.get("start") or "22:00")
        row.quiet_end = str(quiet.get("end") or "08:00")

    sources_doc = load_sources_document(directory / "sources.yaml")
    for raw in sources_doc["sources"]:
        source = session.get(Source, raw["id"])
        if source is None:
            source = Source(id=raw["id"], kind=raw.get("adapter") or "unknown", adapter=raw.get("adapter") or "unknown")
            session.add(source)
        source.kind = raw.get("adapter") or source.kind
        source.adapter = raw.get("adapter") or source.adapter
        source.base_url = str(raw.get("api_base") or raw.get("feed_url") or "")
        source.poll_interval_minutes = int(raw.get("poll_minutes") or 60)
        source.enabled = bool(raw.get("enabled"))
        source.tos_note = "ToS and robots must be rechecked before a live poll."
        previous = dict(source.policy_json or {})
        declared = {key: value for key, value in raw.items() if "token" not in key and "secret" not in key}
        runtime = {key: previous[key] for key in RUNTIME_POLICY_KEYS if key in previous}
        source.policy_json = {**declared, **runtime}
        # circuit_open, robots_blocked and tos_blocked stay as stored. YAML does not clear them.
        if source.health == "unknown":
            source.health = "offline"

    flags = {
        "dry_run": settings.dry_run,
        "publish_enabled": settings.publish_enabled,
        "global_kill_switch": settings.global_kill_switch,
        "sponsored_enabled": settings.sponsored_enabled,
    }
    for key, value in flags.items():
        if session.get(RuntimeSetting, key) is None:
            session.add(
                RuntimeSetting(key=key, value_json={"value": bool(value)}, updated_at=utcnow(), updated_by="bootstrap")
            )
    if session.query(CredentialRef).filter_by(service="telegram").first() is None:
        session.add(CredentialRef(service="telegram", secret_ref="env:TELEGRAM_BOT_TOKEN", created_utc=utcnow()))
        session.add(CredentialRef(service="github", secret_ref="env:GITHUB_READ_TOKEN", created_utc=utcnow()))


def export_public_config(config_dir: Path) -> dict:
    channels = load_channels_document(config_dir / "channels.yaml")
    sources = load_sources_document(config_dir / "sources.yaml")
    editorial = load_yaml(config_dir / "editorial.yaml")

    def scrub(value):
        if isinstance(value, dict):
            return {
                key: scrub(item)
                for key, item in value.items()
                if "token" not in key.lower() and "secret" not in key.lower() and "password" not in key.lower()
            }
        if isinstance(value, list):
            return [scrub(item) for item in value]
        return value

    return scrub({"channels": channels, "sources": sources, "editorial": editorial})
