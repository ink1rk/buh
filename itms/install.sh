#!/bin/bash
# Установка ITMS на Ubuntu: Docker, пароли, контейнеры.
#   sudo bash install.sh          поднять систему
#   sudo bash install.sh passwd   задать новый временный пароль владельца
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  exec sudo bash "$0" "$@"
fi

ROOT="$(cd "$(dirname "$0")" && pwd)"
DEPLOY="${ROOT}/deploy"
ENV_FILE="${DEPLOY}/.env"
NOTE="/root/itms-install.txt"

die() {
  echo "$*" >&2
  exit 1
}

need_dns() {
  python3 - << 'PY'
import socket, sys
try:
    socket.getaddrinfo("archive.ubuntu.com", 443)
    socket.getaddrinfo("download.docker.com", 443)
except OSError:
    sys.exit(1)
PY
}

disable_cdrom_repo() {
  # После установки с ISO источник file:/cdrom остаётся, а диска уже нет.
  # apt-get update из-за него завершается с ошибкой и обрывает скрипт.
  local file
  shopt -s nullglob
  for file in /etc/apt/sources.list /etc/apt/sources.list.d/*; do
    [[ -f "${file}" ]] || continue
    sed -i '/cdrom/s/^deb /# deb /; /cdrom/s/^deb-src /# deb-src /' "${file}"
  done
  shopt -u nullglob
}

install_docker() {
  if docker compose version >/dev/null 2>&1; then
    return
  fi
  need_dns || die "Виртуалка не резолвит archive.ubuntu.com. Сначала настройте DNS, затем запустите скрипт снова."
  disable_cdrom_repo
  apt-get update
  apt-get install -y ca-certificates curl git
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
}

prepare_env() {
  FIRST_INSTALL=0
  if [[ ! -f "${ENV_FILE}" ]]; then
    cp "${DEPLOY}/.env.example" "${ENV_FILE}"
    FIRST_INSTALL=1
  fi
  python3 - "${ENV_FILE}" "${FIRST_INSTALL}" << 'PY'
import pathlib, secrets, socket, sys
path, created = sys.argv[1], sys.argv[2] == "1"
text = pathlib.Path(path).read_text(encoding="utf-8")
placeholders = {"", "смените-этот-пароль", "смените-этот-ключ"}

def host_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"

generated = {}
lines = []
for line in text.splitlines():
    if "=" not in line or line.lstrip().startswith("#"):
        lines.append(line)
        continue
    key, value = line.split("=", 1)
    if key in {"POSTGRES_PASSWORD", "S3_SECRET_KEY", "OWNER_PASSWORD"} and value in placeholders:
        value = secrets.token_urlsafe(18)
        generated[key] = value
        line = f"{key}={value}"
    if key == "PUBLIC_URL" and ("localhost" in value or "127.0.0.1" in value):
        port = "8080"
        for raw in text.splitlines():
            if raw.startswith("WEB_PORT="):
                port = raw.split("=", 1)[1] or port
        line = f"PUBLIC_URL=http://{host_ip()}:{port}"
    lines.append(line)
pathlib.Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
if created or generated:
    note = ["ITMS", ""]
    env = dict(line.split("=", 1) for line in lines if "=" in line and not line.startswith("#"))
    note.append(f"Адрес: {env.get('PUBLIC_URL', '')}")
    note.append(f"Почта: {env.get('OWNER_EMAIL', 'owner@itms.local')}")
    note.append(f"Временный пароль: {env.get('OWNER_PASSWORD', '')}")
    note.append("")
    note.append("При первом входе система попросит задать свой пароль.")
    pathlib.Path("/root/itms-install.txt").write_text("\n".join(note) + "\n", encoding="utf-8")
    print("fresh")
else:
    print("existing")
PY
  chmod 600 "${ENV_FILE}" "${NOTE}" 2>/dev/null || chmod 600 "${ENV_FILE}"
}

use_current_storage_images() {
  sed -i \
    -e 's#quay.io/minio/minio:latest#pgsty/silo:latest#' \
    -e 's#quay.io/minio/mc:latest#pgsty/silo:latest#' \
    "${DEPLOY}/docker-compose.yml"
}

wait_api() {
  local i state
  echo "Жду, пока API начнёт отвечать..."
  for i in $(seq 1 40); do
    if timeout 8 docker compose exec -T api python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" >/dev/null 2>&1; then
      return 0
    fi
    state="$(docker inspect -f '{{.State.Status}}' itms-api-1 2>/dev/null || true)"
    if [[ "${state}" == "restarting" || "${state}" == "exited" ]]; then
      echo "API не запустился (${state}). Журнал:" >&2
      docker compose logs --tail 80 api >&2 || true
      return 1
    fi
    sleep 3
  done
  echo "API ещё не ответил. Журнал:" >&2
  docker compose logs --tail 80 api >&2 || true
  return 1
}

# Вход через nginx: ответ API должен быть JSON, а не HTML-страница 502.
verify_login_proxy() {
  python3 - "${ENV_FILE}" << 'PY'
import json, pathlib, sys, urllib.error, urllib.request
env = {}
for line in pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        key, value = line.split("=", 1)
        env[key] = value
port = env.get("WEB_PORT") or "8080"
url = f"http://127.0.0.1:{port}/api/v1/auth/login"
body = json.dumps({"email": "nobody@itms.local", "password": "wrong-password"}).encode()
req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        status, raw = resp.status, resp.read()
except urllib.error.HTTPError as exc:
    status, raw = exc.code, exc.read()
except OSError as exc:
    print(f"Веб-интерфейс не отвечает: {exc}", file=sys.stderr)
    raise SystemExit(1)
text = raw.decode("utf-8", "replace")
if not text.lstrip().startswith("{") or status != 401 or "invalid_credentials" not in text:
    print(f"Вход через веб не дошёл до API (HTTP {status}).", file=sys.stderr)
    print(text[:400], file=sys.stderr)
    raise SystemExit(1)
print("Вход через веб отвечает JSON.")
PY
}

reset_password() {
  local new="${1:-}"
  cd "${DEPLOY}"
  if [[ -z "${new}" ]]; then
    read -r -s -p "Новый временный пароль (пусто — сгенерировать): " new
    echo
  fi
  if [[ -z "${new}" ]]; then
    new="$(python3 -c 'import secrets; print(secrets.token_urlsafe(12))')"
  fi
  local output status
  set +e
  output="$(docker compose exec -T -e ITMS_NEW_PASSWORD="${new}" api python -m itms.cli set-password 2>&1)"
  status=$?
  set -e
  if [[ "${status}" -eq 0 ]]; then
    printf '%s\n' "${output}"
    return 0
  fi
  if [[ "${output}" != *"Команды:"* ]]; then
    printf '%s\n' "${output}" >&2
    exit 1
  fi
  # Старый образ ещё без команды set-password: пароль меняется тем же способом напрямую.
  docker compose exec -T -e ITMS_NEW_PASSWORD="${new}" api python - << 'PY'
import asyncio, os, sys
from sqlalchemy import text
from itms.core.db import dispose_engine, session_scope
from itms.core.security import hash_password, password_problems

new = os.environ["ITMS_NEW_PASSWORD"]
problems = password_problems(new)
if problems:
    print("Пароль не подходит: не короче 10 символов, нужны буквы и цифра", file=sys.stderr)
    raise SystemExit(1)

async def main() -> None:
    async with session_scope() as session:
        hashed = hash_password(new)
        has_flag = (
            await session.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = 'user_account' AND column_name = 'must_change_password'"
                )
            )
        ).first()
        if has_flag:
            await session.execute(
                text(
                    "UPDATE user_account SET password_hash = :hashed, failed_login_count = 0, "
                    "must_change_password = true WHERE role = 'OWNER'"
                ),
                {"hashed": hashed},
            )
        else:
            await session.execute(
                text(
                    "UPDATE user_account SET password_hash = :hashed, failed_login_count = 0 "
                    "WHERE role = 'OWNER'"
                ),
                {"hashed": hashed},
            )
        email = (
            await session.execute(text("SELECT email FROM user_account WHERE role = 'OWNER'"))
        ).scalar_one()
        print(f"Вход: {email}")
        print(f"Временный пароль: {new}")
    await dispose_engine()

asyncio.run(main())
PY
}

cd "${DEPLOY}"
install_docker
use_current_storage_images

case "${1:-up}" in
  passwd)
    reset_password "${2:-}"
    ;;
  up|"")
    install_mode="$(prepare_env)"
    echo "Собираю и запускаю контейнеры. Первая сборка занимает несколько минут."
    if ! docker compose up -d --build; then
      echo "Стек не поднялся. Журнал API:" >&2
      docker compose ps >&2 || true
      docker compose logs --tail 80 api >&2 || true
      exit 1
    fi
    wait_api
    verify_login_proxy
    echo
    docker compose ps
    echo
    if [[ "${install_mode}" == "fresh" && -f "${NOTE}" ]]; then
      cat "${NOTE}"
      echo
      echo "Пароль также записан в ${NOTE}"
    else
      echo "ITMS запущен. Пароль владельца уже был задан раньше."
      echo "Сменить его: sudo bash ${ROOT}/install.sh passwd"
    fi
    ;;
  *)
    die "Неизвестная команда. Используйте: install.sh  или  install.sh passwd"
    ;;
esac
