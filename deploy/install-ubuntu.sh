#!/usr/bin/env bash
# Personal Finance AI — one-command install for Ubuntu Server
# Usage:
#   sudo bash deploy/install-ubuntu.sh
# Or after clone:
#   git clone https://github.com/ink1rk/buh.git && cd buh && sudo bash deploy/install-ubuntu.sh

set -euo pipefail

APP_NAME="personal-finance-ai"
REPO_URL="${REPO_URL:-https://github.com/ink1rk/buh.git}"
INSTALL_DIR="${INSTALL_DIR:-/opt/personal-finance-ai}"
APP_PORT="${APP_PORT:-80}"
BRANCH="${BRANCH:-main}"

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${CYAN}[PFA]${NC} $*"; }
ok()   { echo -e "${GREEN}[OK]${NC} $*"; }
die()  { echo -e "${RED}[ERR]${NC} $*"; exit 1; }

if [[ "${EUID}" -ne 0 ]]; then
  die "Запустите от root: sudo bash deploy/install-ubuntu.sh"
fi

export DEBIAN_FRONTEND=noninteractive

log "Обновляю систему..."
apt-get update -qq
apt-get install -y -qq ca-certificates curl git gnupg lsb-release ufw rsync openssl >/dev/null

if ! command -v docker >/dev/null 2>&1; then
  log "Ставлю Docker..."
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
  ok "Docker установлен"
else
  ok "Docker уже есть: $(docker --version)"
fi

# docker compose plugin
if ! docker compose version >/dev/null 2>&1; then
  log "Ставлю docker compose plugin..."
  apt-get install -y -qq docker-compose-plugin >/dev/null || true
fi
docker compose version >/dev/null 2>&1 || die "docker compose недоступен"

if [[ -d "${INSTALL_DIR}/.git" ]]; then
  log "Обновляю репозиторий в ${INSTALL_DIR}..."
  git -C "${INSTALL_DIR}" fetch --all --prune
  git -C "${INSTALL_DIR}" checkout "${BRANCH}"
  git -C "${INSTALL_DIR}" pull --ff-only origin "${BRANCH}" || true
else
  log "Клонирую ${REPO_URL} → ${INSTALL_DIR}"
  mkdir -p "$(dirname "${INSTALL_DIR}")"
  # If installer is already running from a local checkout, copy it
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
  if [[ -f "${REPO_ROOT}/docker-compose.prod.yml" ]]; then
    mkdir -p "${INSTALL_DIR}"
    rsync -a --delete \
      --exclude '.git' --exclude 'node_modules' --exclude 'frontend/dist' \
      --exclude 'backend/.venv' --exclude 'database/*.db' \
      "${REPO_ROOT}/" "${INSTALL_DIR}/"
  else
    git clone --branch "${BRANCH}" "${REPO_URL}" "${INSTALL_DIR}"
  fi
fi

cd "${INSTALL_DIR}"

if [[ ! -f .env ]]; then
  log "Создаю .env"
  if [[ -f .env.production.example ]]; then
    cp .env.production.example .env
  else
    cat > .env <<EOF
APP_PORT=${APP_PORT}
SECRET_KEY=$(openssl rand -hex 32)
OPENAI_API_KEY=
DEFAULT_USER_NAME=Кирилл
TIMEZONE=Europe/Moscow
EOF
  fi
  # Always rotate SECRET_KEY on first install
  if grep -q 'replace-with-long-random-string\|change-me' .env 2>/dev/null; then
    sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$(openssl rand -hex 32)/" .env
  fi
  if ! grep -q '^APP_PORT=' .env; then
    echo "APP_PORT=${APP_PORT}" >> .env
  else
    sed -i "s/^APP_PORT=.*/APP_PORT=${APP_PORT}/" .env
  fi
fi

# Optional OpenAI key from environment of the installer
if [[ -n "${OPENAI_API_KEY:-}" ]]; then
  if grep -q '^OPENAI_API_KEY=' .env; then
    sed -i "s|^OPENAI_API_KEY=.*|OPENAI_API_KEY=${OPENAI_API_KEY}|" .env
  else
    echo "OPENAI_API_KEY=${OPENAI_API_KEY}" >> .env
  fi
fi

log "Открываю порт ${APP_PORT} в UFW (если активен)..."
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
  ufw allow "${APP_PORT}/tcp" >/dev/null || true
fi

log "Собираю и запускаю контейнеры (это может занять несколько минут)..."
docker compose -f docker-compose.prod.yml --env-file .env pull || true
docker compose -f docker-compose.prod.yml --env-file .env build --pull
docker compose -f docker-compose.prod.yml --env-file .env up -d

# systemd unit for autostart on reboot
UNIT_PATH="/etc/systemd/system/${APP_NAME}.service"
cat > "${UNIT_PATH}" <<EOF
[Unit]
Description=Personal Finance AI
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${INSTALL_DIR}
ExecStart=/usr/bin/docker compose -f docker-compose.prod.yml --env-file .env up -d
ExecStop=/usr/bin/docker compose -f docker-compose.prod.yml --env-file .env down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "${APP_NAME}.service" >/dev/null

# Wait for health
log "Жду готовности сервиса..."
for i in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${APP_PORT}/health" >/dev/null 2>&1; then
    ok "Сервис отвечает на /health"
    break
  fi
  sleep 2
  if [[ "$i" -eq 60 ]]; then
    die "Сервис не поднялся. Смотрите: docker compose -f ${INSTALL_DIR}/docker-compose.prod.yml logs"
  fi
done

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
ok "Personal Finance AI установлен"
echo "  URL:      http://${IP:-ВАШ_IP}:${APP_PORT}"
echo "  Каталог:  ${INSTALL_DIR}"
echo "  Логи:     cd ${INSTALL_DIR} && docker compose -f docker-compose.prod.yml logs -f"
echo "  Стоп:     cd ${INSTALL_DIR} && docker compose -f docker-compose.prod.yml down"
echo "  Обновить: sudo bash ${INSTALL_DIR}/deploy/install-ubuntu.sh"
echo
echo "Опционально добавьте OPENAI_API_KEY в ${INSTALL_DIR}/.env и перезапустите:"
echo "  nano ${INSTALL_DIR}/.env"
echo "  cd ${INSTALL_DIR} && docker compose -f docker-compose.prod.yml up -d"
echo
