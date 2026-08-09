# scripts/start-dev.ps1
# Start ComfyChat backend (uvicorn) and frontend (vite dev) as background processes.
# Run from the repo root. Both servers run independently; use stop-dev.ps1 to shut them down.

[CmdletBinding()]
param(
    [switch] $OpenBrowser,
    [int] $WaitSeconds = 25
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $RepoRoot

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  [!] $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "  [X] $msg" -ForegroundColor Red; exit 1 }

# 1. Pre-flight checks
Write-Step "Pre-flight checks"
if (-not (Test-Path -LiteralPath "backend\.venv\Scripts\python.exe")) {
    Write-Err "backend\.venv\ missing. Run setup from README.md first."
}
if (-not (Test-Path -LiteralPath "frontend\node_modules")) {
    Write-Err "frontend\node_modules\ missing. Run 'cd frontend && npm install' first."
}
New-Item -ItemType Directory -Force -Path "storage\tmp" | Out-Null
$PidFile = "storage\tmp\.dev-pids.json"

if (Test-Path -LiteralPath $PidFile) {
    Write-Warn "Existing PID file found at $PidFile. Run scripts\stop-dev.ps1 first, or delete the file."
    Write-Err "Refusing to start while previous run is still tracked."
}

# 2. Check ports
foreach ($p in 8000, 5173) {
    $existing = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Err "Port $p is already in use by PID $($existing.OwningProcess). Stop it or change the port."
    }
}

# 3. Start backend
Write-Step "Starting backend (uvicorn :8000)"
$backendOut = "storage\tmp\backend.out.log"
$backendErr = "storage\tmp\backend.err.log"
$backend = Start-Process `
    -FilePath "backend\.venv\Scripts\python.exe" `
    -ArgumentList "-m","uvicorn","app.main:app","--port","8000" `
    -WorkingDirectory $RepoRoot `
    -RedirectStandardOutput $backendOut `
    -RedirectStandardError $backendErr `
    -PassThru
Write-Ok "backend PID $($backend.Id); stdout: $backendOut; stderr: $backendErr"

# 4. Start frontend
Write-Step "Starting frontend (vite :5173)"
$frontendOut = "storage\tmp\frontend.out.log"
$frontendErr = "storage\tmp\frontend.err.log"
$frontend = Start-Process `
    -FilePath "npm.cmd" `
    -ArgumentList "run","dev","--","--host","127.0.0.1" `
    -WorkingDirectory "$RepoRoot\frontend" `
    -RedirectStandardOutput $frontendOut `
    -RedirectStandardError $frontendErr `
    -PassThru
Write-Ok "frontend PID $($frontend.Id); stdout: $frontendOut; stderr: $frontendErr"

# 5. Save PIDs (storage/ is gitignored)
@{ backend = $backend.Id; frontend = $frontend.Id; startedAt = (Get-Date).ToString('o') } |
    ConvertTo-Json | Set-Content -Path $PidFile -Encoding utf8

# 6. Wait for readiness
Write-Step "Waiting up to $WaitSeconds s for both servers to respond"
$deadline = (Get-Date).AddSeconds($WaitSeconds)
$backendReady = $false
$frontendReady = $false
while ((Get-Date) -lt $deadline -and -not ($backendReady -and $frontendReady)) {
    if (-not $backendReady) {
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 2
            if ($r.StatusCode -eq 200) { $backendReady = $true }
        } catch { }
    }
    if (-not $frontendReady) {
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:5173/" -UseBasicParsing -TimeoutSec 2
            if ($r.StatusCode -eq 200) { $frontendReady = $true }
        } catch { }
    }
    if (-not ($backendReady -and $frontendReady)) { Start-Sleep -Seconds 1 }
}

if (-not $backendReady) {
    Write-Warn "backend not responding on :8000/health after $WaitSeconds s. Check $backendErr."
}
if (-not $frontendReady) {
    Write-Warn "frontend not responding on :5173/ after $WaitSeconds s. Check $frontendErr."
}

# 7. Done
Write-Host ""
Write-Host "ComfyChat dev servers:" -ForegroundColor Green
Write-Host "  backend  http://127.0.0.1:8000/health  (PID $($backend.Id))"
Write-Host "  frontend http://127.0.0.1:5173/        (PID $($frontend.Id))"
Write-Host ""
Write-Host "Stop:  powershell -ExecutionPolicy Bypass -File scripts\stop-dev.ps1"

if ($OpenBrowser -and $frontendReady) {
    Start-Process "http://127.0.0.1:5173/" | Out-Null
}