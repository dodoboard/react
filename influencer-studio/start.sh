#!/usr/bin/env bash
# Influencer Studio launcher for Linux/macOS/WSL. ComfyUI must already be running.
set -euo pipefail
cd "$(dirname "$0")"

[ -x .venv/bin/python ] || { python3 -m venv .venv && .venv/bin/python -m pip install --upgrade pip; }
# Reinstall backend dependencies whenever backend/pyproject.toml changes (e.g. after git pull).
if ! cmp -s backend/pyproject.toml .venv/pyproject.installed; then
  .venv/bin/python -m pip install -e backend
  cp backend/pyproject.toml .venv/pyproject.installed
fi

(
  cd frontend
  if ! cmp -s package-lock.json node_modules/.lock.installed; then
    npm install
    cp package-lock.json node_modules/.lock.installed
  fi
  npm run build
)

exec .venv/bin/python -m studio "$@"
