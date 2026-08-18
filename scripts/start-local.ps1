$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$backendDir = Join-Path $repoRoot 'backend'
$frontendDir = Join-Path $repoRoot 'artifacts\xray-academy'
$dbFile = Join-Path $backendDir 'xray_local.db'
$dbUrl = ('sqlite:///' + ($dbFile -replace '\\', '/'))

function Stop-PortListeners {
  param([int[]]$Ports)

  foreach ($port in $Ports) {
    $pids = @()
    $lines = netstat -ano | Select-String ":$port"
    foreach ($line in $lines) {
      $parts = ($line -replace '\s+', ' ').Trim().Split(' ')
      if ($parts.Length -ge 5 -and $parts[0] -eq 'TCP' -and $parts[3] -eq 'LISTENING') {
        $procId = 0
        if ([int]::TryParse($parts[4], [ref]$procId)) {
          $pids += $procId
        }
      }
    }

    $pids | Sort-Object -Unique | ForEach-Object {
      taskkill /PID $_ /F *> $null
    }
  }
}

Stop-PortListeners -Ports @(5173, 8000)

Write-Host "Using repository: $repoRoot"
Write-Host "Using database:   $dbFile"

$backendCmd = "cd /d `"$backendDir`" && set DATABASE_URL=$dbUrl && set OLLAMA_BASE_URL=http://127.0.0.1:11434 && set OLLAMA_MODEL=qwen2.5-7b-fast6:latest && set DEVELOPMENT_MODE=true && set DISABLE_TRANSLATION_RATE_LIMIT=true && set DISABLE_HOURLY_QUOTA=true && set DISABLE_DAILY_QUOTA=true && set DISABLE_MONTHLY_QUOTA=true && set LOCAL_DEVELOPER_USER_IDS=dev-user-local && if exist .venv\Scripts\python.exe (.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000) else (python -m uvicorn main:app --host 127.0.0.1 --port 8000)"
$frontendCmd = "cd /d `"$frontendDir`" && set FRONTEND_PORT=5173 && set PORT=5173 && set BASE_PATH=/ && .\node_modules\.bin\vite.cmd --config vite.config.ts --host 0.0.0.0 --strictPort"

Start-Process -FilePath 'cmd.exe' -ArgumentList '/k', $backendCmd -WindowStyle Normal
Start-Process -FilePath 'cmd.exe' -ArgumentList '/k', $frontendCmd -WindowStyle Normal

Write-Host 'Launcher started backend and frontend from this worktree.'
