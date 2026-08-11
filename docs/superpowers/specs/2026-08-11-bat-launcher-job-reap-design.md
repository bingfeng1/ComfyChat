# .bat 启动器 + Job Object 收尸 — 设计

**Date:** 2026-08-11
**Status:** Approved(头脑风暴完成;待写实现计划)

## Goal

把 PowerShell 的 `start-dev.ps1` / `stop-dev.ps1` 入口替换成 `.bat` 脚本,默认情况下保证:启动器以任意方式退出时(Ctrl+C、点 X、`taskkill /F`、崩溃),OS 都自动杀掉带起来的后端(:BACKEND_PORT)和前端(:FRONTEND_PORT)进程。

## Non-goals

- 跨平台支持(Linux / macOS);仅 Windows。
- 不编译独立 .exe 帮助器;使用 `.bat` 调用的小 `.ps1` 帮助器。
- 不把端口变量加进后端 `Settings` 模型。端口只由启动器和 `vite.config.ts` 读取,不进 pydantic。
- 不破坏现有 `.ps1` 脚本;它们保留在磁盘上,但不再是文档化的入口。

## 新增文件

| 路径 | 作用 |
|------|------|
| `scripts/start-dev.bat` | 默认入口。解析 `-OpenBrowser` 和 `-WaitSeconds N`;跑前置;启动帮助器。 |
| `scripts/stop-dev.bat` | 手动控制。`taskkill /T /F` 杀掉两棵树;兜底清理端口。 |
| `scripts/_job-helper.ps1` | PowerShell 帮助器。持有 Job Object;启动 uvicorn 和 vite;等就绪;向 `.bat` 回报。 |

## 修改的文件

| 路径 | 变更 |
|------|------|
| `.env` | 追加可选的注释行 `BACKEND_PORT=8000` 和 `FRONTEND_PORT=5173`。现有五个 `Settings` 字段不动。 |
| `frontend/vite.config.ts` | 读 `process.env.BACKEND_PORT` 和 `process.env.FRONTEND_PORT`(默认仍是 8000 / 5173),用于 `server.port` 和 `proxy["/api"].target`。 |
| `AGENTS.md` | 第 24、25、39 行改为指向 `.bat` 脚本,并描述 Job-Object 收尸保证。 |

## 保留文件(不再维护)

- `scripts/start-dev.ps1`、`scripts/stop-dev.ps1` —— 留在磁盘上,继续以相同格式读写 `storage/tmp/.dev-pids.json`,但不再作为文档化入口。

## 架构

```
cmd.exe (start-dev.bat)
  ├─ powershell.exe (_job-helper.ps1 -Command PreFlight)
  │     └─ 杀掉旧 PID 文件残留进程 + 端口占用者
  └─ powershell.exe (_job-helper.ps1 -Command RunServersAndWait)
        └─ 持有 Job Object 句柄 (KILL_ON_JOB_CLOSE)
              ├─ python.exe (uvicorn --port $BackendPort)  ← 收进 Job
              └─ node.exe (vite --port $FrontendPort)      ← 收进 Job(端口反查)
```

`.bat` 是会话的生命周期持有者。第一次 `powershell.exe`(`PreFlight`)快速返回退出。第二次(`RunServersAndWait`)阻塞在内部循环,只在 `.bat` 父进程消失时才退出。只要 `.bat` 活着,Job 句柄就活着;`.bat` 一退出(任何原因),OS 关闭 Job,`KILL_ON_JOB_CLOSE` 把所有收进 Job 的进程(含其未来 fork 的子进程 —— vite 热重载、uvicorn 重载器)一并 TerminateProcess。

## 组件:`start-dev.bat`

参数:

- `-OpenBrowser` —— 开关;就绪后通过 `start ""` 打开 `http://127.0.0.1:<FRONTEND_PORT>/`。
- `-WaitSeconds N` —— 整数 ≥ 1,默认 `25`。两个 HTTP 端点的就绪等待预算。

流程:

1. `cd /d "%~dp0\.."` 切到仓库根。
2. 前置文件检查:`backend\.venv\Scripts\python.exe`、`frontend\node_modules`。缺失则 echo 错误 + `exit /b 1`。
3. `mkdir storage\tmp 2>nul`。
4. 调 `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\_job-helper.ps1 -Command PreFlight -RepoRoot "%REPO_ROOT%"`。非零退出则向上传播。
5. 调 `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\_job-helper.ps1 -Command RunServersAndWait -RepoRoot "%REPO_ROOT%" -WaitSeconds N`。在这里阻塞。
6. 若两个端点都已就绪 **且** 传了 `-OpenBrowser` → `start "" http://127.0.0.1:<FRONTEND_PORT>/`。
7. `.bat` 退出。帮助器退出时 OS 关闭 Job。子进程被收尸。

注:步骤 5 在用户保持启动器开启期间会一直阻塞。按 `AGENTS.md` 已建立的规则,助手不得在 shell 工具调用里直接跑 `start-dev.bat` —— 用户自己跑,或助手用 `Start-Process powershell … -WindowStyle Hidden` 分离启动。

## 组件:`stop-dev.bat`

1. 读 `storage\tmp\.dev-pids.json`。文件不存在则警告 + `exit /b 0`。
2. `taskkill /T /F /PID <backend>` 与 `taskkill /T /F /PID <frontend>`。
3. 删除 PID 文件。
4. 对从 `.env` 解析出的 `BACKEND_PORT`、`FRONTEND_PORT`(默认 8000 / 5173)分别查端口所有者,若 `netstat -ano | findstr :<port>` 出现 LISTENING 行则 `taskkill /T /F /PID <owner>`。
5. 输出 `Done.`

## 组件:`_job-helper.ps1`

导出的函数:

```powershell
function New-KillOnCloseJob                 -> [IntPtr]   # Job 句柄
function Add-ToJob([IntPtr]$Job, [int]$Pid) -> void       # AssignProcess
function Wait-HttpReady(
  [string]$Url,
  [int]$TimeoutSeconds
)                                            -> [bool]    # 预算内 200 则 true
function Get-PortOwnerPid([int]$Port)       -> [int]      # 0 = 空闲
function Kill-PortOwner([int]$Port)         -> void
function Read-PidFile([string]$Path)        -> object     # 文件不存在返回 $null
function Write-PidFile(
  [string]$Path,
  [hashtable]$Obj
)                                           -> void
function Read-DotEnv([string]$Path)         -> hashtable  # KEY=VALUE;跳过 # 和空行
function Get-BackendPort                    -> [int]      # 默认 8000
function Get-FrontendPort                   -> [int]      # 默认 5173
```

脚本主体接收 `-Command <PreFlight|RunServersAndWait>` 并分发:

### `-Command PreFlight`

1. `Read-PidFile storage\tmp\.dev-pids.json`。对每个记录的 PID,`Get-Process` 查得到就 `taskkill /T /F /PID <pid>`。
2. 删 PID 文件(best effort)。
3. 解析 `BackendPort = Get-BackendPort`、`FrontendPort = Get-FrontendPort`。
4. `Kill-PortOwner $BackendPort` 和 `Kill-PortOwner $FrontendPort`(空闲则跳过)。

### `-Command RunServersAndWait -RepoRoot <path> -WaitSeconds <int>`

1. 通过 `Get-BackendPort` / `Get-FrontendPort` 取端口,验证两者不等;相等则抛错。
2. `$job = New-KillOnCloseJob`。Win32 调用失败则抛错。
3. 后端:`Start-Process python.exe -ArgumentList '-m','uvicorn','app.main:app','--port',$BackendPort -WorkingDirectory $RepoRoot -RedirectStandardOutput/Error storage\tmp\backend.{out,err}.log -PassThru`。`$backend = $proc`。`Add-ToJob $job $backend.Id`。
4. 前端:`Start-Process npm.cmd -ArgumentList 'run','dev','--','--host','127.0.0.1','--port',$FrontendPort -WorkingDirectory "$RepoRoot\frontend" -RedirectStandardOutput/Error storage\tmp\frontend.{out,err}.log -PassThru`。**不取 PID** —— `npm.cmd` 是 .cmd 垫片,真正的 `node.exe` PID 等会儿从端口反查。
5. 轮询 `$BackendPort` health:`Wait-HttpReady "http://127.0.0.1:$BackendPort/health" $WaitSeconds`。false 则往 stderr 写 `backend not responding on :$BackendPort/health after Ns`,继续(Job 还持有进程)。
6. 轮询 `$FrontendPort`:`Wait-HttpReady "http://127.0.0.1:$FrontendPort/" $WaitSeconds`。同上 warning 行为。
7. `$frontendPid = Get-PortOwnerPid $FrontendPort`。`> 0` 则 `Add-ToJob $job $frontendPid`;等于 0 则往 stderr 写 warning `could not identify frontend PID; will not be reaped` 并继续。
8. `Write-PidFile storage\tmp\.dev-pids.json @{ backend=$backend.Id; frontend=$frontendPid; startedAt=(Get-Date).ToString('o') }`。失败则 warning,不中断。
9. 内部轮询循环 —— 等到 Job 的活跃进程数为 0(不是 PowerShell `Wait-Job` cmdlet,是帮助器自己用 P/Invoke 查 Job 的 active process count)。返回后帮助器退出;若用户已关闭启动器则 `.bat` 已死,否则 `.bat` 继续走到自己末尾。两种情况下帮助器进程退出 → OS 关闭最后一个 Job 句柄 → `KILL_ON_JOB_CLOSE` 触发 → 仍在 Job 里的进程被收尸。

### `New-KillOnCloseJob` 实现要点

- 用 `Add-Type` + C# P/Invoke(或 `[Runtime.InteropServices.NativeLibrary]` + 委托)调:
  - `CreateJobObject(IntPtr.Zero, null)` → 拿句柄。
  - `SetInformationJobObject(handle, JobObjectExtendedLimitInformation, &info, sizeof(info))`,`JOBOBJECT_BASIC_LIMIT_INFORMATION` 标志含 `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` (0x2000)。
- 句柄只以 `[IntPtr]` 局部变量持有在帮助器进程内,无需显式 `CloseHandle` —— 进程退出时 GC 顺手释放。

### `Wait-HttpReady` 实现要点

- 循环用 `Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2`。200 返回 `$true`;任何异常(超时、connection refused)返回 `$false`。每次间隔 1 秒。预算耗尽则停。

### `Read-DotEnv` 实现要点

- `Get-Content -Path $Path` 一行行读。
- 每行 trim,空行跳过,以 `#` 开头跳过。
- 在第一个 `=` 切:左边 key(trim),右边 value(trim;去掉外层 `"` / `'`)。
- 返回 `hashtable`。文件不存在 → 空 hashtable(调用方落回默认值)。

## 状态与数据流

| 文件 | 写入者 | 读取者 | 删除者 |
|------|--------|--------|--------|
| `storage\tmp\.dev-pids.json` | `RunServersAndWait` 步骤 8 | `PreFlight` 步骤 1、`stop-dev.bat` 步骤 1 | `PreFlight` 步骤 2、`stop-dev.bat` 步骤 3 |
| `storage\tmp\backend.out.log` | uvicorn stdout | 用户(手动 tail) | 不删 |
| `storage\tmp\backend.err.log` | uvicorn stderr | 用户 | 不删 |
| `storage\tmp\frontend.out.log` | vite stdout | 用户 | 不删 |
| `storage\tmp\frontend.err.log` | vite stderr | 用户 | 不删 |

PID 文件格式(不变):

```json
{ "backend": 1234, "frontend": 5678, "startedAt": "2026-08-11T..." }
```

Job Object 句柄 **绝不** 序列化、导出或跨进程传递,只在 `RunServersAndWait` 调用内部存活。

## `.env` 改动

在根 `.env` 末尾追加:

```
# Dev ports (optional — read by start-dev.bat / vite.config.ts).
# Defaults are 8000 and 5173; uncomment and edit to override.
# BACKEND_PORT=8000
# FRONTEND_PORT=5173
```

现有 5 个 `Settings` 字段及其值不动。

## `frontend/vite.config.ts` 改动

```ts
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

`process.env.BACKEND_PORT` / `FRONTEND_PORT` 由帮助器通过 PowerShell 的 `$env:` 自动传播给子进程 —— 不需要 `dotenv` 包。

## 错误处理矩阵

### 启动前(`.bat` 或 `PreFlight`)

| 场景 | 行为 |
|------|------|
| `backend\.venv\Scripts\python.exe` 不存在 | `.bat` echo 错误 + `exit /b 1` |
| `frontend\node_modules` 不存在 | `.bat` echo 错误 + `exit /b 1` |
| `.dev-pids.json` 存在,记录 PID 还活着 | `PreFlight` 步骤 1:`taskkill /T /F`,继续 |
| `.dev-pids.json` 存在,记录 PID 已死 | `PreFlight` 步骤 1:跳过 kill,删文件,继续 |
| 端口 `BACKEND_PORT` / `FRONTEND_PORT` 被外部进程占用 | `PreFlight` 步骤 4:`taskkill /T /F`,继续 |
| `BACKEND_PORT == FRONTEND_PORT` | `RunServersAndWait` 步骤 1:抛错,`.bat` 非零退出 |
| `.env` 中 `BACKEND_PORT` 非数字 | `Get-BackendPort` warning,默认 8000 |

### 启动中(`RunServersAndWait`)

| 场景 | 行为 |
|------|------|
| `New-KillOnCloseJob` 失败(Win32 错误) | 抛错;不写 PID 文件;`.bat` 非零退出 |
| 后端 `Start-Process` 返回的进程立即退出非零 | 通过 `$backend.ExitCode`(或短暂 wait + `HasExited`)检测;抛错;不写 PID 文件 |
| 后端 HTTP 在 `WaitSeconds` 内未就绪 | warning 到 stderr;继续(Job 仍持有进程) |
| 前端 HTTP 在 `WaitSeconds` 内未就绪 | warning;继续 |
| `Get-PortOwnerPid` 对前端返回 0 | warning `could not identify frontend PID; will not be reaped`;继续 |
| `Write-PidFile` 失败 | warning;继续(Job Object 才是真正的安全网) |

### 退出时

| 场景 | 行为 |
|------|------|
| 用户在启动器控制台 Ctrl+C | 控制台广播 `CTRL_BREAK_EVENT`;`.bat` 死;帮助器死;Job 关;子进程收尸 |
| 用户点 X 关掉控制台窗口 | 同上 |
| `taskkill /F /PID <cmd.exe>` | 同上 |
| 后端运行中崩溃 | 内部轮询看到活跃进程数掉到 0(vite 仍存活);帮助器立即退出;OS 在 Job 句柄关闭时收掉幸存的 vite |
| 断电 | 不在范围内 |

### 不在范围内

- Vite 热重载 fork 出来的额外 `node.exe` 子进程:已被覆盖 —— `JOB_OBJECT_LIMIT_BREAKAWAY_OK` 是默认,vite 不会用 `CREATE_BREAKAWAY_FROM_JOB` 创建进程。
- 用户双击 `.bat` 时工作目录不对:由 `cd /d "%~dp0\.."` 处理。
- PATH 找不到 `powershell.exe`:不处理(在支持的 Windows 上极少发生)。

## 手动测试矩阵

除非特别说明,所有场景假设干净状态(无残留 PID、端口空闲)。

| # | 场景 | 预期 |
|---|------|------|
| 1 | 跑 `scripts\start-dev.bat` 后按 Ctrl+C | 两个端口都被释放 |
| 2 | 跑 `scripts\start-dev.bat` 后点 X 关掉控制台 | 两个端口都被释放 |
| 3 | 跑 `scripts\start-dev.bat` 后 `taskkill /F /IM cmd.exe` 杀掉启动器 | 两个端口都被释放 |
| 4 | 跑 `scripts\start-dev.bat`,浏览器访问 `:5173`、curl `:8000/health` | 都正常服务 |
| 5 | 预先用一个无关 `python.exe` 占住 `:8000`,再跑 `start-dev.bat` | `PreFlight` 杀掉它;启动器正常服务 |
| 6 | 留下一个 `.dev-pids.json`(其中 PID 还活着),跑 `start-dev.bat` | `PreFlight` 杀掉它们;启动器正常服务 |
| 7 | `scripts\start-dev.bat -OpenBrowser` | 就绪后浏览器自动打开 `http://127.0.0.1:5173/` |
| 8 | `scripts\start-dev.bat -WaitSeconds 2`,后端冷启动慢 | warning 打出;不报错退出;进程继续在跑 |
| 9 | `start-dev.bat` 起来后 `taskkill /F /PID <python.exe>`(uvicorn) | 内部轮询看到活跃数 → 1;帮助器**不**退出;OS 保持 Job 直到用户关掉启动器。用户关掉后两进程都没了 |
| 10 | `scripts\stop-dev.bat`(启动器没在跑,但 PID 文件存在) | 两个 PID 都被杀;端口释放 |
| 11 | `.env` 设 `BACKEND_PORT=9000 FRONTEND_PORT=5174`,跑启动器 | `:9000` 和 `:5174` 都监听;前端 `/api/*` 经 vite 代理成功打到 `:9000`(用 curl 验证) |
| 12 | `.env` 设 `BACKEND_PORT=abc`(无效) | warning;默认 8000 |
| 13 | `.env` 设 `BACKEND_PORT == FRONTEND_PORT` | 启动器在启动任何东西之前报错退出 |
| 14 | `.env` 中这两行被注释掉 | 默认 8000 / 5173 |

### 验收清单

- [ ] 测试 1–3 各自释放两个端口
- [ ] 测试 4、7–10 表现如列表
- [ ] 测试 5、6 确认清理路径
- [ ] 测试 11–14 确认 `.env` 驱动的端口覆盖和校验
- [ ] `AGENTS.md` 第 24、25、39 行已更新
- [ ] `.ps1` 文件保留在磁盘但不再作为文档化入口
- [ ] `.env` 改动是纯追加(不动现有 5 行)

## `AGENTS.md` 改动

- 第 24 行:`scripts\start-dev.ps1` 引用改为 `scripts\start-dev.bat`,并补 `-OpenBrowser` 和 `-WaitSeconds N` 参数说明。
- 第 25 行:`scripts\stop-dev.ps1` 引用改为 `scripts\stop-dev.bat`。
- 第 39 行:现有的 `start-dev.ps1 PID file lock` quirk 替换为 `.bat` 综合 quirk,涵盖 (a) `.dev-pids.json` 锁、(b) Job-Object 收尸保证、(c) `.env` 端口覆盖。

另外在 `## Quirks` 段新增一条:描述新的 `_job-helper.ps1` 边界以及基于环境变量的端口向 vite 传播。