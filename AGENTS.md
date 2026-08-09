# AGENTS.md — ComfyChat

Compact instructions for OpenCode sessions. Specs/plans (`docs/superpowers/{specs,plans}/`) are the source of truth for scope and design — read them before adding files or routes.

## Layout

- `backend/` — FastAPI + SQLAlchemy 2.x + SQLite. Editable install: `pip install -e "backend[dev]"`.
- `frontend/` — Vue 3 + Vite + TypeScript. `npm run dev` on `:5173`, proxies `/api/*` → `:8000` (the proxy **strips `/api`**, so backend routes use no `/api` prefix — see Quirks).
- `docs/superpowers/{specs,plans}/` — design specs and implementation plans; read before new work.
- `storage/` — runtime files (SQLite, uploads, outputs, thumbs, tmp). Fully gitignored; never commit, do not assume empty.
- `.superpowers/sdd/` — per-plan scratch (gitignored by nested `.gitignore`). Delete freely when a plan completes.
- `scripts/start-dev.ps1` / `stop-dev.ps1` — start/stop both services as background processes; PIDs in `storage/tmp/.dev-pids.json`.

## Setup (China network)

- pip per-command: `$env:PIP_INDEX_URL = 'https://pypi.tuna.tsinghua.edu.cn/simple'`. Fallback: `https://mirrors.aliyun.com/pypi/simple/`. Default PyPI times out.
- npm mirror is project-local in `frontend/.npmrc`. **Do not run `npm config set` globally.**
- Local ComfyUI assumed at `:8188` with `COMFYUI_USERDATA_DIR` (e.g. `D:\ComfyUI\ComfyUI_windows_portable\ComfyUI\user\default`). Without it, the browse sync silently skips files.
- `python` on this machine → miniconda 3.13 (use for `python -m venv`). `py -3` → pythoncore 3.14 (don't use for venv).

## Common commands (cwd = repo root)

- Start both: `powershell -ExecutionPolicy Bypass -File scripts\start-dev.ps1` (add `-OpenBrowser` to launch browser).
- Stop both: `powershell -ExecutionPolicy Bypass -File scripts\stop-dev.ps1`.
- Backend tests: `backend\.venv\Scripts\python -m pytest backend/tests/<file> -v`. Target: 49+ passed, 1 known Windows fail (see Quirks).
- Full backend suite: `backend\.venv\Scripts\python -m pytest backend/tests -v`.
- Backend dev alone: `backend\.venv\Scripts\python -m uvicorn app.main:app --port 8000`.
- Frontend typecheck: `npm --prefix frontend run typecheck`.
- Frontend dev alone: `cd frontend && npm run dev`.
- Frontend build: `cd frontend && npm run build` (runs `vue-tsc --noEmit && vite build`).

## Quirks

- **Vite proxy strips `/api`.** Frontend calls `/api/workflows/...`; backend router prefix is `/workflows` (no `/api`). Adding a new route? Match the existing pattern — backend at `/workflows/<thing>`, frontend calls `/api/workflows/<thing>`. Do not add `/api` to the backend prefix.
- **`app = create_app()` runs at module import** and `Base.metadata.create_all` creates ALL tables (including `workflow_versions`) on first import. `storage/data/comfychat.db` is held under a Windows file lock while uvicorn runs. Use `git check-ignore -v storage/data/comfychat.db` (no probe) or `tmp_path` in tests. Don't `Out-File` the live `.db` (IOException).
- **`start-dev.ps1` PID file lock.** If services were killed mid-run, `storage/tmp/.dev-pids.json` persists and the next start refuses. Delete the file or run `stop-dev.ps1` first.
- Wrap `Start-Process` arguments as separate items (`-ArgumentList "-m","uvicorn","app.main:app","--port","8000"`), not one string, or PowerShell collapses them.
- Frontend dev binds to `127.0.0.1` via `npm run dev -- --host 127.0.0.1` (run by `start-dev.ps1`). Without `--host`, vite binds to `localhost` (IPv6 often) and the proxy ready-check fails.
- `test_check_database_returns_false_when_path_unwritable` fails on Windows — `os.chmod(0o500)` doesn't enforce NTFS ACLs. `@pytest.mark.skipif(sys.platform == "win32", ...)` is the documented fix; don't silently delete the test.
- `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead` — real upstream warning, not our code. Out of scope; track for next stage.
- `Frontend/src` files may lack trailing newline at EOF (cosmetic).

## Conventions

- `frontend/vite.config.ts` uses `import.meta.url` + `fileURLToPath(new URL(...))`, **not `__dirname`** (ESM-portable; Vite 5+ official pattern). Don't "fix" it back.
- TypeScript paths: `@/*` → `src/*` mirrored in both `tsconfig.json` and `vite.config.ts` alias.
- Backend is installed editable; `app.*` is importable globally, so pytest runs from the repo root without `cd backend`.
- `Settings` uses `pydantic-settings` with `extra="ignore"` and reads `.env` (CWD). Five fields: `comfyui_base_url`, `comfyui_api_key`, `database_url`, `storage_root`, `comfyui_userdata_dir`. Add new fields with defaults; never break the existing five.
- Backend uses module-level singletons (`app.core.database`) with `reset_for_tests()` for isolation. Prefer `tmp_path` over real paths in tests.
- Per-request DB session via `get_db_session` (in `app.api.deps`) — used by `Depends(get_db_session)` in routers. Don't share a session across requests.
- `app.state.services` holds module singletons + instances (asymmetric by design): `"database"` is the module, `"comfyui"` + `"workflow_repo"` + `"workflow_service"` are instances. Don't "normalize" without a plan.
- `ComfyUIClient.list_browse()` targets `/v2/userdata?path=workflows` (returns structured list). `read_userdata_json(filename)` reads from `COMFYUI_USERDATA_DIR/workflows/{filename}` via filesystem (avoids ComfyUI 0.31.0's broken userdata subdirectory read).
- `WorkflowService.sync()` identifies workflows by `source_key` (ComfyUI filename). Same name + size changed → archives old body to `workflow_versions` (version N+1), updates row, appends to `updates`. Different name = new row. Rename = delete+add.
- `WorkflowRepository.delete()` cascades to `workflow_versions.workflow_id` (FK + explicit delete — CASCADE only fires with `PRAGMA foreign_keys=ON`; the explicit repo-level delete is authoritative).

## Not here yet (next-stage placeholders)

- No alembic / `backend/migrations/`. Adding a new table? Just add the model — `Base.metadata.create_all()` picks it up at next import. New tables are NOT auto-added to existing DBs.
- No lint, formatter, pre-commit, CI, or frontend test framework. Validation = `npm run typecheck` + pytest + manual smoke.
- `frontend/src/features/{dashboard,files,tasks,workflows}` — only `workflows/` has files; the others are still `.gitkeep` placeholders.
- `opencode.json` (enables GitHub MCP) is currently untracked. Commit it so future sessions inherit the MCP setup.

## OpenCode / MCP

- The user runs `superpowers` skills (`brainstorming` → `writing-plans` → `subagent-driven-development`) for any non-trivial work. Expect a planning + SDD loop before any code changes; don't jump straight to implementation.
