#!/usr/bin/env bash
# 开发模式：后端 8123 热更新 + 前端 Vite 5173
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8123}"

trap 'kill 0' EXIT INT TERM

(cd "$ROOT/backend" && uv run uvicorn app.main:app --reload --host 127.0.0.1 --port "$BACKEND_PORT") &
(cd "$ROOT/frontend" && npm run dev) &

echo ""
echo "前端：http://localhost:5173"
echo "后端：http://127.0.0.1:${BACKEND_PORT}"
echo "按 Ctrl+C 停止服务"
echo ""

wait
