#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

source "$ROOT/backend/.venv/bin/activate"
export PYTHONPATH="$ROOT/backend"

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --app-dir "$ROOT/backend" &
BACK_PID=$!

cd "$ROOT/frontend"
npm run dev -- --host 0.0.0.0 --port 5173 &
FRONT_PID=$!

trap 'kill $BACK_PID $FRONT_PID 2>/dev/null || true' EXIT
wait
