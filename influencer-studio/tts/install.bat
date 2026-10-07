@echo off
rem One-time setup of the TTS server's own Python environment (separate from ComfyUI's).
rem PyTorch comes from the CUDA 12.8 index: RTX 50-series (Blackwell) GPUs need torch 2.7 or newer.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv 2>nul || python -m venv .venv || goto :error
)
".venv\Scripts\python.exe" -m pip install --upgrade pip || goto :error
".venv\Scripts\python.exe" -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128 || goto :error
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :error
".venv\Scripts\python.exe" -m pip install --no-deps chatterbox-tts==0.1.7 || goto :error
echo.
echo TTS environment ready. Start it with tts\start.bat
goto :eof

:error
echo Setup failed. Requirements: Python 3.11+ on PATH and an NVIDIA driver for CUDA 12.8.
pause
exit /b 1
