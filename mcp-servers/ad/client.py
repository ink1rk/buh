"""Чтение и точечные изменения Active Directory по LDAPS.

Сервисная учётная запись задаётся окружением. Хэши паролей не читаются.
Операции над встроенными администраторами и привилегированными группами
отклоняются: их делают вне агента.
"""

from __future__ import annotations

import os
import ssl
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

from ldap3 import (
    BASE,
    MODIFY_ADD,
    MODIFY_DELETE,
    MODIFY_REPLACE,
    NONE,
    SUBTREE,
    Connection,
    Server,
    Tls,
)
from ldap3.utils.conv import escape_filter_chars

from mcp_common.errors import IntegrationError
from mcp_common.runtime import env_bool
from mcp_common.validate import clamp_limit

USER_ATTRS = [
    "distinguishedName",
    "sAMAccountName",
    "userPrincipalName",
    "displayName",
    "mail",
    "givenName",
    "sn",
    "department",
    "title",
    "company",
    "telephoneNumber",
    "mobile",
    "manager",
    "memberOf",
    "userAccountControl",
    "lockoutTime",
    "whenCreated",
    "whenChanged",
    "objectSid",
    "primaryGroupID",
    "description",
]
GROUP_ATTRS = [
    "distinguishedName",
    "sAMAccountName",
    "cn",
    "description",
    "mail",
    "groupType",
    "objectSid",
]
COMPUTER_ATTRS = [
    "distinguishedName",
    "cn",
    "dNSHostName",
    "operatingSystem",
    "operatingSystemVersion",
    "whenCreated",
    "userAccountControl",
]

# RID известных привилегированных групп и встроенных учёток.
_PROTECTED_GROUP_RIDS = {512, 518, 519, 544, 548, 551}
_PROTECTED_USER_RIDS = {500, 502}
_PROTECTED_GROUP_NAMES = {
    "domain admins",
    "enterprise admins",
    "schema admins",
    "administrators",
    "account operators",
    "backup operators",
}
_ACCOUNT_DISABLE = 0x0002


@dataclass(frozen=True)
class ADSettings:
    server: str
    port: int
    use_ssl: bool
    starttls: bool
    tls_verify: bool
    bind_user: str
    bind_password: str
    base_dn: str
    timeout: int = 15

    def __repr__(self) -> str:
        return f"ADSettings(server={self.server!r}, base_dn={self.base_dn!r})"

    @classmethod
    def from_env(cls) -> ADSettings:
        required = ("AD_SERVER", "AD_BIND_USER", "AD_BIND_PASSWORD", "AD_BASE_DN")
        missing = [name for name in required if not os.environ.get(name, "").strip()]
        if missing:
            raise IntegrationError("Не заданы переменные: " + ", ".join(missing))
        use_ssl = env_bool("AD_USE_SSL", True)
        port_raw = os.environ.get("AD_PORT", "636" if use_ssl else "389")
        try:
            port = int(port_raw)
        except ValueError as exc:
            raise IntegrationError("AD_PORT должен быть числом") from exc
        server = os.environ["AD_SERVER"].strip()
        if "://" in server or any(ord(ch) < 32 for ch in server):
            raise IntegrationError("AD_SERVER должен быть именем хоста, без схемы")
        return cls(
            server=server,
            port=port,
            use_ssl=use_ssl,
            starttls=env_bool("AD_STARTTLS", False),
            tls_verify=env_bool("AD_TLS_VERIFY", True),
            bind_user=os.environ["AD_BIND_USER"].strip(),
            bind_password=os.environ["AD_BIND_PASSWORD"],
            base_dn=os.environ["AD_BASE_DN"].strip(),
            timeout=int(os.environ.get("AD_TIMEOUT", "15")),
        )


def sid_rid(value: Any) -> int | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if value is None:
        return None
    if isinstance(value, str) and value.upper().startswith("S-"):
        try:
            return int(value.rsplit("-", 1)[-1])
        except ValueError:
            return None
    if isinstance(value, (bytes, bytearray)):
        blob = bytes(value)
        if len(blob) < 8:
            return None
        count = blob[1]
        start = 8 + 4 * (count - 1)
        end = start + 4
        if count < 1 or end > len(blob):
            return None
        return int.from_bytes(blob[start:end], "little")
    return None


def _first(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _integer(value: Any, default: int = 0) -> int:
    raw = _first(value)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def cn_of(dn: str) -> str:
    if not dn.upper().startswith("CN="):
        return dn
    rest = dn[3:]
    chars: list[str] = []
    index = 0
    while index < len(rest):
        char = rest[index]
        if char == "\\" and index + 1 < len(rest):
            chars.append(rest[index + 1])
            index += 2
            continue
        if char == ",":
            break
        chars.append(char)
        index += 1
    return "".join(chars)


def _raw_entry(entry: Any) -> dict[str, Any]:
    attrs = dict(entry.entry_attributes_as_dict)
    attrs["dn"] = entry.entry_dn
    return attrs


def public_user(raw: dict[str, Any]) -> dict[str, Any]:
    uac = _integer(raw.get("userAccountControl"))
    groups = [cn_of(str(item)) for item in _as_list(raw.get("memberOf"))]
    return {
        "dn": raw.get("dn"),
        "sam": _first(raw.get("sAMAccountName")),
        "upn": _first(raw.get("userPrincipalName")),
        "display_name": _first(raw.get("displayName")),
        "mail": _first(raw.get("mail")),
        "given_name": _first(raw.get("givenName")),
        "surname": _first(raw.get("sn")),
        "department": _first(raw.get("department")),
        "title": _first(raw.get("title")),
        "company": _first(raw.get("company")),
        "telephone": _first(raw.get("telephoneNumber")),
        "mobile": _first(raw.get("mobile")),
        "manager": cn_of(str(_first(raw.get("manager")))) if _first(raw.get("manager")) else None,
        "enabled": not bool(uac & _ACCOUNT_DISABLE) if raw.get("userAccountControl") is not None else None,
        "locked": _integer(raw.get("lockoutTime")) > 0,
        "primary_group_rid": _integer(raw.get("primaryGroupID")) or None,
        "groups": groups[:30],
        "groups_truncated": len(groups) > 30,
        "description": _first(raw.get("description")),
        "when_changed": _first(raw.get("whenChanged")),
    }


def public_group(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "dn": raw.get("dn"),
        "sam": _first(raw.get("sAMAccountName")),
        "cn": _first(raw.get("cn")) or cn_of(str(raw.get("dn") or "")),
        "mail": _first(raw.get("mail")),
        "description": _first(raw.get("description")),
        "group_type": _integer(raw.get("groupType")) or None,
    }


def public_computer(raw: dict[str, Any]) -> dict[str, Any]:
    uac = _integer(raw.get("userAccountControl"))
    return {
        "dn": raw.get("dn"),
        "cn": _first(raw.get("cn")),
        "dns": _first(raw.get("dNSHostName")),
        "os": _first(raw.get("operatingSystem")),
        "os_version": _first(raw.get("operatingSystemVersion")),
        "enabled": not bool(uac & _ACCOUNT_DISABLE) if raw.get("userAccountControl") is not None else None,
        "when_created": _first(raw.get("whenCreated")),
    }


def group_is_protected(raw: dict[str, Any]) -> bool:
    if sid_rid(raw.get("objectSid")) in _PROTECTED_GROUP_RIDS:
        return True
    name = str(_first(raw.get("sAMAccountName")) or _first(raw.get("cn")) or "")
    return name.casefold() in _PROTECTED_GROUP_NAMES


class ADClient:
    def __init__(self, settings: ADSettings, connector: Callable[[], Any] | None = None):
        self.settings = settings
        self._connector = connector or self._connect

    @classmethod
    def from_env(cls) -> ADClient:
        return cls(ADSettings.from_env())

    def _safe(self, exc: Exception, extra: str = "") -> str:
        text = str(exc).replace(self.settings.bind_password, "***")
        if extra:
            text = text.replace(extra, "***")
        return text[:300]

    def _connect(self) -> Connection:
        try:
            tls = None
            if self.settings.use_ssl or self.settings.starttls:
                tls = Tls(validate=ssl.CERT_REQUIRED if self.settings.tls_verify else ssl.CERT_NONE)
            server = Server(
                self.settings.server,
                port=self.settings.port,
                use_ssl=self.settings.use_ssl,
                tls=tls,
                connect_timeout=self.settings.timeout,
                get_info=NONE,
            )
            if self.settings.starttls and not self.settings.use_ssl:
                conn = Connection(
                    server,
                    user=self.settings.bind_user,
                    password=self.settings.bind_password,
                    auto_bind=False,
                    auto_referrals=False,
                    receive_timeout=self.settings.timeout,
                )
                if not conn.open():
                    raise IntegrationError("Не удалось открыть соединение с AD")
                conn.start_tls()
                if not conn.bind():
                    raise IntegrationError("Не удалось выполнить bind к AD")
                return conn
            return Connection(
                server,
                user=self.settings.bind_user,
                password=self.settings.bind_password,
                auto_bind=True,
                auto_referrals=False,
                receive_timeout=self.settings.timeout,
            )
        except IntegrationError:
            raise
        except Exception as exc:
            raise IntegrationError(f"AD: {self._safe(exc)}") from exc

    @contextmanager
    def _session(self) -> Iterator[Any]:
        conn = self._connector()
        try:
            yield conn
        finally:
            try:
                conn.unbind()
            except Exception:
                pass

    def _check_base(self, base: str | None) -> str:
        chosen = (base or self.settings.base_dn).strip()
        if not chosen or any(ch in chosen for ch in "()*\x00"):
            raise IntegrationError("Некорректный base DN")
        configured = self.settings.base_dn.strip()
        folded = chosen.casefold()
        root = configured.casefold()
        if folded != root and not folded.endswith("," + root):
            raise IntegrationError("base DN вне настроенного AD_BASE_DN")
        return chosen

    def _query(self, query: str) -> str:
        text = query.strip()
        if len(text) < 2 or len(text) > 64:
            raise IntegrationError("Запрос должен быть от 2 до 64 символов")
        if any(ord(ch) < 32 for ch in text):
            raise IntegrationError("Некорректный запрос")
        return text

    def _identity(self, identity: str) -> str:
        text = identity.strip()
        if not text or len(text) > 512 or any(ord(ch) < 32 for ch in text):
            raise IntegrationError("Некорректный идентификатор")
        return text

    def _is_dn(self, value: str) -> bool:
        upper = value.upper()
        return "," in value and (
            upper.startswith("CN=") or upper.startswith("OU=") or upper.startswith("DC=")
        )

    def _search(
        self,
        conn: Any,
        ldap_filter: str,
        attributes: list[str],
        base: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        search_base = self._check_base(base)
        try:
            conn.search(
                search_base=search_base,
                search_filter=ldap_filter,
                search_scope=SUBTREE,
                attributes=attributes,
                size_limit=limit,
            )
        except Exception as exc:
            raise IntegrationError(f"LDAP: {self._safe(exc)}") from exc
        code = (getattr(conn, "result", None) or {}).get("result", 0)
        entries = list(getattr(conn, "entries", []) or [])
        if not entries and code not in (0, 4):
            description = (conn.result or {}).get("description") or "search failed"
            raise IntegrationError(f"LDAP: {description}")
        return [_raw_entry(entry) for entry in entries[:limit]]

    def _modify(self, conn: Any, dn: str, changes: dict[str, Any], redact: str = "") -> None:
        try:
            ok = conn.modify(dn, changes)
        except Exception as exc:
            raise IntegrationError(f"LDAP: {self._safe(exc, redact)}") from exc
        if not ok:
            description = (getattr(conn, "result", None) or {}).get("description") or "modify failed"
            message = str(description).replace(redact, "***") if redact else str(description)
            raise IntegrationError(f"LDAP: {message}")

    def _user_by_identity(self, conn: Any, identity: str) -> dict[str, Any]:
        ident = self._identity(identity)
        if self._is_dn(ident):
            ldap_filter = f"(&(objectCategory=person)(objectClass=user)(distinguishedName={escape_filter_chars(ident)}))"
        elif "@" in ident:
            ldap_filter = f"(&(objectCategory=person)(objectClass=user)(userPrincipalName={escape_filter_chars(ident)}))"
        else:
            ldap_filter = f"(&(objectCategory=person)(objectClass=user)(sAMAccountName={escape_filter_chars(ident)}))"
        rows = self._search(conn, ldap_filter, USER_ATTRS, limit=5)
        if not rows:
            raise IntegrationError("Пользователь не найден")
        if len(rows) > 1:
            raise IntegrationError("Найдено несколько пользователей, уточните samAccountName или DN")
        return rows[0]

    def _group_by_identity(self, conn: Any, identity: str) -> dict[str, Any]:
        ident = self._identity(identity)
        if self._is_dn(ident):
            ldap_filter = f"(&(objectClass=group)(distinguishedName={escape_filter_chars(ident)}))"
        else:
            safe = escape_filter_chars(ident)
            ldap_filter = f"(&(objectClass=group)(|(sAMAccountName={safe})(cn={safe})))"
        rows = self._search(conn, ldap_filter, GROUP_ATTRS, limit=5)
        if not rows:
            raise IntegrationError("Группа не найдена")
        if len(rows) > 1:
            raise IntegrationError("Найдено несколько групп, уточните имя или DN")
        return rows[0]

    def _assert_mutable_user(self, conn: Any, user: dict[str, Any]) -> None:
        if sid_rid(user.get("objectSid")) in _PROTECTED_USER_RIDS:
            raise IntegrationError("Операция запрещена для встроенной учётной записи")
        if _integer(user.get("primaryGroupID")) in _PROTECTED_GROUP_RIDS:
            raise IntegrationError("Операция запрещена: основная группа учётной записи привилегированная")
        groups = [str(item) for item in _as_list(user.get("memberOf"))]
        if not groups:
            return
        parts = "".join(f"(distinguishedName={escape_filter_chars(dn)})" for dn in groups[:50])
        rows = self._search(
            conn,
            f"(&(objectClass=group)(|{parts}))",
            ["distinguishedName", "sAMAccountName", "cn", "objectSid"],
            limit=50,
        )
        if any(group_is_protected(row) for row in rows):
            raise IntegrationError(
                "Операция запрещена: учётная запись входит в привилегированную группу"
            )

    def ping(self) -> dict[str, Any]:
        with self._session() as conn:
            info: dict[str, Any] = {
                "ok": True,
                "server": self.settings.server,
                "base_dn": self.settings.base_dn,
            }
            try:
                conn.search(
                    search_base="",
                    search_filter="(objectClass=*)",
                    search_scope=BASE,
                    attributes=["dnsHostName", "defaultNamingContext"],
                )
                if conn.entries:
                    raw = _raw_entry(conn.entries[0])
                    info["dns_host"] = _first(raw.get("dnsHostName"))
                    info["naming_context"] = _first(raw.get("defaultNamingContext"))
            except Exception:
                pass
            return info

    def search_users(self, query: str, limit: int = 25, base_dn: str | None = None) -> dict[str, Any]:
        text = self._query(query)
        safe = escape_filter_chars(text)
        ldap_filter = (
            "(&(objectCategory=person)(objectClass=user)"
            f"(|(sAMAccountName={safe}*)(userPrincipalName={safe}*)(displayName=*{safe}*)(mail={safe}*)))"
        )
        applied = clamp_limit(limit, 50)
        with self._session() as conn:
            rows = self._search(conn, ldap_filter, USER_ATTRS, base=base_dn, limit=applied)
        return {"count": len(rows), "users": [public_user(row) for row in rows]}

    def get_user(self, identity: str) -> dict[str, Any]:
        with self._session() as conn:
            return public_user(self._user_by_identity(conn, identity))

    def search_groups(self, query: str, limit: int = 25, base_dn: str | None = None) -> dict[str, Any]:
        text = self._query(query)
        safe = escape_filter_chars(text)
        ldap_filter = f"(&(objectClass=group)(|(cn={safe}*)(sAMAccountName={safe}*)))"
        applied = clamp_limit(limit, 50)
        with self._session() as conn:
            rows = self._search(conn, ldap_filter, GROUP_ATTRS, base=base_dn, limit=applied)
        return {"count": len(rows), "groups": [public_group(row) for row in rows]}

    def group_members(self, identity: str, limit: int = 50) -> dict[str, Any]:
        applied = clamp_limit(limit, 100)
        with self._session() as conn:
            group = self._group_by_identity(conn, identity)
            ldap_filter = (
                "(&(objectCategory=person)(objectClass=user)"
                f"(memberOf={escape_filter_chars(str(group['dn']))}))"
            )
            rows = self._search(conn, ldap_filter, USER_ATTRS, limit=applied)
        return {
            "group": public_group(group),
            "count": len(rows),
            "note": "Участники основной группы (primaryGroupID) в memberOf не возвращаются",
            "users": [public_user(row) for row in rows],
        }

    def search_computers(self, query: str, limit: int = 25, base_dn: str | None = None) -> dict[str, Any]:
        text = self._query(query)
        safe = escape_filter_chars(text)
        ldap_filter = f"(&(objectClass=computer)(|(cn={safe}*)(dNSHostName={safe}*)))"
        applied = clamp_limit(limit, 50)
        with self._session() as conn:
            rows = self._search(conn, ldap_filter, COMPUTER_ATTRS, base=base_dn, limit=applied)
        return {"count": len(rows), "computers": [public_computer(row) for row in rows]}

    def list_ous(self, limit: int = 50, base_dn: str | None = None) -> dict[str, Any]:
        applied = clamp_limit(limit, 100)
        with self._session() as conn:
            rows = self._search(
                conn,
                "(objectClass=organizationalUnit)",
                ["ou", "distinguishedName", "description"],
                base=base_dn,
                limit=applied,
            )
        items = [
            {
                "dn": row.get("dn"),
                "ou": _first(row.get("ou")),
                "description": _first(row.get("description")),
            }
            for row in rows
        ]
        return {"count": len(items), "ous": items}

    def unlock_user(self, identity: str) -> dict[str, Any]:
        with self._session() as conn:
            user = self._user_by_identity(conn, identity)
            self._assert_mutable_user(conn, user)
            self._modify(conn, str(user["dn"]), {"lockoutTime": [(MODIFY_REPLACE, ["0"])]})
        return {"dn": user["dn"], "sam": _first(user.get("sAMAccountName")), "unlocked": True}

    def set_user_enabled(self, identity: str, enabled: bool) -> dict[str, Any]:
        with self._session() as conn:
            user = self._user_by_identity(conn, identity)
            self._assert_mutable_user(conn, user)
            current = _integer(user.get("userAccountControl"), 512)
            updated = current & ~_ACCOUNT_DISABLE if enabled else current | _ACCOUNT_DISABLE
            self._modify(
                conn,
                str(user["dn"]),
                {"userAccountControl": [(MODIFY_REPLACE, [str(updated)])]},
            )
        return {"dn": user["dn"], "sam": _first(user.get("sAMAccountName")), "enabled": enabled}

    def _change_membership(self, user_identity: str, group_identity: str, add: bool) -> dict[str, Any]:
        operation = MODIFY_ADD if add else MODIFY_DELETE
        with self._session() as conn:
            user = self._user_by_identity(conn, user_identity)
            group = self._group_by_identity(conn, group_identity)
            self._assert_mutable_user(conn, user)
            if group_is_protected(group):
                raise IntegrationError("Изменение привилегированной группы запрещено")
            self._modify(conn, str(group["dn"]), {"member": [(operation, [str(user["dn"])])]})
        return {
            "user_dn": user["dn"],
            "group_dn": group["dn"],
            "added" if add else "removed": True,
        }

    def add_group_member(self, user_identity: str, group_identity: str) -> dict[str, Any]:
        return self._change_membership(user_identity, group_identity, add=True)

    def remove_group_member(self, user_identity: str, group_identity: str) -> dict[str, Any]:
        return self._change_membership(user_identity, group_identity, add=False)

    def reset_password(self, identity: str, new_password: str, must_change: bool = True) -> dict[str, Any]:
        if not (self.settings.use_ssl or self.settings.starttls):
            raise IntegrationError("Сброс пароля доступен только по LDAPS или StartTLS")
        if not isinstance(new_password, str) or len(new_password) < 12 or len(new_password) > 256:
            raise IntegrationError("Пароль должен быть от 12 до 256 символов")
        if any(ord(ch) < 32 for ch in new_password):
            raise IntegrationError("Пароль содержит недопустимые символы")
        with self._session() as conn:
            user = self._user_by_identity(conn, identity)
            self._assert_mutable_user(conn, user)
            sam = str(_first(user.get("sAMAccountName")) or "")
            if sam and sam.casefold() in new_password.casefold():
                raise IntegrationError("Пароль не должен содержать имя учётной записи")
            encoded = f'"{new_password}"'.encode("utf-16-le")
            changes: dict[str, Any] = {
                "unicodePwd": [(MODIFY_REPLACE, [encoded])],
                "pwdLastSet": [(MODIFY_REPLACE, ["0" if must_change else "-1"])],
            }
            self._modify(conn, str(user["dn"]), changes, redact=new_password)
        return {
            "dn": user["dn"],
            "sam": _first(user.get("sAMAccountName")),
            "reset": True,
            "must_change": must_change,
        }
