#!/usr/bin/env bash
# Influencer Studio launcher for Linux/macOS/WSL. ComfyUI must already be running.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -e backend
fi

if [ ! -f frontend/dist/index.html ]; then
  (cd frontend && npm install && npm run build)
fi

exec .venv/bin/python -m studio "$@"
