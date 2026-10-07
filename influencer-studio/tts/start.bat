@echo off
rem Influencer Studio TTS server (http://127.0.0.1:7870). Set TTS_DEVICE=cpu to keep the GPU free.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call install.bat || exit /b 1
".venv\Scripts\python.exe" server.py
