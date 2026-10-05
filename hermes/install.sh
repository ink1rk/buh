#!/bin/sh
# Кладёт навыки и vault в профиль Hermes. Сам Hermes не скачивает:
# установка бинарника — отдельный шаг с сайта Nous Research.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
HOME_DIR=${HERMES_HOME:-"$HOME/.hermes"}
mkdir -p "$HOME_DIR/skills"
for skill in desk mail calendar finance obsidian browser telegram voice; do
  ln -sfn "$ROOT/skills/$skill" "$HOME_DIR/skills/$skill"
done
if [ ! -f "$HOME_DIR/config.yaml" ]; then
  cp "$ROOT/config.yaml" "$HOME_DIR/config.yaml"
  if [ -n "${MCP_TOKEN:-}" ]; then
    # В yaml Hermes не всегда раскрывает переменные в заголовках MCP.
    sed -i "s|Bearer \${MCP_TOKEN}|Bearer ${MCP_TOKEN}|" "$HOME_DIR/config.yaml"
  fi
fi
if [ ! -f "$HOME_DIR/.env" ]; then
  cp "$ROOT/env.example" "$HOME_DIR/.env"
  chmod 600 "$HOME_DIR/.env"
fi
mkdir -p "$ROOT/vault/00 Inbox" "$ROOT/vault/01 Daily" "$ROOT/vault/02 Finance" "$ROOT/vault/03 People"
echo "навыки: $HOME_DIR/skills"
echo "vault: ${OBSIDIAN_VAULT_PATH:-$ROOT/vault}"
if ! command -v hermes >/dev/null 2>&1; then
  echo "бинарника hermes нет. Поставить с https://hermes-agent.nousresearch.com/docs/getting-started/installation и затем: hermes model, hermes gateway setup"
fi
