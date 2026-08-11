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

# -------- Job Object (KILL_ON_JOB_CLOSE) --------

if (-not ('DevJobObject' -as [type])) {
    Add-Type -Namespace DevJobObject -Name Native -MemberDefinition @'
        [StructLayout(LayoutKind.Sequential)]
        public struct JOBOBJECT_BASIC_LIMIT_INFORMATION {
            public long PerProcessUserTimeLimit;
            public long PerJobUserTimeLimit;
            public uint LimitFlags;
            public UIntPtr MinimumWorkingSetSize;
            public UIntPtr MaximumWorkingSetSize;
            public uint ActiveProcessLimit;
            public UIntPtr Affinity;
            public uint PriorityClass;
            public uint SchedulingClass;
        }

        [StructLayout(LayoutKind.Sequential)]
        public struct IO_COUNTERS {
            public ulong ReadOperationCount;
            public ulong WriteOperationCount;
            public ulong OtherOperationCount;
            public ulong ReadTransferCount;
            public ulong WriteTransferCount;
            public ulong OtherTransferCount;
        }

        [StructLayout(LayoutKind.Sequential)]
        public struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION {
            public JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation;
            public IO_COUNTERS IoInfo;
            public UIntPtr ProcessMemoryLimit;
            public UIntPtr JobMemoryLimit;
            public UIntPtr PeakProcessMemoryUsed;
            public UIntPtr PeakJobMemoryUsed;
        }

        public const uint JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000;
        public const uint JobObjectExtendedLimitInformation = 9;

        [DllImport("kernel32.dll", CharSet=CharSet.Unicode)]
        public static extern IntPtr CreateJobObject(IntPtr a, string n);

        [DllImport("kernel32.dll", SetLastError=true)]
        public static extern bool SetInformationJobObject(
            IntPtr h, uint infoClass, IntPtr info, uint cb);

        [DllImport("kernel32.dll", SetLastError=true)]
        public static extern bool AssignProcessToJobObject(IntPtr h, IntPtr p);
'@
}

$script:DevJob = [IntPtr]::Zero
$script:DevJobPids = New-Object System.Collections.Generic.List[int]

function New-KillOnCloseJob {
    if ($script:DevJob -ne [IntPtr]::Zero) { return $script:DevJob }
    $info = New-Object DevJobObject.Native+JOBOBJECT_EXTENDED_LIMIT_INFORMATION
    $basic = $info.BasicLimitInformation
    $basic.LimitFlags = [DevJobObject.Native]::JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    $info.BasicLimitInformation = $basic
    $size = [System.Runtime.InteropServices.Marshal]::SizeOf(
        [type]'DevJobObject.Native+JOBOBJECT_EXTENDED_LIMIT_INFORMATION')
    $ptr = [System.Runtime.InteropServices.Marshal]::AllocHGlobal($size)
    try {
        [System.Runtime.InteropServices.Marshal]::StructureToPtr($info, $ptr, $false)
        $h = [DevJobObject.Native]::CreateJobObject([IntPtr]::Zero, $null)
        if ($h -eq [IntPtr]::Zero) {
            throw [System.ComponentModel.Win32Exception]::new(
                [System.Runtime.InteropServices.Marshal]::GetLastWin32Error())
        }
        $ok = [DevJobObject.Native]::SetInformationJobObject(
            $h,
            [DevJobObject.Native]::JobObjectExtendedLimitInformation,
            $ptr, $size)
        if (-not $ok) {
            throw [System.ComponentModel.Win32Exception]::new(
                [System.Runtime.InteropServices.Marshal]::GetLastWin32Error())
        }
        $script:DevJob = $h
        return $h
    } finally {
        [System.Runtime.InteropServices.Marshal]::FreeHGlobal($ptr)
    }
}

function Add-ToJob {
    param([Alias('Pid')][int]$ProcessId)
    if ($script:DevJob -eq [IntPtr]::Zero) {
        throw 'Job Object not initialized; call New-KillOnCloseJob first'
    }
    $proc = [System.Diagnostics.Process]::GetProcessById($ProcessId)
    try {
        $ok = [DevJobObject.Native]::AssignProcessToJobObject(
            $script:DevJob, $proc.Handle)
        if (-not $ok) {
            throw [System.ComponentModel.Win32Exception]::new(
                [System.Runtime.InteropServices.Marshal]::GetLastWin32Error())
        }
        if (-not $script:DevJobPids.Contains($ProcessId)) {
            $script:DevJobPids.Add($ProcessId)
        }
    } finally {
        $proc.Dispose()
    }
}

function Wait-JobEmpty {
    param([int]$TimeoutSeconds = 0)
    if ($script:DevJobPids.Count -eq 0) { return $true }
    $deadline = if ($TimeoutSeconds -gt 0) {
        (Get-Date).AddSeconds($TimeoutSeconds)
    } else { [DateTime]::MaxValue }
    while ((Get-Date) -lt $deadline) {
        $any = $false
        foreach ($p in @($script:DevJobPids)) {
            if (Get-Process -Id $p -ErrorAction SilentlyContinue) {
                $any = $true
                break
            }
        }
        if (-not $any) { return $true }
        Start-Sleep -Milliseconds 500
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
    $RepoRoot = (Resolve-Path $RepoRoot).Path
    Set-Location $RepoRoot

    $tmpDir = Join-Path $RepoRoot 'storage\tmp'
    if (-not (Test-Path -LiteralPath $tmpDir)) {
        New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null
    }
    $pidFile = Join-Path $tmpDir '.dev-pids.json'

    # 1) Clean stale PID file
    $existing = Read-PidFile $pidFile
    if ($existing) {
        foreach ($label in 'backend','frontend') {
            $targetPid = $existing.$label
            if (-not $targetPid) { continue }
            $proc = Get-Process -Id $targetPid -ErrorAction SilentlyContinue
            if ($proc) {
                Write-Warning "PreFlight: killing stale $label PID $targetPid"
                taskkill /T /F /PID $targetPid 2>&1 | Out-Null
            }
        }
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    }

    # 2) Belt-and-suspenders port cleanup
    Kill-PortOwner (Get-BackendPort)
    Kill-PortOwner (Get-FrontendPort)

    Write-Host "PreFlight done." -ForegroundColor Green
    exit 0
}

if ($Command -eq 'RunServersAndWait') {
    $RepoRoot = (Resolve-Path $RepoRoot).Path
    Set-Location $RepoRoot

    $tmpDir = Join-Path $RepoRoot 'storage\tmp'
    if (-not (Test-Path -LiteralPath $tmpDir)) {
        New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null
    }
    $pidFile = Join-Path $tmpDir '.dev-pids.json'
    $backendOut = Join-Path $tmpDir 'backend.out.log'
    $backendErr = Join-Path $tmpDir 'backend.err.log'
    $frontendOut = Join-Path $tmpDir 'frontend.out.log'
    $frontendErr = Join-Path $tmpDir 'frontend.err.log'

    $backendPort = Get-BackendPort
    $frontendPort = Get-FrontendPort
    if ($backendPort -eq $frontendPort) {
        throw "BACKEND_PORT ($backendPort) and FRONTEND_PORT ($frontendPort) must differ"
    }

    $job = New-KillOnCloseJob

    # 1) Backend (uvicorn) — python.exe main process goes into the Job. Its
    #    workers (spawned by uvicorn) automatically inherit the Job.
    $backend = Start-Process `
        -FilePath (Join-Path $RepoRoot 'backend\.venv\Scripts\python.exe') `
        -ArgumentList '-m','uvicorn','app.main:app','--port',"$backendPort" `
        -WorkingDirectory $RepoRoot `
        -RedirectStandardOutput $backendOut `
        -RedirectStandardError $backendErr `
        -PassThru
    Add-ToJob -Pid $backend.Id

    # 2) Frontend (vite) — pass env vars so vite.config.ts reads them.
    #    npm.cmd is a cmd.exe shim; putting IT in the Job means the node.exe
    #    it spawns inherits the Job automatically. Do NOT look up the port
    #    owner and assign it directly — that path hits "access denied".
    $env:BACKEND_PORT = "$backendPort"
    $env:FRONTEND_PORT = "$frontendPort"
    $frontend = Start-Process `
        -FilePath 'npm.cmd' `
        -ArgumentList 'run','dev','--','--host','127.0.0.1','--port',"$frontendPort" `
        -WorkingDirectory (Join-Path $RepoRoot 'frontend') `
        -RedirectStandardOutput $frontendOut `
        -RedirectStandardError $frontendErr `
        -PassThru
    Add-ToJob -Pid $frontend.Id

    # 3) Wait for readiness
    $backendReady = Wait-HttpReady "http://127.0.0.1:$backendPort/health" $WaitSeconds
    if (-not $backendReady) {
        Write-Warning "backend not responding on :$backendPort/health after $WaitSeconds s"
    }
    $frontendReady = Wait-HttpReady "http://127.0.0.1:$frontendPort/" $WaitSeconds
    if (-not $frontendReady) {
        Write-Warning "frontend not responding on :$frontendPort/ after $WaitSeconds s"
    }

    # 3b) Open the browser in the default app once the frontend is up
    if ($frontendReady) {
        try {
            Start-Process "http://127.0.0.1:$frontendPort/"
        } catch {
            Write-Warning "failed to open browser: $($_.Exception.Message)"
        }
    }

    # 4) Persist PID file (frontend = npm.cmd shim PID; stop-dev taskkill /T
    #    tree-kills it and node.exe together)
    try {
        Write-PidFile $pidFile @{
            backend   = $backend.Id
            frontend  = $frontend.Id
            startedAt = (Get-Date).ToString('o')
        }
    } catch {
        Write-Warning "failed to write PID file: $($_.Exception.Message)"
    }

    # 5) Block until Job empty
    $null = Wait-JobEmpty -TimeoutSeconds 0
    exit 0
}
