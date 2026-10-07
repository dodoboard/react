@echo off
rem Influencer Studio launcher for Windows. ComfyUI must already be running (default http://127.0.0.1:8188).
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Creating Python environment...
  py -3.12 -m venv .venv 2>nul || python -m venv .venv || goto :error
  ".venv\Scripts\python.exe" -m pip install --upgrade pip || goto :error
)
rem Reinstall backend dependencies whenever backend\pyproject.toml changes (e.g. after git pull).
fc /b "backend\pyproject.toml" ".venv\pyproject.installed" >nul 2>&1 || (
  ".venv\Scripts\python.exe" -m pip install -e backend || goto :error
  copy /y "backend\pyproject.toml" ".venv\pyproject.installed" >nul
)

pushd frontend
fc /b "package-lock.json" "node_modules\.lock.installed" >nul 2>&1 || (
  call npm install || (popd & goto :error)
  copy /y "package-lock.json" "node_modules\.lock.installed" >nul
)
echo Building the web UI...
call npm run build || (popd & goto :error)
popd

".venv\Scripts\python.exe" -m studio
goto :eof

:error
echo.
echo Setup failed. Requirements: Python 3.11+ and Node.js 22+ on PATH.
pause
exit /b 1
