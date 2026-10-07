#!/usr/bin/env bash
# One-time setup of the TTS server's own Python environment (separate from ComfyUI's).
set -euo pipefail
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install torch torchaudio --index-url "${TORCH_INDEX:-https://download.pytorch.org/whl/cu128}"
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install --no-deps chatterbox-tts==0.1.7
echo "TTS environment ready. Start it with tts/start.sh"
