#!/usr/bin/env bash
# Lite VPS: native WireGuard + Telegram MTProto (mtg).
# Does NOT deploy the Personal Finance AI app and does not install HTTP/SOCKS proxies.
#
# Usage (as root):
#   sudo bash deploy/install-stack.sh

set -euo pipefail

WG_PORT="${WG_PORT:-51820}"
WG_NET="${WG_NET:-10.8.0.0/24}"
WG_SERVER_ADDR="${WG_SERVER_ADDR:-10.8.0.1/24}"
MTG_PORT="${MTG_PORT:-443}"
MTG_VERSION="${MTG_VERSION:-2.2.8}"
MTG_FRONT="${MTG_FRONT:-www.cloudflare.com}"

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'
log() { echo -e "${CYAN}[VPN]${NC} $*"; }
ok()  { echo -e "${GREEN}[OK]${NC} $*"; }
die() { echo -e "${RED}[ERR]${NC} $*"; exit 1; }

[[ "${EUID}" -eq 0 ]] || die "Запустите от root"

# Do not delete ourselves if launched from the app checkout
if [[ "${BASH_SOURCE[0]}" == /opt/personal-finance-ai/* ]]; then
  cp "${BASH_SOURCE[0]}" /root/install-vpn.sh
  exec bash /root/install-vpn.sh "$@"
fi

export DEBIAN_FRONTEND=noninteractive
export LC_ALL=C.UTF-8
export LANG=C.UTF-8

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PUBLIC_IP="${PUBLIC_IP:-$(curl -4 -fsS --max-time 8 https://ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')}"
WAN_IF="$(ip -4 route show default | awk '{print $5; exit}')"
[[ -n "${PUBLIC_IP}" && -n "${WAN_IF}" ]] || die "Нет PUBLIC_IP или WAN-интерфейса"

# --- strip this project's app and leftover proxies ---
log "Снимаю приложение проекта и лишние прокси..."
systemctl disable --now pfa.service 2>/dev/null || true
systemctl disable --now nginx 2>/dev/null || true
systemctl disable --now tinyproxy 2>/dev/null || true
systemctl disable --now microsocks 2>/dev/null || true
rm -f /etc/systemd/system/pfa.service \
      /etc/systemd/system/microsocks.service \
      /etc/nginx/sites-enabled/pfa.conf \
      /etc/nginx/sites-available/pfa.conf
systemctl daemon-reload
apt-get remove --purge -y nginx nginx-common nginx-core tinyproxy microsocks >/dev/null 2>&1 || true
rm -rf /opt/personal-finance-ai
ok "Приложение и HTTP/SOCKS сняты"

log "Пакеты..."
apt-get update -qq
apt-get install -y -qq \
  ca-certificates curl git openssl qrencode \
  wireguard wireguard-tools \
  ufw fail2ban iptables iproute2 \
  unattended-upgrades >/dev/null

# --- WireGuard lite (native wg-quick, no panel) ---
log "WireGuard lite..."
umask 077
mkdir -p /etc/wireguard /root/vpn-clients
if [[ ! -f /etc/wireguard/server.key ]]; then
  wg genkey | tee /etc/wireguard/server.key | wg pubkey > /etc/wireguard/server.pub
fi
SERVER_PRIV="$(cat /etc/wireguard/server.key)"
SERVER_PUB="$(cat /etc/wireguard/server.pub)"

make_peer() {
  local name="$1" addr="$2"
  if [[ ! -f "/etc/wireguard/${name}.key" ]]; then
    wg genkey | tee "/etc/wireguard/${name}.key" | wg pubkey > "/etc/wireguard/${name}.pub"
    wg genpsk > "/etc/wireguard/${name}.psk"
  fi
  local cpriv cpub cpsk
  cpriv="$(cat "/etc/wireguard/${name}.key")"
  cpub="$(cat "/etc/wireguard/${name}.pub")"
  cpsk="$(cat "/etc/wireguard/${name}.psk")"
  cat > "/root/vpn-clients/${name}-full.conf" <<EOF
[Interface]
PrivateKey = ${cpriv}
Address = ${addr}/24
DNS = 1.1.1.1, 8.8.8.8

[Peer]
PublicKey = ${SERVER_PUB}
PresharedKey = ${cpsk}
Endpoint = ${PUBLIC_IP}:${WG_PORT}
AllowedIPs = 0.0.0.0/0, ::/0
PersistentKeepalive = 25
EOF
  cat > "/root/vpn-clients/${name}-split.conf" <<EOF
[Interface]
PrivateKey = ${cpriv}
Address = ${addr}/24
DNS = 1.1.1.1

[Peer]
PublicKey = ${SERVER_PUB}
PresharedKey = ${cpsk}
Endpoint = ${PUBLIC_IP}:${WG_PORT}
AllowedIPs = 10.8.0.0/24
PersistentKeepalive = 25
EOF
  echo "${cpub} ${cpsk}"
}

laptop_meta="$(make_peer laptop 10.8.0.2)"
phone_meta="$(make_peer phone 10.8.0.3)"
laptop_pub="$(echo "${laptop_meta}" | awk '{print $1}')"
laptop_psk="$(echo "${laptop_meta}" | awk '{print $2}')"
phone_pub="$(echo "${phone_meta}" | awk '{print $1}')"
phone_psk="$(echo "${phone_meta}" | awk '{print $2}')"

cat > /etc/wireguard/wg0.conf <<EOF
[Interface]
Address = ${WG_SERVER_ADDR}
ListenPort = ${WG_PORT}
PrivateKey = ${SERVER_PRIV}
SaveConfig = false
PostUp = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -A FORWARD -o wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -s ${WG_NET} -o ${WAN_IF} -j MASQUERADE
PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -D FORWARD -o wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -s ${WG_NET} -o ${WAN_IF} -j MASQUERADE

[Peer]
PublicKey = ${laptop_pub}
PresharedKey = ${laptop_psk}
AllowedIPs = 10.8.0.2/32

[Peer]
PublicKey = ${phone_pub}
PresharedKey = ${phone_psk}
AllowedIPs = 10.8.0.3/32
EOF
chmod 600 /etc/wireguard/wg0.conf

cat > /etc/sysctl.d/99-vpn-lite.conf <<EOF
net.ipv4.ip_forward=1
net.core.default_qdisc=fq
net.ipv4.tcp_congestion_control=bbr
net.core.rmem_max=2500000
net.core.wmem_max=2500000
EOF
sysctl --system >/dev/null 2>&1 || sysctl -p /etc/sysctl.d/99-vpn-lite.conf >/dev/null
systemctl enable --now wg-quick@wg0
systemctl restart wg-quick@wg0
ok "WireGuard ${PUBLIC_IP}:${WG_PORT}/udp"

# --- Telegram MTProto (mtg FakeTLS) ---
log "Ставлю mtg ${MTG_VERSION}..."
tmp="$(mktemp -d)"
curl -fsSL "https://github.com/9seconds/mtg/releases/download/v${MTG_VERSION}/mtg-${MTG_VERSION}-linux-amd64.tar.gz" \
  -o "${tmp}/mtg.tgz"
tar -xzf "${tmp}/mtg.tgz" -C "${tmp}"
install -m 0755 "${tmp}/mtg" /usr/local/bin/mtg || install -m 0755 "${tmp}/mtg-${MTG_VERSION}-linux-amd64/mtg" /usr/local/bin/mtg
rm -rf "${tmp}"
id mtg >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin mtg
setcap cap_net_bind_service=+ep /usr/local/bin/mtg || true

if [[ ! -f /etc/mtg.toml ]]; then
  SECRET="$(/usr/local/bin/mtg generate-secret --hex "${MTG_FRONT}")"
  cat > /etc/mtg.toml <<EOF
secret = "${SECRET}"
bind-to = "0.0.0.0:${MTG_PORT}"
EOF
  chmod 640 /etc/mtg.toml
  chown root:mtg /etc/mtg.toml
fi

if [[ -f "${SCRIPT_DIR}/stack/mtg.service" ]]; then
  install -m 0644 "${SCRIPT_DIR}/stack/mtg.service" /etc/systemd/system/mtg.service
else
  cat > /etc/systemd/system/mtg.service <<EOF
[Unit]
Description=Telegram MTProto proxy (mtg)
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
User=mtg
Group=mtg
ExecStart=/usr/local/bin/mtg run /etc/mtg.toml
Restart=on-failure
RestartSec=2
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
MemoryMax=128M
[Install]
WantedBy=multi-user.target
EOF
fi
systemctl daemon-reload
systemctl enable --now mtg
systemctl restart mtg
sleep 1
systemctl is-active mtg >/dev/null || { journalctl -u mtg -n 40 --no-pager; die "mtg не поднялся"; }

/usr/local/bin/mtg access /etc/mtg.toml > /root/mtproto.txt 2>/dev/null || true
ok "MTProto :${MTG_PORT} (FakeTLS ${MTG_FRONT})"

# --- firewall: SSH + WG + MTProto only ---
log "UFW..."
sed -i 's/^DEFAULT_FORWARD_POLICY=.*/DEFAULT_FORWARD_POLICY="ACCEPT"/' /etc/default/ufw
sed -i 's|^#\?net/ipv4/ip_forward=.*|net/ipv4/ip_forward=1|' /etc/ufw/sysctl.conf 2>/dev/null || true
if ! grep -q 'PFA-WG-NAT\|VPN-WG-NAT' /etc/ufw/before.rules; then
  python3 - <<PY
from pathlib import Path
p = Path("/etc/ufw/before.rules")
block = """
# VPN-WG-NAT
*nat
:POSTROUTING ACCEPT [0:0]
-A POSTROUTING -s ${WG_NET} -o ${WAN_IF} -j MASQUERADE
COMMIT
"""
p.write_text(block + "\\n" + p.read_text())
PY
fi
ufw --force reset >/dev/null
sed -i 's/^DEFAULT_FORWARD_POLICY=.*/DEFAULT_FORWARD_POLICY="ACCEPT"/' /etc/default/ufw
if ! grep -q 'VPN-WG-NAT' /etc/ufw/before.rules; then
  python3 - <<PY
from pathlib import Path
p = Path("/etc/ufw/before.rules")
block = """
# VPN-WG-NAT
*nat
:POSTROUTING ACCEPT [0:0]
-A POSTROUTING -s ${WG_NET} -o ${WAN_IF} -j MASQUERADE
COMMIT
"""
p.write_text(block + "\\n" + p.read_text())
PY
fi
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw default allow routed >/dev/null || true
ufw allow OpenSSH >/dev/null
ufw allow "${WG_PORT}/udp" >/dev/null
ufw allow "${MTG_PORT}/tcp" >/dev/null
ufw route allow in on wg0 out on "${WAN_IF}" >/dev/null || true
ufw route allow in on "${WAN_IF}" out on wg0 >/dev/null || true
ufw --force enable >/dev/null
systemctl restart wg-quick@wg0
systemctl enable --now fail2ban >/dev/null 2>&1 || true
ok "Открыто: 22/tcp, ${WG_PORT}/udp, ${MTG_PORT}/tcp"

echo
ok "Готово — только WG lite + Telegram MTProto"
echo "  WireGuard:     ${PUBLIC_IP}:${WG_PORT}/udp"
echo "  Клиенты WG:    /root/vpn-clients/"
echo "  MTProto:       порт ${MTG_PORT}, ссылки в /root/mtproto.txt"
echo
cat /root/mtproto.txt 2>/dev/null || true
echo
echo "HTTP/SOCKS намеренно не ставились. Приложение этого репозитория на сервере нет."
echo
