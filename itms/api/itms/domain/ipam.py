"""Правила адресации: подсети, адреса, занятость.

Арифметика адресов считается стандартной библиотекой, а не вручную: это избавляет
от ошибок с границами диапазонов и одинаково работает для IPv4 и IPv6.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from dataclasses import dataclass

from itms.core.errors import Invalid

IpNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network
IpInterface = ipaddress.IPv4Interface | ipaddress.IPv6Interface


def parse_network(value: str) -> IpNetwork:
    try:
        return ipaddress.ip_network(value.strip(), strict=False)
    except ValueError as exc:
        raise Invalid(f"Подсеть «{value}» некорректна: {exc}", code_hint="bad_cidr") from exc


def parse_address(value: str) -> IpInterface:
    """Принимает и `10.20.5.17`, и `10.20.5.17/24` — маска сохраняется, если указана."""
    try:
        return ipaddress.ip_interface(value.strip())
    except ValueError as exc:
        raise Invalid(f"Адрес «{value}» некорректен: {exc}", code_hint="bad_ip") from exc


def ensure_address_in_prefix(address: str, cidr: str) -> None:
    network = parse_network(cidr)
    host = parse_address(address).ip
    if host not in network:
        raise Invalid(
            f"Адрес {host} не принадлежит подсети {network}", code_hint="ip_outside_prefix"
        )


@dataclass(frozen=True, slots=True)
class PrefixCapacity:
    """Ёмкость подсети в терминах, в которых о ней думает инженер."""

    cidr: str
    version: int
    prefix_length: int
    network_address: str
    broadcast_address: str | None
    netmask: str
    usable_total: int
    used: int
    free: int
    utilisation_pct: float

    @property
    def is_full(self) -> bool:
        return self.free == 0


def usable_hosts(network: IpNetwork) -> int:
    """Число адресов, которые можно раздать.

    /31 и /32 (и их IPv6-аналоги) — особые случаи: там нет сети и широковещания.
    """
    total = network.num_addresses
    if network.version == 4 and network.prefixlen <= 30:
        return total - 2
    if network.version == 6 and network.prefixlen < 127:
        return total - 1
    return total


def prefix_capacity(cidr: str, used_addresses: Iterable[str]) -> PrefixCapacity:
    network = parse_network(cidr)
    counted = {
        parse_address(item).ip for item in used_addresses if parse_address(item).ip in network
    }
    total = usable_hosts(network)
    used = len(counted)
    free = max(total - used, 0)
    broadcast = str(network.broadcast_address) if network.version == 4 else None
    return PrefixCapacity(
        cidr=str(network),
        version=network.version,
        prefix_length=network.prefixlen,
        network_address=str(network.network_address),
        broadcast_address=broadcast,
        netmask=str(network.netmask),
        usable_total=total,
        used=used,
        free=free,
        utilisation_pct=round(used / total * 100, 1) if total else 0.0,
    )


def next_free_addresses(
    cidr: str, used_addresses: Iterable[str], limit: int = 10, skip: Iterable[str] = ()
) -> list[str]:
    """Возвращает первые свободные адреса подсети — подсказка при выдаче адреса."""
    network = parse_network(cidr)
    taken = {parse_address(item).ip for item in used_addresses}
    taken.update(parse_address(item).ip for item in skip if item)
    result: list[str] = []
    candidates = network.hosts() if network.prefixlen <= 30 or network.version == 6 else network
    for host in candidates:
        if host in taken:
            continue
        result.append(str(host))
        if len(result) >= limit:
            break
    return result


def address_conflicts(addresses: Iterable[tuple[str, str | None]]) -> list[str]:
    """Находит адреса, назначенные больше одного раза в пределах одного VRF."""
    seen: dict[tuple[str, str | None], int] = {}
    for address, vrf in addresses:
        key = (str(parse_address(address).ip), vrf)
        seen[key] = seen.get(key, 0) + 1
    return sorted(address for (address, _), count in seen.items() if count > 1)
