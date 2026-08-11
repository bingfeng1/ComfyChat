# scripts/_job-helper.ps1
# PowerShell helper for start-dev.bat / stop-dev.bat.
# Owns the Windows Job Object that reaps backend + frontend on launcher exit.

[CmdletBinding()]
param(
    [ValidateSet('PreFlight','RunServersAndWait','Test')]
    [string]$Command = '',
    [string]$RepoRoot = '',
    [int]$WaitSeconds = 25
)

$ErrorActionPreference = 'Stop'

# -------- env / pid-file utilities --------

function Read-DotEnv {
    param([string]$Path)
    $h = @{}
    if (-not (Test-Path -LiteralPath $Path)) { return $h }
    Get-Content -LiteralPath $Path | ForEach-Object {
        $line = $_.Trim()
        if ($line -eq '') { return }
        if ($line.StartsWith('#')) { return }
        $eq = $line.IndexOf('=')
        if ($eq -lt 1) { return }
        $k = $line.Substring(0, $eq).Trim()
        $v = $line.Substring($eq + 1).Trim()
        if (($v.StartsWith('"') -and $v.EndsWith('"')) -or
            ($v.StartsWith("'") -and $v.EndsWith("'"))) {
            $v = $v.Substring(1, $v.Length - 2)
        }
        $h[$k] = $v
    }
    return $h
}

function Get-BackendPort {
    $raw = (Read-DotEnv (Join-Path $RepoRoot '.env'))['BACKEND_PORT']
    if ([string]::IsNullOrWhiteSpace($raw)) { return 8000 }
    $n = 0
    if ([int]::TryParse($raw, [ref]$n) -and $n -gt 0 -and $n -lt 65536) { return $n }
    Write-Warning "BACKEND_PORT '$raw' is not a valid port; using default 8000"
    return 8000
}

function Get-FrontendPort {
    $raw = (Read-DotEnv (Join-Path $RepoRoot '.env'))['FRONTEND_PORT']
    if ([string]::IsNullOrWhiteSpace($raw)) { return 5173 }
    $n = 0
    if ([int]::TryParse($raw, [ref]$n) -and $n -gt 0 -and $n -lt 65536) { return $n }
    Write-Warning "FRONTEND_PORT '$raw' is not a valid port; using default 5173"
    return 5173
}

function Read-PidFile {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    try {
        return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    } catch {
        Write-Warning "Failed to parse PID file $Path; ignoring"
        return $null
    }
}

function Write-PidFile {
    param([string]$Path, [hashtable]$Obj)
    $dir = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }
    $Obj | ConvertTo-Json | Set-Content -LiteralPath $Path -Encoding utf8
}

# -------- port / http utilities --------

function Get-PortOwnerPid {
    param([int]$Port)
    try {
        $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop
        return [int]$conn.OwningProcess
    } catch {
        return 0
    }
}

function Kill-PortOwner {
    param([int]$Port)
    $pid_ = Get-PortOwnerPid $Port
    if ($pid_ -le 0) { return }
    Write-Warning "Killing straggler on port $Port (PID $pid_)"
    taskkill /T /F /PID $pid_ 2>&1 | Out-Null
}

function Wait-HttpReady {
    param([string]$Url, [int]$TimeoutSeconds)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            if ($r.StatusCode -eq 200) { return $true }
        } catch {
            # try again
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

# -------- command dispatch --------

if ($Command -eq 'Test') {
    Write-Host "Read-DotEnv(.) keys: $((Read-DotEnv (Join-Path $RepoRoot '.env')).Keys -join ',')"
    Write-Host "Get-BackendPort = $(Get-BackendPort)"
    Write-Host "Get-FrontendPort = $(Get-FrontendPort)"
    return
}

if ($Command -eq 'PreFlight') {
    Write-Host "PreFlight not implemented yet" -ForegroundColor Yellow
    exit 0
}

if ($Command -eq 'RunServersAndWait') {
    Write-Host "RunServersAndWait not implemented yet" -ForegroundColor Yellow
    exit 0
}
