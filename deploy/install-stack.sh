#!/usr/bin/env bash
# Personal Finance AI — full stack on a small Ubuntu VPS
# WireGuard + HTTP/SOCKS proxy (WG-only) + nginx + FastAPI
#
# Usage (from repo root, as root):
#   sudo bash deploy/install-stack.sh
#
# Optional:
#   PUBLIC_IP=1.2.3.4 WG_PORT=51820 APP_PORT=80 sudo bash deploy/install-stack.sh

set -euo pipefail

APP_NAME="personal-finance-ai"
INSTALL_DIR="${INSTALL_DIR:-/opt/personal-finance-ai}"
APP_PORT="${APP_PORT:-80}"
WG_PORT="${WG_PORT:-51820}"
WG_NET="${WG_NET:-10.8.0.0/24}"
WG_SERVER_ADDR="${WG_SERVER_ADDR:-10.8.0.1/24}"
HTTP_PROXY_PORT="${HTTP_PROXY_PORT:-3128}"
SOCKS_PORT="${SOCKS_PORT:-1080}"
BRANCH="${BRANCH:-main}"
REPO_URL="${REPO_URL:-https://github.com/ink1rk/buh.git}"

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

log() { echo -e "${CYAN}[STACK]${NC} $*"; }
ok()  { echo -e "${GREEN}[OK]${NC} $*"; }
die() { echo -e "${RED}[ERR]${NC} $*"; exit 1; }

if [[ "${EUID}" -ne 0 ]]; then
  die "Запустите от root: sudo bash deploy/install-stack.sh"
fi

export DEBIAN_FRONTEND=noninteractive
export LC_ALL=C.UTF-8
export LANG=C.UTF-8

PUBLIC_IP="${PUBLIC_IP:-}"
if [[ -z "${PUBLIC_IP}" ]]; then
  PUBLIC_IP="$(curl -4 -fsS --max-time 8 https://ifconfig.me 2>/dev/null || true)"
fi
if [[ -z "${PUBLIC_IP}" ]]; then
  PUBLIC_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
fi
[[ -n "${PUBLIC_IP}" ]] || die "Не удалось определить PUBLIC_IP"

WAN_IF="$(ip -4 route show default | awk '{print $5; exit}')"
[[ -n "${WAN_IF}" ]] || die "Не найден WAN-интерфейс"

ensure_swap() {
  local need_mb=2048
  local have_mb
  have_mb="$(awk '/SwapTotal/ {print int($2/1024)}' /proc/meminfo)"
  if [[ "${have_mb}" -ge 1500 ]]; then
    ok "Swap уже ${have_mb} MB"
    return
  fi
  log "Добавляю swap 2G (на VPS мало RAM)..."
  if [[ -f /swapfile-pfa ]]; then
    chmod 600 /swapfile-pfa
    swapon /swapfile-pfa 2>/dev/null || true
    return
  fi
  fallocate -l 2G /swapfile-pfa || dd if=/dev/zero of=/swapfile-pfa bs=1M count=2048
  chmod 600 /swapfile-pfa
  mkswap /swapfile-pfa >/dev/null
  swapon /swapfile-pfa
  if ! grep -q '/swapfile-pfa' /etc/fstab; then
    echo '/swapfile-pfa none swap sw 0 0' >> /etc/fstab
  fi
  ok "Swap включён"
}

log "Обновляю пакеты..."
apt-get update -qq
apt-get install -y -qq \
  ca-certificates curl git gnupg lsb-release ufw rsync openssl \
  wireguard wireguard-tools qrencode \
  nginx tinyproxy \
  python3 python3-venv python3-pip python3-dev \
  build-essential pkg-config libffi-dev \
  fail2ban \
  iproute2 iptables >/dev/null

if apt-get install -y -qq microsocks >/dev/null 2>&1; then
  SOCKS_BIN="/usr/bin/microsocks"
else
  log "microsocks нет в репозитории — собираю 3proxy SOCKS..."
  apt-get install -y -qq gcc make >/dev/null
  tmpdir="$(mktemp -d)"
  curl -fsSL https://github.com/3proxy/3proxy/archive/refs/tags/0.9.4.tar.gz | tar xz -C "${tmpdir}" --strip-components=1
  make -C "${tmpdir}" -f Makefile.Linux >/dev/null
  install -m 0755 "${tmpdir}/bin/3proxy" /usr/local/bin/3proxy
  rm -rf "${tmpdir}"
  SOCKS_BIN="3proxy"
fi

ensure_swap

# --- sync repo into INSTALL_DIR ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ "${REPO_ROOT}" == "${INSTALL_DIR}" ]]; then
  log "Уже в ${INSTALL_DIR}"
elif [[ -f "${REPO_ROOT}/docker-compose.prod.yml" ]]; then
  log "Копирую репозиторий → ${INSTALL_DIR}"
  mkdir -p "${INSTALL_DIR}"
  rsync -a --delete \
    --exclude '.git' --exclude 'node_modules' --exclude 'backend/.venv' \
    --exclude 'database/*.db' --exclude 'database/chroma' \
    "${REPO_ROOT}/" "${INSTALL_DIR}/"
elif [[ -d "${INSTALL_DIR}/.git" ]]; then
  git -C "${INSTALL_DIR}" fetch --all --prune
  git -C "${INSTALL_DIR}" checkout "${BRANCH}"
  git -C "${INSTALL_DIR}" pull --ff-only origin "${BRANCH}" || true
else
  git clone --branch "${BRANCH}" "${REPO_URL}" "${INSTALL_DIR}"
fi

cd "${INSTALL_DIR}"

# --- .env ---
if [[ ! -f .env ]]; then
  log "Создаю .env"
  SECRET_KEY="$(openssl rand -hex 32)"
  cat > .env <<EOF
APP_PORT=${APP_PORT}
SECRET_KEY=${SECRET_KEY}
DEBUG=false
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
VISION_MODEL=gpt-4o-mini
DEFAULT_USER_NAME=Кирилл
DEFAULT_CURRENCY=RUB
TIMEZONE=Europe/Moscow
DATA_DIR=${INSTALL_DIR}/database
EOF
fi
if [[ -n "${OPENAI_API_KEY:-}" ]]; then
  if grep -q '^OPENAI_API_KEY=' .env; then
    sed -i "s|^OPENAI_API_KEY=.*|OPENAI_API_KEY=${OPENAI_API_KEY}|" .env
  else
    echo "OPENAI_API_KEY=${OPENAI_API_KEY}" >> .env
  fi
fi
mkdir -p "${INSTALL_DIR}/database"
chown -R www-data:www-data "${INSTALL_DIR}/database"

# --- WireGuard ---
log "Настраиваю WireGuard :${WG_PORT}/udp..."
umask 077
mkdir -p /etc/wireguard /root/vpn-clients
if [[ ! -f /etc/wireguard/server.key ]]; then
  wg genkey | tee /etc/wireguard/server.key | wg pubkey > /etc/wireguard/server.pub
fi
SERVER_PRIV="$(cat /etc/wireguard/server.key)"
SERVER_PUB="$(cat /etc/wireguard/server.pub)"

make_peer() {
  local name="$1"
  local addr="$2"
  local keyfile="/etc/wireguard/${name}.key"
  local pubfile="/etc/wireguard/${name}.pub"
  local pskfile="/etc/wireguard/${name}.psk"
  if [[ ! -f "${keyfile}" ]]; then
    wg genkey | tee "${keyfile}" | wg pubkey > "${pubfile}"
    wg genpsk > "${pskfile}"
  fi
  local cpriv cpub cpsk
  cpriv="$(cat "${keyfile}")"
  cpub="$(cat "${pubfile}")"
  cpsk="$(cat "${pskfile}")"

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

  echo "${cpub} ${cpsk} ${addr}"
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
# laptop
PublicKey = ${laptop_pub}
PresharedKey = ${laptop_psk}
AllowedIPs = 10.8.0.2/32

[Peer]
# phone
PublicKey = ${phone_pub}
PresharedKey = ${phone_psk}
AllowedIPs = 10.8.0.3/32
EOF
chmod 600 /etc/wireguard/wg0.conf

cat > /etc/sysctl.d/99-pfa-forward.conf <<EOF
net.ipv4.ip_forward=1
net.ipv6.conf.all.forwarding=1
EOF
sysctl --system >/dev/null

systemctl enable --now wg-quick@wg0
ok "WireGuard слушает ${PUBLIC_IP}:${WG_PORT}"

# --- HTTP proxy (tinyproxy) ---
log "Настраиваю HTTP-прокси :${HTTP_PROXY_PORT} (только WG-клиенты)..."
install -m 0644 "${INSTALL_DIR}/deploy/stack/tinyproxy.conf" /etc/tinyproxy/tinyproxy.conf
sed -i "s/^Port .*/Port ${HTTP_PROXY_PORT}/" /etc/tinyproxy/tinyproxy.conf
mkdir -p /var/log/tinyproxy /run/tinyproxy
chown tinyproxy:tinyproxy /var/log/tinyproxy /run/tinyproxy 2>/dev/null || true
mkdir -p /etc/systemd/system/tinyproxy.service.d
cat > /etc/systemd/system/tinyproxy.service.d/override.conf <<EOF
[Unit]
After=wg-quick@wg0.service
EOF
systemctl daemon-reload
systemctl enable --now tinyproxy
systemctl restart tinyproxy
ok "HTTP proxy 10.8.0.1:${HTTP_PROXY_PORT}"

# --- SOCKS5 ---
log "Настраиваю SOCKS5 :${SOCKS_PORT}..."
if [[ "${SOCKS_BIN}" == "/usr/bin/microsocks" ]]; then
  install -m 0644 "${INSTALL_DIR}/deploy/stack/microsocks.service" /etc/systemd/system/microsocks.service
  sed -i "s/-p 1080/-p ${SOCKS_PORT}/" /etc/systemd/system/microsocks.service
  systemctl daemon-reload
  systemctl enable --now microsocks
  systemctl restart microsocks
  ok "SOCKS5 0.0.0.0:${SOCKS_PORT} (UFW пускает только 10.8.0.0/24)"
else
  cat > /etc/3proxy.cfg <<EOF
nscache 65536
timeouts 1 5 30 60 180 1800 15 60
users wg:CL:wg
auth none
allow * 10.8.0.0/24
socks -p${SOCKS_PORT} -i0.0.0.0
EOF
  cat > /etc/systemd/system/3proxy.service <<EOF
[Unit]
Description=3proxy SOCKS
After=wg-quick@wg0.service
[Service]
ExecStart=/usr/local/bin/3proxy /etc/3proxy.cfg
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable --now 3proxy
  ok "SOCKS5 via 3proxy :${SOCKS_PORT}"
fi

# --- Backend ---
log "Ставлю Python venv (это может занять несколько минут)..."
cd "${INSTALL_DIR}/backend"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip wheel setuptools >/dev/null
REQ_FILE="${INSTALL_DIR}/backend/requirements.prod.txt"
if [[ ! -f "${REQ_FILE}" ]]; then
  REQ_FILE="${INSTALL_DIR}/backend/requirements.txt"
fi
.venv/bin/pip install --no-cache-dir -r "${REQ_FILE}"

# --- Frontend ---
if [[ ! -f "${INSTALL_DIR}/frontend/dist/index.html" ]]; then
  if command -v npm >/dev/null 2>&1 || apt-get install -y -qq nodejs npm >/dev/null; then
    log "Собираю frontend..."
    cd "${INSTALL_DIR}/frontend"
    if [[ -f package-lock.json ]]; then npm ci; else npm install; fi
    npm run build
  else
    die "Нет frontend/dist и не удалось собрать. Положите dist на сервер и повторите."
  fi
fi
ok "Frontend dist готов"

install -m 0644 "${INSTALL_DIR}/deploy/stack/pfa.service" /etc/systemd/system/pfa.service
chown -R www-data:www-data "${INSTALL_DIR}/database"
# venv and code readable by www-data
chmod -R a+rX "${INSTALL_DIR}/backend" "${INSTALL_DIR}/frontend/dist" || true
chown -R root:root "${INSTALL_DIR}/backend"
chown -R www-data:www-data "${INSTALL_DIR}/database"
# allow www-data to read venv
chmod -R a+rX "${INSTALL_DIR}/backend/.venv"

systemctl daemon-reload
systemctl enable --now pfa.service
systemctl restart pfa.service

# --- nginx ---
log "Настраиваю nginx :${APP_PORT}..."
rm -f /etc/nginx/sites-enabled/default
install -m 0644 "${INSTALL_DIR}/deploy/stack/nginx.conf" /etc/nginx/sites-available/pfa.conf
if [[ "${APP_PORT}" != "80" ]]; then
  sed -i "s/listen 80/listen ${APP_PORT}/; s/listen \[::\]:80/listen [::]:${APP_PORT}/" /etc/nginx/sites-available/pfa.conf
fi
ln -sfn /etc/nginx/sites-available/pfa.conf /etc/nginx/sites-enabled/pfa.conf
nginx -t
systemctl enable --now nginx
systemctl reload nginx

# --- firewall ---
log "Включаю UFW..."
ufw --force reset >/dev/null
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow OpenSSH >/dev/null
ufw allow "${WG_PORT}/udp" >/dev/null
ufw allow "${APP_PORT}/tcp" >/dev/null
ufw allow from 10.8.0.0/24 to any port "${HTTP_PROXY_PORT}" proto tcp >/dev/null
ufw allow from 10.8.0.0/24 to any port "${SOCKS_PORT}" proto tcp >/dev/null
ufw --force enable >/dev/null
ok "UFW: 22/tcp, ${WG_PORT}/udp, ${APP_PORT}/tcp; proxy только из 10.8.0.0/24"

systemctl enable --now fail2ban >/dev/null 2>&1 || true

# --- wait for health ---
log "Жду backend /health..."
healthy=0
for i in $(seq 1 45); do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
    healthy=1
    break
  fi
  sleep 2
done
if [[ "${healthy}" -ne 1 ]]; then
  journalctl -u pfa.service -n 80 --no-pager || true
  die "Backend не поднялся"
fi
ok "Backend healthy"

echo
ok "Стек установлен"
echo "  App (публично):     http://${PUBLIC_IP}:${APP_PORT}"
echo "  App (через WG):     http://10.8.0.1/"
echo "  Health:             http://${PUBLIC_IP}:${APP_PORT}/health"
echo "  WireGuard:          ${PUBLIC_IP}:${WG_PORT}/udp"
echo "  HTTP proxy (WG):    10.8.0.1:${HTTP_PROXY_PORT}"
echo "  SOCKS5 (WG):        10.8.0.1:${SOCKS_PORT}"
echo "  Клиенты WG:         /root/vpn-clients/"
echo
echo "  full-tunnel = весь интернет через VPS"
echo "  split       = только 10.8.0.0/24 (приложение + прокси)"
echo
if command -v qrencode >/dev/null 2>&1; then
  echo "----- QR laptop-full -----"
  qrencode -t ansiutf8 < /root/vpn-clients/laptop-full.conf || true
fi
echo "Импорт: /root/vpn-clients/laptop-full.conf  и  phone-full.conf"
echo
