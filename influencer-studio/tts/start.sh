#!/usr/bin/env bash
# Influencer Studio TTS server (http://127.0.0.1:7870). TTS_DEVICE=cpu keeps the GPU free.
set -euo pipefail
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || ./install.sh
exec .venv/bin/python server.py
