#!/bin/bash
# Первый запуск appliance: секреты только в /opt/itms/deploy/.env и в локальном файле на консоли.
set -euo pipefail

deploy=/opt/itms/deploy
note=/root/itms-first-boot.txt

if [[ ! -f "$deploy/docker-compose.yml" ]]; then
  echo "Нет $deploy/docker-compose.yml" >&2
  exit 1
fi

if [[ ! -f "$deploy/.env" ]]; then
  cp "$deploy/.env.example" "$deploy/.env"
  python3 - "$deploy/.env" << 'PY'
import secrets, sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
replacements = {
    "POSTGRES_PASSWORD=": secrets.token_urlsafe(24),
    "S3_SECRET_KEY=": secrets.token_urlsafe(24),
    "OWNER_PASSWORD=": secrets.token_urlsafe(18),
}
lines = []
generated = {}
for line in text.splitlines():
    for key, value in replacements.items():
        if line.startswith(key):
            line = key + value
            generated[key[:-1]] = value
            break
    lines.append(line)
open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
open("/root/itms-first-boot.txt", "w", encoding="utf-8").write(
    "Пароль владельца ITMS (один показ, храните отдельно):\n"
    + generated.get("OWNER_PASSWORD", "")
    + "\n"
)
PY
  chmod 600 "$deploy/.env" "$note"
fi

cd "$deploy"
docker compose up -d
public=$(grep -E '^PUBLIC_URL=' .env | cut -d= -f2- || true)
echo "ITMS: ${public:-http://<адрес-сервера>/}"
if [[ -f "$note" ]]; then
  echo "Пароль владельца записан в $note"
fi
