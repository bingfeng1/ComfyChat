# scripts/stop-dev.ps1
# Stop the ComfyChat backend and frontend started by start-dev.ps1.
# Reads PIDs from storage/tmp/.dev-pids.json and kills the process trees.

[CmdletBinding()]
param()

$ErrorActionPreference = 'Continue'
$RepoRoot = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $RepoRoot

$PidFile = "storage\tmp\.dev-pids.json"
if (-not (Test-Path -LiteralPath $PidFile)) {
    Write-Host "No PID file at $PidFile. Nothing to stop." -ForegroundColor Yellow
    exit 0
}

$pids = Get-Content -Path $PidFile -Raw | ConvertFrom-Json

function Stop-Tree($label, $pid) {
    if (-not $pid) { return }
    $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
    if (-not $proc) {
        Write-Host "  [skip] $label PID $pid not running" -ForegroundColor DarkGray
        return
    }
    try {
        taskkill /T /F /PID $pid | Out-Null
        Write-Host "  [ok]   $label PID $pid killed (tree)" -ForegroundColor Green
    } catch {
        Write-Host "  [warn] $label PID $pid (kill failed)" -ForegroundColor Yellow
    }
}

Write-Host "Stopping ComfyChat dev servers..." -ForegroundColor Cyan
Stop-Tree "backend"  $pids.backend
Stop-Tree "frontend" $pids.frontend

Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue

# Belt-and-suspenders: kill any straggler on the dev ports
foreach ($p in 8000, 5173) {
    $conn = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
    if ($conn) {
        Write-Host "  [clean] straggler on port $p -> PID $($conn.OwningProcess)" -ForegroundColor Yellow
        taskkill /T /F /PID $conn.OwningProcess 2>&1 | Out-Null
    }
}

Write-Host "Done." -ForegroundColor Green