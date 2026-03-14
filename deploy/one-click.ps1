Param(
  [ValidateSet("Auto", "Docker", "Local")]
  [string]$Mode = "Auto"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
if (-not $env:HOME -and $HOME) {
  $env:HOME = $HOME
}
$RuntimeDir = Join-Path $HOME ".auraeve"
$EnvFile = Join-Path $ProjectDir ".env"
$EnvTemplate = Join-Path $ProjectDir ".env.docker.example"
$ConfigFile = Join-Path $RuntimeDir "auraeve.json"
$AppLog = Join-Path $ScriptDir "app.log"
$AppPidFile = Join-Path $ScriptDir "app.pid"

function Stop-LocalAppProcess {
  param(
    [string]$PidFile,
    [string]$PythonExe
  )

  if (Test-Path $PidFile) {
    $oldPid = (Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($oldPid) {
      $proc = Get-Process -Id $oldPid -ErrorAction SilentlyContinue
      if ($proc) {
        Write-Host "[one-click] stopping old app: pid=$oldPid"
        Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
      }
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
  }

  try {
    $escapedPy = [Regex]::Escape($PythonExe)
    $stale = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
      $_.CommandLine -match "$escapedPy.+-m\s+auraeve\s+run"
    }
    foreach ($proc in $stale) {
      Write-Host "[one-click] stopping stale app process: pid=$($proc.ProcessId)"
      Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    }
  } catch {
  }
}

function Stop-LocalDockerServices {
  param([string]$ProjectPath)
  Write-Host "[one-click] stopping previous docker services for clean restart (webui/backend)"
  Push-Location $ProjectPath
  try {
    docker compose stop webui backend | Out-Null
  } catch {
  }
  try {
    docker compose rm -f webui backend | Out-Null
  } catch {
  }
  Pop-Location
}

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

if (!(Test-Path $ConfigFile)) {
  Copy-Item (Join-Path $ProjectDir "auraeve/config.example.json") $ConfigFile -Force
  Write-Host "[one-click] initialized config: $ConfigFile"
}

if (!(Test-Path $EnvFile)) {
  Copy-Item $EnvTemplate $EnvFile -Force
  Write-Host "[one-click] initialized env: $EnvFile"
}

python -c @"
import json
from pathlib import Path
cfg = Path(r'$ConfigFile')
payload = json.loads(cfg.read_text(encoding='utf-8'))
cfg.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '`n', encoding='utf-8')
"@

$VenvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"
if (!(Test-Path $VenvPython)) {
  python -m venv (Join-Path $ProjectDir ".venv")
}
& $VenvPython -m pip install -q -r (Join-Path $ProjectDir "requirements.txt")

$hasDocker = $false
try {
  docker compose version | Out-Null
  $hasDocker = $true
} catch {
  $hasDocker = $false
}

if ($Mode -eq "Auto") {
  $Mode = "Local"
}
if ($Mode -eq "Docker" -and -not $hasDocker) {
  throw "docker mode requested but docker compose is unavailable"
}

if ($Mode -eq "Docker") {
  Push-Location $ProjectDir
  docker compose down
  docker compose up -d --build
  Pop-Location
  Write-Host "[one-click] done"
  Write-Host "  backend: http://127.0.0.1:18080"
  Write-Host "  webui:   http://127.0.0.1:18081"
  exit 0
}

if (-not $hasDocker) {
  throw "local mode requires Docker for webui container, but docker compose is unavailable"
}

$LocalBackendPort = 18780
if ($env:AURAEVE_WEBUI_BIND_PORT) {
  try {
    $LocalBackendPort = [int]$env:AURAEVE_WEBUI_BIND_PORT
  } catch {
    $LocalBackendPort = 18780
  }
}

Stop-LocalAppProcess -PidFile $AppPidFile -PythonExe $VenvPython
Stop-LocalDockerServices -ProjectPath $ProjectDir

Write-Host "[one-click] starting webui container (proxy -> host.docker.internal:$LocalBackendPort)"
Push-Location $ProjectDir
$env:AURAEVE_API_UPSTREAM = "host.docker.internal:$LocalBackendPort"
docker compose up -d --build --no-deps webui
Remove-Item Env:AURAEVE_API_UPSTREAM -ErrorAction SilentlyContinue
Pop-Location

$env:AURAEVE_WEBUI_BIND_PORT = "$LocalBackendPort"
$app = Start-Process -FilePath $VenvPython `
  -ArgumentList @("-m", "auraeve", "run") `
  -RedirectStandardOutput $AppLog `
  -RedirectStandardError $AppLog `
  -PassThru
Remove-Item Env:AURAEVE_WEBUI_BIND_PORT -ErrorAction SilentlyContinue
Set-Content -Path $AppPidFile -Value "$($app.Id)" -Encoding UTF8
Write-Host "[one-click] app started (local mode): pid=$($app.Id)"
