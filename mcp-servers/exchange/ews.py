"""On-prem Exchange через EWS. Basic или NTLM, ящик указывается явно.

Имперсонация включается EXCHANGE_IMPERSONATE=true и требует роли
ApplicationImpersonation у сервисной учётной записи. Скрытые правила
пересылки и выгрузка всех ящиков здесь не делаются.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree
from xml.sax.saxutils import escape

from mcp_common.errors import IntegrationError
from mcp_common.runtime import env_bool
from mcp_common.validate import clamp_limit, emails, mailbox, plain_text

NS = {
    "s": "http://schemas.xmlsoap.org/soap/envelope/",
    "m": "http://schemas.microsoft.com/exchange/services/2006/messages",
    "t": "http://schemas.microsoft.com/exchange/services/2006/types",
}
_BODY_LIMIT = 8000
_FOLDERS = {"inbox", "sentitems", "drafts", "deleteditems", "calendar", "junkemail", "outbox", "msgfolderroot"}


class EwsExchange:
    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        auth: str = "ntlm",
        impersonate: bool = False,
        verify_tls: bool = True,
        version: str = "Exchange2013",
        timeout: float = 30,
        poster: Callable[[str], str] | None = None,
    ):
        self.url = url
        self.username = username
        self._password = password
        self.auth = auth
        self.impersonate = impersonate
        self.verify_tls = verify_tls
        self.version = version
        self.timeout = timeout
        self._poster = poster or self._post
        self._session: Any = None

    def __repr__(self) -> str:
        return f"EwsExchange(url={self.url!r}, username={self.username!r}, auth={self.auth!r})"

    @classmethod
    def from_env(cls) -> EwsExchange:
        required = ("EXCHANGE_EWS_URL", "EXCHANGE_USERNAME", "EXCHANGE_PASSWORD")
        missing = [name for name in required if not os.environ.get(name, "").strip()]
        if missing:
            raise IntegrationError("Не заданы переменные: " + ", ".join(missing))
        url = os.environ["EXCHANGE_EWS_URL"].strip()
        _check_url(url)
        auth = os.environ.get("EXCHANGE_AUTH", "ntlm").strip().lower()
        if auth not in {"ntlm", "basic"}:
            raise IntegrationError("EXCHANGE_AUTH должен быть ntlm или basic")
        return cls(
            url=url,
            username=os.environ["EXCHANGE_USERNAME"].strip(),
            password=os.environ["EXCHANGE_PASSWORD"],
            auth=auth,
            impersonate=env_bool("EXCHANGE_IMPERSONATE", False),
            verify_tls=env_bool("EXCHANGE_VERIFY_TLS", True),
            version=os.environ.get("EXCHANGE_VERSION", "Exchange2013").strip() or "Exchange2013",
            timeout=float(os.environ.get("EXCHANGE_TIMEOUT", "30")),
        )

    def _session_client(self) -> Any:
        if self._session is not None:
            return self._session
        import requests

        session = requests.Session()
        if self.auth == "ntlm":
            from requests_ntlm import HttpNtlmAuth

            session.auth = HttpNtlmAuth(self.username, self._password)
        else:
            session.auth = (self.username, self._password)
        self._session = session
        return session

    def _post(self, xml: str) -> str:
        try:
            response = self._session_client().post(
                self.url,
                data=xml.encode("utf-8"),
                headers={"Content-Type": "text/xml; charset=utf-8"},
                timeout=self.timeout,
                verify=self.verify_tls,
            )
        except Exception as exc:
            text = str(exc).replace(self._password, "***")
            raise IntegrationError(f"EWS: {exc.__class__.__name__}: {text[:200]}") from exc
        if response.status_code >= 400:
            body = response.text.replace(self._password, "***")[:400]
            raise IntegrationError(f"EWS HTTP {response.status_code}: {body}")
        return response.text

    def _call(self, body: str, mailbox_id: str | None) -> ElementTree.Element:
        target = mailbox(mailbox_id) if mailbox_id else None
        impersonation = target if self.impersonate else None
        xml = _envelope(body, impersonation, self.version)
        try:
            root = ElementTree.fromstring(self._poster(xml))
        except ElementTree.ParseError as exc:
            raise IntegrationError("EWS вернул не XML") from exc
        fault = root.find(".//s:Fault", NS)
        if fault is not None:
            message = "".join(fault.itertext()).strip()
            raise IntegrationError(f"EWS: {message[:400]}")
        code = root.find(".//m:ResponseCode", NS)
        if code is not None and (code.text or "") not in {"", "NoError"}:
            detail = root.find(".//m:MessageText", NS)
            raise IntegrationError(f"EWS {(code.text or '').strip()}: {((detail.text if detail is not None else '') or '')[:300]}")
        return root

    def ping(self) -> dict[str, Any]:
        body = """
        <m:ResolveNames ReturnFullContactData="false">
          <m:UnresolvedEntry>healthcheck</m:UnresolvedEntry>
        </m:ResolveNames>
        """
        # Ошибка разрешения имени тоже значит, что EWS ответил. Смотрим только SOAP-транспорт.
        try:
            self._call(body, None)
        except IntegrationError as exc:
            if str(exc).startswith("EWS Error") or "ErrorNameResolution" in str(exc):
                return {"ok": True, "mode": "ews", "url": self.url}
            raise
        return {"ok": True, "mode": "ews", "url": self.url, "auth": self.auth}

    def find_users(self, query: str, limit: int = 20) -> dict[str, Any]:
        text = plain_text(query, "query", 64)
        applied = clamp_limit(limit, 25)
        root = self._call(
            f"""
            <m:ResolveNames ReturnFullContactData="false">
              <m:UnresolvedEntry>{escape(text)}</m:UnresolvedEntry>
            </m:ResolveNames>
            """,
            None,
        )
        users = []
        for mailbox_node in root.findall(".//t:Mailbox", NS)[:applied]:
            users.append(
                {
                    "display_name": _text(mailbox_node, "t:Name"),
                    "mail": _text(mailbox_node, "t:EmailAddress"),
                }
            )
        return {"count": len(users), "users": users}

    def list_folders(self, mailbox_id: str) -> dict[str, Any]:
        owner = mailbox(mailbox_id)
        root = self._call(
            f"""
            <m:FindFolder Traversal="Shallow">
              <m:FolderShape><t:BaseShape>Default</t:BaseShape></m:FolderShape>
              <m:ParentFolderIds>{_folder_xml("msgfolderroot", owner, self.impersonate)}</m:ParentFolderIds>
            </m:FindFolder>
            """,
            owner,
        )
        folders = []
        for node in root.findall(".//t:Folder", NS) + root.findall(".//t:CalendarFolder", NS):
            folder_id = node.find("t:FolderId", NS)
            folders.append(
                {
                    "id": folder_id.get("Id") if folder_id is not None else None,
                    "name": _text(node, "t:DisplayName"),
                    "total": _text(node, "t:TotalCount"),
                    "unread": _text(node, "t:UnreadCount"),
                }
            )
        return {"mailbox": owner, "folders": folders}

    def list_messages(
        self,
        mailbox_id: str,
        folder: str = "inbox",
        limit: int = 15,
        query: str = "",
    ) -> dict[str, Any]:
        owner = mailbox(mailbox_id)
        folder_name = _folder_name(folder)
        applied = clamp_limit(limit, 30)
        restriction = ""
        if query.strip():
            text = plain_text(query, "query", 80)
            restriction = f"""
            <m:Restriction>
              <t:Contains ContainmentMode="Substring" ContainmentComparison="IgnoreCase">
                <t:FieldURI FieldURI="item:Subject"/>
                <t:Constant Value="{escape(text)}"/>
              </t:Contains>
            </m:Restriction>
            """
        root = self._call(
            f"""
            <m:FindItem Traversal="Shallow">
              <m:ItemShape>
                <t:BaseShape>IdOnly</t:BaseShape>
                <t:AdditionalProperties>
                  <t:FieldURI FieldURI="item:Subject"/>
                  <t:FieldURI FieldURI="item:DateTimeReceived"/>
                  <t:FieldURI FieldURI="message:From"/>
                </t:AdditionalProperties>
              </m:ItemShape>
              <m:IndexedPageItemView MaxEntriesReturned="{applied}" Offset="0" BasePoint="Beginning"/>
              {restriction}
              <m:ParentFolderIds>{_folder_xml(folder_name, owner, self.impersonate)}</m:ParentFolderIds>
            </m:FindItem>
            """,
            owner,
        )
        messages = [_ews_message(node, include_body=False) for node in root.findall(".//t:Message", NS)]
        return {"mailbox": owner, "folder": folder_name, "count": len(messages), "messages": messages}

    def get_message(self, mailbox_id: str, message_id: str, include_body: bool = False) -> dict[str, Any]:
        owner = mailbox(mailbox_id)
        mid = _item_id(message_id)
        body_shape = "<t:BodyType>Text</t:BodyType>" if include_body else ""
        root = self._call(
            f"""
            <m:GetItem>
              <m:ItemShape>
                <t:BaseShape>Default</t:BaseShape>
                {body_shape}
              </m:ItemShape>
              <m:ItemIds><t:ItemId Id="{escape(mid)}"/></m:ItemIds>
            </m:GetItem>
            """,
            owner,
        )
        node = root.find(".//t:Message", NS)
        if node is None:
            raise IntegrationError("Письмо не найдено")
        return _ews_message(node, include_body=include_body)

    def send_mail(self, mailbox_id: str, to: list[str], subject: str, body: str) -> dict[str, Any]:
        owner = mailbox(mailbox_id)
        recipients = emails(to)
        blocks = "".join(
            f"<t:Mailbox><t:EmailAddress>{escape(addr)}</t:EmailAddress></t:Mailbox>" for addr in recipients
        )
        saved = "" if self.impersonate else f"<m:SavedItemFolderId>{_folder_xml('sentitems', owner, False)}</m:SavedItemFolderId>"
        self._call(
            f"""
            <m:CreateItem MessageDisposition="SendAndSaveCopy">
              {saved}
              <m:Items>
                <t:Message>
                  <t:Subject>{escape(plain_text(subject, "subject", 255))}</t:Subject>
                  <t:Body BodyType="Text">{escape(plain_text(body, "body", 20_000))}</t:Body>
                  <t:ToRecipients>{blocks}</t:ToRecipients>
                </t:Message>
              </m:Items>
            </m:CreateItem>
            """,
            owner,
        )
        return {"sent": True, "mailbox": owner, "to": recipients}

    def list_events(self, mailbox_id: str, start: str, end: str, limit: int = 20) -> dict[str, Any]:
        owner = mailbox(mailbox_id)
        applied = clamp_limit(limit, 40)
        root = self._call(
            f"""
            <m:FindItem Traversal="Shallow">
              <m:ItemShape><t:BaseShape>Default</t:BaseShape></m:ItemShape>
              <m:CalendarView MaxEntriesReturned="{applied}" StartDate="{escape(_timestamp(start))}" EndDate="{escape(_timestamp(end))}"/>
              <m:ParentFolderIds>{_folder_xml("calendar", owner, self.impersonate)}</m:ParentFolderIds>
            </m:FindItem>
            """,
            owner,
        )
        events = [_ews_event(node) for node in root.findall(".//t:CalendarItem", NS)]
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
        zone = escape(plain_text(timezone, "timezone", 64))
        root = self._call(
            f"""
            <m:CreateItem SendMeetingInvitations="SendToNone">
              <m:SavedItemFolderId>{_folder_xml("calendar", owner, self.impersonate)}</m:SavedItemFolderId>
              <m:Items>
                <t:CalendarItem>
                  <t:Subject>{escape(plain_text(subject, "subject", 255))}</t:Subject>
                  <t:Body BodyType="Text">{escape(body.strip()[:20_000])}</t:Body>
                  <t:Start>{escape(_timestamp(start))}</t:Start>
                  <t:End>{escape(_timestamp(end))}</t:End>
                  <t:StartTimeZone Id="{zone}"/>
                  <t:EndTimeZone Id="{zone}"/>
                </t:CalendarItem>
              </m:Items>
            </m:CreateItem>
            """,
            owner,
        )
        node = root.find(".//t:CalendarItem", NS)
        item_id = root.find(".//t:ItemId", NS)
        event = _ews_event(node) if node is not None else {"subject": subject}
        if item_id is not None:
            event["id"] = item_id.get("Id")
        return event


def _check_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc or parsed.username or parsed.password:
        raise IntegrationError("EXCHANGE_EWS_URL должен быть адресом Exchange.asmx без логина в URL")


def _envelope(body: str, impersonate: str | None, version: str) -> str:
    header = f'<t:RequestServerVersion Version="{escape(version)}"/>'
    if impersonate:
        header += (
            "<t:ExchangeImpersonation><t:ConnectingSID>"
            f"<t:PrimarySmtpAddress>{escape(impersonate)}</t:PrimarySmtpAddress>"
            "</t:ConnectingSID></t:ExchangeImpersonation>"
        )
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"'
        ' xmlns:m="http://schemas.microsoft.com/exchange/services/2006/messages"'
        ' xmlns:t="http://schemas.microsoft.com/exchange/services/2006/types">'
        f"<s:Header>{header}</s:Header><s:Body>{body}</s:Body></s:Envelope>"
    )


def _folder_name(folder: str) -> str:
    text = (folder or "inbox").strip()
    if text.casefold() in _FOLDERS:
        return text.casefold()
    if not text or len(text) > 512 or any(ch in text for ch in " <>\"'&"):
        raise IntegrationError("Некорректная папка")
    return text


def _folder_xml(folder: str, mailbox_id: str, impersonate: bool) -> str:
    name = _folder_name(folder)
    mailbox_xml = ""
    if not impersonate:
        mailbox_xml = f"<t:Mailbox><t:EmailAddress>{escape(mailbox_id)}</t:EmailAddress></t:Mailbox>"
    if name in _FOLDERS:
        return f'<t:DistinguishedFolderId Id="{name}">{mailbox_xml}</t:DistinguishedFolderId>'
    return f'<t:FolderId Id="{escape(name)}"/>'


def _item_id(value: str) -> str:
    text = value.strip()
    if not text or len(text) > 1024 or any(ord(ch) < 32 for ch in text):
        raise IntegrationError("Некорректный идентификатор письма")
    return text


def _timestamp(value: str) -> str:
    text = value.strip()
    if len(text) < 16 or len(text) > 40 or any(ch in text for ch in " <>\"'"):
        raise IntegrationError("Дата должна быть в ISO, например 2026-10-05T09:00:00")
    return text


def _text(node: ElementTree.Element | None, path: str) -> str | None:
    if node is None:
        return None
    found = node.find(path, NS)
    if found is None or found.text is None:
        return None
    return found.text


def _ews_message(node: ElementTree.Element, include_body: bool) -> dict[str, Any]:
    item_id = node.find("t:ItemId", NS)
    sender = node.find("t:From/t:Mailbox/t:EmailAddress", NS)
    body = _text(node, "t:Body") if include_body else None
    return {
        "id": item_id.get("Id") if item_id is not None else None,
        "subject": _text(node, "t:Subject"),
        "from": sender.text if sender is not None else None,
        "received": _text(node, "t:DateTimeReceived"),
        "preview": _text(node, "t:Preview"),
        "body": (body or "")[:_BODY_LIMIT] if body is not None else None,
    }


def _ews_event(node: ElementTree.Element | None) -> dict[str, Any]:
    if node is None:
        return {}
    item_id = node.find("t:ItemId", NS)
    return {
        "id": item_id.get("Id") if item_id is not None else None,
        "subject": _text(node, "t:Subject"),
        "start": _text(node, "t:Start"),
        "end": _text(node, "t:End"),
        "location": _text(node, "t:Location"),
    }
