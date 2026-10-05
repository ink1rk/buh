"""1С:Предприятие по стандартному OData. COM в Linux-контейнере нет.

Публикация: http://host/base/odata/standard.odata
Логин берётся из окружения, не из URL.
"""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx2 as httpx

from mcp_common.errors import IntegrationError
from mcp_common.runtime import env_bool
from mcp_common.validate import clamp_limit

_ENTITY = re.compile(r"^[0-9A-Za-z_\u0400-\u04FF]+$")
_GUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_FIELDS = re.compile(r"^[0-9A-Za-z_\u0400-\u04FF, /]+$")
_PATH = re.compile(r"[0-9A-Za-z_./-]+")


class OneCClient:
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        http_service_url: str = "",
        verify_tls: bool = True,
        timeout: float = 30,
        http: httpx.Client | None = None,
    ):
        self.base_url = _check_base(base_url)
        self.username = username
        self._password = password
        self.http_service_url = _check_base(http_service_url) if http_service_url else ""
        self._http = http or httpx.Client(
            timeout=timeout,
            verify=verify_tls,
            follow_redirects=False,
            auth=httpx.BasicAuth(username, password),
        )

    def __repr__(self) -> str:
        return f"OneCClient(base_url={self.base_url!r}, username={self.username!r})"

    @classmethod
    def from_env(cls) -> OneCClient:
        required = ("ONEC_BASE_URL", "ONEC_USERNAME", "ONEC_PASSWORD")
        missing = [name for name in required if not os.environ.get(name, "").strip()]
        if missing:
            raise IntegrationError("Не заданы переменные: " + ", ".join(missing))
        return cls(
            base_url=os.environ["ONEC_BASE_URL"].strip(),
            username=os.environ["ONEC_USERNAME"].strip(),
            password=os.environ["ONEC_PASSWORD"],
            http_service_url=os.environ.get("ONEC_HTTP_SERVICE_URL", "").strip(),
            verify_tls=env_bool("ONEC_VERIFY_TLS", True),
            timeout=float(os.environ.get("ONEC_TIMEOUT", "30")),
        )

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        if method.upper() != "GET":
            raise IntegrationError("1С MCP работает только на чтение")
        self._same_origin(url, self.base_url if url.startswith(self.base_url) else self.http_service_url)
        headers = {"Accept": "application/json", **(kwargs.pop("headers", {}) or {})}
        try:
            response = self._http.request(method, url, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise IntegrationError(f"1С: {exc.__class__.__name__}") from exc
        if response.is_redirect:
            raise IntegrationError("1С вернула редирект, он не выполняется")
        if response.status_code >= 400:
            raise IntegrationError(f"1С HTTP {response.status_code}: {response.text[:400]}")
        return response

    def _same_origin(self, url: str, allowed: str) -> None:
        target = urlparse(url)
        origin = urlparse(allowed)
        if target.scheme != origin.scheme or target.netloc != origin.netloc:
            raise IntegrationError("Запрос вне настроенного адреса 1С")

    def _entity(self, entity: str) -> str:
        if not _ENTITY.fullmatch(entity or ""):
            raise IntegrationError("Имя сущности OData может содержать только буквы, цифры и _")
        return entity

    def _guid(self, value: str) -> str:
        if not _GUID.fullmatch((value or "").strip()):
            raise IntegrationError("Нужен GUID объекта 1С")
        return value.strip()

    def _filter(self, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        text = value.strip()
        if len(text) > 2000 or any(ch in text for ch in "<>") or any(ord(ch) < 32 for ch in text):
            raise IntegrationError("Некорректный $filter")
        return text

    def _fields(self, value: str | None, name: str) -> str | None:
        if value is None or not value.strip():
            return None
        text = value.strip()
        if not _FIELDS.fullmatch(text):
            raise IntegrationError(f"Некорректный {name}")
        return text

    def _object_url(self, entity: str, guid: str | None = None) -> str:
        url = f"{self.base_url}/{self._entity(entity)}"
        if guid:
            url += f"(guid'{self._guid(guid)}')"
        return url

    def ping(self) -> dict[str, Any]:
        response = self._request("GET", self.base_url, params={"$format": "json"})
        payload = _json(response)
        names = _entity_names(payload)
        return {"ok": True, "base_url": self.base_url, "entity_sets": len(names)}

    def list_entities(self) -> dict[str, Any]:
        response = self._request("GET", self.base_url, params={"$format": "json"})
        names = _entity_names(_json(response))
        return {"count": len(names), "entities": names}

    def list_objects(
        self,
        entity: str,
        filter: str = "",
        select: str = "",
        orderby: str = "",
        top: int = 20,
        skip: int = 0,
        expand: str = "",
    ) -> dict[str, Any]:
        if skip < 0 or skip > 10_000:
            raise IntegrationError("skip должен быть от 0 до 10000")
        params: dict[str, str] = {
            "$format": "json",
            "$top": str(clamp_limit(top, 100)),
            "$skip": str(skip),
        }
        for key, value, label in (
            ("$filter", self._filter(filter), "filter"),
            ("$select", self._fields(select, "$select"), "select"),
            ("$orderby", self._fields(orderby, "$orderby"), "orderby"),
            ("$expand", self._fields(expand, "$expand"), "expand"),
        ):
            if value:
                params[key] = value
        response = self._request("GET", self._object_url(entity), params=params)
        payload = _json(response)
        rows = payload.get("value", payload if isinstance(payload, list) else [])
        if not isinstance(rows, list):
            rows = [payload]
        return {"entity": entity, "count": len(rows), "items": rows}

    def get_object(self, entity: str, guid: str, select: str = "") -> dict[str, Any]:
        params = {"$format": "json"}
        chosen = self._fields(select, "$select")
        if chosen:
            params["$select"] = chosen
        response = self._request("GET", self._object_url(entity, guid), params=params)
        return _json(response)

    def count(self, entity: str, filter: str = "") -> dict[str, Any]:
        params = {"$format": "json"}
        chosen = self._filter(filter)
        if chosen:
            params["$filter"] = chosen
        response = self._request("GET", f"{self._object_url(entity)}/$count", params=params)
        text = response.text.strip().strip('"')
        try:
            number = int(text)
        except ValueError as exc:
            raise IntegrationError(f"1С вернула нечисловой $count: {text[:80]}") from exc
        return {"entity": entity, "count": number}

    def call_http(self, path: str, query: dict[str, Any] | None = None) -> Any:
        if not self.http_service_url:
            raise IntegrationError("ONEC_HTTP_SERVICE_URL не задан")
        response = self._request("GET", self._service_url(path), params=query or None)
        if not response.content:
            return {"ok": True, "status": response.status_code}
        try:
            return _json(response)
        except IntegrationError:
            return {"status": response.status_code, "text": response.text[:4000]}

    def _service_url(self, path: str) -> str:
        text = (path or "").strip().lstrip("/")
        if (
            not text
            or ".." in text.split("/")
            or "://" in text
            or text.startswith("//")
            or not _PATH.fullmatch(text)
        ):
            raise IntegrationError("Некорректный путь HTTP-сервиса")
        url = self.http_service_url.rstrip("/") + "/" + text
        self._same_origin(url, self.http_service_url)
        return url


def _check_base(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise IntegrationError("Адрес 1С должен быть http(s) без логина в URL")
    return url.strip().rstrip("/")


def _json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception as exc:
        raise IntegrationError("1С вернула не JSON") from exc


def _entity_names(payload: Any) -> list[str]:
    rows = payload.get("value", []) if isinstance(payload, dict) else []
    names: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            name = row.get("name") or row.get("url")
        else:
            name = row
        if isinstance(name, str) and name:
            names.append(name)
    return names
