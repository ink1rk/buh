#!/bin/sh
# Публичный HTTPS для уже запущенного сайта.
# Сначала: ./serve.sh
# Адрес вида https://….trycloudflare.com появится в выводе.
cd "$(dirname "$0")" || exit 1
PORT="${PORT:-8787}"
exec cloudflared tunnel --url "http://127.0.0.1:${PORT}" --no-autoupdate
