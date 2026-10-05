#!/bin/sh
# Ставит Hermes на Ubuntu: финансы, ассистент, навыки и vault.
# Виртуалка pfa для этого больше не нужна.
# Запуск от root: bash hermes/deploy-host.sh
set -eu

REPO_URL="${REPO_URL:-https://github.com/ink1rk/buh.git}"
BRANCH="${BRANCH:-cursor/news-composition-and-prompt-d806}"
INSTALL_DIR="${INSTALL_DIR:-/opt/assistant}"
HERMES_USER="${HERMES_USER:-cursor}"

if [ "$(id -u)" -ne 0 ]; then
  echo "нужен root" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl git openssl sudo python3 python3-venv python3-pip libatomic1 >/dev/null

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker

if [ ! -d "${INSTALL_DIR}/.git" ]; then
  git clone --branch "${BRANCH}" "${REPO_URL}" "${INSTALL_DIR}"
else
  git -C "${INSTALL_DIR}" fetch origin "${BRANCH}"
  git -C "${INSTALL_DIR}" checkout "${BRANCH}"
  git -C "${INSTALL_DIR}" pull --ff-only origin "${BRANCH}"
fi

if ! id "${HERMES_USER}" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "${HERMES_USER}"
fi
usermod -aG docker "${HERMES_USER}" || true
chown -R "${HERMES_USER}:${HERMES_USER}" "${INSTALL_DIR}"

if [ ! -f /etc/finance.env ]; then
  MCP_TOKEN="$(openssl rand -hex 24)"
  SECRET_KEY="$(openssl rand -hex 32)"
  umask 077
  cat > /etc/finance.env <<EOF
APP_PORT=80
SECRET_KEY=${SECRET_KEY}
MCP_TOKEN=${MCP_TOKEN}
OPENAI_API_KEY=
DEFAULT_USER_NAME=Кирилл
TIMEZONE=Europe/Moscow
EOF
  chmod 600 /etc/finance.env
fi
# shellcheck disable=SC1091
. /etc/finance.env

cd "${INSTALL_DIR}"
docker compose -p finance -f docker-compose.prod.yml --env-file /etc/finance.env up -d --build

python3 -m venv "${INSTALL_DIR}/.venv"
"${INSTALL_DIR}/.venv/bin/pip" install -q -U pip
"${INSTALL_DIR}/.venv/bin/pip" install -q -r "${INSTALL_DIR}/assistant/requirements.txt"
chown -R "${HERMES_USER}:${HERMES_USER}" "${INSTALL_DIR}/.venv"

umask 077
cat > /etc/assistant.env <<EOF
ASSISTANT_DB=${INSTALL_DIR}/assistant.db
TZ_NAME=Europe/Moscow
OWNER_NAME=Кирилл
ASSISTANT_NAME=Джарвис
FINANCE_API=http://127.0.0.1/api/v1
TG_USER_URL=http://127.0.0.1:8810
TG_INGEST=0
NOTIFY=0
LLM_DEFAULT_PROVIDER=local
LLM_PRIVATE_PROVIDER=local
EXT_PROXY=
EOF
chown root:"${HERMES_USER}" /etc/assistant.env
chmod 640 /etc/assistant.env

install -m 644 "${INSTALL_DIR}/hermes/assistant.service" /etc/systemd/system/assistant.service
systemctl daemon-reload
systemctl enable --now assistant.service

# Бинарник Hermes — под пользователем, который им пользуется.
# С этой сети Vercel часто отвечает 403, поэтому запасной адрес — скрипт в GitHub.
if ! sudo -u "${HERMES_USER}" -H bash -lc 'command -v hermes' >/dev/null 2>&1; then
  if ! curl -fsSL -o /tmp/hermes-install.sh https://hermes-agent.nousresearch.com/install.sh; then
    curl -fsSL -o /tmp/hermes-install.sh https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh
  fi
  chmod 644 /tmp/hermes-install.sh
  sudo -u "${HERMES_USER}" -H bash -lc 'bash /tmp/hermes-install.sh --non-interactive'
fi

HERMES_HOME="/home/${HERMES_USER}/.hermes"
mkdir -p "${HERMES_HOME}"
chown "${HERMES_USER}:${HERMES_USER}" "${HERMES_HOME}"
sudo -u "${HERMES_USER}" -H env HERMES_HOME="${HERMES_HOME}" MCP_TOKEN="${MCP_TOKEN}" \
  sh "${INSTALL_DIR}/hermes/install.sh"
# install.sh не затирает уже созданный Hermes-ом config.yaml — кладём наш профиль.
cp "${INSTALL_DIR}/hermes/config.yaml" "${HERMES_HOME}/config.yaml"
sed -i "s|/opt/assistant/hermes/skills|${INSTALL_DIR}/hermes/skills|" "${HERMES_HOME}/config.yaml"
sed -i "s|Bearer \${MCP_TOKEN}|Bearer ${MCP_TOKEN}|" "${HERMES_HOME}/config.yaml"
umask 077
cat > "${HERMES_HOME}/.env" <<EOF
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=
ELEVENLABS_MODEL=eleven_multilingual_v2
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_USERS=
OBSIDIAN_VAULT_PATH=${INSTALL_DIR}/hermes/vault
ASSISTANT_URL=http://127.0.0.1:8800
FINANCE_API=http://127.0.0.1/api/v1
TG_USER_URL=http://127.0.0.1:8810
MCP_TOKEN=${MCP_TOKEN}
EOF
chown "${HERMES_USER}:${HERMES_USER}" "${HERMES_HOME}/config.yaml" "${HERMES_HOME}/.env"
chmod 600 "${HERMES_HOME}/.env"

MARKER='export PYTHONPATH=/opt/assistant/hermes${PYTHONPATH:+:$PYTHONPATH}'
BASHRC="/home/${HERMES_USER}/.bashrc"
grep -q 'PYTHONPATH=/opt/assistant/hermes' "${BASHRC}" 2>/dev/null || echo "${MARKER}" >> "${BASHRC}"
grep -q 'OBSIDIAN_VAULT_PATH=' "${BASHRC}" 2>/dev/null || echo "export OBSIDIAN_VAULT_PATH=${INSTALL_DIR}/hermes/vault" >> "${BASHRC}"
chown "${HERMES_USER}:${HERMES_USER}" "${BASHRC}"

echo "жду финансы и ассистента"
ok=0
i=0
while [ "$i" -lt 60 ]; do
  if curl -fsS http://127.0.0.1/health >/dev/null 2>&1 && curl -fsS http://127.0.0.1:8800/health >/dev/null 2>&1; then
    ok=1
    break
  fi
  i=$((i + 1))
  sleep 5
done
sudo -u "${HERMES_USER}" -H env \
  PYTHONPATH="${INSTALL_DIR}/hermes" \
  OBSIDIAN_VAULT_PATH="${INSTALL_DIR}/hermes/vault" \
  ASSISTANT_URL=http://127.0.0.1:8800 \
  FINANCE_API=http://127.0.0.1/api/v1 \
  python3 -m desk modules
if [ "$ok" -ne 1 ]; then
  echo "сервисы не ответили на /health" >&2
  exit 1
fi
echo "hermes готов: ${INSTALL_DIR}"
