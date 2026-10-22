#!/usr/bin/env bash
# 生产模式启动：安装依赖 -> 构建前端（如缺失）-> 单端口运行
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-8123}"

cd "$ROOT/backend"
uv sync

if [ ! -d "$ROOT/frontend/dist" ]; then
  echo "未找到前端构建产物，开始构建..."
  cd "$ROOT/frontend"
  npm install
  npm run build
fi

echo ""
echo "条漫工作台已启动：http://127.0.0.1:${PORT}"
echo "按 Ctrl+C 停止服务"
echo ""

cd "$ROOT/backend"
exec uv run uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
