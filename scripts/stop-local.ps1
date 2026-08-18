$ErrorActionPreference = 'Stop'

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
Write-Host 'Stopped listeners on ports 5173 and 8000 (if present).'
