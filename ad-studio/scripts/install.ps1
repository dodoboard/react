# AdForge — Windows one-shot installer (base scope: Flux + upscaler + fonts + Ollama qwen3:14b, ~30 GB)
# Usage (PowerShell, from the ad-studio folder):
#   powershell -ExecutionPolicy Bypass -File scripts\install.ps1 [-ComfyDir C:\AI\ComfyUI_windows_portable] [-Full] [-SkipModels]
# Safe to re-run: every step checks before it installs/downloads.
param(
  [string]$ComfyDir = "C:\AI\ComfyUI_windows_portable",
  [switch]$Full,          # also Kontext, InfiniteTalk, Wan i2v (~65 GB more)
  [switch]$SkipModels,
  [string]$OllamaModel = "qwen3:14b"
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Have($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
function Refresh-Path {
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}
function Winget($id, $cmd) {
  if (Have $cmd) { Write-Host "  [ok] $cmd"; return }
  Write-Host "  [kur] $id"
  winget install --id $id -e --accept-source-agreements --accept-package-agreements --silent | Out-Host
  Refresh-Path
  if (-not (Have $cmd)) { throw "$id kuruldu ama '$cmd' PATH'te bulunamadı — yeni bir terminal açıp tekrar çalıştırın." }
}

Step "Donanım"
if (Have nvidia-smi) { nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader }
else { Write-Warning "nvidia-smi yok — NVIDIA sürücüsünü kurun (RTX 50 serisi için 570+)." }
$free = [math]::Round((Get-PSDrive (Split-Path -Qualifier $ComfyDir).TrimEnd(':')).Free / 1GB)
Write-Host "  $ComfyDir sürücüsünde boş alan: $free GB"
if ($free -lt 40) { Write-Warning "En az 40 GB önerilir (tam kurulum için 110 GB)." }

Step "Araçlar (winget)"
if (-not (Have winget)) { throw "winget yok — Microsoft Store'dan 'App Installer' kurun." }
Winget "Python.Python.3.12" "python"
Winget "OpenJS.NodeJS.LTS" "node"
Winget "Git.Git" "git"
Winget "Gyan.FFmpeg" "ffmpeg"
Winget "Ollama.Ollama" "ollama"
Winget "7zip.7zip" "7z"

Step "ComfyUI"
# Reuse an existing install (portable, desktop app or git clone): find its models folder.
function Find-Models($dir) {
  foreach ($c in @((Join-Path $dir "ComfyUI\models"), (Join-Path $dir "models"))) { if (Test-Path $c) { return (Resolve-Path $c).Path } }
  return $null
}
$comfyRunning = [bool](Get-NetTCPConnection -LocalPort 8188 -State Listen -ErrorAction SilentlyContinue)
$modelsDir = Find-Models $ComfyDir
if (-not $modelsDir) {
  foreach ($guess in @("$env:USERPROFILE\Documents\ComfyUI", "$env:LOCALAPPDATA\Programs\ComfyUI\resources\ComfyUI",
                       "C:\ComfyUI", "C:\ComfyUI_windows_portable", "D:\ComfyUI", "D:\ComfyUI_windows_portable",
                       "C:\AI\ComfyUI", "C:\AI\ComfyUI_windows_portable")) {
    if ($m = Find-Models $guess) { $ComfyDir = $guess; $modelsDir = $m; break }
  }
}
if ($comfyRunning -and -not $modelsDir) {
  throw "ComfyUI 8188'de çalışıyor ama models klasörü bulunamadı. -ComfyDir <ComfyUI klasörü> ile yolu verin."
}
$comfyPy = Join-Path $ComfyDir "python_embeded\python.exe"
$state = if ($comfyRunning) { " (çalışıyor)" } else { "" }
if ($modelsDir) { Write-Host "  [ok] mevcut ComfyUI: $modelsDir$state" }
elseif (-not (Test-Path $comfyPy)) {
  $parent = Split-Path -Parent $ComfyDir
  New-Item -ItemType Directory -Force -Path $parent | Out-Null
  $archive = Join-Path $parent "ComfyUI_windows_portable_nvidia.7z"
  if (-not (Test-Path $archive)) {
    Write-Host "  indiriliyor (~2 GB)…"
    Invoke-WebRequest "https://github.com/comfyanonymous/ComfyUI/releases/latest/download/ComfyUI_windows_portable_nvidia.7z" -OutFile $archive
  }
  & 7z x $archive "-o$parent" -y | Out-Null
  if (-not (Test-Path $comfyPy)) { throw "ComfyUI açılamadı: $archive" }
  $modelsDir = Find-Models $ComfyDir
}

Step "AdForge backend"
$venvPy = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { python -m venv backend\.venv }
& $venvPy -m pip install -q --upgrade pip
& $venvPy -m pip install -q -r backend\requirements.txt -r backend\requirements-youtube.txt
if (-not (Test-Path ".env")) { Copy-Item .env.example .env }
(Get-Content .env) -replace '^ADF_DRY_RUN=.*', 'ADF_DRY_RUN=0' | Set-Content .env

Step "AdForge arayüz"
Push-Location frontend
if (-not (Test-Path node_modules)) { npm install --no-audit --no-fund | Out-Host }
npm run build | Out-Host
Pop-Location

if (-not $SkipModels) {
  Step "Modeller ve fontlar"
  $only = if ($Full) { "flux,upscaler,fonts,kontext,wan-i2v,infinitetalk" } else { "flux,upscaler,fonts" }
  # setup_models skips files that already exist, so models you already have are not downloaded again
  & $venvPy scripts\setup_models.py --comfy (Split-Path -Parent $modelsDir) --only $only --skip-ollama
  Step "Ollama modeli: $OllamaModel"
  if (-not (Get-Process ollama -ErrorAction SilentlyContinue)) { Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden; Start-Sleep 3 }
  ollama pull $OllamaModel
}

Step "Varsayılan ayarlar (data\config.json)"
$cfgPath = Join-Path $root "data\config.json"
New-Item -ItemType Directory -Force -Path (Split-Path $cfgPath) | Out-Null
$cfg = if (Test-Path $cfgPath) { Get-Content $cfgPath -Raw | ConvertFrom-Json } else { [pscustomobject]@{} }
$set = @{ image_workflow = "flux_realism"; ollama_model = $OllamaModel; identity_lock = [bool]$Full; doc_i2v_ratio = $(if ($Full) { 0.25 } else { 0.0 }) }
foreach ($k in $set.Keys) { $cfg | Add-Member -NotePropertyName $k -NotePropertyValue $set[$k] -Force }
$cfg | ConvertTo-Json -Depth 5 | Set-Content $cfgPath -Encoding UTF8

Step "Başlatma"
$bat = Join-Path $ComfyDir "run_nvidia_gpu.bat"
if (-not (Get-NetTCPConnection -LocalPort 8188 -State Listen -ErrorAction SilentlyContinue) -and (Test-Path $bat)) {
  Start-Process -FilePath $bat -WorkingDirectory $ComfyDir -WindowStyle Minimized
}
if (-not (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)) {
  Start-Process -FilePath $venvPy -ArgumentList "-m", "app.main" -WorkingDirectory (Join-Path $root "backend") -WindowStyle Minimized
}
for ($i = 0; $i -lt 60; $i++) {
  try { Invoke-WebRequest http://127.0.0.1:8000/api/health -UseBasicParsing -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep 2 }
}
Start-Process "http://127.0.0.1:8000/doctor"
Write-Host "`nKurulum tamam. Açılan 'Sistem Durumu' sayfasında her şey yeşil olmalı." -ForegroundColor Green
Write-Host "ElevenLabs API anahtarını Ayarlar → Seslendirme'ye girin, sonra 'Gerçek testi çalıştır'."
