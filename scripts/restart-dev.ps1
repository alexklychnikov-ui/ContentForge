param(
    [switch]$Foreground
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$FrontendDir = Join-Path $RepoRoot.Path 'frontend'
$ApiScript = Join-Path $PSScriptRoot 'restart-api.ps1'
$VitePort = 5173
$ViteUrl = 'http://127.0.0.1:5173'

function Test-TcpOpen {
    param([string]$TargetHost, [int]$TargetPort, [int]$TimeoutMs = 400)
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

function Start-FrontendIfNeeded {
    if (Test-TcpOpen -TargetHost '127.0.0.1' -TargetPort $VitePort) {
        Write-Host "Frontend already listening on $ViteUrl - not starting another npm."
        return
    }
    if (-not (Test-Path -LiteralPath (Join-Path $FrontendDir 'package.json'))) {
        Write-Host "frontend/package.json not found: $FrontendDir"
        exit 1
    }
    $inner = 'cd /d "' + $FrontendDir + '" && npm run dev'
    Start-Process -FilePath 'cmd.exe' -ArgumentList @('/k', $inner) -WorkingDirectory $FrontendDir | Out-Null
    Write-Host 'Started frontend in a new console: npm run dev'
    Write-Host "UI: $ViteUrl"
}

if ($Foreground) {
    Start-FrontendIfNeeded
    & $ApiScript -Foreground
    exit $LASTEXITCODE
}

& $ApiScript
$apiCode = $LASTEXITCODE
if ($null -ne $apiCode -and $apiCode -ne 0) {
    Write-Host "API restart failed (exit $apiCode). Frontend not started."
    exit $apiCode
}

Start-FrontendIfNeeded
