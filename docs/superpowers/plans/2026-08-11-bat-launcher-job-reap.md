# .bat 启动器 + Job Object 收尸 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把启动器换成 `.bat`,默认保证后台(:BACKEND_PORT)和前端(:FRONTEND_PORT)进程在启动器以任意方式退出时被 OS 收尸;端口由根 `.env` 覆盖。

**Architecture:** `.bat` 调独立 PowerShell 帮助器 `_job-helper.ps1`。帮助器持有带 `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` 的 Job Object,把后端 uvicorn 和前端 vite 收进 Job。`.bat` 退出 → 帮助器退出 → OS 关闭 Job → 收尸。端口从 `.env` 读,经 PowerShell `$env:` 传给 vite 子进程。

**Tech Stack:** Windows cmd.exe (`.bat`), PowerShell 5.1 (`.ps1` + C# `Add-Type` P/Invoke), TypeScript (vite.config.ts), pydantic-settings (`.env` 现有字段不动).

## Global Constraints

- **Windows only.** PowerShell 5.1(`$PSVersionTable.PSVersion.Major` 等于 5)。不要假设 PowerShell Core(`pwsh`)。
- **`.bat` 永远不要直接通过 `bash` 工具调用** —— 按 AGENTS.md 已建立的规则。用户自己跑,或助手用 `Start-Process powershell … -WindowStyle Hidden` 分离启动并立刻返回。
- **Job Object 句柄只在 `_job-helper.ps1` 的 `RunServersAndWait` 调用内部存活**。不序列化、不导出、不跨进程传递。
- **`.dev-pids.json` 格式不变** —— `{backend, frontend, startedAt}`。`.bat` 和现有 `.ps1` 共享格式。
- **现有 `.ps1` 脚本保留在磁盘上**,不删。
- **`Settings` 字段集仍是 5 个**(`comfyui_base_url` / `comfyui_api_key` / `database_url` / `storage_root` / `comfyui_userdata_dir`)。两个新端口变量 **不进** `Settings`。
- **`process.env.BACKEND_PORT` / `process.env.FRONTEND_PORT` 由 PowerShell `$env:` 自动传给子进程** —— 不需要 `dotenv` 包。
- **`storage/` 全 gitignore** —— `.dev-pids.json` 和 `.out.log` / `.err.log` 永远不提交。
- **前端 dev 绑定 `127.0.0.1`** —— `npm run dev -- --host 127.0.0.1 --port <port>`。不要换成 `localhost`。
- **Vite 代理保留 `/api` → `http://127.0.0.1:${BACKEND_PORT}`**,rewrite `/api` 前缀。**不要**给后端路由加 `/api` 前缀(沿用现有约定)。
- **PowerShell 调用约定**:`powershell -NoProfile -ExecutionPolicy Bypass -File <path> -Command <Name> [args]`,`-ArgumentList` 中的项必须作为独立元素,避免被 PowerShell 合并成单个字符串。

---

## File Map

| 文件 | 角色 | 状态 |
|------|------|------|
| `.env` | 加 `BACKEND_PORT=8000` / `FRONTEND_PORT=5173` 注释行 | 修改 |
| `frontend/vite.config.ts` | 顶部读 `process.env.BACKEND_PORT` / `process.env.FRONTEND_PORT`,用于 `server.port` 和 `proxy["/api"].target` | 修改 |
| `scripts/_job-helper.ps1` | PowerShell 帮助器:env/pid 工具、端口工具、Job Object P/Invoke、`PreFlight`、`RunServersAndWait` | 新增 |
| `scripts/start-dev.bat` | 默认启动入口;调帮助器 `PreFlight` + `RunServersAndWait` | 新增 |
| `scripts/stop-dev.bat` | 手动控制:`taskkill /T /F` + 端口兜底 | 新增 |
| `AGENTS.md` | 更新第 24/25/39 行,改指 `.bat`,描述 Job-Object 收尸与 `.env` 端口覆盖 | 修改 |

---

## Task 1: `.env` 追加端口配置

**Files:**
- Modify: `.env`(末尾追加)

**Interfaces:**
- Consumes: 无
- Produces: 键 `BACKEND_PORT` / `FRONTEND_PORT`(可选,默认 8000 / 5173)

- [ ] **Step 1: 编辑 `.env`,在末尾追加两行注释占位**

在 `.env` 文件最后追加(用 `read` 工具读后再 `edit`,或在文件末尾追加):

```
# Dev ports (optional — read by start-dev.bat / vite.config.ts).
# Defaults are 8000 and 5173; uncomment and edit to override.
# BACKEND_PORT=8000
# FRONTEND_PORT=5173
```

- [ ] **Step 2: 验证 `.env` 的现有 5 个 `Settings` 字段未受影响**

Run:
```bash
Get-Content .env
```
Expected: 仍包含 `COMFYUI_BASE_URL`、`DATABASE_URL`、`STORAGE_ROOT`、`COMFYUI_USERDATA_DIR` 四行(可能 `COMFYUI_API_KEY` 为空),且新增 4 行注释占位。

- [ ] **Step 3: 提交**

```bash
git add .env
git commit -m "feat(scripts): add optional BACKEND_PORT / FRONTEND_PORT to .env"
```

---

## Task 2: `vite.config.ts` 端口从环境变量读取

**Files:**
- Modify: `frontend/vite.config.ts`(替换前几行 server 块)

**Interfaces:**
- Consumes: `process.env.BACKEND_PORT` / `process.env.FRONTEND_PORT`(由 PowerShell `$env:` 注入)
- Produces: vite dev server 在 `<FRONTEND_PORT>` 监听,代理 `/api/*` 到 `http://127.0.0.1:<BACKEND_PORT>`

- [ ] **Step 1: 修改 `frontend/vite.config.ts`**

将现有内容替换为(只改前几行 + server 块;插件块、resolve.alias 块不动):

```ts
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import AutoImport from "unplugin-auto-import/vite";
import Components from "unplugin-vue-components/vite";
import { ElementPlusResolver } from "unplugin-vue-components/resolvers";
import { fileURLToPath, URL } from "node:url";

const backendPort = process.env.BACKEND_PORT ?? "8000";
const frontendPort = process.env.FRONTEND_PORT ?? "5173";

export default defineConfig({
  plugins: [
    vue(),
    AutoImport({ resolvers: [ElementPlusResolver()] }),
    Components({ resolvers: [ElementPlusResolver({ styleExtension: "scss" })] }),
  ],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: Number(frontendPort),
    proxy: {
      "/api": {
        target: `http://127.0.0.1:${backendPort}`,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
});
```

- [ ] **Step 2: 跑前端 typecheck 确认无回归**

Run:
```bash
npm --prefix frontend run typecheck
```
Expected: 0 error,退出码 0。

- [ ] **Step 3: 跑 vite dev 一次,验证默认端口仍是 5173**

Run(后台启动,10 秒后停):
```bash
cd frontend && BACKEND_PORT=8000 FRONTEND_PORT=5173 npx vite --host 127.0.0.1 --port 5173
```
Expected: stdout 出现 `Local: http://127.0.0.1:5173/`。Ctrl+C 退出。

或简单做法:
```bash
cd frontend && npm run dev -- --host 127.0.0.1 --port 5173
```
启动后 `Invoke-WebRequest http://127.0.0.1:5173/` 应得 200。

- [ ] **Step 4: 提交**

```bash
git add frontend/vite.config.ts
git commit -m "feat(frontend): read BACKEND_PORT / FRONTEND_PORT from env in vite.config"
```

---

## Task 3: `_job-helper.ps1` — env / pid 文件工具

**Files:**
- Create: `scripts/_job-helper.ps1`

**Interfaces:**
- Consumes: `.env` 路径,`storage\tmp\.dev-pids.json` 路径
- Produces:
  - `Read-DotEnv` —— 返回 `hashtable`
  - `Get-BackendPort` / `Get-FrontendPort` —— 返回 `[int]`
  - `Read-PidFile` —— 返回 `object` 或 `$null`
  - `Write-PidFile` —— 无返回值

- [ ] **Step 1: 写脚本骨架 + 4 个工具函数**

`scripts/_job-helper.ps1` 全部内容(暂时只含 param 块 + 这 4 个函数 + 调度占位):

```powershell
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
```

- [ ] **Step 2: 跑 Test 命令验证 env / port 解析**

Run:
```bash
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\_job-helper.ps1 -Command Test -RepoRoot "$PWD"
```
Expected: 输出包含 `Get-BackendPort = 8000`、`Get-FrontendPort = 5173`(因为 `.env` 中两行被注释)。

- [ ] **Step 3: 临时改 `.env` 验证覆盖解析**

Run:
```bash
# 临时把 .env 中的两行注释打开,改端口
$content = Get-Content .env
$content += @('BACKEND_PORT=9000', 'FRONTEND_PORT=5174')
Set-Content -LiteralPath .env -Value $content
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\_job-helper.ps1 -Command Test -RepoRoot "$PWD"
```
Expected: `Get-BackendPort = 9000`、`Get-FrontendPort = 5174`。

- [ ] **Step 4: 还原 `.env`(删除刚加的两行)**

Run:
```bash
$content = Get-Content .env | Where-Object { $_ -notmatch '^(BACKEND_PORT|FRONTEND_PORT)=' }
Set-Content -LiteralPath .env -Value $content
```

- [ ] **Step 5: 临时构造 `.dev-pids.json` 验证 Read/Write-PidFile**

Run(一行 PowerShell):
```bash
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { . ./scripts/_job-helper.ps1; Write-PidFile 'storage/tmp/.dev-pids.json' @{ backend=12345; frontend=67890; startedAt=(Get-Date).ToString('o') }; $obj = Read-PidFile 'storage/tmp/.dev-pids.json'; Write-Host \"backend=$($obj.backend) frontend=$($obj.frontend)\" }"
```
Expected: 输出 `backend=12345 frontend=67890`。

- [ ] **Step 6: 删除测试用的 PID 文件**

Run:
```bash
Remove-Item -LiteralPath storage/tmp/.dev-pids.json -Force
```

- [ ] **Step 7: 提交**

```bash
git add scripts/_job-helper.ps1
git commit -m "feat(scripts): add _job-helper.ps1 with env/pid-file utilities"
```

---

## Task 4: `_job-helper.ps1` — 端口与 HTTP 工具

**Files:**
- Modify: `scripts/_job-helper.ps1`(追加 3 个函数;dispatch 块不变)

**Interfaces:**
- Consumes: 端口号 / URL
- Produces:
  - `Get-PortOwnerPid([int]$Port)` → `[int]`(0 表示空闲)
  - `Kill-PortOwner([int]$Port)` → `void`(空闲时静默)
  - `Wait-HttpReady([string]$Url, [int]$TimeoutSeconds)` → `[bool]`

- [ ] **Step 1: 在 `_job-helper.ps1` 的 `Write-PidFile` 后追加 3 个函数**

```powershell
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
```

- [ ] **Step 2: 端口空闲时 `Get-PortOwnerPid` 返回 0**

Run:
```bash
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { . ./scripts/_job-helper.ps1; $p = Get-PortOwnerPid 5173; Write-Host \"pid=$p\" }"
```
Expected: `pid=0`(空闲)。

- [ ] **Step 3: 启动一个临时 http 监听,验证 `Get-PortOwnerPid` 命中**

Run(分两步:启动 + 查询):

```bash
# 1. 后台启动一个简单 HTTP 服务,绑 8765
python -m http.server 8765 --bind 127.0.0.1
# (留此进程在另一窗口跑,或加 Start-Process -NoNewWindow 之类;这里手动另开 shell)
```
另开一个 PowerShell:
```bash
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { . ./scripts/_job-helper.ps1; $p = Get-PortOwnerPid 8765; Write-Host \"pid=$p\" }"
```
Expected: `pid=<某非零整数>`(命中 python.exe)。

关掉临时 http 服务(回到原 shell,Ctrl+C)。

- [ ] **Step 4: 验证 `Wait-HttpReady` 对 200 端点返回 true**

Run:
```bash
# 临时启动 backend(开发用)若干秒;或者用 python -m http.server
python -m http.server 8000 --bind 127.0.0.1
```
另开 shell:
```bash
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { . ./scripts/_job-helper.ps1; $ok = Wait-HttpReady 'http://127.0.0.1:8000/' 5; Write-Host \"ready=$ok\" }"
```
Expected: `ready=True`。

关掉 python http.server。

- [ ] **Step 5: 验证 `Wait-HttpReady` 对不存在端点返回 false**

Run:
```bash
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { . ./scripts/_job-helper.ps1; $ok = Wait-HttpReady 'http://127.0.0.1:1/' 3; Write-Host \"ready=$ok\" }"
```
Expected: `ready=False`(端口 1 不监听)。

- [ ] **Step 6: 提交**

```bash
git add scripts/_job-helper.ps1
git commit -m "feat(scripts): add port-owner lookup and HTTP readiness helpers"
```

---

## Task 5: `_job-helper.ps1` — Job Object P/Invoke 层

**Files:**
- Modify: `scripts/_job-helper.ps1`(追加 C# Add-Type + `New-KillOnCloseJob` / `Add-ToJob` / `Wait-JobEmpty`)

**Interfaces:**
- Consumes: PID 列表(由 RunServersAndWait 收集)
- Produces:
  - `[IntPtr]$script:DevJob` —— 当前进程的 Job 句柄(模块级变量,Job Object 生命周期跟帮助器进程)
  - `New-KillOnCloseJob` —— 调 C# 创建 Job,赋 `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`
  - `Add-ToJob([int]$Pid)` —— 把进程 assign 进 Job
  - `Wait-JobEmpty($Pids, [int]$TimeoutSeconds)` —— 轮询 `Get-Process` 直到列表全退出,返回 `$true`(全退)/`$false`(超时)

- [ ] **Step 1: 追加 C# Add-Type 块 + 3 个函数**

在 `Wait-HttpReady` 函数之后追加:

```powershell
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
    $info.BasicLimitInformation.LimitFlags =
        [DevJobObject.Native+JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE]
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
            [DevJobObject.Native+JobObjectExtendedLimitInformation],
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
    param([int]$Pid)
    if ($script:DevJob -eq [IntPtr]::Zero) {
        throw 'Job Object not initialized; call New-KillOnCloseJob first'
    }
    $proc = [System.Diagnostics.Process]::GetProcessById($Pid)
    try {
        $ok = [DevJobObject.Native]::AssignProcessToJobObject(
            $script:DevJob, $proc.Handle)
        if (-not $ok) {
            throw [System.ComponentModel.Win32Exception]::new(
                [System.Runtime.InteropServices.Marshal]::GetLastWin32Error())
        }
        if (-not $script:DevJobPids.Contains($Pid)) {
            $script:DevJobPids.Add($Pid)
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
```

- [ ] **Step 2: 验证 Job Object 能成功创建并 assign 一个 sleep 子进程**

Run(打开新 PowerShell 一次完成):

```bash
powershell -NoProfile -ExecutionPolicy Bypass -Command @'
$here = (Get-Location).Path
& ./scripts/_job-helper.ps1
$sb = { & ./scripts/_job-helper.ps1; $h = New-KillOnCloseJob; Write-Host ("job handle: " + $h.ToInt64()) }
. $sb
# 启动一个 sleep 子进程
$child = Start-Process -FilePath "powershell.exe" -ArgumentList "-NoProfile","-Command","Start-Sleep -Seconds 30" -PassThru
Start-Sleep -Seconds 1
Add-ToJob -Pid $child.Id
Write-Host ("child pid assigned: " + $child.Id)
# 验证 Get-Process 能找到
Get-Process -Id $child.Id | Select-Object Id, ProcessName
# 现在 taskkill 帮助器自己,kill-on-close 应该带走子进程
Get-Process -Id $PID | Stop-Process -Force
'@
```
Expected: 子进程 `powershell` 出现一次,Stop-Process 帮助器后不久,子进程也被收尸(再开一个 shell `Get-Process -Id <child.Id>` 应找不到)。

> 注:这是验证 `KILL_ON_JOB_CLOSE` 真正生效。失败的话会有 `AssignProcessToJobObject` 抛 `Win32Exception`(常见原因:Job 已经赋过这个进程;或 P/Invoke 签名错误)。

- [ ] **Step 3: 验证 `Wait-JobEmpty` 在子进程退出后返回 true**

Run:

```bash
powershell -NoProfile -ExecutionPolicy Bypass -Command @'
& ./scripts/_job-helper.ps1
$h = New-KillOnCloseJob
$child = Start-Process -FilePath "powershell.exe" -ArgumentList "-NoProfile","-Command","Start-Sleep -Seconds 3" -PassThru
Add-ToJob -Pid $child.Id
Write-Host ("waiting for child pid " + $child.Id + " to exit...")
$ok = Wait-JobEmpty -TimeoutSeconds 10
Write-Host ("Wait-JobEmpty returned: " + $ok)
'@
```
Expected: `Wait-JobEmpty returned: True`(子进程 3 秒后自然退出,循环检测到全部不在)。

- [ ] **Step 4: 提交**

```bash
git add scripts/_job-helper.ps1
git commit -m "feat(scripts): add KILL_ON_JOB_CLOSE Job Object layer to helper"
```

---

## Task 6: `_job-helper.ps1` — PreFlight 命令

**Files:**
- Modify: `scripts/_job-helper.ps1`(实现 `-Command PreFlight` 分支)

**Interfaces:**
- Consumes: `$RepoRoot`,`$Command = 'PreFlight'`
- Produces: 旧 PID 进程树被杀,旧端口占用被杀,`storage\tmp\.dev-pids.json` 被删

- [ ] **Step 1: 实现 PreFlight 块**

把现在的 `if ($Command -eq 'PreFlight') { ... }` 块替换为:

```powershell
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
```

- [ ] **Step 2: 准备测试场景 —— 临时构造一个"旧 PID 文件"指向真实进程**

Run:

```bash
# 启动一个会持续运行的 sleep 子进程作为"旧后端"
$child = Start-Process -FilePath "powershell.exe" -ArgumentList "-NoProfile","-Command","Start-Sleep -Seconds 120" -PassThru
Write-PidFile storage/tmp/.dev-pids.json @{ backend=$child.Id; frontend=0; startedAt=(Get-Date).ToString('o') }
Get-Content storage/tmp/.dev-pids.json
```
Expected: PID 文件内容存在,记录 sleep 子进程 PID。

- [ ] **Step 3: 跑 PreFlight,验证旧 PID 被杀、PID 文件被删**

Run:

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\_job-helper.ps1 -Command PreFlight -RepoRoot "$PWD"
```
Expected:
- `PreFlight: killing stale backend PID <X>` warning 出现
- `PreFlight done.` 出现
- `storage\tmp\.dev-pids.json` 已删除

确认子进程被收尸:`Get-Process -Id <X>` 应找不到(进程已被 taskkill)。

- [ ] **Step 4: 提交**

```bash
git add scripts/_job-helper.ps1
git commit -m "feat(scripts): implement PreFlight command in helper"
```

---

## Task 7: `_job-helper.ps1` — RunServersAndWait 命令

**Files:**
- Modify: `scripts/_job-helper.ps1`(实现 `-Command RunServersAndWait` 分支)

**Interfaces:**
- Consumes: `$RepoRoot`,`$WaitSeconds`,端口(从 `.env`)
- Produces: 后端 uvicorn + 前端 vite 进程在跑且被收进 Job,`storage\tmp\.dev-pids.json` 已写,阻塞至子进程退出

- [ ] **Step 1: 实现 RunServersAndWait 块**

把现在的 `if ($Command -eq 'RunServersAndWait') { ... }` 块替换为:

```powershell
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

    # 1) Backend (uvicorn)
    $backend = Start-Process `
        -FilePath (Join-Path $RepoRoot 'backend\.venv\Scripts\python.exe') `
        -ArgumentList '-m','uvicorn','app.main:app','--port',"$backendPort" `
        -WorkingDirectory $RepoRoot `
        -RedirectStandardOutput $backendOut `
        -RedirectStandardError $backendErr `
        -PassThru
    Add-ToJob -Pid $backend.Id

    # 2) Frontend (vite) — pass env vars so vite.config.ts reads them
    $env:BACKEND_PORT = "$backendPort"
    $env:FRONTEND_PORT = "$frontendPort"
    $frontend = Start-Process `
        -FilePath 'npm.cmd' `
        -ArgumentList 'run','dev','--','--host','127.0.0.1','--port',"$frontendPort" `
        -WorkingDirectory (Join-Path $RepoRoot 'frontend') `
        -RedirectStandardOutput $frontendOut `
        -RedirectStandardError $frontendErr `
        -PassThru
    # Do NOT Add-ToJob with $frontend.Id — npm.cmd is a shim; the real PID is the port owner.

    # 3) Wait for readiness
    $backendReady = Wait-HttpReady "http://127.0.0.1:$backendPort/health" $WaitSeconds
    if (-not $backendReady) {
        Write-Warning "backend not responding on :$backendPort/health after $WaitSeconds s"
    }
    $frontendReady = Wait-HttpReady "http://127.0.0.1:$frontendPort/" $WaitSeconds
    if (-not $frontendReady) {
        Write-Warning "frontend not responding on :$frontendPort/ after $WaitSeconds s"
    }

    # 4) Identify the actual vite/node PID via port lookup, add to job
    $frontendPid = Get-PortOwnerPid $frontendPort
    if ($frontendPid -gt 0) {
        try {
            Add-ToJob -Pid $frontendPid
        } catch {
            Write-Warning "could not add frontend PID $frontendPid to Job: $($_.Exception.Message)"
        }
    } else {
        Write-Warning "could not identify frontend PID; will not be reaped"
    }

    # 5) Persist PID file
    try {
        Write-PidFile $pidFile @{
            backend   = $backend.Id
            frontend  = $frontendPid
            startedAt = (Get-Date).ToString('o')
        }
    } catch {
        Write-Warning "failed to write PID file: $($_.Exception.Message)"
    }

    # 6) Block until Job empty
    $null = Wait-JobEmpty -TimeoutSeconds 0
    exit 0
}
```

- [ ] **Step 2: 端到端验证 RunServersAndWait 真能起服务**

Run(从前台,Ctrl+C 测试):

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\_job-helper.ps1 -Command RunServersAndWait -RepoRoot "$PWD" -WaitSeconds 30
```
Expected:
- `:8000/health` 200
- `:5173/` 200
- `storage\tmp\.dev-pids.json` 写入
- Ctrl+C 后两端口都被释放

打开新 shell 验证服务在跑:

```bash
Invoke-WebRequest http://127.0.0.1:8000/health -UseBasicParsing | Select-Object StatusCode
Invoke-WebRequest http://127.0.0.1:5173/ -UseBasicParsing | Select-Object StatusCode
```
Expected: 两者 StatusCode 都是 200。

- [ ] **Step 3: 验证 Ctrl+C 收尸**

回到 RunServersAndWait 的 shell,Ctrl+C。

然后:
```bash
Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue
```
Expected: 两者都无输出(端口空闲)。

- [ ] **Step 4: 提交**

```bash
git add scripts/_job-helper.ps1
git commit -m "feat(scripts): implement RunServersAndWait with Job-Object reaping"
```

---

## Task 8: `start-dev.bat`

**Files:**
- Create: `scripts/start-dev.bat`

**Interfaces:**
- Consumes: 命令行 `-OpenBrowser` / `-WaitSeconds N`
- Produces: 调帮助器 `PreFlight` → `RunServersAndWait`,就绪后可选打开浏览器

- [ ] **Step 1: 写 `start-dev.bat`**

```bat
@echo off
REM scripts/start-dev.bat
REM Start ComfyChat backend + frontend with Job-Object reaping on exit.

setlocal

set "REPO_ROOT=%~dp0.."
pushd "%REPO_ROOT%" >nul
set "REPO_ROOT=%CD%"
popd >nul

set "OPEN_BROWSER=0"
set "WAIT_SECONDS=25"

:parse_args
if "%~1"=="" goto after_parse
if /i "%~1"=="-OpenBrowser" set "OPEN_BROWSER=1" & shift & goto parse_args
if /i "%~1"=="-WaitSeconds" (
    set "WAIT_SECONDS=%~2"
    shift
    shift
    goto parse_args
)
echo Unknown argument: %~1
exit /b 1

:after_parse

REM Preflight file checks
if not exist "backend\.venv\Scripts\python.exe" (
    echo [X] backend\.venv\ missing. Run setup from README.md first.
    exit /b 1
)
if not exist "frontend\node_modules" (
    echo [X] frontend\node_modules\ missing. Run 'cd frontend ^&^& npm install' first.
    exit /b 1
)
if not exist "storage\tmp" mkdir "storage\tmp" 2>nul

echo ==^> Pre-flight
powershell -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%\scripts\_job-helper.ps1" -Command PreFlight -RepoRoot "%REPO_ROOT%"
if errorlevel 1 exit /b 1

echo ==^> Starting backend + frontend (Ctrl+C to stop)
powershell -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%\scripts\_job-helper.ps1" -Command RunServersAndWait -RepoRoot "%REPO_ROOT%" -WaitSeconds %WAIT_SECONDS%
if errorlevel 1 exit /b 1

if "%OPEN_BROWSER%"=="1" start "" "http://127.0.0.1:5173/" >nul

endlocal
```

- [ ] **Step 2: 端到端跑 start-dev.bat**

Run:
```bash
cmd.exe /c scripts\start-dev.bat
```
预期:
- 两端口都起来
- `:8000/health` 与 `:5173/` 都返回 200
- 关掉窗口 / Ctrl+C 后端口被释放

- [ ] **Step 3: 跑 `-OpenBrowser`**

Run:
```bash
cmd.exe /c scripts\start-dev.bat -OpenBrowser
```
预期: 浏览器(或默认应用)被要求打开 `http://127.0.0.1:5173/`。

- [ ] **Step 4: 跑 `-WaitSeconds 2` 配慢启动,确认不报错退出**

```bash
cmd.exe /c scripts\start-dev.bat -WaitSeconds 2
```
预期: 启动后等 2 秒,可能打出 `backend not responding on :8000/health after 2 s` warning,但进程仍在跑;Ctrl+C 后端口释放。

- [ ] **Step 5: 提交**

```bash
git add scripts/start-dev.bat
git commit -m "feat(scripts): add start-dev.bat with helper delegation"
```

---

## Task 9: `stop-dev.bat`

**Files:**
- Create: `scripts/stop-dev.bat`

**Interfaces:**
- Consumes: `storage\tmp\.dev-pids.json`
- Produces: 两进程树被杀,端口被释放

- [ ] **Step 1: 写 `stop-dev.bat`**

```bat
@echo off
REM scripts/stop-dev.bat
REM Manually stop ComfyChat dev servers started by start-dev.bat.

setlocal
set "REPO_ROOT=%~dp0.."
pushd "%REPO_ROOT%" >nul
set "REPO_ROOT=%CD%"
popd >nul

set "PID_FILE=%REPO_ROOT%\storage\tmp\.dev-pids.json"

if not exist "%PID_FILE%" (
    echo [!] No PID file at %PID_FILE%. Nothing to stop.
    exit /b 0
)

echo Stopping ComfyChat dev servers...

REM Use PowerShell to parse JSON (we have it for the helper anyway)
for /f "usebackq tokens=*" %%B in (`powershell -NoProfile -Command "(Get-Content -LiteralPath '%PID_FILE%' -Raw | ConvertFrom-Json).backend"`) do set "BACKEND_PID=%%B"
for /f "usebackq tokens=*" %%F in (`powershell -NoProfile -Command "(Get-Content -LiteralPath '%PID_FILE%' -Raw | ConvertFrom-Json).frontend"`) do set "FRONTEND_PID=%%F"

if defined BACKEND_PID  taskkill /T /F /PID %BACKEND_PID%  2>nul
if defined FRONTEND_PID taskkill /T /F /PID %FRONTEND_PID% 2>nul

del /f /q "%PID_FILE%" 2>nul

REM Belt-and-suspenders port cleanup
for %%P in (8000 5173) do (
    for /f "tokens=5" %%O in ('netstat -ano ^| findstr :%%P ^| findstr LISTENING') do (
        echo [!] straggler on port %%P -^> PID %%O
        taskkill /T /F /PID %%O 2>nul
    )
)

echo Done.
endlocal
```

- [ ] **Step 2: 启动 `start-dev.bat`(后台),再跑 `stop-dev.bat`,验证收尸**

Run:

```bash
# 后台起 start-dev
Start-Process powershell -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File",".\scripts\start-dev.bat" -WindowStyle Hidden
Start-Sleep -Seconds 15
# 验证服务在跑
(Invoke-WebRequest http://127.0.0.1:8000/health -UseBasicParsing).StatusCode
(Invoke-WebRequest http://127.0.0.1:5173/ -UseBasicParsing).StatusCode
# 跑 stop-dev
cmd.exe /c scripts\stop-dev.bat
Start-Sleep -Seconds 2
# 验证端口释放
Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue
```
预期: 两个 StatusCode 都是 200;stop-dev 后两个端口都空闲。

- [ ] **Step 3: 提交**

```bash
git add scripts/stop-dev.bat
git commit -m "feat(scripts): add stop-dev.bat for manual cleanup"
```

---

## Task 10: 更新 `AGENTS.md`

**Files:**
- Modify: `AGENTS.md`(第 24、25、39 行;Quirks 段加一条)

**Interfaces:**
- Consumes: 当前 `AGENTS.md` 内容
- Produces: 文档化新 `.bat` 入口、Job-Object 保证、`.env` 端口覆盖

- [ ] **Step 1: 第 24 行 —— 把 `scripts\start-dev.ps1` 改为 `scripts\start-dev.bat`,补参数**

把:

```
- Start both: `powershell -ExecutionPolicy Bypass -File scripts\start-dev.ps1` (add `-OpenBrowser` to launch browser).
```

改为:

```
- Start both: `cmd /c scripts\start-dev.bat` (参数 `-OpenBrowser` 启动后开浏览器;`-WaitSeconds N` 改就绪等待超时,默认 25)。
```

- [ ] **Step 2: 第 25 行 —— 把 `scripts\stop-dev.ps1` 改为 `scripts\stop-dev.bat`**

把:

```
- Stop both: `powershell -ExecutionPolicy Bypass -File scripts\stop-dev.ps1`.
```

改为:

```
- Stop both: `cmd /c scripts\stop-dev.bat`。
```

- [ ] **Step 3: 第 39 行 —— 改写 PID file lock quirk,合并 Job-Object 与 .env 内容**

把:

```
- **`start-dev.ps1` PID file lock.** If services were killed mid-run, `storage/tmp/.dev-pids.json` persists and the next start refuses. Delete the file or run `stop-dev.ps1` first.
```

改为:

```
- **`start-dev.bat` PID file lock.** 如果上次启动后服务被杀,`storage/tmp/.dev-pids.json` 残留,下次 `start-dev.bat` 启动前会自动清理(由 `_job-helper.ps1 -Command PreFlight` 处理);也可用 `stop-dev.bat` 手动清理。
- **`start-dev.bat` 用 Windows Job Object 收尸子进程。** `_job-helper.ps1` 创建带 `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` 的 Job,把 uvicorn 与 vite 收进去。`.bat` 以任意方式退出(Ctrl+C、点 X、`taskkill /F`、崩溃)→ 帮助器退出 → OS 关闭 Job → 子进程被 TerminateProcess。
- **端口由根 `.env` 覆盖。** `BACKEND_PORT`(默认 8000)与 `FRONTEND_PORT`(默认 5173)由 `_job-helper.ps1` 读取,并通过 PowerShell `$env:` 传给 vite。`frontend/vite.config.ts` 通过 `process.env` 拿值,改 `.env` 后重启 vite 生效。
```

- [ ] **Step 4: 第 74 行 —— 修正 `scripts\start-dev.ps1` 引用为 `start-dev.bat`**

把现有的 `scripts\start-dev.ps1` / `stop-dev.ps1` 引用替换为 `start-dev.bat` / `stop-dev.bat`(其他文字保留)。

- [ ] **Step 5: 提交**

```bash
git add AGENTS.md
git commit -m "docs: switch documented launcher to .bat with Job-Object and .env port override"
```

---

## Task 11: 跑完整手动测试矩阵

**Files:** 无(纯验证)

**Interfaces:**
- 14 个场景来自 spec §"手动测试矩阵"

- [ ] **Step 1: 准备干净状态**

Run:
```bash
# 确保没有遗留进程 / 端口占用
cmd.exe /c scripts\stop-dev.bat
Get-NetTCPConnection -LocalPort 8000,5173 -State Listen -ErrorAction SilentlyContinue
```
预期: stop-dev 输出 `Done.`(或 `Nothing to stop`),两个端口都空闲。

- [ ] **Step 2: 测试 1 — Ctrl+C 释放端口**

Run:
```bash
Start-Process powershell -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File",".\scripts\start-dev.bat" -WindowStyle Hidden
Start-Sleep -Seconds 20
# 找到主 cmd 进程并 Ctrl+C 等价:taskkill 不带 /F,让它走 Ctrl+C 路径
$proc = Get-Process -Name cmd -ErrorAction SilentlyContinue | Select-Object -First 1
# 用 SendCtrlC 让 cmd 自己处理 Ctrl+C,而不是 taskkill /F
Add-Type -Name W -Namespace U -MemberDefinition '[DllImport("kernel32.dll")] public static extern bool GenerateConsoleCtrlEvent(uint e, uint p);'
[U.W]::GenerateConsoleCtrlEvent(0, $proc.Id)
Start-Sleep -Seconds 3
Get-NetTCPConnection -LocalPort 8000,5173 -State Listen -ErrorAction SilentlyContinue
```
预期: 两端口空闲。

- [ ] **Step 3: 测试 2 — 点 X / 关掉 cmd 窗口**

Run:
```bash
Start-Process powershell -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File",".\scripts\start-dev.bat" -WindowStyle Hidden
Start-Sleep -Seconds 20
$proc = Get-Process -Name cmd -ErrorAction SilentlyContinue | Select-Object -First 1
# 直接 taskkill cmd(模拟强制退出):taskkill 默认走关闭消息
taskkill /PID $proc.Id
Start-Sleep -Seconds 5
Get-NetTCPConnection -LocalPort 8000,5173 -State Listen -ErrorAction SilentlyContinue
```
预期: 两端口空闲。

- [ ] **Step 4: 测试 3 — `taskkill /F /IM cmd.exe`**

Run:
```bash
Start-Process powershell -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File",".\scripts\start-dev.bat" -WindowStyle Hidden
Start-Sleep -Seconds 20
taskkill /F /IM cmd.exe
Start-Sleep -Seconds 5
Get-NetTCPConnection -LocalPort 8000,5173 -State Listen -ErrorAction SilentlyContinue
```
预期: 两端口空闲。

- [ ] **Step 5: 测试 4 — 浏览器 + curl 正常服务**

Run:
```bash
Start-Process powershell -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File",".\scripts\start-dev.bat" -WindowStyle Hidden
Start-Sleep -Seconds 20
(Invoke-WebRequest http://127.0.0.1:8000/health -UseBasicParsing).StatusCode
(Invoke-WebRequest http://127.0.0.1:5173/ -UseBasicParsing).StatusCode
(Invoke-WebRequest http://127.0.0.1:5173/api/workflows -UseBasicParsing).StatusCode
# 清理
taskkill /F /IM cmd.exe
Start-Sleep -Seconds 3
```
预期: 三个 StatusCode 都是 200(或至少后端 200、vite 代理成功)。注意:实际值可能是 200 或被前端 SPA 路由重定向,这取决于 vite 配置;关键是没有 connection refused。

- [ ] **Step 6: 测试 5 — 端口被外部进程占用**

Run:
```bash
# 临时占住 :8000
python -m http.server 8000 --bind 127.0.0.1
Start-Sleep -Seconds 2
Get-NetTCPConnection -LocalPort 8000 -State Listen
# 启动 start-dev.bat(它会杀掉占用的进程)
Start-Process powershell -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File",".\scripts\start-dev.bat" -WindowStyle Hidden
Start-Sleep -Seconds 20
(Invoke-WebRequest http://127.0.0.1:8000/health -UseBasicParsing).StatusCode
# 清理
taskkill /F /IM cmd.exe
taskkill /F /IM python.exe
Start-Sleep -Seconds 3
```
预期: python http.server 被 taskkill,start-dev 后 :8000/health 仍 200(现在由 uvicorn 服务)。

- [ ] **Step 7: 测试 6 — 残留 PID 文件**

Run:
```bash
cmd.exe /c scripts\stop-dev.bat
Start-Process powershell -ArgumentList "-NoProfile","-Command","Start-Sleep -Seconds 120" -WindowStyle Hidden
Start-Sleep -Seconds 1
$fakePid = (Get-Process -Name powershell | Select-Object -First 1).Id
# 构造伪 PID 文件
'{ "backend": ' + $fakePid + ', "frontend": 0, "startedAt": "2026-08-11T00:00:00Z" }' | Set-Content -LiteralPath storage\tmp\.dev-pids.json
Get-Content storage\tmp\.dev-pids.json
# 启动 start-dev
Start-Process powershell -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File",".\scripts\start-dev.bat" -WindowStyle Hidden
Start-Sleep -Seconds 20
(Invoke-WebRequest http://127.0.0.1:8000/health -UseBasicParsing).StatusCode
# 验证原 powershell sleep 已死
Get-Process -Id $fakePid -ErrorAction SilentlyContinue
# 清理
taskkill /F /IM cmd.exe
Start-Sleep -Seconds 3
```
预期: PreFlight 杀掉原 sleep 子进程;start-dev 起来后 :8000/health 200;残留 PID 文件已被删除。

- [ ] **Step 8: 测试 7 — `-OpenBrowser`**

Run:
```bash
Start-Process powershell -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File",".\scripts\start-dev.bat","-OpenBrowser" -WindowStyle Hidden
Start-Sleep -Seconds 25
Get-Process | Where-Object { $_.MainWindowTitle -match '5173|ComfyChat' } | Select-Object Id, ProcessName, MainWindowTitle
# 清理
taskkill /F /IM cmd.exe
Start-Sleep -Seconds 3
```
预期: 一个浏览器进程(可能是 chrome / msedge)出现在进程列表中,标题含 `5173` 或页面 title(取决于默认浏览器)。手动可视确认更好。

- [ ] **Step 9: 测试 8 — `-WaitSeconds 2` 慢启动不报错**

Run:
```bash
Start-Process powershell -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File",".\scripts\start-dev.bat","-WaitSeconds","2" -WindowStyle Hidden
Start-Sleep -Seconds 30
Get-Content storage\tmp\backend.err.log -Tail 10
Get-NetTCPConnection -LocalPort 8000,5173 -State Listen -ErrorAction SilentlyContinue
# 清理
taskkill /F /IM cmd.exe
Start-Sleep -Seconds 3
```
预期: backend.err.log 含 `backend not responding on :8000/health after 2 s` warning(来自 _job-helper.ps1);两端口仍监听(进程仍在跑)。

- [ ] **Step 10: 测试 9 — 杀 uvicorn 不应让 vite 继续跑**

Run:
```bash
Start-Process powershell -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File",".\scripts\start-dev.bat" -WindowStyle Hidden
Start-Sleep -Seconds 20
$uvi = Get-NetTCPConnection -LocalPort 8000 -State Listen | Select-Object -ExpandProperty OwningProcess
taskkill /F /PID $uvi
Start-Sleep -Seconds 3
Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue
# vite 仍存活,直到 .bat 也退出
# 现在退出 .bat
$cmd = Get-Process -Name cmd -ErrorAction SilentlyContinue | Select-Object -First 1
taskkill /PID $cmd.Id
Start-Sleep -Seconds 3
Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue
```
预期: 杀 uvicorn 后 vite 仍在(只有当 .bat 退出,Job 收尸才会触发);退出 .bat 后 vite 也无。

- [ ] **Step 11: 测试 10 — `stop-dev.bat`**

Run:
```bash
Start-Process powershell -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File",".\scripts\start-dev.bat" -WindowStyle Hidden
Start-Sleep -Seconds 20
cmd.exe /c scripts\stop-dev.bat
Start-Sleep -Seconds 3
Get-NetTCPConnection -LocalPort 8000,5173 -State Listen -ErrorAction SilentlyContinue
Get-Content storage\tmp\.dev-pids.json -ErrorAction SilentlyContinue
```
预期: 两端口空闲;PID 文件已不存在。

- [ ] **Step 12: 测试 11 — `.env` 端口覆盖**

Run:
```bash
cmd.exe /c scripts\stop-dev.bat
# 临时改 .env
$content = Get-Content .env
$content += @('BACKEND_PORT=9000', 'FRONTEND_PORT=5174')
Set-Content -LiteralPath .env -Value $content
Start-Process powershell -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File",".\scripts\start-dev.bat" -WindowStyle Hidden
Start-Sleep -Seconds 25
Get-NetTCPConnection -LocalPort 9000,5174 -State Listen
# 验证 vite 代理打到 9000
(Invoke-WebRequest http://127.0.0.1:5174/api/workflows -UseBasicParsing).StatusCode
# 清理
taskkill /F /IM cmd.exe
Start-Sleep -Seconds 3
# 还原 .env
$content = Get-Content .env | Where-Object { $_ -notmatch '^(BACKEND_PORT|FRONTEND_PORT)=' }
Set-Content -LiteralPath .env -Value $content
```
预期: :9000 和 :5174 都监听;`/api/workflows` 经 vite 代理成功(200 或 SPA fallback,关键是后端可达)。

- [ ] **Step 13: 测试 12 — `.env` 端口非法值**

Run:
```bash
cmd.exe /c scripts\stop-dev.bat
$content = Get-Content .env
$content += 'BACKEND_PORT=abc'
Set-Content -LiteralPath .env -Value $content
Start-Process powershell -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File",".\scripts\start-dev.bat" -WindowStyle Hidden
Start-Sleep -Seconds 25
# 应该 warning + 用 8000
Get-NetTCPConnection -LocalPort 8000 -State Listen
Get-NetTCPConnection -LocalPort 5173 -State Listen
# 清理
taskkill /F /IM cmd.exe
Start-Sleep -Seconds 3
# 还原 .env
$content = Get-Content .env | Where-Object { $_ -ne 'BACKEND_PORT=abc' }
Set-Content -LiteralPath .env -Value $content
```
预期: warning `BACKEND_PORT 'abc' is not a valid port; using default 8000` 出现(在 stderr 或 backend.out.log);:8000 和 :5173 都监听。

- [ ] **Step 14: 测试 13 — 两端口相等**

Run:
```bash
cmd.exe /c scripts\stop-dev.bat
$content = Get-Content .env
$content += @('BACKEND_PORT=8000', 'FRONTEND_PORT=8000')
Set-Content -LiteralPath .env -Value $content
cmd.exe /c scripts\start-dev.bat -WaitSeconds 3
# 检查 exit code
echo Exit code: %errorlevel%
Get-NetTCPConnection -LocalPort 8000,5173 -State Listen -ErrorAction SilentlyContinue
# 还原 .env
$content = Get-Content .env | Where-Object { $_ -notmatch '^(BACKEND_PORT|FRONTEND_PORT)=' }
Set-Content -LiteralPath .env -Value $content
```
预期: start-dev.bat exit code 非 0;两端口都空闲(没启动任何东西)。

- [ ] **Step 15: 测试 14 — `.env` 注释(默认)**

Run:
```bash
cmd.exe /c scripts\stop-dev.bat
# .env 中两行仍是注释
Start-Process powershell -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File",".\scripts\start-dev.bat" -WindowStyle Hidden
Start-Sleep -Seconds 20
Get-NetTCPConnection -LocalPort 8000,5173 -State Listen
taskkill /F /IM cmd.exe
Start-Sleep -Seconds 3
```
预期: :8000 和 :5173 都监听。

- [ ] **Step 16: 提交验证日志(可选)**

如果任何测试未通过,**不要**继续。先用 `systematic-debugging` 技能调查根因,修对应 Task 后重跑矩阵。

- [ ] **Step 17: 最终提交(若需要)**

如果测试矩阵过程中有 AGENTS.md 之外的微调:

```bash
git status
git add <files>
git commit -m "fix(scripts): adjust based on manual test matrix findings"
```

---

## Self-Review (against spec)

逐条核对 spec 的要求:

- **Goal** — 11 个 Task 覆盖 .bat 入口、Job Object 收尸、.env 端口覆盖。✓
- **新增文件** — Task 8 (start-dev.bat)、Task 9 (stop-dev.bat)、Task 5-7 共同构建 _job-helper.ps1。✓
- **修改的文件** — Task 1 (.env)、Task 2 (vite.config.ts)、Task 10 (AGENTS.md)。✓
- **保留文件** — Task 10 描述了"现有 .ps1 保留在磁盘上"(没改它们)。✓
- **架构图** — Task 5-7 实现了 cmd.exe → powershell.exe(Job owner) → python.exe / node.exe 的拓扑。✓
- **`start-dev.bat` 流程** — Task 8 完整实现 7 步流程。✓
- **`stop-dev.bat` 流程** — Task 9 完整实现 5 步流程。✓
- **`_job-helper.ps1` 函数** — Task 3-5 实现所有 11 个导出函数。✓
- **`PreFlight` 步骤** — Task 6 完整实现 4 步。✓
- **`RunServersAndWait` 步骤** — Task 7 完整实现 6 步。✓
- **Job Object P/Invoke** — Task 5 实现 C# Add-Type + CreateJobObject + SetInformationJobObject(KILL_ON_JOB_CLOSE)+ AssignProcessToJobObject。✓
- **状态与数据流** — Task 6/7 的 PreFlight / RunServersAndWait 读写同一份 `.dev-pids.json`。✓
- **`.env` 改动** — Task 1 是纯追加。✓
- **`vite.config.ts` 改动** — Task 2 用 process.env 取值。✓
- **错误处理矩阵** — 各 Task 在注释中标注了对应错误行为(端口冲突、非法值、Job 失败等)。✓
- **手动测试矩阵 14 条** — Task 11 覆盖全部 14 条。✓
- **AGENTS.md 更新** — Task 10 改第 24/25/39 行。✓

类型 / 命名一致性:

- `New-KillOnCloseJob` / `Add-ToJob` / `Wait-JobEmpty` —— Task 5 定义,Task 7 使用,签名一致。✓
- `Get-BackendPort` / `Get-FrontendPort` —— Task 3 定义,Task 6/7 使用。✓
- `Get-PortOwnerPid` / `Kill-PortOwner` —— Task 4 定义,Task 6 使用。✓
- `Wait-HttpReady` —— Task 4 定义,Task 7 使用。✓
- `Read-PidFile` / `Write-PidFile` —— Task 3 定义,Task 6/7 使用。✓
- `Read-DotEnv` —— Task 3 定义,Task 3 的 Get-BackendPort/FrontendPort 内部使用。✓

无占位符、无 TBD、无"see Task N"重复。