# AGENTS.md — ComfyChat

Compact instructions for OpenCode sessions. Specs/plans (`docs/superpowers/{specs,plans}/`) are the source of truth for scope and design — read them before adding files or routes.

## Layout

- `backend/` — FastAPI + SQLAlchemy 2.x + SQLite. Editable install: `pip install -e "backend[dev]"`.
- `frontend/` — Vue 3 + Vite + TypeScript, **UI via Element Plus** (auto-imported) + SCSS. `npm run dev` on `:5173`, proxies `/api/*` → `:8000` (the proxy **strips `/api`**, so backend routes use no `/api` prefix — see Quirks).
- `frontend/src/styles/` — `index.scss` (global, imported in `main.ts`), `_variables.scss` (app tokens `$cc-*`), `_element-overrides.scss` (EP theme: `--el-color-primary: #0ea5e9`).
- `docs/superpowers/{specs,plans}/` — design specs and implementation plans; read before new work.
- `storage/` — runtime files (SQLite, uploads, outputs, thumbs, tmp). Fully gitignored; never commit, do not assume empty. Generated images live under `storage/outputs/{YYYY-MM}/{gen_id}/`.
- `.superpowers/` — brainstorm visual-companion + SDD workspace scratch, gitignored. Delete freely when a plan completes.
- `scripts/start-dev.bat` / `stop-dev.bat` — start/stop both services as background processes with Job-Object reaping; PIDs in `storage/tmp/.dev-pids.json`.

## Setup (China network)

- pip per-command: `$env:PIP_INDEX_URL = 'https://pypi.tuna.tsinghua.edu.cn/simple'`. Fallback: `https://mirrors.aliyun.com/pypi/simple/`. Default PyPI times out.
- npm mirror is project-local in `frontend/.npmrc`. **Do not run `npm config set` globally.**
- Local ComfyUI assumed at `:8188` with `COMFYUI_USERDATA_DIR` (e.g. `D:\ComfyUI\ComfyUI_windows_portable\ComfyUI\user\default`). Without it, the browse sync silently skips files.
- `python` on this machine → miniconda 3.13 (use for `python -m venv`). `py -3` → pythoncore 3.14 (don't use for venv).

## Common commands (cwd = repo root)

- Start both: `cmd /c scripts\start-dev.bat` (参数 `-WaitSeconds N` 改就绪等待超时,默认 25;前端就绪后自动打开默认浏览器)。
- Stop both: `cmd /c scripts\stop-dev.bat`。
- Backend tests: `backend\.venv\Scripts\python -m pytest backend/tests/<file> -v`. Target: 111 tests collected, 110 pass + 1 known Windows fail (see Quirks).
- Full backend suite: `backend\.venv\Scripts\python -m pytest backend/tests -v`.
- Backend dev alone: `backend\.venv\Scripts\python -m uvicorn app.main:app --port 8000`.
- Frontend typecheck: `npm --prefix frontend run typecheck`.
- Frontend dev alone: `cd frontend && npm run dev`.
- Frontend build: `cd frontend && npm run build` (runs `vue-tsc --noEmit && vite build`).

## Quirks

- **Vite proxy strips `/api`.** Frontend calls `/api/workflows/...`; backend router prefix is `/workflows` (no `/api`). Adding a new route? Match the existing pattern — backend at `/workflows/<thing>`, frontend calls `/api/workflows/<thing>`. Do not add `/api` to the backend prefix.
- **Element Plus is auto-imported** via `unplugin-vue-components` + `unplugin-auto-import` with `ElementPlusResolver({ styleExtension: "scss" })` in `vite.config.ts`. Never write `import { ElButton }` etc. in components. Icons (`@element-plus/icons-vue`) are **NOT** auto-imported — import them explicitly. Generated `frontend/auto-imports.d.ts` + `frontend/components.d.ts` are gitignored.
- **`main.ts` registers Element Plus with zh-cn locale** (`import zhCn from "element-plus/es/locale/lang/zh-cn"`) — use the `es/` path, NOT `dist/locale/...` (EP 2.14 `dist/` has no `.d.ts`, `vue-tsc` fails with TS7016).
- **`app = create_app()` runs at module import** and `Base.metadata.create_all` creates ALL tables (including `workflow_versions`) on first import. `storage/data/comfychat.db` is held under a Windows file lock while uvicorn runs. Use `git check-ignore -v storage/data/comfychat.db` (no probe) or `tmp_path` in tests. Don't `Out-File` the live `.db` (IOException).
- **`start-dev.bat` PID file lock.** 如果上次启动后服务被杀,`storage/tmp/.dev-pids.json` 残留,下次 `start-dev.bat` 启动前会自动清理(由 `_job-helper.ps1 -Command PreFlight` 处理);也可用 `stop-dev.bat` 手动清理。
- **`start-dev.bat` 用 Windows Job Object 收尸子进程。** `_job-helper.ps1` 创建带 `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` 的 Job,把 uvicorn 与 vite 收进去。`.bat` 以任意方式退出(Ctrl+C、点 X、`taskkill /F`、崩溃)→ 帮助器退出 → OS 关闭 Job → 子进程被 TerminateProcess。前端通过把 `npm.cmd` shim 放进 Job 让 `node.exe` 自动继承 Job(直接对 node 反查端口再 assign 会报 Access Denied)。
- **端口由根 `.env` 覆盖。** `BACKEND_PORT`(默认 8000)与 `FRONTEND_PORT`(默认 5173)由 `_job-helper.ps1` 读取,并通过 PowerShell `$env:` 传给 vite。`frontend/vite.config.ts` 通过 `process.env` 拿值,改 `.env` 后重启 vite 生效。
- Wrap `Start-Process` arguments as separate items (`-ArgumentList "-m","uvicorn","app.main:app","--port","8000"`), not one string, or PowerShell collapses them.
- Frontend dev binds to `127.0.0.1` via `npm run dev -- --host 127.0.0.1` (run by `start-dev.ps1`). Without `--host`, vite binds to `localhost` (IPv6 often) and the proxy ready-check fails.
- `test_check_database_returns_false_when_path_unwritable` fails on Windows — `os.chmod(0o500)` doesn't enforce NTFS ACLs. `@pytest.mark.skipif(sys.platform == "win32", ...)` is the documented fix; don't silently delete the test.
- `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead` — real upstream warning, not our code. Out of scope; track for next stage.
- `Frontend/src` files may lack trailing newline at EOF (cosmetic).
- **Element Plus main chunk is ~1 MB / 346 KB gzip** — Vite warns about chunk size; not a blocker, code-splitting deferred.

## Conventions

- `frontend/vite.config.ts` uses `import.meta.url` + `fileURLToPath(new URL(...))`, **not `__dirname`** (ESM-portable; Vite 5+ official pattern). Don't "fix" it back.
- TypeScript paths: `@/*` → `src/*` mirrored in both `tsconfig.json` and `vite.config.ts` alias.
- Backend is installed editable; `app.*` is importable globally, so pytest runs from the repo root without `cd backend`.
- `Settings` uses `pydantic-settings` with `extra="ignore"` and reads `.env` (CWD). Five fields: `comfyui_base_url`, `comfyui_api_key`, `database_url`, `storage_root`, `comfyui_userdata_dir`. Add new fields with defaults; never break the existing five.
- Backend uses module-level singletons (`app.core.database`) with `reset_for_tests()` for isolation. Prefer `tmp_path` over real paths in tests.
- Per-request DB session via `get_db_session` (in `app.api.deps`) — used by `Depends(get_db_session)` in routers. Don't share a session across requests.
- `app.state.services` holds module singletons + instances (asymmetric by design): `"database"` is the module, `"comfyui"` + `"workflow_repo"` + `"workflow_service"` are instances. Don't "normalize" without a plan.
- `ComfyUIClient.list_browse()` targets `/v2/userdata?path=workflows` (returns structured list). `read_userdata_json(filename)` reads from `$COMFYUI_USERDATA_DIR/workflows/{filename}` via filesystem (avoids ComfyUI 0.31.0's broken userdata subdirectory read). The client also exposes execution methods: `submit_prompt(prompt) -> prompt_id` (POST `/prompt`), `get_history(prompt_id) -> dict`, `get_image(filename, subfolder, type) -> bytes` (GET `/view`), `get_queue()`, `get_object_info(node_types)` (POST `/object_info/{type}`, per-type) — failures raise `ComfyUIError`.
- `WorkflowService.sync()` identifies workflows by `source_key` (ComfyUI filename). Same name + size changed → archives old body to `workflow_versions` (version N+1), updates row, appends to `updates`. Different name = new row. Rename = delete+add.
- `WorkflowRepository.delete()` cascades explicitly to `WorkflowVersion`, `Generation`, and `WorkflowGenerationConfig` for the same `workflow_id` (FK `ondelete="CASCADE"` is inert — no `PRAGMA foreign_keys=ON` is set — so the repo-level explicit `sa_delete` is authoritative). Mirror the existing `sa_delete(WorkflowVersion)` pattern when adding new tables with FKs to workflows.
- **Generations feature** (`/generations` page): `WorkflowGenerationConfig` is 1:1 with workflow (`UNIQUE(workflow_id)`); stores `api_template` (executable API-format JSON) + `fields_json` (parameter field definitions). `Generation` rows reference a workflow_id and a `prompt_id` from ComfyUI. POST `/generations` triggers FastAPI `BackgroundTasks` polling every 2 s (fresh session per iteration via `services["database"]`) and downloads outputs via `get_image` to `storage/outputs/{YYYY-MM}/{gen_id}/`. Image serving has a path-traversal guard (`Path(filename).name` + `resolve()` + parent-equality).
- **Field auto-discovery** (`backend/app/services/generation.py` pure functions + `GET /workflows/{id}/generation-config/discover`):
  - `Workflow.body` is **UI-format** (`{"nodes":[{id,type,inputs,widgets_values,links}], "links":[...]}`), NOT the API format ComfyUI `/prompt` needs. `workflow_to_api_template(body, object_info)` converts UI→API: widgets from `widgets_values` (positionally aligned to `inputs[]` entries with `widget`), **link inputs resolved to `["<from_node_id>", from_slot]` via the `links` array** (missing this caused ComfyUI "Required input is missing: images" errors). `control_after_generate` (e.g. seed's `'fixed'`/`'randomize'`) occupies one extra `widgets_values` slot and must be skipped (`_align_widgets`).
  - `discover_fields(body, object_info)` returns candidate fields: type `text|seed|number|select` (inferred from object_info COMBO options / INT / FLOAT, else value shape); **`default` always from workflow `widgets_values`, never from object_info** (object_info `default` is node-type default and overrides real values — a past bug). `_field_meta` only supplies `min/max/step/options`. Labels prefer `inputs[].localized_name` (Chinese); `_conditioning_labels` renames CLIPTextEncode `text` fields to 正面/负面提示词 by tracing KSampler `positive`/`negative` links. `_LOADER_INPUTS` blacklist drops loader fields (clip_name/type/device/vae_name/shift/etc.) but keeps lora_name + strength_model.
  - `apply_parameters(api_template, fields, parameters)` deep-copies the template, fills only checked fields' slots, keeps everything else at template defaults. `GenerationField.type` regex is `^(text|seed|number|select)$`.

## Not here yet (next-stage placeholders)

- No alembic / `backend/migrations/`. Adding a new table? Just add the model — `Base.metadata.create_all()` picks it up at next import. New tables are NOT auto-added to existing DBs.
- No lint, formatter, pre-commit, CI, or frontend test framework. Validation = `npm run typecheck` + pytest + manual smoke.
- `frontend/src/features/{dashboard,files,tasks}` — still `.gitkeep` placeholders. `workflows/` and `generations/` are implemented.

## OpenCode / MCP

- The user runs `superpowers` skills (`brainstorming` → `writing-plans` → `subagent-driven-development`) for any non-trivial work. Expect a planning + SDD loop before any code changes; don't jump straight into implementation.
- **NEVER run resident/long-running tasks directly in a bash command** — `uvicorn`, `npm run dev`, `vite`, `node server.cjs`, `scripts\start-dev.ps1` (it blocks ~25 s waiting for readiness), etc. Running them directly hangs the tool call and makes the conversation appear stuck. Instead:
  - To start/stop dev servers: tell the user to run `scripts\start-dev.bat` / `stop-dev.bat` in their own terminal, **or** launch the script itself detached via `Start-Process powershell -ArgumentList ... -WindowStyle Hidden` (capture its PID, don't wait on it). Do NOT call the script synchronously.
  - Short-lived checks only (e.g. a single `Invoke-WebRequest` to a health endpoint, a test run, a build) are fine, always with an explicit `timeout` on the tool call.
  - Always follow up a server-start with a text reply confirming the result, so the user is never left reading stale output.
- For verifying a dev-server start, stop it immediately after the smoke check — don't leave ports 8000/5173 occupied.
