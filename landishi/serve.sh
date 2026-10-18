#!/bin/sh
# Отдельный процесс только для сайта ТСН «Ландыши».
cd "$(dirname "$0")" || exit 1
PORT="${PORT:-8787}"
echo "Сайт: http://127.0.0.1:${PORT}"
exec python3 -m http.server "$PORT" --bind 0.0.0.0
