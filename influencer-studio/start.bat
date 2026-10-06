@echo off
rem Influencer Studio launcher for Windows. ComfyUI must already be running (default http://127.0.0.1:8188).
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Creating Python environment...
  py -3.12 -m venv .venv 2>nul || python -m venv .venv || goto :error
  ".venv\Scripts\python.exe" -m pip install --upgrade pip || goto :error
  ".venv\Scripts\python.exe" -m pip install -e backend || goto :error
)

if not exist "frontend\dist\index.html" (
  echo Building the web UI...
  pushd frontend
  call npm install || goto :error
  call npm run build || goto :error
  popd
)

".venv\Scripts\python.exe" -m studio
goto :eof

:error
echo.
echo Setup failed. Requirements: Python 3.11+ and Node.js 22+ on PATH.
pause
exit /b 1
