@echo off
rem Install ai-toolkit (LoRA training) next to the studio, in its own Python environment.
rem PyTorch comes from the CUDA 12.8 index: RTX 50-series (Blackwell) GPUs need it.
setlocal
cd /d "%~dp0.."
if not exist "ai-toolkit\run.py" (
  git clone --depth 1 https://github.com/ostris/ai-toolkit.git ai-toolkit || goto :error
)
cd ai-toolkit
if not exist "venv\Scripts\python.exe" (
  py -3.12 -m venv venv 2>nul || python -m venv venv || goto :error
)
"venv\Scripts\python.exe" -m pip install --upgrade pip || goto :error
"venv\Scripts\python.exe" -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128 || goto :error
"venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :error
echo.
echo ai-toolkit ready. Set STUDIO_COMFY_DIR to your ComfyUI folder, then use "Train LoRA" on a character page.
goto :eof

:error
echo Setup failed. Requirements: git and Python 3.11+ on PATH, an NVIDIA driver for CUDA 12.8.
pause
exit /b 1
