# Run from anywhere: powershell -NoProfile -ExecutionPolicy Bypass -File C:\Python\Projects\AIPlatform4ContentMarketing\scripts\restart-api.ps1
param(
    [switch]$Foreground
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$BackendDir = Join-Path $RepoRoot.Path 'backend'
$PythonExe = Join-Path $BackendDir '.venv\Scripts\python.exe'
$UvicornArgs = @('-m', 'uvicorn', 'app.main:app', '--reload', '--host', '127.0.0.1', '--port', '8000')
$HealthUrl = 'http://127.0.0.1:8000/health'
$DocsUrl = 'http://127.0.0.1:8000/docs'
$Port = 8000

function Write-BindHint {
    Write-Host ''
    Write-Host 'Port 8000 did not come up. Typical causes:'
    Write-Host '  1) A second uvicorn/instance is still bound to 8000'
    Write-Host '  2) Windows excluded port range (Hyper-V / WinNAT). Check:'
    Write-Host '     netsh interface ipv4 show excludedportrange protocol=tcp'
    Write-Host '     If 8000 is inside a range: net stop winnat  (or reboot / pick another port)'
}

function Test-TcpOpen {
    param([string]$TargetHost, [int]$TargetPort, [int]$TimeoutMs = 800)
    $client = $null
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $iar = $client.BeginConnect($TargetHost, $TargetPort, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) {
            return $false
        }
        $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        if ($client) { $client.Close() }
    }
}

function Test-PortExcluded {
    param([int]$TargetPort)
    $raw = & netsh interface ipv4 show excludedportrange protocol=tcp 2>$null | Out-String
    if (-not $raw) { return $false }
    foreach ($line in ($raw -split "`r?`n")) {
        if ($line -match '^\s*(\d+)\s+(\d+)\s*\*?') {
            $start = [int]$Matches[1]
            $end = [int]$Matches[2]
            if ($TargetPort -ge $start -and $TargetPort -le $end) {
                return $true
            }
        }
    }
    return $false
}

function Get-ProjectUvicornProcesses {
    $pythonNeedle = $PythonExe.ToLowerInvariant().Replace('/', '\')
    $backendNeedle = $BackendDir.ToLowerInvariant().Replace('/', '\')
    Get-CimInstance Win32_Process | Where-Object {
        $ok = $false
        if ($_.CommandLine) {
            $cl = $_.CommandLine.ToLowerInvariant().Replace('/', '\')
            if ($cl -like '*app.main:app*' -and $cl -like '*uvicorn*') {
                $ok = $cl.Contains($pythonNeedle) -or $cl.Contains($backendNeedle)
            }
        }
        $ok
    }
}

if (-not (Test-Path -LiteralPath $PythonExe)) {
    Write-Host "venv python not found: $PythonExe"
    exit 1
}

$existing = @(Get-ProjectUvicornProcesses)
if ($existing.Count -gt 0) {
    foreach ($proc in $existing) {
        Write-Host ("Stopping PID {0} ({1})" -f $proc.ProcessId, $proc.Name)
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    }
    $deadline = (Get-Date).AddSeconds(5)
    do {
        Start-Sleep -Milliseconds 250
        $existing = @(Get-ProjectUvicornProcesses)
    } while ($existing.Count -gt 0 -and (Get-Date) -lt $deadline)

    if (@(Get-ProjectUvicornProcesses).Count -gt 0) {
        Write-Host 'Warning: some project uvicorn processes did not exit.'
    }
}

$waitPort = (Get-Date).AddSeconds(3)
while ((Test-TcpOpen -TargetHost '127.0.0.1' -TargetPort $Port -TimeoutMs 200) -and (Get-Date) -lt $waitPort) {
    Start-Sleep -Milliseconds 200
}

if (Test-PortExcluded -TargetPort $Port) {
    Write-Host "Warning: TCP port $Port is in a Windows excluded range. Bind will likely fail."
    Write-BindHint
}

Write-Host "Repo:    $($RepoRoot.Path)"
Write-Host "Python:  $PythonExe"
Write-Host "Health:  $HealthUrl"
Write-Host "Docs:    $DocsUrl"
Write-Host "Command: $PythonExe $($UvicornArgs -join ' ')"

if ($Foreground) {
    Set-Location -LiteralPath $BackendDir
    & $PythonExe @UvicornArgs
    $code = $LASTEXITCODE
    if ($code -ne 0 -and $code -ne $null) {
        Write-BindHint
        exit $code
    }
    exit 0
}

$quotedPy = '"' + $PythonExe + '"'
$inner = 'cd /d "' + $BackendDir + '" && ' + $quotedPy + ' -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000'
Start-Process -FilePath 'cmd.exe' -ArgumentList @('/k', $inner) -WorkingDirectory $BackendDir | Out-Null
Write-Host 'Started in a new console window (cmd /k).'

$up = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 500
    try {
        $resp = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 2
        if ($resp.StatusCode -eq 200) {
            $up = $true
            break
        }
    } catch {
        # still booting or bind failed
    }
}

if ($up) {
    Write-Host "API is up: $HealthUrl"
} else {
    Write-BindHint
    exit 1
}
