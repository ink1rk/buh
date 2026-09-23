"""Типовые модели каталога.

Цифры — паспортные ориентиры для предзаполнения карточки, а не замер на объекте.
Ёмкость ИБП и номинал PDU сознательно не пишутся в мощность модели: сумма стойки
берёт power_nameplate_w как потребление, а не как отдаваемую мощность.
"""

from __future__ import annotations

from dataclasses import dataclass

from itms.models.enums import DeviceRole, InterfaceType

CATALOG_NOTE = "Типовые паспортные значения каталога, не замер на объекте."
CAPACITY_NOTE = (
    "Номинал выхода указан текстом и не входит в сумму стойки: это ёмкость, не потребление."
)


@dataclass(frozen=True, slots=True)
class PortSpec:
    name_pattern: str
    count: int
    interface_type: InterfaceType
    speed_mbps: int | None = None
    poe_capable: bool = False
    start_index: int = 1
    position: int = 100


@dataclass(frozen=True, slots=True)
class ModelSpec:
    manufacturer: str
    model: str
    default_role: DeviceRole
    u_height: float
    ports: tuple[PortSpec, ...] = ()
    psu_count: int = 1
    power_nameplate_w: int | None = None
    power_max_w: int | None = None
    weight_kg: float | None = None
    is_full_depth: bool = True
    notes: str = CATALOG_NOTE


def _p(
    pattern: str,
    count: int,
    kind: InterfaceType,
    speed: int | None = None,
    *,
    poe: bool = False,
    position: int = 100,
) -> PortSpec:
    return PortSpec(pattern, count, kind, speed, poe, 1, position)


def _server(vendor: str, model: str, u: float, typical: int, maximum: int) -> ModelSpec:
    return ModelSpec(
        vendor,
        model,
        DeviceRole.SERVER,
        u,
        ports=(
            _p("GbE{n}", 2, InterfaceType.RJ45, 1000, position=10),
            _p("SFP+{n}", 2, InterfaceType.SFP_PLUS, 10000, position=20),
            _p("iDRAC", 1, InterfaceType.RJ45, 1000, position=30),
        ),
        psu_count=2,
        power_nameplate_w=typical,
        power_max_w=maximum,
        weight_kg=26 if u >= 2 else 16,
    )


LIBRARY: tuple[ModelSpec, ...] = (
    ModelSpec(
        "Cisco",
        "Catalyst 9300-48P",
        DeviceRole.L3_SWITCH,
        1,
        ports=(
            _p("Gi1/0/{n}", 48, InterfaceType.RJ45, 1000, poe=True, position=10),
            _p("Te1/1/{n}", 4, InterfaceType.SFP_PLUS, 10000, position=20),
            _p("console", 1, InterfaceType.CONSOLE, position=30),
        ),
        psu_count=2,
        power_nameplate_w=180,
        power_max_w=1100,
        weight_kg=7.5,
    ),
    ModelSpec(
        "Cisco",
        "ISR 4331",
        DeviceRole.ROUTER,
        1,
        ports=(
            _p("Gi0/0/{n}", 3, InterfaceType.RJ45, 1000, position=10),
            _p("console", 1, InterfaceType.CONSOLE, position=20),
        ),
        power_nameplate_w=40,
        power_max_w=250,
        weight_kg=4,
    ),
    ModelSpec(
        "MikroTik",
        "CRS328-24P-4S+",
        DeviceRole.L2_SWITCH,
        1,
        ports=(
            _p("ether{n}", 24, InterfaceType.RJ45, 1000, poe=True, position=10),
            _p("sfp-sfpplus{n}", 4, InterfaceType.SFP_PLUS, 10000, position=20),
        ),
        power_nameplate_w=44,
        power_max_w=494,
        weight_kg=4,
    ),
    ModelSpec(
        "Eltex",
        "MES2424P",
        DeviceRole.L2_SWITCH,
        1,
        ports=(
            _p("gi1/0/{n}", 24, InterfaceType.RJ45, 1000, poe=True, position=10),
            _p("sfp{n}", 4, InterfaceType.SFP, 1000, position=20),
        ),
        power_nameplate_w=40,
        power_max_w=450,
        weight_kg=3.5,
    ),
    ModelSpec(
        "Huawei",
        "S5735-L48P4X-A",
        DeviceRole.L3_SWITCH,
        1,
        ports=(
            _p("GE1/0/{n}", 48, InterfaceType.RJ45, 1000, poe=True, position=10),
            _p("XGE1/0/{n}", 4, InterfaceType.SFP_PLUS, 10000, position=20),
        ),
        power_nameplate_w=80,
        power_max_w=900,
        weight_kg=5,
    ),
    ModelSpec(
        "Juniper",
        "EX4300-48P",
        DeviceRole.L3_SWITCH,
        1,
        ports=(
            _p("ge-0/0/{n}", 48, InterfaceType.RJ45, 1000, poe=True, position=10),
            _p("xe-0/2/{n}", 4, InterfaceType.SFP_PLUS, 10000, position=20),
        ),
        power_nameplate_w=120,
        power_max_w=900,
        weight_kg=7,
    ),
    ModelSpec(
        "Aruba",
        "6300M 48G PoE",
        DeviceRole.L3_SWITCH,
        1,
        ports=(
            _p("1/1/{n}", 48, InterfaceType.RJ45, 1000, poe=True, position=10),
            _p("1/2/{n}", 4, InterfaceType.SFP_PLUS, 10000, position=20),
        ),
        psu_count=2,
        power_nameplate_w=150,
        power_max_w=950,
        weight_kg=7,
    ),
    ModelSpec(
        "Fortinet",
        "FortiGate 200F",
        DeviceRole.FIREWALL,
        1,
        ports=(
            _p("port{n}", 16, InterfaceType.RJ45, 1000, position=10),
            _p("sfp{n}", 4, InterfaceType.SFP, 1000, position=20),
            _p("x{n}", 4, InterfaceType.SFP_PLUS, 10000, position=30),
        ),
        power_nameplate_w=40,
        power_max_w=120,
        weight_kg=3,
    ),
    ModelSpec(
        "Ubiquiti",
        "USW-Pro-48-PoE",
        DeviceRole.L2_SWITCH,
        1,
        ports=(
            _p("Port {n}", 48, InterfaceType.RJ45, 1000, poe=True, position=10),
            _p("SFP+ {n}", 4, InterfaceType.SFP_PLUS, 10000, position=20),
        ),
        power_nameplate_w=50,
        power_max_w=600,
        weight_kg=6,
    ),
    ModelSpec(
        "Ubiquiti",
        "U6-Pro",
        DeviceRole.ACCESS_POINT,
        0,
        ports=(_p("eth0", 1, InterfaceType.RJ45, 1000, poe=True),),
        power_nameplate_w=13,
        power_max_w=13,
        is_full_depth=False,
        notes=CATALOG_NOTE + " Нестоечная точка доступа.",
    ),
    _server("Dell", "PowerEdge R750", 2, 800, 1400),
    _server("HPE", "ProLiant DL380 Gen11", 2, 700, 1600),
    _server("Lenovo", "ThinkSystem SR650 V3", 2, 700, 1600),
    _server("Supermicro", "SYS-120U-TNR", 1, 400, 800),
    _server("Fujitsu", "PRIMERGY RX2540 M7", 2, 700, 1600),
    _server("Huawei", "FusionServer 2288H V6", 2, 700, 1600),
    ModelSpec(
        "HPE",
        "Alletra 5030",
        DeviceRole.STORAGE,
        2,
        ports=(
            _p("mgmt{n}", 2, InterfaceType.RJ45, 1000, position=10),
            _p("fc{n}", 4, InterfaceType.SFP_PLUS, 16000, position=20),
        ),
        psu_count=2,
        power_nameplate_w=400,
        power_max_w=800,
        weight_kg=30,
    ),
    ModelSpec(
        "Dell EMC",
        "PowerStore 500T",
        DeviceRole.STORAGE,
        2,
        ports=(
            _p("mgmt{n}", 2, InterfaceType.RJ45, 1000, position=10),
            _p("fc{n}", 4, InterfaceType.SFP_PLUS, 32000, position=20),
        ),
        psu_count=2,
        power_nameplate_w=400,
        power_max_w=800,
        weight_kg=32,
    ),
    ModelSpec(
        "NetApp",
        "AFF A250",
        DeviceRole.STORAGE,
        2,
        ports=(
            _p("e0{n}", 2, InterfaceType.RJ45, 1000, position=10),
            _p("fc{n}", 4, InterfaceType.SFP_PLUS, 16000, position=20),
        ),
        psu_count=2,
        power_nameplate_w=300,
        power_max_w=600,
        weight_kg=24,
    ),
    ModelSpec(
        "Huawei",
        "OceanStor 5310",
        DeviceRole.STORAGE,
        2,
        ports=(
            _p("mgmt{n}", 2, InterfaceType.RJ45, 1000, position=10),
            _p("fc{n}", 4, InterfaceType.SFP_PLUS, 16000, position=20),
        ),
        psu_count=2,
        power_nameplate_w=400,
        power_max_w=800,
        weight_kg=30,
    ),
    ModelSpec(
        "APC",
        "Smart-UPS SRT 5000",
        DeviceRole.UPS,
        3,
        psu_count=0,
        weight_kg=55,
        notes=CAPACITY_NOTE + " Ориентир выхода около 4500 Вт.",
    ),
    ModelSpec(
        "Eaton",
        "9PX 3000",
        DeviceRole.UPS,
        2,
        psu_count=0,
        weight_kg=28,
        notes=CAPACITY_NOTE + " Ориентир выхода около 2700 Вт.",
    ),
    ModelSpec(
        "Vertiv",
        "Geist rPDU",
        DeviceRole.PDU,
        0,
        psu_count=0,
        is_full_depth=False,
        notes=CAPACITY_NOTE + " Вертикальный PDU, ориентир ввода 32 А.",
    ),
    ModelSpec(
        "Dell",
        "OptiPlex 7010",
        DeviceRole.OTHER,
        0,
        ports=(_p("eth0", 1, InterfaceType.RJ45, 1000),),
        power_nameplate_w=65,
        power_max_w=180,
        is_full_depth=False,
        notes=CATALOG_NOTE + " Настольный компьютер, не стойка.",
    ),
    ModelSpec(
        "ASUS",
        "ExpertCenter D7",
        DeviceRole.OTHER,
        0,
        ports=(_p("eth0", 1, InterfaceType.RJ45, 1000),),
        power_nameplate_w=65,
        power_max_w=180,
        is_full_depth=False,
        notes=CATALOG_NOTE + " Настольный компьютер, не стойка.",
    ),
    ModelSpec(
        "HP",
        "Z2 Tower G9",
        DeviceRole.OTHER,
        0,
        ports=(_p("eth0", 1, InterfaceType.RJ45, 1000),),
        power_nameplate_w=90,
        power_max_w=260,
        is_full_depth=False,
        notes=CATALOG_NOTE + " Рабочая станция HP Inc, не сервер HPE.",
    ),
)
