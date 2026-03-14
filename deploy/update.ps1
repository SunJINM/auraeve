Param(
  [ValidateSet("Auto", "Docker", "Local")]
  [string]$Mode = "Auto"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
$VenvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"

Push-Location $ProjectDir
try {
  Write-Host "[update] pulling latest code..."
  git pull --rebase

  if (!(Test-Path $VenvPython)) {
    python -m venv (Join-Path $ProjectDir ".venv")
  }
  & $VenvPython -m pip install -q -r (Join-Path $ProjectDir "requirements.txt")

  Write-Host "[update] restarting services..."
  powershell -ExecutionPolicy Bypass -File (Join-Path $ScriptDir "one-click.ps1") -Mode $Mode
  Write-Host "[update] done"
} finally {
  Pop-Location
}

