#!/usr/bin/env bash
# Influencer Studio TTS server (http://127.0.0.1:7870). TTS_DEVICE=cpu keeps the GPU free.
set -euo pipefail
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || ./install.sh
# Pick up new dependencies after a git pull (e.g. speech recognition for subtitles).
if ! cmp -s requirements.txt .venv/requirements.installed; then
  .venv/bin/python -m pip install -r requirements.txt
  cp requirements.txt .venv/requirements.installed
fi
exec .venv/bin/python server.py
