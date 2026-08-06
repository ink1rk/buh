#!/usr/bin/env bash
# Update Personal Finance AI on Ubuntu Server
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/personal-finance-ai}"
cd "${INSTALL_DIR}"

echo "[PFA] Pulling latest..."
if [[ -d .git ]]; then
  git pull --ff-only || true
fi

echo "[PFA] Rebuilding..."
docker compose -f docker-compose.prod.yml --env-file .env build
docker compose -f docker-compose.prod.yml --env-file .env up -d

echo "[PFA] Done. Health:"
curl -fsS "http://127.0.0.1:${APP_PORT:-80}/health" || true
echo
