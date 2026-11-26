#!/usr/bin/env bash
# AdForge — Linux/macOS başlatıcı. Kullanım: scripts/start.sh [--dev]
set -euo pipefail
cd "$(dirname "$0")/.."
for t in ffmpeg python3 node; do command -v $t >/dev/null || { echo "$t bulunamadı"; exit 1; }; done
curl -sf -m 2 http://127.0.0.1:11434/api/tags >/dev/null && echo "[OK] Ollama" || echo "[--] Ollama ulaşılamıyor"
curl -sf -m 2 http://127.0.0.1:8188/system_stats >/dev/null && echo "[OK] ComfyUI" || echo "[--] ComfyUI ulaşılamıyor"
[ -d backend/.venv ] || { python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt; }
[ -f .env ] || cp .env.example .env
if [ "${1:-}" = "--dev" ]; then
  (cd backend && .venv/bin/python -m app.main) &
  cd frontend && { [ -d node_modules ] || npm install; } && npm run dev
else
  [ -d frontend/dist ] || (cd frontend && npm install && npm run build)
  cd backend && exec .venv/bin/python -m app.main
fi
