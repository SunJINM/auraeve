Param(
  [ValidateSet("Auto", "Docker", "Local")]
  [string]$Mode = "Auto"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
$AppPidFile = Join-Path $ScriptDir "app.pid"
$VenvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"

function Stop-LocalAppProcess {
  param(
    [string]$PidFile,
    [string]$PythonExe
  )

  if (Test-Path $PidFile) {
    $oldPid = (Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($oldPid -and ($oldPid -as [int])) {
      $proc = Get-Process -Id ([int]$oldPid) -ErrorAction SilentlyContinue
      if ($proc) {
        Write-Host "[stop] stopping app from pid file: pid=$oldPid"
        Stop-Process -Id ([int]$oldPid) -Force -ErrorAction SilentlyContinue
      }
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
  }

  try {
    $patterns = @()
    if ($PythonExe) {
      $escapedPy = [Regex]::Escape($PythonExe)
      $patterns += "$escapedPy.+-m\s+auraeve\s+run"
    }
    $patterns += "-m\s+auraeve\s+run"

    $stale = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
      $cmd = $_.CommandLine
      if (-not $cmd) { return $false }
      foreach ($p in $patterns) {
        if ($cmd -match $p) { return $true }
      }
      return $false
    }

    foreach ($proc in $stale) {
      Write-Host "[stop] stopping local app process: pid=$($proc.ProcessId)"
      Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    }
  } catch {
  }
}

function Stop-DockerServices {
  param([string]$ProjectPath)
  Push-Location $ProjectPath
  try {
    Write-Host "[stop] stopping docker compose services (webui/backend)"
    docker compose stop webui backend | Out-Null
  } catch {
  }
  try {
    docker compose rm -f webui backend | Out-Null
  } catch {
  }
  try {
    $all = docker compose ps -q 2>$null
    if ($all) {
      Write-Host "[stop] docker compose down"
      docker compose down | Out-Null
    }
  } catch {
  }
  Pop-Location
}

$hasDocker = $false
try {
  docker compose version | Out-Null
  $hasDocker = $true
} catch {
  $hasDocker = $false
}

if ($Mode -eq "Auto") {
  if ($hasDocker) {
    Stop-DockerServices -ProjectPath $ProjectDir
  }
  Stop-LocalAppProcess -PidFile $AppPidFile -PythonExe $VenvPython
  Write-Host "[stop] done (auto)"
  exit 0
}

if ($Mode -eq "Docker") {
  if (-not $hasDocker) {
    throw "docker compose is unavailable"
  }
  Stop-DockerServices -ProjectPath $ProjectDir
  Write-Host "[stop] done (docker)"
  exit 0
}

Stop-LocalAppProcess -PidFile $AppPidFile -PythonExe $VenvPython
Write-Host "[stop] done (local)"
