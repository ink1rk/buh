"""Exchange Online и гибрид через Microsoft Graph, приложение client credentials."""

from __future__ import annotations

import os
import time
from typing import Any
from urllib.parse import quote

import httpx2 as httpx

from mcp_common.errors import IntegrationError
from mcp_common.validate import clamp_limit, emails, mailbox, plain_text

_MESSAGE_SELECT = "id,subject,from,toRecipients,receivedDateTime,bodyPreview,isRead,hasAttachments"
_BODY_LIMIT = 8000


class GraphExchange:
    def __init__(
        self,
        tenant: str,
        client_id: str,
        client_secret: str,
        scope: str = "https://graph.microsoft.com/.default",
        timeout: float = 30,
        http: httpx.Client | None = None,
    ):
        self.tenant = tenant
        self.client_id = client_id
        self._client_secret = client_secret
        self.scope = scope
        self._http = http or httpx.Client(timeout=timeout)
        self._token: tuple[str, float] | None = None

    def __repr__(self) -> str:
        return f"GraphExchange(tenant={self.tenant!r}, client_id={self.client_id!r})"

    @classmethod
    def from_env(cls) -> GraphExchange:
        required = ("EXCHANGE_TENANT_ID", "EXCHANGE_CLIENT_ID", "EXCHANGE_CLIENT_SECRET")
        missing = [name for name in required if not os.environ.get(name, "").strip()]
        if missing:
            raise IntegrationError("Не заданы переменные: " + ", ".join(missing))
        return cls(
            tenant=os.environ["EXCHANGE_TENANT_ID"].strip(),
            client_id=os.environ["EXCHANGE_CLIENT_ID"].strip(),
            client_secret=os.environ["EXCHANGE_CLIENT_SECRET"],
            scope=os.environ.get("EXCHANGE_GRAPH_SCOPE", "https://graph.microsoft.com/.default").strip(),
            timeout=float(os.environ.get("EXCHANGE_TIMEOUT", "30")),
        )

    def _token_value(self) -> str:
        now = time.monotonic()
        if self._token and self._token[1] > now:
            return self._token[0]
        try:
            response = self._http.post(
                f"https://login.microsoftonline.com/{quote(self.tenant)}/oauth2/v2.0/token",
                data={
                    "client_id": self.client_id,
                    "client_secret": self._client_secret,
                    "scope": self.scope,
                    "grant_type": "client_credentials",
                },
            )
        except httpx.HTTPError as exc:
            raise IntegrationError(f"Graph token: {exc.__class__.__name__}") from exc
        if response.status_code >= 400:
            description = _error_text(response).replace(self._client_secret, "***")
            raise IntegrationError(f"Graph token HTTP {response.status_code}: {description}")
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise IntegrationError("Graph не вернул access_token")
        self._token = (token, now + max(int(payload.get("expires_in", 3600)) - 60, 30))
        return token

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["Authorization"] = f"Bearer {self._token_value()}"
        try:
            response = self._http.request(method, "https://graph.microsoft.com/v1.0" + path, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise IntegrationError(f"Graph: {exc.__class__.__name__}") from exc
        if response.status_code >= 400:
            raise IntegrationError(f"Graph HTTP {response.status_code}: {_error_text(response)}")
        if response.status_code == 202 or not response.content:
            return {}
        return response.json()

    def ping(self) -> dict[str, Any]:
        payload = self._request(
            "GET",
            "/users",
            params={"$select": "id,displayName,mail", "$top": "1"},
        )
        return {"ok": True, "mode": "graph", "tenant": self.tenant, "sample_count": len(payload.get("value", []))}

    def find_users(self, query: str, limit: int = 20) -> dict[str, Any]:
        text = plain_text(query, "query", 64).replace('"', " ")
        applied = clamp_limit(limit, 25)
        payload = self._request(
            "GET",
            "/users",
            params={
                "$search": f'"displayName:{text}" OR "mail:{text}" OR "userPrincipalName:{text}"',
                "$select": "id,displayName,mail,userPrincipalName",
                "$top": str(applied),
            },
            headers={"ConsistencyLevel": "eventual"},
        )
        users = [
            {
                "id": item.get("id"),
                "display_name": item.get("displayName"),
                "mail": item.get("mail"),
                "upn": item.get("userPrincipalName"),
            }
            for item in payload.get("value", [])
        ]
        return {"count": len(users), "users": users}

    def list_folders(self, mailbox_id: str) -> dict[str, Any]:
        owner = mailbox(mailbox_id)
        payload = self._request(
            "GET",
            f"/users/{quote(owner)}/mailFolders",
            params={"$top": "50", "$select": "id,displayName,totalItemCount,unreadItemCount"},
        )
        folders = [
            {
                "id": item.get("id"),
                "name": item.get("displayName"),
                "total": item.get("totalItemCount"),
                "unread": item.get("unreadItemCount"),
            }
            for item in payload.get("value", [])
        ]
        return {"mailbox": owner, "folders": folders}

    def list_messages(
        self,
        mailbox_id: str,
        folder: str = "inbox",
        limit: int = 15,
        query: str = "",
    ) -> dict[str, Any]:
        owner = mailbox(mailbox_id)
        folder_id = _folder(folder)
        applied = clamp_limit(limit, 30)
        params: dict[str, str] = {"$top": str(applied), "$select": _MESSAGE_SELECT}
        headers: dict[str, str] = {}
        if query.strip():
            text = plain_text(query, "query", 80).replace('"', " ")
            params["$search"] = f'"{text}"'
            headers["ConsistencyLevel"] = "eventual"
        else:
            params["$orderby"] = "receivedDateTime desc"
        payload = self._request(
            "GET",
            f"/users/{quote(owner)}/mailFolders/{quote(folder_id)}/messages",
            params=params,
            headers=headers,
        )
        return {
            "mailbox": owner,
            "folder": folder_id,
            "count": len(payload.get("value", [])),
            "messages": [_message(item, include_body=False) for item in payload.get("value", [])],
        }

    def get_message(self, mailbox_id: str, message_id: str, include_body: bool = False) -> dict[str, Any]:
        owner = mailbox(mailbox_id)
        mid = _item_id(message_id)
        select = _MESSAGE_SELECT + (",body" if include_body else "")
        payload = self._request(
            "GET",
            f"/users/{quote(owner)}/messages/{quote(mid, safe='')}",
            params={"$select": select},
        )
        return _message(payload, include_body=include_body)

    def send_mail(self, mailbox_id: str, to: list[str], subject: str, body: str) -> dict[str, Any]:
        owner = mailbox(mailbox_id)
        recipients = emails(to)
        self._request(
            "POST",
            f"/users/{quote(owner)}/sendMail",
            json={
                "message": {
                    "subject": plain_text(subject, "subject", 255),
                    "body": {"contentType": "Text", "content": plain_text(body, "body", 20_000)},
                    "toRecipients": [{"emailAddress": {"address": addr}} for addr in recipients],
                },
                "saveToSentItems": True,
            },
        )
        return {"sent": True, "mailbox": owner, "to": recipients}

    def list_events(self, mailbox_id: str, start: str, end: str, limit: int = 20) -> dict[str, Any]:
        owner = mailbox(mailbox_id)
        applied = clamp_limit(limit, 40)
        payload = self._request(
            "GET",
            f"/users/{quote(owner)}/calendarView",
            params={
                "startDateTime": _timestamp(start),
                "endDateTime": _timestamp(end),
                "$top": str(applied),
                "$select": "id,subject,start,end,organizer,location,isAllDay",
            },
        )
        events = [_event(item) for item in payload.get("value", [])]
        return {"mailbox": owner, "count": len(events), "events": events}

    def create_event(
        self,
        mailbox_id: str,
        subject: str,
        start: str,
        end: str,
        body: str = "",
        timezone: str = "UTC",
    ) -> dict[str, Any]:
        owner = mailbox(mailbox_id)
        zone = plain_text(timezone, "timezone", 64)
        payload = self._request(
            "POST",
            f"/users/{quote(owner)}/calendar/events",
            json={
                "subject": plain_text(subject, "subject", 255),
                "start": {"dateTime": _timestamp(start), "timeZone": zone},
                "end": {"dateTime": _timestamp(end), "timeZone": zone},
                "body": {"contentType": "Text", "content": body.strip()[:20_000]},
            },
        )
        return _event(payload)


def _error_text(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except Exception:
        return response.text[:400]
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])[:400]
        if payload.get("error_description"):
            return str(payload["error_description"])[:400]
    return response.text[:400]


def _folder(folder: str) -> str:
    text = folder.strip() or "inbox"
    if len(text) > 256 or any(ch in text for ch in " /\\?&#"):
        raise IntegrationError("Некорректная папка")
    return text


def _item_id(value: str) -> str:
    text = value.strip()
    if not text or len(text) > 512 or any(ch in text for ch in " ?&#<>"):
        raise IntegrationError("Некорректный идентификатор письма или события")
    return text


def _timestamp(value: str) -> str:
    text = value.strip()
    if len(text) < 16 or len(text) > 40 or any(ch in text for ch in " <>\"'"):
        raise IntegrationError("Дата должна быть в ISO, например 2026-10-05T09:00:00")
    return text


def _address(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    email = value.get("emailAddress") or {}
    if isinstance(email, dict):
        return email.get("address") or email.get("name")
    return None


def _message(item: dict[str, Any], include_body: bool) -> dict[str, Any]:
    body = None
    if include_body:
        raw = item.get("body") or {}
        content = raw.get("content") if isinstance(raw, dict) else None
        body = (content or "")[:_BODY_LIMIT]
    return {
        "id": item.get("id"),
        "subject": item.get("subject"),
        "from": _address(item.get("from")),
        "to": [
            addr
            for addr in (_address(recipient) for recipient in item.get("toRecipients") or [])
            if addr
        ],
        "received": item.get("receivedDateTime"),
        "preview": item.get("bodyPreview"),
        "is_read": item.get("isRead"),
        "has_attachments": item.get("hasAttachments"),
        "body": body,
    }


def _event(item: dict[str, Any]) -> dict[str, Any]:
    location = item.get("location") or {}
    return {
        "id": item.get("id"),
        "subject": item.get("subject"),
        "start": item.get("start"),
        "end": item.get("end"),
        "organizer": _address(item.get("organizer")),
        "location": location.get("displayName") if isinstance(location, dict) else None,
        "is_all_day": item.get("isAllDay"),
    }
