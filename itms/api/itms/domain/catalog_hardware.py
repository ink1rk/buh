"""Популярные паспорта: серверы, СХД, сеть и комплектующие.

Цифры — типовые конфигурации из публичных описаний платформ (сокет, слоты, корзины,
юниты), а не замер конкретного экземпляра. Дисковые полки и лезвия помечены в тексте.
"""

from __future__ import annotations

from itms.domain.catalog_library import CATALOG_NOTE, ModelSpec, PortSpec, _p
from itms.models.enums import DeviceRole, InterfaceType

_MGMT = {
    "Dell": "iDRAC",
    "HPE": "iLO",
    "Lenovo": "XCC",
    "Huawei": "iBMC",
    "Fujitsu": "iRMC",
    "ASUS": "BMC",
    "Supermicro": "IPMI",
}


def _srv(
    vendor: str,
    model: str,
    u: float,
    typical: int,
    maximum: int,
    sockets: int,
    socket: str,
    ram_slots: int,
    ram: str,
    bays: int,
    form: str,
    *,
    role: DeviceRole = DeviceRole.SERVER,
    extra: str = "",
) -> ModelSpec:
    mgmt = _MGMT.get(vendor, "mgmt")
    rack = u > 0
    text = f"{sockets}× {socket}, {ram_slots}× {ram}, {bays}× {form}."
    if extra:
        text = f"{text} {extra}"
    return ModelSpec(
        vendor,
        model,
        role,
        u,
        ports=(
            _p("GbE{n}", 2, InterfaceType.RJ45, 1000, position=10),
            _p("SFP+{n}", 2, InterfaceType.SFP_PLUS, 10000, position=20),
            _p(mgmt, 1, InterfaceType.RJ45, 1000, position=30),
        ),
        psu_count=2 if rack or sockets > 1 else 1,
        power_nameplate_w=typical,
        power_max_w=maximum,
        weight_kg=None if not rack else (28 if u >= 2 else 16),
        is_full_depth=rack,
        notes=f"{text} {CATALOG_NOTE}",
        cpu_sockets=sockets,
        cpu_socket=socket,
        ram_slots=ram_slots,
        ram_type=ram,
        drive_bays=bays,
        drive_form=form,
    )


def _part(
    vendor: str,
    model: str,
    kind: str,
    *,
    socket: str | None = None,
    ram: str | None = None,
    form: str | None = None,
    sockets: int | None = None,
    ram_slots: int | None = None,
    notes: str = "",
) -> ModelSpec:
    text = notes or CATALOG_NOTE
    return ModelSpec(
        vendor,
        model,
        DeviceRole.OTHER,
        0,
        psu_count=0,
        is_full_depth=False,
        notes=text,
        component_class=kind,
        cpu_sockets=sockets,
        cpu_socket=socket,
        ram_slots=ram_slots,
        ram_type=ram,
        drive_form=form,
    )


def _box(
    vendor: str,
    model: str,
    role: DeviceRole,
    u: float,
    ports: tuple[PortSpec, ...],
    *,
    typical: int | None,
    maximum: int | None,
    psu: int = 1,
    weight: float | None = None,
    bays: int | None = None,
    form: str | None = None,
    extra: str = "",
) -> ModelSpec:
    note = CATALOG_NOTE if not extra else f"{extra} {CATALOG_NOTE}"
    return ModelSpec(
        vendor,
        model,
        role,
        u,
        ports=ports,
        psu_count=psu,
        power_nameplate_w=typical,
        power_max_w=maximum,
        weight_kg=weight,
        is_full_depth=u > 0,
        notes=note,
        drive_bays=bays,
        drive_form=form,
    )


def _sw(vendor: str, model: str, copper: int, uplinks: int, *, poe: bool, role: DeviceRole,
        typical: int, maximum: int, uplink: InterfaceType = InterfaceType.SFP_PLUS,
        speed: int = 10000, pattern: str = "ether{n}") -> ModelSpec:
    ports: list[PortSpec] = []
    if copper:
        ports.append(_p(pattern, copper, InterfaceType.RJ45, 1000, poe=poe, position=10))
    if uplinks:
        ports.append(_p("sfp{n}", uplinks, uplink, speed, position=20))
    return _box(
        vendor, model, role, 1, tuple(ports), typical=typical, maximum=maximum, psu=1, weight=4,
    )


def _fc(vendor: str, model: str, count: int, speed: int, u: float = 1) -> ModelSpec:
    return _box(
        vendor,
        model,
        DeviceRole.L2_SWITCH,
        u,
        (_p("fc{n}", count, InterfaceType.SFP_PLUS, speed, position=10),),
        typical=150,
        maximum=300,
        psu=2,
        weight=8,
        extra=f"Коммутатор Fibre Channel, {count}× {speed // 1000} Гбит/с.",
    )


def _ap(vendor: str, model: str, watts: int = 13) -> ModelSpec:
    return ModelSpec(
        vendor,
        model,
        DeviceRole.ACCESS_POINT,
        0,
        ports=(_p("eth0", 1, InterfaceType.RJ45, 1000, poe=True),),
        power_nameplate_w=watts,
        power_max_w=watts,
        is_full_depth=False,
        notes=CATALOG_NOTE + " Нестоечная точка доступа.",
    )


# (вендор, модель, U, типично Вт, макс Вт, сокеты, сокет, слоты, тип RAM, корзины, форма)
_SERVERS: tuple[tuple, ...] = (
    ("HPE", "ProLiant DL20 Gen11", 1, 150, 500, 1, "LGA1700", 4, "DDR5", 2, "LFF"),
    ("HPE", "ProLiant DL360 Gen10", 1, 400, 800, 2, "LGA3647", 24, "DDR4", 8, "SFF"),
    ("HPE", "ProLiant DL360 Gen10 Plus", 1, 500, 1000, 2, "LGA4189", 32, "DDR4", 8, "SFF"),
    ("HPE", "ProLiant DL360 Gen11", 1, 500, 1100, 2, "LGA4677", 32, "DDR5", 8, "SFF"),
    ("HPE", "ProLiant DL380 Gen10", 2, 600, 1400, 2, "LGA3647", 24, "DDR4", 12, "SFF"),
    ("HPE", "ProLiant DL380 Gen10 Plus", 2, 650, 1600, 2, "LGA4189", 32, "DDR4", 24, "SFF"),
    ("HPE", "ProLiant DL325 Gen11", 1, 350, 800, 1, "SP5", 12, "DDR5", 8, "SFF"),
    ("HPE", "ProLiant DL345 Gen11", 2, 450, 1000, 1, "SP5", 12, "DDR5", 12, "SFF"),
    ("HPE", "ProLiant DL385 Gen11", 2, 600, 1600, 2, "SP5", 24, "DDR5", 24, "SFF"),
    ("HPE", "ProLiant DL560 Gen11", 2, 900, 2200, 4, "LGA4677", 64, "DDR5", 8, "SFF"),
    ("HPE", "ProLiant ML350 Gen11", 0, 400, 1200, 2, "LGA4677", 32, "DDR5", 8, "SFF"),
    ("HPE", "Apollo 4200 Gen10", 2, 700, 1600, 2, "LGA3647", 16, "DDR4", 28, "LFF"),
    ("Dell", "PowerEdge R250", 1, 150, 450, 1, "LGA1700", 4, "DDR4", 4, "LFF"),
    ("Dell", "PowerEdge R350", 1, 180, 500, 1, "LGA1700", 4, "DDR4", 8, "SFF"),
    ("Dell", "PowerEdge R450", 1, 400, 800, 2, "LGA4189", 16, "DDR4", 8, "SFF"),
    ("Dell", "PowerEdge R550", 2, 450, 1100, 2, "LGA4189", 16, "DDR4", 8, "LFF"),
    ("Dell", "PowerEdge R650", 1, 500, 1100, 2, "LGA4189", 32, "DDR4", 10, "SFF"),
    ("Dell", "PowerEdge R650xs", 1, 400, 900, 2, "LGA4189", 16, "DDR4", 10, "SFF"),
    ("Dell", "PowerEdge R750xs", 2, 500, 1400, 2, "LGA4189", 16, "DDR4", 12, "LFF"),
    ("Dell", "PowerEdge R660", 1, 550, 1400, 2, "LGA4677", 32, "DDR5", 10, "SFF"),
    ("Dell", "PowerEdge R760", 2, 700, 1800, 2, "LGA4677", 32, "DDR5", 16, "SFF"),
    ("Dell", "PowerEdge R760xs", 2, 550, 1400, 2, "LGA4677", 16, "DDR5", 12, "LFF"),
    ("Dell", "PowerEdge R860", 2, 1000, 2400, 4, "LGA4677", 64, "DDR5", 8, "SFF"),
    ("Dell", "PowerEdge R960", 4, 1400, 2800, 4, "LGA4677", 64, "DDR5", 12, "SFF"),
    ("Dell", "PowerEdge T560", 0, 400, 1400, 2, "LGA4677", 16, "DDR5", 8, "LFF"),
    ("Dell", "PowerEdge MX760c", 0, 600, 1600, 2, "LGA4677", 32, "DDR5", 6, "SFF"),
    ("Lenovo", "ThinkSystem SR250 V2", 1, 150, 450, 1, "LGA1200", 4, "DDR4", 4, "LFF"),
    ("Lenovo", "ThinkSystem SR630 V2", 1, 500, 1100, 2, "LGA4189", 32, "DDR4", 10, "SFF"),
    ("Lenovo", "ThinkSystem SR630 V3", 1, 550, 1400, 2, "LGA4677", 32, "DDR5", 10, "SFF"),
    ("Lenovo", "ThinkSystem SR650 V2", 2, 600, 1600, 2, "LGA4189", 32, "DDR4", 16, "SFF"),
    ("Lenovo", "ThinkSystem SR850 V3", 2, 900, 2200, 4, "LGA4677", 64, "DDR5", 8, "SFF"),
    ("Lenovo", "ThinkSystem SR860 V3", 4, 1200, 2600, 4, "LGA4677", 64, "DDR5", 16, "SFF"),
    ("Lenovo", "ThinkSystem ST650 V3", 0, 400, 1200, 2, "LGA4677", 16, "DDR5", 8, "LFF"),
    ("Huawei", "FusionServer 1288H V6", 1, 450, 1000, 2, "LGA4189", 32, "DDR4", 8, "SFF"),
    ("Huawei", "FusionServer 2288H V5", 2, 550, 1400, 2, "LGA3647", 24, "DDR4", 12, "SFF"),
    ("Huawei", "FusionServer 2288H V7", 2, 700, 1800, 2, "LGA4677", 32, "DDR5", 12, "SFF"),
    ("Huawei", "FusionServer 5288 V6", 4, 800, 2000, 2, "LGA4189", 32, "DDR4", 36, "LFF"),
    ("ASUS", "RS700-E11-RS4U", 1, 500, 1200, 2, "LGA4677", 32, "DDR5", 4, "SFF"),
    ("ASUS", "RS720-E11-RS12U", 2, 650, 1600, 2, "LGA4677", 32, "DDR5", 12, "SFF"),
    ("ASUS", "RS700A-E11-RS4U", 1, 450, 1100, 2, "SP3", 16, "DDR4", 4, "SFF"),
    ("ASUS", "RS520A-E12-RS12U", 2, 500, 1200, 1, "SP5", 12, "DDR5", 12, "SFF"),
    ("ASUS", "ESC8000A-E12", 4, 1500, 3000, 2, "SP5", 24, "DDR5", 8, "SFF"),
    ("Supermicro", "SYS-220U-TNR", 2, 600, 1600, 2, "LGA4189", 32, "DDR4", 12, "SFF"),
    ("Supermicro", "SYS-121H-TNR", 1, 550, 1400, 2, "LGA4677", 32, "DDR5", 10, "SFF"),
    ("Supermicro", "SYS-221H-TNR", 2, 700, 1800, 2, "LGA4677", 32, "DDR5", 12, "SFF"),
    ("Supermicro", "AS-2015HS-TNR", 2, 500, 1200, 1, "SP5", 12, "DDR5", 12, "SFF"),
    ("Supermicro", "SSG-640SP-E1CR60", 4, 800, 1600, 2, "LGA4189", 16, "DDR4", 60, "LFF"),
    ("Fujitsu", "PRIMERGY RX2530 M7", 1, 500, 1200, 2, "LGA4677", 32, "DDR5", 8, "SFF"),
    ("Fujitsu", "PRIMERGY RX4770 M7", 4, 1200, 2600, 4, "LGA4677", 64, "DDR5", 8, "SFF"),
    ("Fujitsu", "PRIMERGY TX2550 M7", 0, 400, 1200, 2, "LGA4677", 16, "DDR5", 8, "LFF"),
    ("HPE", "ProLiant DL20 Gen9", 1, 120, 400, 1, "LGA1151", 4, "DDR4", 2, "LFF"),
    ("HPE", "ProLiant DL60 Gen9", 1, 200, 500, 1, "LGA2011-3", 8, "DDR4", 4, "LFF"),
    ("HPE", "ProLiant DL80 Gen9", 2, 300, 800, 2, "LGA2011-3", 16, "DDR4", 12, "LFF"),
    ("HPE", "ProLiant DL120 Gen9", 1, 250, 600, 1, "LGA2011-3", 8, "DDR4", 4, "LFF"),
    ("HPE", "ProLiant DL160 Gen9", 1, 350, 800, 2, "LGA2011-3", 16, "DDR4", 8, "SFF"),
    ("HPE", "ProLiant DL180 Gen9", 2, 400, 900, 2, "LGA2011-3", 16, "DDR4", 12, "LFF"),
    ("HPE", "ProLiant DL360 Gen9", 1, 400, 800, 2, "LGA2011-3", 24, "DDR4", 8, "SFF"),
    ("HPE", "ProLiant DL380 Gen9", 2, 500, 1200, 2, "LGA2011-3", 24, "DDR4", 24, "SFF"),
    ("HPE", "ProLiant DL560 Gen9", 2, 800, 1600, 4, "LGA2011-3", 48, "DDR4", 6, "SFF"),
    ("HPE", "ProLiant DL580 Gen9", 4, 1000, 2000, 4, "LGA2011-3", 96, "DDR4", 10, "SFF"),
    ("HPE", "ProLiant ML110 Gen9", 0, 150, 400, 1, "LGA1151", 4, "DDR4", 4, "LFF"),
    ("HPE", "ProLiant ML150 Gen9", 0, 250, 700, 2, "LGA2011-3", 16, "DDR4", 8, "LFF"),
    ("HPE", "ProLiant ML350 Gen9", 0, 400, 1000, 2, "LGA2011-3", 24, "DDR4", 16, "SFF"),
    ("HPE", "ProLiant BL460c Gen9", 0, 400, 800, 2, "LGA2011-3", 16, "DDR4", 2, "SFF"),
    ("HPE", "ProLiant DL360p Gen8", 1, 350, 750, 2, "LGA2011", 24, "DDR3", 8, "SFF"),
    ("HPE", "ProLiant DL380p Gen8", 2, 450, 1200, 2, "LGA2011", 24, "DDR3", 16, "SFF"),
    ("HPE", "ProLiant DL380e Gen8", 2, 400, 1000, 2, "LGA2011", 12, "DDR3", 12, "LFF"),
    ("HPE", "ProLiant DL160 Gen8", 1, 300, 750, 2, "LGA2011", 16, "DDR3", 8, "SFF"),
    ("HPE", "ProLiant ML350p Gen8", 0, 350, 900, 2, "LGA2011", 24, "DDR3", 8, "LFF"),
    ("HPE", "ProLiant BL460c Gen8", 0, 350, 750, 2, "LGA2011", 16, "DDR3", 2, "SFF"),
    ("HPE", "ProLiant DL325 Gen10", 1, 300, 700, 1, "SP3", 16, "DDR4", 8, "SFF"),
    ("HPE", "ProLiant DL385 Gen10", 2, 500, 1400, 2, "SP3", 32, "DDR4", 24, "SFF"),
    ("HPE", "ProLiant DL385 Gen10 Plus", 2, 550, 1600, 2, "SP3", 32, "DDR4", 24, "SFF"),
    ("HPE", "ProLiant DL560 Gen10", 2, 800, 1800, 4, "LGA3647", 48, "DDR4", 6, "SFF"),
    ("HPE", "ProLiant DL580 Gen10", 4, 1100, 2200, 4, "LGA3647", 48, "DDR4", 8, "SFF"),
    ("HPE", "Synergy 480 Gen10", 0, 500, 1200, 2, "LGA3647", 24, "DDR4", 2, "SFF"),
    ("Dell", "PowerEdge R230", 1, 120, 350, 1, "LGA1151", 4, "DDR4", 4, "LFF"),
    ("Dell", "PowerEdge R330", 1, 150, 400, 1, "LGA1151", 4, "DDR4", 4, "LFF"),
    ("Dell", "PowerEdge R430", 1, 300, 700, 2, "LGA2011-3", 12, "DDR4", 4, "LFF"),
    ("Dell", "PowerEdge R530", 2, 350, 800, 2, "LGA2011-3", 12, "DDR4", 8, "LFF"),
    ("Dell", "PowerEdge R630", 1, 400, 900, 2, "LGA2011-3", 24, "DDR4", 10, "SFF"),
    ("Dell", "PowerEdge R730", 2, 500, 1200, 2, "LGA2011-3", 24, "DDR4", 16, "SFF"),
    ("Dell", "PowerEdge R730xd", 2, 550, 1400, 2, "LGA2011-3", 24, "DDR4", 24, "SFF"),
    ("Dell", "PowerEdge T630", 0, 400, 1100, 2, "LGA2011-3", 24, "DDR4", 8, "LFF"),
    ("Dell", "PowerEdge R620", 1, 350, 800, 2, "LGA2011", 24, "DDR3", 10, "SFF"),
    ("Dell", "PowerEdge R720", 2, 450, 1100, 2, "LGA2011", 24, "DDR3", 16, "SFF"),
    ("Dell", "PowerEdge R720xd", 2, 500, 1300, 2, "LGA2011", 24, "DDR3", 24, "SFF"),
    ("Dell", "PowerEdge T620", 0, 400, 1100, 2, "LGA2011", 24, "DDR3", 8, "LFF"),
    ("Dell", "PowerEdge R440", 1, 300, 750, 2, "LGA3647", 16, "DDR4", 4, "LFF"),
    ("Dell", "PowerEdge R540", 2, 400, 1000, 2, "LGA3647", 16, "DDR4", 12, "LFF"),
    ("Dell", "PowerEdge R640", 1, 450, 1100, 2, "LGA3647", 24, "DDR4", 10, "SFF"),
    ("Dell", "PowerEdge R740", 2, 550, 1400, 2, "LGA3647", 24, "DDR4", 16, "SFF"),
    ("Dell", "PowerEdge R740xd", 2, 600, 1600, 2, "LGA3647", 24, "DDR4", 24, "SFF"),
    ("Dell", "PowerEdge T640", 0, 450, 1200, 2, "LGA3647", 24, "DDR4", 8, "LFF"),
    ("Dell", "PowerEdge FC640", 0, 450, 1100, 2, "LGA3647", 16, "DDR4", 2, "SFF"),
    ("Lenovo", "System x3550 M5", 1, 400, 900, 2, "LGA2011-3", 24, "DDR4", 8, "SFF"),
    ("Lenovo", "System x3650 M5", 2, 500, 1200, 2, "LGA2011-3", 24, "DDR4", 16, "SFF"),
    ("Lenovo", "ThinkSystem SR570", 1, 300, 750, 2, "LGA3647", 16, "DDR4", 4, "LFF"),
    ("Lenovo", "ThinkSystem SR550", 2, 350, 900, 2, "LGA3647", 12, "DDR4", 8, "LFF"),
    ("Lenovo", "ThinkSystem SR630", 1, 450, 1100, 2, "LGA3647", 24, "DDR4", 10, "SFF"),
    ("Lenovo", "ThinkSystem SR650", 2, 550, 1400, 2, "LGA3647", 24, "DDR4", 16, "SFF"),
    ("Huawei", "FusionServer RH2288 V3", 2, 450, 1100, 2, "LGA2011-3", 16, "DDR4", 12, "LFF"),
    ("Huawei", "FusionServer 2288H V3", 2, 450, 1100, 2, "LGA2011-3", 16, "DDR4", 8, "SFF"),
    ("Huawei", "FusionServer 1288H V5", 1, 400, 1000, 2, "LGA3647", 24, "DDR4", 8, "SFF"),
    ("Huawei", "FusionServer 2488H V5", 2, 800, 1800, 4, "LGA3647", 48, "DDR4", 8, "SFF"),
    ("ASUS", "RS700-E9-RS4", 1, 400, 1000, 2, "LGA3647", 16, "DDR4", 4, "SFF"),
    ("ASUS", "RS720-E9-RS12", 2, 500, 1300, 2, "LGA3647", 16, "DDR4", 12, "SFF"),
    ("Supermicro", "SYS-1029U-TRT", 1, 450, 1100, 2, "LGA3647", 24, "DDR4", 10, "SFF"),
    ("Supermicro", "SYS-2029U-TRT", 2, 550, 1400, 2, "LGA3647", 24, "DDR4", 12, "SFF"),
    ("Fujitsu", "PRIMERGY RX2530 M2", 1, 350, 800, 2, "LGA2011-3", 24, "DDR4", 8, "SFF"),
    ("Fujitsu", "PRIMERGY RX2540 M2", 2, 450, 1100, 2, "LGA2011-3", 24, "DDR4", 16, "SFF"),
    ("Fujitsu", "PRIMERGY RX2530 M4", 1, 400, 1000, 2, "LGA3647", 24, "DDR4", 8, "SFF"),
    ("Fujitsu", "PRIMERGY RX2540 M4", 2, 500, 1300, 2, "LGA3647", 24, "DDR4", 16, "SFF"),
    ("Fujitsu", "PRIMERGY RX2530 M5", 1, 450, 1100, 2, "LGA4189", 32, "DDR4", 8, "SFF"),
    ("Fujitsu", "PRIMERGY RX2540 M5", 2, 550, 1400, 2, "LGA4189", 32, "DDR4", 16, "SFF"),
)

_BOARDS: tuple[tuple, ...] = (
    ("Supermicro", "X13DEM", 2, "LGA4677", 32, "DDR5"),
    ("Supermicro", "X12DPi-NT6", 2, "LGA4189", 16, "DDR4"),
    ("Supermicro", "H13SSL-N", 1, "SP5", 12, "DDR5"),
    ("Supermicro", "H12SSL-i", 1, "SP3", 8, "DDR4"),
    ("Supermicro", "X11DPi-N", 2, "LGA3647", 16, "DDR4"),
    ("Supermicro", "X10DRi", 2, "LGA2011-3", 16, "DDR4"),
    ("Supermicro", "X9DRi-LN4F", 2, "LGA2011", 16, "DDR3"),
    ("ASUS", "Z13PR-D32", 2, "LGA4677", 32, "DDR5"),
    ("ASUS", "Pro WS W790-ACE", 1, "LGA4677", 8, "DDR5"),
)

# (вендор, модель, сокет, пояснение)
_CPUS: tuple[tuple[str, str, str, str], ...] = (
    ("Intel", "Xeon E3-1220 v5", "LGA1151", "4 ядра, DDR4 ECC UDIMM."),
    ("Intel", "Xeon E3-1240 v5", "LGA1151", "4 ядра, DDR4 ECC UDIMM."),
    ("Intel", "Xeon E3-1270 v6", "LGA1151", "4 ядра, DDR4 ECC UDIMM."),
    ("Intel", "Xeon E-2136", "LGA1151", "6 ядер, DDR4 ECC UDIMM."),
    ("Intel", "Xeon E-2236", "LGA1151", "6 ядер, DDR4 ECC UDIMM."),
    ("Intel", "Xeon E5-2620 v2", "LGA2011", "6 ядер, Ivy Bridge-EP, DDR3."),
    ("Intel", "Xeon E5-2650 v2", "LGA2011", "8 ядер, Ivy Bridge-EP, DDR3."),
    ("Intel", "Xeon E5-2670 v2", "LGA2011", "10 ядер, Ivy Bridge-EP, DDR3."),
    ("Intel", "Xeon E5-2690 v2", "LGA2011", "10 ядер, Ivy Bridge-EP, DDR3."),
    ("Intel", "Xeon E5-2620 v3", "LGA2011-3", "6 ядер, Haswell-EP, DDR4."),
    ("Intel", "Xeon E5-2630 v4", "LGA2011-3", "10 ядер, Broadwell-EP, DDR4."),
    ("Intel", "Xeon E5-2640 v4", "LGA2011-3", "10 ядер, Broadwell-EP, DDR4."),
    ("Intel", "Xeon E5-2650 v4", "LGA2011-3", "12 ядер, Broadwell-EP, DDR4."),
    ("Intel", "Xeon E5-2660 v4", "LGA2011-3", "14 ядер, Broadwell-EP, DDR4."),
    ("Intel", "Xeon E5-2680 v3", "LGA2011-3", "12 ядер, Haswell-EP, DDR4."),
    ("Intel", "Xeon E5-2680 v4", "LGA2011-3", "14 ядер, Broadwell-EP, DDR4."),
    ("Intel", "Xeon E5-2690 v4", "LGA2011-3", "14 ядер, Broadwell-EP, DDR4."),
    ("Intel", "Xeon E5-2697 v4", "LGA2011-3", "18 ядер, Broadwell-EP, DDR4."),
    ("Intel", "Xeon E5-2699 v4", "LGA2011-3", "22 ядра, Broadwell-EP, DDR4."),
    ("Intel", "Xeon Silver 4110", "LGA3647", "8 ядер, Skylake."),
    ("Intel", "Xeon Silver 4114", "LGA3647", "10 ядер, Skylake."),
    ("Intel", "Xeon Silver 4210", "LGA3647", "10 ядер, Cascade Lake."),
    ("Intel", "Xeon Silver 4214", "LGA3647", "12 ядер, Cascade Lake."),
    ("Intel", "Xeon Gold 5118", "LGA3647", "12 ядер, Skylake."),
    ("Intel", "Xeon Gold 6130", "LGA3647", "16 ядер, Skylake."),
    ("Intel", "Xeon Gold 6138", "LGA3647", "20 ядер, Skylake."),
    ("Intel", "Xeon Gold 6148", "LGA3647", "20 ядер, Skylake."),
    ("Intel", "Xeon Gold 6248", "LGA3647", "20 ядер, Cascade Lake."),
    ("Intel", "Xeon Gold 6258R", "LGA3647", "28 ядер, Cascade Lake."),
    ("Intel", "Xeon Platinum 8160", "LGA3647", "24 ядра, Skylake."),
    ("Intel", "Xeon Platinum 8176", "LGA3647", "28 ядер, Skylake."),
    ("Intel", "Xeon Platinum 8260", "LGA3647", "24 ядра, Cascade Lake."),
    ("Intel", "Xeon Platinum 8280", "LGA3647", "28 ядер, Cascade Lake."),
    ("Intel", "Xeon E-2388G", "LGA1200", "8 ядер, DDR4 ECC UDIMM."),
    ("Intel", "Xeon E-2488", "LGA1700", "8 ядер, DDR5 ECC UDIMM."),
    ("Intel", "Xeon Silver 4314", "LGA4189", "16 ядер, Ice Lake."),
    ("Intel", "Xeon Gold 5318Y", "LGA4189", "24 ядра, Ice Lake."),
    ("Intel", "Xeon Gold 6338", "LGA4189", "32 ядра, Ice Lake."),
    ("Intel", "Xeon Silver 4410Y", "LGA4677", "12 ядер, Sapphire Rapids."),
    ("Intel", "Xeon Gold 5418Y", "LGA4677", "24 ядра, Sapphire Rapids."),
    ("Intel", "Xeon Gold 6430", "LGA4677", "32 ядра, Sapphire Rapids."),
    ("Intel", "Xeon Gold 6448Y", "LGA4677", "32 ядра, Sapphire Rapids."),
    ("Intel", "Xeon Gold 6548Y+", "LGA4677", "32 ядра, Emerald Rapids."),
    ("Intel", "Xeon Platinum 8460Y+", "LGA4677", "40 ядер, Sapphire Rapids."),
    ("Intel", "Xeon Platinum 8480+", "LGA4677", "56 ядер, Sapphire Rapids."),
    ("Intel", "Xeon Platinum 8592+", "LGA4677", "64 ядра, Emerald Rapids."),
    ("AMD", "EPYC 7302", "SP3", "16 ядер, Rome."),
    ("AMD", "EPYC 7402", "SP3", "24 ядра, Rome."),
    ("AMD", "EPYC 7502", "SP3", "32 ядра, Rome."),
    ("AMD", "EPYC 7542", "SP3", "32 ядра, Rome."),
    ("AMD", "EPYC 7742", "SP3", "64 ядра, Rome."),
    ("AMD", "EPYC 7543", "SP3", "32 ядра, Milan."),
    ("AMD", "EPYC 7763", "SP3", "64 ядра, Milan."),
    ("AMD", "EPYC 9124", "SP5", "16 ядер, Genoa."),
    ("AMD", "EPYC 9334", "SP5", "32 ядра, Genoa."),
    ("AMD", "EPYC 9354", "SP5", "32 ядра, Genoa."),
    ("AMD", "EPYC 9454", "SP5", "48 ядер, Genoa."),
    ("AMD", "EPYC 9554", "SP5", "64 ядра, Genoa."),
    ("AMD", "EPYC 9654", "SP5", "96 ядер, Genoa."),
    ("AMD", "EPYC 9555", "SP5", "64 ядра, Turin."),
    ("AMD", "EPYC 9655", "SP5", "96 ядер, Turin."),
)

# (вендор, модель, тип)
_RAM: tuple[tuple[str, str, str], ...] = (
    ("Samsung", "DDR3 RDIMM 8 ГБ 1600", "DDR3"),
    ("Samsung", "DDR3 RDIMM 16 ГБ 1600", "DDR3"),
    ("Samsung", "DDR3 RDIMM 32 ГБ 1866", "DDR3"),
    ("Samsung", "DDR4 RDIMM 8 ГБ 2400", "DDR4"),
    ("Samsung", "DDR4 RDIMM 16 ГБ 2400", "DDR4"),
    ("Samsung", "DDR4 RDIMM 32 ГБ 2400", "DDR4"),
    ("Samsung", "DDR4 RDIMM 16 ГБ 2666", "DDR4"),
    ("Samsung", "DDR4 RDIMM 32 ГБ 2933", "DDR4"),
    ("Samsung", "DDR4 RDIMM 16 ГБ 3200", "DDR4"),
    ("Samsung", "DDR4 RDIMM 32 ГБ 3200", "DDR4"),
    ("Samsung", "DDR4 RDIMM 64 ГБ 3200", "DDR4"),
    ("Samsung", "DDR5 RDIMM 16 ГБ 4800", "DDR5"),
    ("Samsung", "DDR5 RDIMM 32 ГБ 4800", "DDR5"),
    ("Samsung", "DDR5 RDIMM 64 ГБ 5600", "DDR5"),
    ("Samsung", "DDR5 RDIMM 96 ГБ 5600", "DDR5"),
    ("Samsung", "DDR5 RDIMM 128 ГБ 5600", "DDR5"),
    ("Samsung", "DDR5 ECC UDIMM 32 ГБ", "DDR5"),
    ("Micron", "DDR4 RDIMM 32 ГБ 3200", "DDR4"),
    ("Micron", "DDR4 RDIMM 64 ГБ 3200", "DDR4"),
    ("Micron", "DDR5 RDIMM 32 ГБ 5600", "DDR5"),
    ("Micron", "DDR5 RDIMM 64 ГБ 5600", "DDR5"),
    ("Micron", "DDR5 RDIMM 128 ГБ 5600", "DDR5"),
    ("Kingston", "DDR4 ECC UDIMM 16 ГБ", "DDR4"),
    ("Kingston", "DDR4 ECC UDIMM 32 ГБ", "DDR4"),
    ("Kingston", "DDR5 ECC UDIMM 32 ГБ", "DDR5"),
    ("HPE", "SmartMemory DDR3 16 ГБ", "DDR3"),
    ("HPE", "SmartMemory DDR4 16 ГБ 2400", "DDR4"),
    ("HPE", "SmartMemory DDR4 32 ГБ 2400", "DDR4"),
    ("HPE", "SmartMemory DDR4 32 ГБ", "DDR4"),
    ("HPE", "SmartMemory DDR5 32 ГБ", "DDR5"),
    ("HPE", "SmartMemory DDR5 64 ГБ", "DDR5"),
    ("HPE", "SmartMemory DDR5 128 ГБ", "DDR5"),
    ("Dell", "DDR3 RDIMM 16 ГБ", "DDR3"),
    ("Dell", "DDR4 RDIMM 16 ГБ 2400", "DDR4"),
    ("Dell", "DDR4 RDIMM 32 ГБ 2666", "DDR4"),
    ("Dell", "DDR4 RDIMM 32 ГБ", "DDR4"),
    ("Dell", "DDR5 RDIMM 32 ГБ", "DDR5"),
    ("Dell", "DDR5 RDIMM 64 ГБ", "DDR5"),
    ("Dell", "DDR5 RDIMM 128 ГБ", "DDR5"),
)

# (вендор, модель, форма)
_DISKS: tuple[tuple[str, str, str], ...] = (
    ("Seagate", "Exos 7E8 4 ТБ", "LFF"),
    ("Seagate", "Exos X18 16 ТБ", "LFF"),
    ("Seagate", "Exos X20 20 ТБ", "LFF"),
    ("Seagate", "Savvio 600 ГБ 10k", "SFF"),
    ("Seagate", "Exos 10E2400 1.2 ТБ", "SFF"),
    ("Seagate", "Exos 10E2400 1.8 ТБ", "SFF"),
    ("Seagate", "Exos 10E2400 2.4 ТБ", "SFF"),
    ("Western Digital", "Ultrastar DC HC550 16 ТБ", "LFF"),
    ("Western Digital", "Ultrastar DC HC560 20 ТБ", "LFF"),
    ("Samsung", "PM893 1.92 ТБ SATA", "SFF"),
    ("Samsung", "PM893 3.84 ТБ SATA", "SFF"),
    ("Samsung", "PM9A3 1.92 ТБ NVMe", "NVMe"),
    ("Samsung", "PM9A3 3.84 ТБ NVMe", "NVMe"),
    ("Samsung", "PM9A3 7.68 ТБ NVMe", "NVMe"),
    ("Kioxia", "CM6-V 3.2 ТБ NVMe", "NVMe"),
    ("Kioxia", "CD8-R 3.84 ТБ NVMe", "NVMe"),
    ("Micron", "5400 PRO 1.92 ТБ SATA", "SFF"),
    ("Micron", "7450 PRO 3.84 ТБ NVMe", "NVMe"),
    ("Micron", "7450 MAX 1.6 ТБ NVMe", "NVMe"),
    ("HPE", "1.92 ТБ SATA MU", "SFF"),
    ("HPE", "3.84 ТБ NVMe MU", "NVMe"),
    ("HPE", "600 ГБ SAS 10k", "SFF"),
    ("HPE", "1.2 ТБ SAS 10k", "SFF"),
    ("HPE", "1.8 ТБ SAS 10k", "SFF"),
    ("HPE", "2.4 ТБ SAS 10k", "SFF"),
    ("Dell", "1.92 ТБ SATA SSD", "SFF"),
    ("Dell", "3.84 ТБ NVMe", "NVMe"),
    ("Dell", "2.4 ТБ SAS 10k", "SFF"),
    ("Dell", "16 ТБ SATA 7.2k", "LFF"),
)

_NICS: tuple[tuple[str, str, str], ...] = (
    ("Intel", "I350-T4", "4× RJ45 1 Гбит/с."),
    ("Intel", "X520-DA2", "2× SFP+ 10 Гбит/с."),
    ("Intel", "X710-DA2", "2× SFP+ 10 Гбит/с."),
    ("Intel", "X710-DA4", "4× SFP+ 10 Гбит/с."),
    ("Intel", "E810-XXVDA2", "2× SFP28 25 Гбит/с."),
    ("Intel", "E810-CQDA2", "2× QSFP28 100 Гбит/с."),
    ("Broadcom", "BCM57414", "2× SFP28 25 Гбит/с."),
    ("Broadcom", "BCM57508", "2× QSFP56 100/200 Гбит/с."),
    ("NVIDIA", "ConnectX-6 Dx", "2× QSFP56, 100 Гбит/с."),
    ("NVIDIA", "ConnectX-7", "QSFP112, до 400 Гбит/с."),
)

_HBAS: tuple[tuple[str, str, str], ...] = (
    ("HPE", "H240", "SAS HBA на 8 внутренних линий."),
    ("Dell", "PERC H730", "RAID-контроллер 12 Гбит/с SAS."),
    ("Dell", "PERC H740P", "RAID-контроллер 12 Гбит/с SAS."),
    ("Broadcom", "LPe35002", "2× 32 Гбит/с Fibre Channel."),
    ("Broadcom", "LPe36002", "2× 64 Гбит/с Fibre Channel."),
    ("Marvell", "QLE2772", "2× 32 Гбит/с Fibre Channel."),
    ("Marvell", "QLE2872", "2× 64 Гбит/с Fibre Channel."),
    ("HPE", "SN1610Q", "2× 32 Гбит/с Fibre Channel."),
    ("HPE", "SN1700Q", "2× 64 Гбит/с Fibre Channel."),
)

_PSUS: tuple[tuple[str, str], ...] = (
    ("HPE", "Flex Slot 500 Вт",),
    ("HPE", "Flex Slot 800 Вт",),
    ("HPE", "Flex Slot 1600 Вт",),
    ("Dell", "750 Вт 12G/13G",),
    ("Dell", "1100 Вт 13G",),
    ("Dell", "Titanium 800 Вт",),
    ("Dell", "Titanium 1400 Вт",),
    ("Dell", "Titanium 2400 Вт",),
    ("Supermicro", "PWS-1K02A-1R 1000 Вт",),
)


def _servers() -> list[ModelSpec]:
    items = []
    for row in _SERVERS:
        vendor, model, u, typical, maximum, sockets, socket, slots, ram, bays, form = row
        extra = ""
        blade = any(token in model for token in ("MX760c", "BL460", "Synergy", "FC640"))
        if blade:
            extra = "Лезвие, само по себе юниты стойки не занимает."
        elif u == 0:
            extra = "Башня, в стойку без комплекта не ставится."
        elif "5288" in model or "Apollo" in model or "SSG-" in model:
            extra = "Сервер с большим числом дисковых корзин."
        items.append(
            _srv(
                vendor, model, u, typical, maximum, sockets, socket, slots, ram, bays, form,
                extra=extra,
            )
        )
    return items


def _components() -> list[ModelSpec]:
    items: list[ModelSpec] = []
    for vendor, model, sockets, socket, slots, ram in _BOARDS:
        items.append(
            _part(
                vendor,
                model,
                "BOARD",
                sockets=sockets,
                socket=socket,
                ram_slots=slots,
                ram=ram,
                notes=f"Плата {sockets}× {socket}, {slots}× {ram}. {CATALOG_NOTE}",
            )
        )
    for vendor, model, socket, note in _CPUS:
        items.append(_part(vendor, model, "CPU", socket=socket, notes=f"{note} {CATALOG_NOTE}"))
    for vendor, model, ram in _RAM:
        items.append(
            _part(vendor, model, "MEMORY", ram=ram, notes=f"Модуль {ram}. {CATALOG_NOTE}")
        )
    for vendor, model, form in _DISKS:
        items.append(
            _part(vendor, model, "DISK", form=form, notes=f"Накопитель {form}. {CATALOG_NOTE}")
        )
    for vendor, model, note in _NICS:
        items.append(_part(vendor, model, "NIC", notes=f"{note} {CATALOG_NOTE}"))
    for vendor, model, note in _HBAS:
        items.append(_part(vendor, model, "HBA", notes=f"{note} {CATALOG_NOTE}"))
    for (vendor, model) in _PSUS:
        items.append(_part(vendor, model, "PSU", notes=f"Блок питания. {CATALOG_NOTE}"))
    return items


def _storage() -> list[ModelSpec]:
    fc4 = (
        _p("mgmt{n}", 2, InterfaceType.RJ45, 1000, position=10),
        _p("fc{n}", 4, InterfaceType.SFP_PLUS, 32000, position=20),
    )
    specs = [
        ("HPE", "3PAR 8200", 2, 24, "SFF", 400, 800, "Контроллерный модуль 2 узла."),
        ("HPE", "3PAR 8440", 4, 24, "SFF", 600, 1200, "Контроллерный модуль 4 узла."),
        ("HPE", "3PAR 8450", 4, 24, "SFF", 700, 1400, "All-NVMe контроллерный модуль."),
        ("HPE", "3PAR 8000 SFF Enclosure", 2, 24, "SFF", 150, 300, "Дисковая полка."),
        ("HPE", "MSA 2060", 2, 24, "SFF", 250, 500, "Двухконтроллерный массив."),
        ("HPE", "MSA 2062", 2, 24, "SFF", 250, 500, "Массив с предустановленными SSD."),
        ("HPE", "Primera 600", 2, 24, "NVMe", 500, 1000, "Контроллерный модуль."),
        ("HPE", "Alletra 6000", 2, 24, "NVMe", 500, 1000, "Контроллерный модуль."),
        ("HPE", "Alletra MP", 2, 24, "NVMe", 600, 1200, "Модуль контроллеров."),
        ("Dell", "PowerVault ME5012", 2, 12, "LFF", 250, 500, "Двухконтроллерный массив."),
        ("Dell", "PowerVault ME5024", 2, 24, "SFF", 280, 550, "Двухконтроллерный массив."),
        ("Dell", "PowerVault ME424", 2, 24, "SFF", 150, 300, "Полка расширения."),
        ("Dell EMC", "PowerStore 1200T", 2, 25, "NVMe", 500, 1000, "Базовый модуль."),
        ("Dell EMC", "PowerStore 3200T", 2, 25, "NVMe", 600, 1200, "Базовый модуль."),
        ("Dell EMC", "Unity XT 380", 2, 25, "SFF", 400, 800, "Двухконтроллерный массив."),
        ("Dell EMC", "Unity XT 480", 2, 25, "SFF", 500, 1000, "Двухконтроллерный массив."),
        ("NetApp", "AFF A400", 4, 24, "NVMe", 500, 1000, "Пара контроллеров."),
        ("NetApp", "FAS2750", 2, 24, "SFF", 300, 600, "Пара контроллеров."),
        ("NetApp", "FAS8300", 4, 24, "SFF", 500, 1000, "Пара контроллеров."),
        ("NetApp", "DS224C", 2, 24, "SFF", 150, 300, "Дисковая полка."),
        ("NetApp", "NS224", 2, 24, "NVMe", 200, 400, "Полка NVMe."),
        ("Huawei", "OceanStor Dorado 5000 V6", 2, 25, "NVMe", 500, 1100, "Контроллерный модуль."),
        ("Huawei", "OceanStor 5510", 2, 25, "SFF", 450, 900, "Гибридный массив."),
        ("Huawei", "OceanStor DAE", 2, 25, "SFF", 150, 300, "Дисковая полка."),
        ("Yadro", "TATLIN.UNIFIED", 2, 24, "SFF", 400, 900, "Контроллерный модуль."),
        ("Yadro", "TATLIN.AFA", 2, 24, "NVMe", 500, 1100, "All-flash модуль."),
        ("Lenovo", "ThinkSystem DE4000H", 2, 24, "SFF", 300, 600, "Двухконтроллерный массив."),
        ("IBM", "FlashSystem 5200", 1, 12, "NVMe", 300, 700, "Компактный all-flash."),
        ("IBM", "FlashSystem 7300", 2, 24, "NVMe", 500, 1100, "Контроллерный модуль."),
        ("Hitachi", "VSP E590", 2, 24, "SFF", 400, 800, "Контроллерный модуль."),
        ("Fujitsu", "ETERNUS DX200 S5", 2, 24, "SFF", 300, 600, "Двухконтроллерный массив."),
    ]
    items = []
    for vendor, model, u, bays, form, typical, maximum, extra in specs:
        items.append(
            _box(
                vendor,
                model,
                DeviceRole.STORAGE,
                u,
                fc4,
                typical=typical,
                maximum=maximum,
                psu=2,
                weight=30,
                bays=bays,
                form=form,
                extra=extra,
            )
        )
    return items


def _network() -> list[ModelSpec]:
    items: list[ModelSpec] = []
    eltex = [
        ("MES2308P", 8, 2, True, DeviceRole.L2_SWITCH, 20, 150),
        ("MES2324", 24, 4, False, DeviceRole.L2_SWITCH, 25, 60),
        ("MES2324P", 24, 4, True, DeviceRole.L2_SWITCH, 40, 400),
        ("MES2448", 48, 4, False, DeviceRole.L2_SWITCH, 40, 80),
        ("MES2448P", 48, 4, True, DeviceRole.L2_SWITCH, 60, 800),
        ("MES3308F", 0, 8, False, DeviceRole.L2_SWITCH, 30, 70),
        ("MES3324", 24, 4, False, DeviceRole.L3_SWITCH, 40, 90),
        ("MES3324F", 0, 24, False, DeviceRole.L3_SWITCH, 45, 100),
        ("MES3348", 48, 4, False, DeviceRole.L3_SWITCH, 55, 120),
        ("MES5312", 0, 12, False, DeviceRole.L3_SWITCH, 50, 120),
        ("MES5324", 0, 24, False, DeviceRole.L3_SWITCH, 60, 140),
    ]
    for model, copper, uplinks, poe, role, typical, maximum in eltex:
        slow = model in {"MES3308F", "MES3324F"}
        uplink = InterfaceType.SFP if slow else InterfaceType.SFP_PLUS
        speed = 1000 if uplink == InterfaceType.SFP else 10000
        items.append(
            _sw(
                "Eltex", model, copper, uplinks, poe=poe, role=role,
                typical=typical, maximum=maximum, uplink=uplink, speed=speed,
                pattern="gi1/0/{n}",
            )
        )
    # 48-портовые Eltex: медь или оптика плюс аплинки 10/40/100G.
    eltex_48 = [
        ("MES2348B", 48, False, 4, 0, DeviceRole.L3_SWITCH, 50, 120, 1),
        ("MES2348P", 48, True, 4, 0, DeviceRole.L3_SWITCH, 80, 1600, 2),
        ("MES2300-48P", 48, True, 4, 0, DeviceRole.L3_SWITCH, 80, 1600, 2),
        ("MES2300B-48", 48, False, 4, 0, DeviceRole.L3_SWITCH, 50, 120, 1),
        ("MES2448B", 48, False, 4, 0, DeviceRole.L3_SWITCH, 50, 120, 1),
        ("MES2420-48P", 48, True, 4, 0, DeviceRole.L2_SWITCH, 80, 1500, 2),
        ("MES3400-48", 48, False, 4, 0, DeviceRole.L3_SWITCH, 55, 140, 2),
        ("MES3400-48F", 0, False, 48, 4, DeviceRole.L3_SWITCH, 60, 160, 2),
        ("MES3348F", 0, False, 48, 4, DeviceRole.L3_SWITCH, 60, 160, 2),
        ("MES5448", 0, False, 48, 4, DeviceRole.L3_SWITCH, 90, 250, 2),
        ("MES5300-48", 0, False, 48, 6, DeviceRole.L3_SWITCH, 120, 300, 2),
        ("MES5305-48", 0, False, 48, 6, DeviceRole.L3_SWITCH, 120, 300, 2),
        ("MES5310-48", 0, False, 48, 6, DeviceRole.L3_SWITCH, 140, 350, 2),
        ("MES5400-48", 0, False, 48, 6, DeviceRole.L3_SWITCH, 150, 400, 2),
        ("MES5410-48", 0, False, 48, 6, DeviceRole.L3_SWITCH, 160, 400, 2),
    ]
    for model, copper, poe, sfp, qsfp, role, typical, maximum, psu in eltex_48:
        ports: list[PortSpec] = []
        if copper:
            ports.append(_p("gi1/0/{n}", copper, InterfaceType.RJ45, 1000, poe=poe, position=10))
        if model.endswith("F"):
            ports.append(_p("sfp{n}", 48, InterfaceType.SFP, 1000, position=20))
            ports.append(_p("sfpplus{n}", 4, InterfaceType.SFP_PLUS, 10000, position=30))
            note = "48× SFP 1 Гбит/с и 4× SFP+ 10 Гбит/с."
        elif model == "MES5448":
            ports.append(_p("sfp{n}", 48, InterfaceType.SFP_PLUS, 10000, position=20))
            ports.append(_p("qsfp{n}", 4, InterfaceType.QSFP_PLUS, 40000, position=30))
            note = "48× 10 Гбит/с и 4× 40 Гбит/с."
        elif model.startswith(("MES53", "MES54")):
            ports.append(_p("sfp{n}", sfp, InterfaceType.SFP_PLUS, 10000, position=20))
            ports.append(_p("qsfp{n}", qsfp, InterfaceType.QSFP28, 100000, position=30))
            note = "48× 10 Гбит/с и аплинки 100 Гбит/с."
        else:
            ports.append(_p("sfp{n}", sfp, InterfaceType.SFP_PLUS, 10000, position=20))
            note = "48 портов доступа и 4 аплинка 10 Гбит/с."
        items.append(
            _box(
                "Eltex", model, role, 1, tuple(ports),
                typical=typical, maximum=maximum, psu=psu, weight=5, extra=note,
            )
        )
    items.append(
        _box(
            "Eltex", "ESR-200", DeviceRole.ROUTER, 1,
            (
                _p("gi1/0/{n}", 8, InterfaceType.RJ45, 1000, position=10),
                _p("sfp{n}", 4, InterfaceType.SFP, 1000, position=20),
            ),
            typical=30, maximum=80, weight=3,
        )
    )
    items.append(
        _box(
            "Eltex", "ESR-1000", DeviceRole.ROUTER, 1,
            (
                _p("gi1/0/{n}", 4, InterfaceType.RJ45, 1000, position=10),
                _p("xe1/0/{n}", 4, InterfaceType.SFP_PLUS, 10000, position=20),
            ),
            typical=60, maximum=150, weight=4,
        )
    )
    items.append(
        _box(
            "Eltex", "WLC-3200", DeviceRole.WLC, 1,
            (_p("gi1/0/{n}", 4, InterfaceType.RJ45, 1000, position=10),),
            typical=40, maximum=100, weight=4,
            extra="Контроллер точек доступа.",
        )
    )
    for model in ("WEP-2ac", "WEP-12ac", "WOP-2ac", "WEP-30L"):
        items.append(_ap("Eltex", model, 15))

    mikrotik = [
        ("CRS310-1G-5S-4S+", 1, 0, False, 15, 25),
        ("CRS317-1G-16S+", 1, 16, False, 25, 50),
        ("CRS326-24G-2S+", 24, 2, False, 20, 40),
        ("CRS326-24S+2Q+", 0, 24, False, 40, 70),
        ("CRS518-16XS-2XQ", 0, 16, False, 50, 90),
        ("RB4011iGS+", 10, 1, False, 20, 40),
        ("RB5009UG+S+", 8, 1, False, 15, 30),
        ("CCR2004-16G-2S+", 16, 2, False, 25, 50),
        ("CCR2116-12G-4S+", 13, 4, False, 40, 80),
        ("CCR2216-1G-12XS-2XQ", 1, 12, False, 70, 120),
    ]
    for model, copper, uplinks, poe, typical, maximum in mikrotik:
        role = DeviceRole.ROUTER if model.startswith(("RB", "CCR")) else DeviceRole.L2_SWITCH
        items.append(
            _sw(
                "MikroTik", model, copper, uplinks, poe=poe, role=role,
                typical=typical, maximum=maximum,
            )
        )
    items.append(
        _box(
            "MikroTik", "CRS354-48G-4S+2Q+RM", DeviceRole.L2_SWITCH, 1,
            (
                _p("ether{n}", 48, InterfaceType.RJ45, 1000, position=10),
                _p("sfp-sfpplus{n}", 4, InterfaceType.SFP_PLUS, 10000, position=20),
                _p("qsfpplus{n}", 2, InterfaceType.QSFP_PLUS, 40000, position=30),
            ),
            typical=40, maximum=60, psu=2, weight=4,
            extra="48× 1 Гбит/с, 4× 10 Гбит/с и 2× 40 Гбит/с.",
        )
    )
    items.append(
        _box(
            "MikroTik", "CRS354-48P-4S+2Q+RM", DeviceRole.L2_SWITCH, 1,
            (
                _p("ether{n}", 48, InterfaceType.RJ45, 1000, poe=True, position=10),
                _p("sfp-sfpplus{n}", 4, InterfaceType.SFP_PLUS, 10000, position=20),
                _p("qsfpplus{n}", 2, InterfaceType.QSFP_PLUS, 40000, position=30),
            ),
            typical=80, maximum=800, psu=1, weight=6,
            extra="48× PoE, 4× 10 Гбит/с и 2× 40 Гбит/с. Бюджет PoE около 700 Вт.",
        )
    )
    items.append(_ap("MikroTik", "cAP ax", 12))
    items.append(_ap("MikroTik", "hAP ax3", 15))
    items.append(
        _sw(
            "Cisco", "Catalyst 2960X-48FPS-L", 48, 4, poe=True, role=DeviceRole.L2_SWITCH,
            typical=60, maximum=800, uplink=InterfaceType.SFP, speed=1000, pattern="Gi1/0/{n}",
        )
    )
    items.append(
        _sw(
            "Cisco", "Catalyst 9200-48P", 48, 4, poe=True, role=DeviceRole.L3_SWITCH,
            typical=80, maximum=1000, pattern="Gi1/0/{n}",
        )
    )
    items.append(
        _sw(
            "Huawei", "S5735-L48T4X-A", 48, 4, poe=False, role=DeviceRole.L3_SWITCH,
            typical=50, maximum=150, pattern="GE1/0/{n}",
        )
    )
    items.append(
        _sw(
            "Aruba", "2930F-48G-PoE", 48, 4, poe=True, role=DeviceRole.L3_SWITCH,
            typical=70, maximum=500, uplink=InterfaceType.SFP, speed=1000, pattern="1/{n}",
        )
    )

    unifi_sw = [
        ("USW-24-PoE", 24, 2, True, 40, 400),
        ("USW-48-PoE", 48, 4, True, 60, 450),
        ("USW-Pro-24-PoE", 24, 2, True, 40, 400),
        ("USW-Pro-Max-24-PoE", 24, 2, True, 50, 400),
        ("USW-Aggregation", 0, 8, False, 30, 60),
        ("USW-Pro-Aggregation", 0, 28, False, 60, 100),
        ("USW-Flex", 5, 0, True, 5, 25),
    ]
    for model, copper, uplinks, poe, typical, maximum in unifi_sw:
        u = 0 if model == "USW-Flex" else 1
        spec = _sw(
            "Ubiquiti", model, copper, uplinks, poe=poe, role=DeviceRole.L2_SWITCH,
            typical=typical, maximum=maximum, pattern="Port {n}",
        )
        if u == 0:
            spec = ModelSpec(
                spec.manufacturer, spec.model, spec.default_role, 0, ports=spec.ports,
                psu_count=spec.psu_count, power_nameplate_w=spec.power_nameplate_w,
                power_max_w=spec.power_max_w, is_full_depth=False, notes=spec.notes,
            )
        items.append(spec)
    for model, watts in (
        ("U6-Lite", 13),
        ("U6+", 13),
        ("U6-LR", 18),
        ("U6-Enterprise", 22),
        ("U6-Mesh", 13),
        ("U7-Pro", 21),
        ("U7-Pro-Max", 25),
        ("U7-Lite", 13),
        ("UAP-AC-Pro", 9),
        ("UAP-AC-Lite", 6),
        ("UAP-nanoHD", 10),
    ):
        items.append(_ap("Ubiquiti", model, watts))
    items.append(
        _box(
            "Ubiquiti", "UDM-Pro", DeviceRole.FIREWALL, 1,
            (
                _p("Port {n}", 8, InterfaceType.RJ45, 1000, position=10),
                _p("SFP+ {n}", 2, InterfaceType.SFP_PLUS, 10000, position=20),
            ),
            typical=33, maximum=33, weight=3,
            extra="Шлюз и контроллер UniFi.",
        )
    )
    items.append(
        _box(
            "Ubiquiti", "UDM-SE", DeviceRole.FIREWALL, 1,
            (
                _p("Port {n}", 8, InterfaceType.RJ45, 1000, poe=True, position=10),
                _p("SFP+ {n}", 2, InterfaceType.SFP_PLUS, 10000, position=20),
            ),
            typical=40, maximum=180, weight=4,
            extra="Шлюз и контроллер UniFi, порты PoE.",
        )
    )
    items.append(
        _box(
            "Ubiquiti", "UDM-Pro-Max", DeviceRole.FIREWALL, 1,
            (
                _p("Port {n}", 8, InterfaceType.RJ45, 1000, position=10),
                _p("SFP+ {n}", 2, InterfaceType.SFP_PLUS, 10000, position=20),
            ),
            typical=50, maximum=60, weight=4,
            extra="Шлюз и контроллер UniFi.",
        )
    )
    items.append(
        _box(
            "Ubiquiti", "UXG-Pro", DeviceRole.FIREWALL, 1,
            (
                _p("Port {n}", 8, InterfaceType.RJ45, 1000, position=10),
                _p("SFP+ {n}", 2, InterfaceType.SFP_PLUS, 10000, position=20),
            ),
            typical=30, maximum=40, weight=3,
        )
    )
    items.append(
        ModelSpec(
            "Ubiquiti", "UCK-G2-PLUS", DeviceRole.WLC, 0,
            ports=(_p("eth0", 1, InterfaceType.RJ45, 1000),),
            power_nameplate_w=10, power_max_w=10, is_full_depth=False,
            notes=CATALOG_NOTE + " Контроллер UniFi Cloud Key, не стойка.",
        )
    )
    items.append(
        _box(
            "Ubiquiti", "UNVR", DeviceRole.STORAGE, 1,
            (_p("Port {n}", 1, InterfaceType.RJ45, 1000, position=10),),
            typical=30, maximum=50, bays=4, form="LFF",
            extra="Видеорегистратор UniFi Protect, 4 диска.",
        )
    )
    items.extend(
        [
            _fc("Broadcom", "Brocade G610", 24, 32000),
            _fc("Broadcom", "Brocade G620", 48, 32000),
            _fc("Broadcom", "Brocade G720", 64, 64000),
            _fc("Cisco", "MDS 9132T", 32, 32000),
            _fc("Cisco", "MDS 9148T", 48, 32000),
            _fc("Cisco", "MDS 9396T", 96, 32000, 2),
            _fc("HPE", "SN3600B", 24, 32000),
            _fc("HPE", "SN6600B", 128, 32000, 2),
            _fc("Huawei", "SNS2248", 48, 32000),
            _fc("Huawei", "SNS3664", 64, 64000),
        ]
    )
    return items


HARDWARE: tuple[ModelSpec, ...] = (
    *_servers(),
    *_components(),
    *_storage(),
    *_network(),
)
