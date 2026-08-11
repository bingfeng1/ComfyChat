# .bat Launcher with Job-Object Reaping — Design

**Date:** 2026-08-11
**Status:** Approved (brainstorming complete; pending implementation plan)

## Goal

Replace the PowerShell `start-dev.ps1` / `stop-dev.ps1` entry points with `.bat` scripts that, by default, guarantee backend (:BACKEND_PORT) and frontend (:FRONTEND_PORT) processes are killed by the OS whenever the launcher exits — for any reason (Ctrl+C, X-button, `taskkill /F`, crash).

## Non-goals

- Cross-platform support (Linux/macOS); Windows-only.
- A compiled helper binary; use a small `.ps1` helper invoked from the `.bat`.
- Adding the port variables to the backend `Settings` model. They are read only by the launcher and `vite.config.ts`, not by pydantic.
- Breaking the existing `.ps1` scripts; they remain on disk but are no longer the documented entry point.

## Files added

| Path | Role |
|------|------|
| `scripts/start-dev.bat` | Default entry point. Parses `-OpenBrowser` and `-WaitSeconds N`; runs preflight; spawns the helper. |
| `scripts/stop-dev.bat` | Manual control. Kills both trees via `taskkill /T /F`; belt-and-suspenders port cleanup. |
| `scripts/_job-helper.ps1` | PowerShell helper. Owns the Job Object; runs uvicorn and vite; waits for readiness; reports state back to `.bat`. |

## Files modified

| Path | Change |
|------|--------|
| `.env` | Append optional commented `BACKEND_PORT=8000` and `FRONTEND_PORT=5173`. Existing five `Settings` fields untouched. |
| `frontend/vite.config.ts` | Read `process.env.BACKEND_PORT` and `process.env.FRONTEND_PORT` (with the existing 8000 / 5173 defaults). Use them for `server.port` and `proxy["/api"].target`. |
| `AGENTS.md` | Update lines 24 / 25 / 39 to point at the `.bat` scripts and describe the Job-Object guarantee. |

## Files preserved (not maintained)

- `scripts/start-dev.ps1`, `scripts/stop-dev.ps1` — kept on disk so users on `.bat`-less shells still have something, but removed from the documented entry point. They continue to write/read `storage/tmp/.dev-pids.json` in the same format.

## Architecture

```
cmd.exe (start-dev.bat)
  ├─ powershell.exe (_job-helper.ps1 -Command PreFlight)
  │     └─ kills old PID file processes + port owners
  └─ powershell.exe (_job-helper.ps1 -Command RunServersAndWait)
        └─ owns the Job Object handle (KILL_ON_JOB_CLOSE)
              ├─ python.exe (uvicorn --port $BackendPort)  ← assigned to Job
              └─ node.exe (vite --port $FrontendPort)      ← assigned to Job (via port lookup)
```

The `.bat` is the lifetime owner of the session. The first `powershell.exe` (`PreFlight`) returns quickly and exits. The second (`RunServersAndWait`) blocks on `Wait-Job` and exits only when its `.bat` parent goes away. As long as the `.bat` is alive, the Job handle is alive; as soon as the `.bat` exits for any reason, the OS closes the Job, and the `KILL_ON_JOB_CLOSE` flag terminates every process assigned to it (including their future children — vite reloads, uvicorn reloaders).

## Component: `start-dev.bat`

Parameters:

- `-OpenBrowser` — switch; on readiness, launch `http://127.0.0.1:5173/` (or whatever `FRONTEND_PORT` resolves to) via `start ""`.
- `-WaitSeconds N` — integer ≥ 1, default `25`. Readiness-wait budget for both HTTP endpoints.

Flow:

1. `cd /d "%~dp0\.."` to repo root.
2. Preflight file checks: `backend\.venv\Scripts\python.exe`, `frontend\node_modules`. Missing → echo error + `exit /b 1`.
3. `mkdir storage\tmp 2>nul`.
4. Call `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\_job-helper.ps1 -Command PreFlight -RepoRoot "%REPO_ROOT%"`. If non-zero exit, propagate.
5. Call `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\_job-helper.ps1 -Command RunServersAndWait -RepoRoot "%REPO_ROOT%" -WaitSeconds N`. Blocks here.
6. If both endpoints reported ready **and** `-OpenBrowser` was passed → `start "" http://127.0.0.1:<FRONTEND_PORT>/`.
7. `.bat` exits. OS closes the Job when the helper exits. Children are reaped.

Note: step 5 blocks the `.bat` for as long as the user keeps the launcher open. Per the established rule in `AGENTS.md`, the assistant must never invoke `start-dev.bat` directly from a shell tool call — users run it themselves, or the assistant launches it detached via `Start-Process powershell … -WindowStyle Hidden`.

## Component: `stop-dev.bat`

1. Read `storage\tmp\.dev-pids.json`. Missing → warn + `exit /b 0`.
2. `taskkill /T /F /PID <backend>` and `taskkill /T /F /PID <frontend>`.
3. Delete the PID file.
4. For each port in `BACKEND_PORT, FRONTEND_PORT` (resolved from `.env` with defaults): if `netstat -ano | findstr :<port>` shows a LISTENING row, `taskkill /T /F /PID <owner>`.
5. Echo `Done.`

## Component: `_job-helper.ps1`

Exports these functions:

```powershell
function New-KillOnCloseJob                 -> [IntPtr]   # Job handle
function Add-ToJob([IntPtr]$Job, [int]$Pid) -> void       # AssignProcess
function Wait-HttpReady(
  [string]$Url,
  [int]$TimeoutSeconds
)                                            -> [bool]    # true if 200 within budget
function Get-PortOwnerPid([int]$Port)       -> [int]      # 0 if free
function Kill-PortOwner([int]$Port)         -> void
function Read-PidFile([string]$Path)        -> object     # $null if missing
function Write-PidFile(
  [string]$Path,
  [hashtable]$Obj
)                                           -> void
function Read-DotEnv([string]$Path)         -> hashtable  # KEY=VALUE lines; skips # and blanks
function Get-BackendPort                    -> [int]      # default 8000
function Get-FrontendPort                   -> [int]      # default 5173
```

The script body accepts `-Command <PreFlight|RunServersAndWait>` and dispatches:

### `-Command PreFlight`

1. `Read-PidFile storage\tmp\.dev-pids.json`. For each recorded PID: if `Get-Process` finds it, `taskkill /T /F /PID <pid>`.
2. Delete the PID file (best effort).
3. Resolve `BackendPort = Get-BackendPort`, `FrontendPort = Get-FrontendPort`.
4. `Kill-PortOwner $BackendPort` and `Kill-PortOwner $FrontendPort` (skip if already free).

### `-Command RunServersAndWait -RepoRoot <path> -WaitSeconds <int>`

1. Resolve ports via `Get-BackendPort` / `Get-FrontendPort`. Validate they differ; if equal → throw.
2. `$job = New-KillOnCloseJob`. If Win32 call fails → throw.
3. Backend: `Start-Process python.exe -ArgumentList '-m','uvicorn','app.main:app','--port',$BackendPort -WorkingDirectory $RepoRoot -RedirectStandardOutput/Error storage\tmp\backend.{out,err}.log -PassThru`. `$backend = $proc`. `Add-ToJob $job $backend.Id`.
4. Frontend: `Start-Process npm.cmd -ArgumentList 'run','dev','--','--host','127.0.0.1','--port',$FrontendPort -WorkingDirectory "$RepoRoot\frontend" -RedirectStandardOutput/Error storage\tmp\frontend.{out,err}.log -PassThru`. **Do not** capture the PID — npm.cmd is a `.cmd` shim; the actual node.exe PID is the port owner.
5. Poll `$BackendPort` health: `Wait-HttpReady "http://127.0.0.1:$BackendPort/health" $WaitSeconds`. If false → write `backend not responding on :$BackendPort/health after Ns` to stderr but continue (Job still holds the process).
6. Poll `$FrontendPort`: `Wait-HttpReady "http://127.0.0.1:$FrontendPort/" $WaitSeconds`. If false → similar warning.
7. `$frontendPid = Get-PortOwnerPid $FrontendPort`. If `> 0`, `Add-ToJob $job $frontendPid`. If `0`, write warning `could not identify frontend PID; will not be reaped` to stderr and continue.
8. `Write-PidFile storage\tmp\.dev-pids.json @{ backend=$backend.Id; frontend=$frontendPid; startedAt=(Get-Date).ToString('o') }`. If write fails → warning, do not abort.
9. `Wait-Job` — a helper-internal polling loop on the Job's active-process count (not the PowerShell `Wait-Job` cmdlet). It blocks until active count drops to 0 (all assigned processes exited). When it returns, the helper exits. If the user has already closed the launcher console, the `.bat` is already dead; otherwise the `.bat` proceeds to its own end. Either way the helper process exits, the OS closes the last Job handle, and `KILL_ON_JOB_CLOSE` fires — reaping any process still assigned.

### Implementation notes for `New-KillOnCloseJob`

- Use `Add-Type` with C# P/Invoke (or `[Runtime.InteropServices.NativeLibrary]` + delegates) to call:
  - `CreateJobObject(IntPtr.Zero, null)` → handle.
  - `SetInformationJobObject(handle, JobObjectExtendedLimitInformation, &info, sizeof(info))` with `JOBOBJECT_BASIC_LIMIT_INFORMATION` flags containing `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` (0x2000).
  - The helper keeps the handle in a `[IntPtr]` local. No need to ever call `CloseHandle` explicitly — the GC closes it when the helper process exits.

### Implementation notes for `Wait-HttpReady`

- Loop with `Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2`. On `200` return `$true`. On any exception (timeout, connection refused) `$false`. Sleep 1 s between attempts. Stop when budget exhausted.

### Implementation notes for `Read-DotEnv`

- `Get-Content -Path $Path` line-by-line.
- For each line: trim, skip empty, skip lines starting with `#`.
- Split on first `=`. Left = key (trim). Right = value (trim; strip surrounding `"` or `'`).
- Return `hashtable`. Missing file → empty hashtable (caller falls back to defaults).

## State and data flow

| File | Written by | Read by | Deleted by |
|------|------------|---------|------------|
| `storage\tmp\.dev-pids.json` | `RunServersAndWait` step 8 | `PreFlight` step 1, `stop-dev.bat` step 1 | `PreFlight` step 2, `stop-dev.bat` step 3 |
| `storage\tmp\backend.out.log` | uvicorn stdout | users (manual tail) | never |
| `storage\tmp\backend.err.log` | uvicorn stderr | users | never |
| `storage\tmp\frontend.out.log` | vite stdout | users | never |
| `storage\tmp\frontend.err.log` | vite stderr | users | never |

PID file format (unchanged):

```json
{ "backend": 1234, "frontend": 5678, "startedAt": "2026-08-11T..." }
```

The Job Object handle is **never** serialized, exported, or shared across processes. It lives only inside the `RunServersAndWait` invocation.

## `.env` patch

Append at the bottom of the existing root `.env`:

```
# Dev ports (optional — read by start-dev.bat / vite.config.ts).
# Defaults are 8000 and 5173; uncomment and edit to override.
# BACKEND_PORT=8000
# FRONTEND_PORT=5173
```

The five existing `Settings` fields and their values are unchanged.

## `frontend/vite.config.ts` patch

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

`process.env.BACKEND_PORT` / `FRONTEND_PORT` are populated by the helper via PowerShell's `$env:` propagation to child processes — no `dotenv` package required.

## Error handling matrix

### Before launch (`.bat` or `PreFlight`)

| Scenario | Behaviour |
|----------|-----------|
| `backend\.venv\Scripts\python.exe` missing | `.bat` echoes error, `exit /b 1` |
| `frontend\node_modules` missing | `.bat` echoes error, `exit /b 1` |
| `.dev-pids.json` exists, recorded PID alive | `PreFlight` step 1: `taskkill /T /F`, continue |
| `.dev-pids.json` exists, recorded PID dead | `PreFlight` step 1: skip kill, delete file, continue |
| Port `BACKEND_PORT` / `FRONTEND_PORT` held by external process | `PreFlight` step 4: `taskkill /T /F`, continue |
| `BACKEND_PORT == FRONTEND_PORT` | `RunServersAndWait` step 1: throw; `.bat` exits non-zero |
| `BACKEND_PORT` non-numeric in `.env` | `Get-BackendPort` warning, default 8000 |

### During launch (`RunServersAndWait`)

| Scenario | Behaviour |
|----------|-----------|
| `New-KillOnCloseJob` fails (Win32 error) | Throw; no PID file written; `.bat` exits non-zero |
| Backend `Start-Process` returns a process that immediately exits non-zero | Detect via `$backend.ExitCode` (or wait briefly + `HasExited`); throw; no PID file |
| Backend HTTP not ready within `WaitSeconds` | Warning to stderr; continue (Job still holds the process) |
| Frontend HTTP not ready within `WaitSeconds` | Warning; continue |
| `Get-PortOwnerPid` returns 0 for frontend | Warning `could not identify frontend PID; will not be reaped`; continue |
| `Write-PidFile` fails | Warning; continue (Job Object is the real safety net) |

### At exit

| Scenario | Behaviour |
|----------|-----------|
| User Ctrl+C in launcher console | Console sends `CTRL_BREAK_EVENT`; `.bat` dies; helper dies; Job closes; children reaped |
| User clicks X on console window | Same path |
| `taskkill /F /PID <cmd.exe>` | Same path |
| Backend crashes mid-run | `Wait-Job` polling loop sees active count drop to 0 (vite still alive); helper exits immediately; the OS reap on Job-handle-close takes the surviving vite process |
| Power outage | Not in scope |

### Out of scope

- Vite reload spawning extra `node.exe` children: covered — `JOB_OBJECT_LIMIT_BREAKAWAY_OK` is the default and vite never calls `CreateProcess` with `CREATE_BREAKAWAY_FROM_JOB`.
- User double-clicking the `.bat` and the working directory being wrong: handled by `cd /d "%~dp0\.."`.
- PATH missing `powershell.exe`: not handled (vanishingly rare on supported Windows).

## Manual test matrix

All scenarios assume a clean state (no orphan PIDs, ports free) unless noted.

| # | Scenario | Expected |
|---|----------|----------|
| 1 | Run `scripts\start-dev.bat`; press Ctrl+C | Both ports released |
| 2 | Run `scripts\start-dev.bat`; click X on console | Both ports released |
| 3 | Run `scripts\start-dev.bat`; `taskkill /F /IM cmd.exe` on the launcher | Both ports released |
| 4 | Run `scripts\start-dev.bat`; use browser at `:5173` and curl `:8000/health` | Both serve |
| 5 | Pre-occupy `:8000` with an unrelated `python.exe`; run `start-dev.bat` | `PreFlight` kills it; launcher serves normally |
| 6 | Leave a stale `.dev-pids.json` whose PIDs are alive; run `start-dev.bat` | `PreFlight` kills them; launcher serves normally |
| 7 | `scripts\start-dev.bat -OpenBrowser` | On readiness, browser opens to `http://127.0.0.1:5173/` |
| 8 | `scripts\start-dev.bat -WaitSeconds 2` with a slow backend cold start | Warning printed; no error exit; processes keep running |
| 9 | `start-dev.bat` then `taskkill /F /PID <python.exe>` (uvicorn) | `Wait-Job` polling sees active count → 1; helper does **not** exit yet; OS keeps Job alive until user closes launcher. When user closes launcher, both processes are gone. |
| 10 | `scripts\stop-dev.bat` (no `start-dev.bat` running, but PID file present) | Both PIDs killed; ports released |
| 11 | `.env` sets `BACKEND_PORT=9000 FRONTEND_PORT=5174`; run launcher | `:9000` and `:5174` listening; frontend `/api/*` proxies through to `:9000` (verify with curl) |
| 12 | `.env` sets `BACKEND_PORT=abc` (invalid) | Warning; default 8000 used |
| 13 | `.env` sets `BACKEND_PORT == FRONTEND_PORT` | Launcher exits with error before starting anything |
| 14 | `.env` has the two new lines commented out | Defaults 8000 / 5173 |

### Acceptance checklist

- [ ] Tests 1–3 each release both ports
- [ ] Tests 4, 7–10 behave as listed
- [ ] Tests 5, 6 confirm cleanup paths
- [ ] Tests 11–14 confirm `.env`-driven port override and validation
- [ ] `AGENTS.md` updated at lines 24, 25, 39
- [ ] `.ps1` files preserved on disk but removed from the documented entry point
- [ ] `.env` patch is additive only (no edits to existing five lines)

## Update to `AGENTS.md`

Lines 24, 25, 39:

- 24 — replace `scripts\start-dev.ps1` reference with `scripts\start-dev.bat`; add `-OpenBrowser` and `-WaitSeconds N` parameter list.
- 25 — replace `scripts\stop-dev.ps1` reference with `scripts\stop-dev.bat`.
- 39 — replace the existing `start-dev.ps1 PID file lock` quirk with a combined `.bat` quirk that documents (a) the `.dev-pids.json` lock, (b) the Job-Object reaping guarantee, (c) the `.env` port override.

Also add an entry to `## Quirks` describing the new `_job-helper.ps1` boundary and the env-var-based port propagation to vite.