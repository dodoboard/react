#!/usr/bin/env bash
# Install ai-toolkit (LoRA training) next to the studio, in its own Python environment.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f ai-toolkit/run.py ] || git clone --depth 1 https://github.com/ostris/ai-toolkit.git ai-toolkit
cd ai-toolkit
[ -x venv/bin/python ] || python3 -m venv venv
venv/bin/python -m pip install --upgrade pip
venv/bin/python -m pip install torch torchvision torchaudio --index-url "${TORCH_INDEX:-https://download.pytorch.org/whl/cu128}"
venv/bin/python -m pip install -r requirements.txt
echo "ai-toolkit ready. Set STUDIO_COMFY_DIR to your ComfyUI folder, then use Train LoRA on a character page."
