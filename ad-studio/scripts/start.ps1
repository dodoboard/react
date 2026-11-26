# AdForge — Windows başlatıcı. Kullanım:  powershell -ExecutionPolicy Bypass -File scripts\start.ps1 [-Dev]
param([switch]$Dev)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Check($name, $url) {
  try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 $url | Out-Null; Write-Host "[OK]  $name" -ForegroundColor Green }
  catch { Write-Host "[--]  $name ulaşılamıyor ($url)" -ForegroundColor Yellow }
}
foreach ($t in "ffmpeg", "python", "node") {
  if (-not (Get-Command $t -ErrorAction SilentlyContinue)) { Write-Host "$t bulunamadı. README > Kurulum." -ForegroundColor Red; exit 1 }
}
Check "Ollama"  "http://127.0.0.1:11434/api/tags"
Check "ComfyUI" "http://127.0.0.1:8188/system_stats"

if (-not (Test-Path "backend\.venv")) {
  python -m venv backend\.venv
  backend\.venv\Scripts\pip install -r backend\requirements.txt
}
if (-not (Test-Path ".env")) { Copy-Item .env.example .env }

if ($Dev) {
  Start-Process -NoNewWindow -FilePath "backend\.venv\Scripts\python.exe" -ArgumentList "-m","app.main" -WorkingDirectory "backend"
  Set-Location frontend; if (-not (Test-Path node_modules)) { npm install }; npm run dev
} else {
  if (-not (Test-Path "frontend\dist")) { Push-Location frontend; npm install; npm run build; Pop-Location }
  Start-Process "http://127.0.0.1:8000"
  Set-Location backend; .\.venv\Scripts\python.exe -m app.main
}
