@echo off
rem Influencer Studio TTS server (http://127.0.0.1:7870). Set TTS_DEVICE=cpu to keep the GPU free.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call install.bat || exit /b 1
rem Pick up new dependencies after a git pull (e.g. speech recognition for subtitles).
fc /b "requirements.txt" ".venv\requirements.installed" >nul 2>&1 || (
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || exit /b 1
  copy /y "requirements.txt" ".venv\requirements.installed" >nul
)
".venv\Scripts\python.exe" server.py
