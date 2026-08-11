# Generation Modal Image Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `GenerationCreateModal.vue` so a submitted generation stays visible in the modal (right-column image panel), supports re-generation against a thumbnail history, and exposes a ComfyUI-backed abort button while the generation is active.

**Architecture:** Two-column modal (left = existing 1/2/3 step form, right = main image + status + thumbnail history). Frontend polls `GET /generations/{id}` every 2s after submit and stops polling on terminal status. Backend gains `ComfyUIClient.interrupt` / `delete_queued`, `GenerationService.cancel`, and `POST /generations/{id}/cancel` route; reuses existing `failed` status with `error="用户中止"`. `_poll_once` gets a `poll_miss_count` counter to break the polling loop when ComfyUI drops history entries after interrupt.

**Tech Stack:** Vue 3 + Vite + TypeScript (Element Plus auto-imported, zh-cn locale). FastAPI + SQLAlchemy 2.x + SQLite. pytest. httpx mock pattern (see existing `test_comfyui_client.py`).

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/integrations/comfyui/client.py` | Add `interrupt()` and `delete_queued(prompt_id)` |
| `backend/app/models/generation.py` | Add `poll_miss_count` column |
| `backend/app/core/migrate.py` | Extend `_ensure_column` to accept col_type + default |
| `backend/app/repositories/generation.py` | Add `update_poll_miss_count` |
| `backend/app/services/generation.py` | Add `cancel()`; patch `_poll_once` for interrupt-miss fallback |
| `backend/app/api/routes/generations.py` | Add `POST /generations/{id}/cancel` |
| `backend/tests/test_comfyui_client.py` | Tests for new client methods |
| `backend/tests/test_generation_repository.py` (or extend existing) | Test for `update_poll_miss_count` |
| `backend/tests/test_generation_service.py` | Tests for `cancel` + `_poll_once` fallback |
| `backend/tests/test_generations_api.py` | Tests for cancel route |
| `frontend/src/services/api.ts` | Add `generations.cancel` |
| `frontend/src/features/generations/GenerationCreateModal.vue` | Width, two-column layout, state machine, polling, abort, thumbnails |

Out of scope (no edits): `Modal.vue`, `types/api.ts` (existing `GenerationStatus` already covers all states), `useGenerations.ts`, `GenerationsView.vue`, `WorkflowsView.vue` (callers — they already listen on `@close` / `@generated`, and after this change those events still fire identically).

## Global Constraints

These constraints apply to every task. They are copied verbatim from the project spec or AGENTS.md.

- **Backend is editable-installed** (`pip install -e "backend[dev]"`). `app.*` is importable globally — pytest runs from repo root: `backend\.venv\Scripts\python -m pytest backend/tests/<file> -v`.
- **Vite proxy strips `/api`.** Frontend calls `/api/generations/...`; backend router prefix is `/generations`. Do not add `/api` to backend routes.
- **No alembic.** Column additions go through `backend/app/core/migrate.py:_ensure_column` (idempotent ALTER via `PRAGMA table_info`).
- **`Base.metadata.create_all` does NOT add columns to existing tables.** New tables in model definitions are NOT auto-created in existing DBs either. Both must go through `migrate.py` for existing DBs.
- **Element Plus is auto-imported** via `unplugin-vue-components` in `vite.config.ts`. Never write `import { ElButton }` etc. in `.vue` files. Icons (`@element-plus/icons-vue`) are NOT auto-imported — import explicitly.
- **No frontend test framework.** Validation = `npm --prefix frontend run typecheck` + manual smoke.
- **ComfyUI endpoints are synchronous `httpx`** (see `client.py` style). Mock pattern in `backend/tests/test_comfyui_client.py` uses `monkeypatch.setattr("app.integrations.comfyui.client.httpx.Client", FakeHttpx)`.
- **Element Plus primary color** is `--el-color-primary: #0ea5e9` (set in `frontend/src/styles/_element-overrides.scss`).
- **`_utcnow()` returns `datetime.now(timezone.utc).isoformat()`** — use it for `updated_at` writes.
- **Repo update pattern** (`GenerationRepository`): fetch via `self.get(id)`, mutate, set `gen.updated_at = _utcnow()`, `self.session.commit()`. Existing methods: `update_status`, `mark_failed`, `update_success`. Mirror their style.
- **Settings fields** (6 total, `extra="ignore"`): `comfyui_base_url`, `comfyui_api_key`, `database_url`, `storage_root`, `comfyui_userdata_dir`, `comfyui_loras_dir`. Tests pass explicit `Settings(...)` to `create_app` or use fixtures.
- **Branch workflow:** Implement on a new git branch off `main`. Test on the branch. Merge to `main` only after smoke. Never push untested changes.
- **Modal currently 640px wide.** Final width is `1200px` — change the `width` prop on the existing `<Modal>` invocation; do not edit `Modal.vue`.

---

## Task 1: ComfyUIClient 新增 interrupt / delete_queued

**Files:**
- Modify: `backend/app/integrations/comfyui/client.py:93` (append after `get_queue` method, before `get_object_info`)
- Modify: `backend/tests/test_comfyui_client.py:186` (append at end)

**Interfaces:**
- Produces: `ComfyUIClient.interrupt() -> None` (raises `ComfyUIError` on failure)
- Produces: `ComfyUIClient.delete_queued(prompt_id: str) -> None`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_comfyui_client.py`:

```python
def test_interrupt_posts_interrupt_endpoint(monkeypatch):
    calls = []

    def handler(kind, url, payload):
        calls.append((kind, url, payload))

    _fake_client(monkeypatch, handler)
    client = ComfyUIClient(Settings(comfyui_base_url="http://example.com:8188/"))

    client.interrupt()

    assert calls == [("post", "http://example.com:8188/interrupt", None)]


def test_delete_queued_posts_queue_with_prompt_id(monkeypatch):
    calls = []

    def handler(kind, url, payload):
        calls.append((kind, url, payload))

    _fake_client(monkeypatch, handler)
    client = ComfyUIClient(Settings(comfyui_base_url="http://example.com:8188/"))

    client.delete_queued("p-42")

    assert calls == [("post", "http://example.com:8188/queue", {"delete": ["p-42"]})]
```

Note: `_fake_client` returns `FakeResponse({"prompt_id": "abc123"})` for any POST and ignores the `json` body. We don't care about the return value — `interrupt()` / `delete_queued()` return `None` and only assert on captured `calls`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend\.venv\Scripts\python -m pytest backend/tests/test_comfyui_client.py::test_interrupt_posts_interrupt_endpoint backend/tests/test_comfyui_client.py::test_delete_queued_posts_queue_with_prompt_id -v`

Expected: FAIL with `AttributeError: 'ComfyUIClient' object has no attribute 'interrupt'` (and same for `delete_queued`).

- [ ] **Step 3: Implement the two methods**

In `backend/app/integrations/comfyui/client.py`, between `get_queue` (line 95) and `get_object_info` (line 97), insert:

```python
    def interrupt(self) -> None:
        """POST /interrupt — 中止当前正在运行的 job(无 request body)。"""
        self._request("post", "/interrupt", json=None)

    def delete_queued(self, prompt_id: str) -> None:
        """POST /queue body {"delete":[prompt_id]} — 从队列删除 pending job。"""
        self._request("post", "/queue", json={"delete": [prompt_id]})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend\.venv\Scripts\python -m pytest backend/tests/test_comfyui_client.py -v`

Expected: PASS for both new tests; all previous tests still pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/comfyui/client.py backend/tests/test_comfyui_client.py
git commit -m "feat(backend): ComfyUIClient interrupt + delete_queued"
```

---

## Task 2: Generation 模型新增 poll_miss_count + 迁移扩展

**Files:**
- Modify: `backend/app/models/generation.py:16-30` (add column to `Generation`)
- Modify: `backend/app/core/migrate.py:7-27` (extend `_ensure_column` signature, register new column)

**Interfaces:**
- Produces: `Generation.poll_miss_count: int` (default `0`, `nullable=False`)
- Produces: `_ensure_column(engine, table, column, *, col_type="BOOLEAN", default="0")` (backward-compatible — existing call still works)

- [ ] **Step 1: Add the column to the model**

In `backend/app/models/generation.py`, change the import (line 6) from:

```python
from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
```

to:

```python
from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
```

Then in `Generation` (after `outputs_json` line, before `created_at`), add:

```python
    poll_miss_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
```

- [ ] **Step 2: Extend `_ensure_column` to accept column type + default**

Rewrite `backend/app/core/migrate.py` to:

```python
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


def migrate(engine: Engine) -> None:
    """启动时执行的幂等迁移。

    无 alembic;Base.metadata.create_all 不会给已有表加列,这里用 PRAGMA
    检测缺失列并 ALTER。已存在列时跳过,可重复执行。
    """
    _ensure_column(engine, "loras", "deleted_from_comfyui")
    _ensure_column(
        engine,
        "generations",
        "poll_miss_count",
        col_type="INTEGER",
        default="0",
    )


def _ensure_column(
    engine: Engine,
    table: str,
    column: str,
    *,
    col_type: str = "BOOLEAN",
    default: str = "0",
) -> None:
    with engine.begin() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        names = {row[1] for row in rows}
        if column in names:
            return
        conn.execute(
            text(
                f"ALTER TABLE {table} ADD COLUMN {column} "
                f"{col_type} NOT NULL DEFAULT {default}"
            )
        )
```

- [ ] **Step 3: Verify model + migration load and migrate is idempotent**

Run: `backend\.venv\Scripts\python -c "from app.main import create_app; from app.core.config import Settings; s = Settings(database_url='sqlite:///:memory:', storage_root='./tmp'); create_app(s); print('ok')"`

Expected: prints `ok`. (This exercises `Base.metadata.create_all` and `migrate(engine)`.)

Run: `backend\.venv\Scripts\python -c "from app.core.migrate import migrate; from sqlalchemy import create_engine; e = create_engine('sqlite:///:memory:'); migrate(e); migrate(e); print('idempotent ok')"`

Expected: prints `idempotent ok`. Second `migrate` call must be a no-op.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/generation.py backend/app/core/migrate.py
git commit -m "feat(backend): Generation.poll_miss_count + migrate extension"
```

---

## Task 3: GenerationRepository.update_poll_miss_count

**Files:**
- Modify: `backend/app/repositories/generation.py:75-90` (insert after `update_status`)

**Interfaces:**
- Produces: `GenerationRepository.update_poll_miss_count(generation_id: str, count: int) -> None` — sets `gen.poll_miss_count = count`, bumps `updated_at`, commits. No-op if `gen is None`.

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_generation_repository.py` (create if missing; check existing file first). The test:

```python
from app.models.generation import Generation
from app.repositories.generation import GenerationRepository


def test_update_poll_miss_count(session):
    repo = GenerationRepository(session)
    gen = repo.create(
        workflow_id="wf1",
        workflow_name="z-image",
        parameters={},
        status="running",
        prompt_id="p-1",
    )
    assert gen.poll_miss_count == 0

    repo.update_poll_miss_count(gen.id, 1)
    session.expire_all()
    assert repo.get(gen.id).poll_miss_count == 1

    repo.update_poll_miss_count(gen.id, 0)
    session.expire_all()
    assert repo.get(gen.id).poll_miss_count == 0


def test_update_poll_miss_count_noop_when_missing(session):
    repo = GenerationRepository(session)
    repo.update_poll_miss_count("nonexistent", 5)  # should not raise
```

If `test_generation_repository.py` doesn't exist, create it with the conftest fixture import already in place (see existing pattern in `test_generation_service.py` which uses bare `session` fixture from `conftest.py`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend\.venv\Scripts\python -m pytest backend/tests/test_generation_repository.py -v`

Expected: FAIL — first test fails on `repo.create(...)` attribute check (no `poll_miss_count` because model wasn't refreshed) OR fails on `update_poll_miss_count` call (AttributeError). Either way: failure.

- [ ] **Step 3: Implement the method**

In `backend/app/repositories/generation.py`, after `update_status` (line 75-81) and before `mark_failed` (line 83), insert:

```python
    def update_poll_miss_count(self, generation_id: str, count: int) -> None:
        gen = self.get(generation_id)
        if gen is None:
            return
        gen.poll_miss_count = count
        gen.updated_at = _utcnow()
        self.session.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend\.venv\Scripts\python -m pytest backend/tests/test_generation_repository.py -v`

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories/generation.py backend/tests/test_generation_repository.py
git commit -m "feat(backend): GenerationRepository.update_poll_miss_count"
```

---

## Task 4: GenerationService.cancel + _poll_once 兜底

**Files:**
- Modify: `backend/app/services/generation.py:298-409` (add `cancel()` after `create`; patch `_poll_once`)
- Modify: `backend/tests/test_generation_service.py:539` (append tests)

**Interfaces:**
- Produces: `GenerationService.cancel(generation_id: str) -> Generation`
  - Raises `ValueError("generation not found")` if id missing
  - Raises `ValueError("already terminal: {status}")` if `status in {"success","failed"}`
  - Calls `comfyui.delete_queued(prompt_id)` if `status == "queued"`; `comfyui.interrupt()` if `status == "running"`
  - On `ComfyUIError`: swallows, still marks DB as failed
  - Always writes `status="failed", error="用户中止"` via `mark_failed`
- Produces: `_poll_once` updated to break the polling loop after 2 consecutive `get_history` misses when `gen.status == "running"`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_generation_service.py`:

```python
from app.integrations.comfyui.client import ComfyUIError


class FakeCancellableComfy(FakeComfy):
    def __init__(self):
        super().__init__()
        self.interrupt_calls = 0
        self.delete_queued_calls = []

    def interrupt(self):
        self.interrupt_calls += 1

    def delete_queued(self, prompt_id):
        self.delete_queued_calls.append(prompt_id)


def test_cancel_queued_calls_delete_queued(session, tmp_path):
    settings = _settings(tmp_path)
    _config(session, "wf1")
    comfy = FakeCancellableComfy()
    svc = _service(session, settings, comfy)
    gen = svc.create("wf1", {"positive_prompt": "cat", "seed": 5, "seed_random": False})

    result = svc.cancel(gen.id)

    assert result.status == "failed"
    assert result.error == "用户中止"
    assert comfy.delete_queued_calls == ["p-1"]
    assert comfy.interrupt_calls == 0


def test_cancel_running_calls_interrupt(session, tmp_path):
    settings = _settings(tmp_path)
    _config(session, "wf1")
    comfy = FakeCancellableComfy()
    repo = GenerationRepository(session)
    comfy.history = {}
    svc = _service(session, settings, comfy)
    gen = repo.create("wf1", "z-image", {}, "running", "p-1")

    result = svc.cancel(gen.id)

    assert result.status == "failed"
    assert result.error == "用户中止"
    assert comfy.interrupt_calls == 1
    assert comfy.delete_queued_calls == []


def test_cancel_terminal_status_raises(session, tmp_path):
    settings = _settings(tmp_path)
    comfy = FakeCancellableComfy()
    svc = _service(session, settings, comfy)
    repo = GenerationRepository(session)
    gen = repo.create("wf1", "z-image", {}, "success", "p-1")

    with pytest.raises(ValueError, match="already terminal"):
        svc.cancel(gen.id)


def test_cancel_not_found_raises(session, tmp_path):
    settings = _settings(tmp_path)
    svc = _service(session, settings, FakeCancellableComfy())

    with pytest.raises(ValueError, match="not found"):
        svc.cancel("nonexistent")


def test_cancel_swallows_comfyui_error(session, tmp_path):
    settings = _settings(tmp_path)
    _config(session, "wf1")
    comfy = FakeCancellableComfy()
    comfy.history = {}
    svc = _service(session, settings, comfy)
    repo = GenerationRepository(session)
    gen = repo.create("wf1", "z-image", {}, "running", "p-1")

    def boom():
        raise ComfyUIError("comfyui down")

    comfy.interrupt = boom

    result = svc.cancel(gen.id)

    assert result.status == "failed"
    assert result.error == "用户中止"


def test_poll_marks_failed_after_two_running_misses(session, tmp_path):
    settings = _settings(tmp_path)
    comfy = FakeComfy()
    comfy.history = {}  # always empty
    svc = _service(session, settings, comfy)
    repo = GenerationRepository(session)
    gen = repo.create("wf1", "z-image", {}, "running", "p-1")

    svc.poll_until_done(gen.id, poll_interval=0.0)

    got = repo.get(gen.id)
    assert got.status == "failed"
    assert "生成结果丢失" in (got.error or "")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend\.venv\Scripts\python -m pytest backend/tests/test_generation_service.py -v -k "cancel or poll_marks_failed_after_two"`

Expected: all 6 new tests FAIL. `cancel_*` fail with `AttributeError: 'FakeComfy' object has no attribute 'interrupt'`. `poll_marks_failed_after_two_running_misses` fails because the current `_poll_once` doesn't break on misses (it just keeps polling).

- [ ] **Step 3: Implement `cancel()`**

In `backend/app/services/generation.py`, after `create()` (around line 331, before `outputs_dir`), insert:

```python
    def cancel(self, generation_id: str) -> Generation:
        """按 generation 当前状态选对应 ComfyUI 端点,把 row 标 failed=用户中止。"""
        with self._session_scope() as session:
            repo = GenerationRepository(session)
            gen = repo.get(generation_id)
            if gen is None:
                raise ValueError("generation not found")
            if gen.status in ("success", "failed"):
                raise ValueError(f"already terminal: {gen.status}")
            try:
                if gen.status == "queued":
                    self.comfyui.delete_queued(gen.prompt_id)
                else:  # running
                    self.comfyui.interrupt()
            except ComfyUIError:
                pass
            return repo.mark_failed(generation_id, "用户中止")
```

Also add `from app.integrations.comfyui.client import ComfyUIError` to imports at top of file (search existing imports; it's already imported if `submit_prompt` raises are caught elsewhere — check first; if not, add).

- [ ] **Step 4: Patch `_poll_once` for miss fallback**

Replace the current `_poll_once` (line 348-384) with:

```python
    def _poll_once(self, session: Session, gen: Generation) -> bool:
        """查询一次 ComfyUI,返回 True 表示已到达终态。

        用户中止 + ComfyUI 清掉 history 的边缘场景:`gen.status == "running"`
        但 `get_history` 返回空;连续 2 次空就 mark_failed 退出,避免轮询死循环。
        """
        repo = GenerationRepository(session)
        if gen.status == "running":
            history = self.comfyui.get_history(gen.prompt_id)
            if not history:
                miss = (gen.poll_miss_count or 0) + 1
                if miss >= 2:
                    repo.mark_failed(gen.id, "生成结果丢失")
                    return True
                repo.update_poll_miss_count(gen.id, miss)
                return False
            if (gen.poll_miss_count or 0) > 0:
                repo.update_poll_miss_count(gen.id, 0)
            entry = history.get(gen.prompt_id)
        else:
            try:
                history = self.comfyui.get_history(gen.prompt_id)
            except Exception:
                return False
            entry = history.get(gen.prompt_id)
        if entry is None:
            if gen.status == "queued":
                repo.update_status(gen.id, "running")
            return False
        status_str = (entry.get("status") or {}).get("status_str")
        if status_str == "error":
            messages = (entry.get("status") or {}).get("messages") or []
            repo.mark_failed(gen.id, json.dumps(messages, ensure_ascii=False))
            return True
        images = collect_images(entry)
        saved = []
        if images:
            out_dir = self.outputs_dir(gen)
            out_dir.mkdir(parents=True, exist_ok=True)
            for img in images:
                filename = Path(img["filename"]).name
                if not filename:
                    continue
                try:
                    data = self.comfyui.get_image(
                        img["filename"], img.get("subfolder", ""), img.get("type", "output")
                    )
                except Exception as exc:
                    repo.mark_failed(gen.id, f"下载图片失败: {filename}: {exc}")
                    return True
                (out_dir / filename).write_bytes(data)
                saved.append(filename)
        repo.update_success(gen.id, saved)
        return True
```

The original logic path (for `queued`) is preserved; only the `running` branch gets the new miss-counter logic. `entry` is set either way; the rest of the function is unchanged.

- [ ] **Step 5: Run tests to verify they pass**

Run: `backend\.venv\Scripts\python -m pytest backend/tests/test_generation_service.py -v`

Expected: all 6 new tests PASS; all existing tests still pass.

- [ ] **Step 6: Run full backend suite to confirm no regression**

Run: `backend\.venv\Scripts\python -m pytest backend/tests -v`

Expected: 146 collected, ≥ 152 pass (added 6 cancel/miss tests). One pre-existing Windows-skip remains.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/generation.py backend/tests/test_generation_service.py
git commit -m "feat(backend): GenerationService.cancel + _poll_once miss fallback"
```

---

## Task 5: POST /generations/{id}/cancel 路由

**Files:**
- Modify: `backend/app/api/routes/generations.py:70-78` (insert new route after `get_generation`)

**Interfaces:**
- Produces: `POST /generations/{generation_id}/cancel` (no body)
  - 200: `GenerationOut`
  - 404: detail `"generation not found"`
  - 409: detail `"already terminal: {status}"`
  - 503: detail `"ComfyUI 不可用: {err}"` (only when `ComfyUIError` not swallowed — currently always swallowed in `cancel()`, so 503 path is defensive only)

- [ ] **Step 1: Write failing API tests**

Append to `backend/tests/test_generations_api.py`:

```python
def test_cancel_marks_failed_and_returns_200(tmp_path, monkeypatch):
    client, _ = _client(tmp_path)
    wid = _import_workflow(client)
    _config(client, wid)

    from app.integrations.comfyui.client import ComfyUIClient

    class FakeComfy:
        def submit_prompt(self, prompt):
            return "p-1"
        def get_history(self, prompt_id):
            return {}
        def interrupt(self):
            pass
        def delete_queued(self, prompt_id):
            pass

    for name in ("submit_prompt", "get_history", "interrupt", "delete_queued"):
        monkeypatch.setattr(ComfyUIClient, name, getattr(FakeComfy, name))

    gen = client.post("/generations", json={
        "workflow_id": wid,
        "parameters": {"positive_prompt": "cat", "seed": 42, "seed_random": False},
    }).json()

    r = client.post(f"/generations/{gen['id']}/cancel")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "failed"
    assert body["error"] == "用户中止"


def test_cancel_returns_404_for_unknown_id(tmp_path):
    client, _ = _client(tmp_path)
    r = client.post("/generations/nonexistent/cancel")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"]


def test_cancel_returns_409_for_terminal(tmp_path, monkeypatch):
    client, _ = _client(tmp_path)
    wid = _import_workflow(client)
    _config(client, wid)

    from app.integrations.comfyui.client import ComfyUIClient

    class FakeComfy:
        def submit_prompt(self, prompt):
            return "p-1"
        def get_history(self, prompt_id):
            return {"p-1": {"status": {"status_str": "success"}, "outputs": {}}}
        def get_image(self, filename, subfolder="", image_type="output"):
            return b""
        def interrupt(self):
            pass
        def delete_queued(self, prompt_id):
            pass

    for name in ("submit_prompt", "get_history", "get_image", "interrupt", "delete_queued"):
        monkeypatch.setattr(ComfyUIClient, name, getattr(FakeComfy, name))

    gen = client.post("/generations", json={
        "workflow_id": wid,
        "parameters": {"positive_prompt": "cat", "seed": 42, "seed_random": False},
    }).json()

    # wait for background poll to land at success
    import time
    for _ in range(20):
        g = client.get(f"/generations/{gen['id']}").json()
        if g["status"] == "success":
            break
        time.sleep(0.05)
    assert g["status"] == "success"

    r = client.post(f"/generations/{gen['id']}/cancel")
    assert r.status_code == 409
    assert "already terminal" in r.json()["detail"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend\.venv\Scripts\python -m pytest backend/tests/test_generations_api.py -v -k "cancel"`

Expected: 3 FAIL with 404 (route not found by FastAPI).

- [ ] **Step 3: Implement the route**

In `backend/app/api/routes/generations.py`, after `get_generation` (line 78, the `def get_generation(...)` block), insert:

```python
@router.post("/{generation_id}/cancel", response_model=GenerationOut)
def cancel_generation(
    generation_id: str,
    service: GenerationService = Depends(_service),
) -> GenerationOut:
    try:
        gen = service.cancel(generation_id)
    except ValueError as exc:
        msg = str(exc)
        raise HTTPException(
            status_code=404 if "not found" in msg else 409,
            detail=msg,
        )
    except ComfyUIError as exc:
        raise HTTPException(status_code=503, detail=f"ComfyUI 不可用: {exc}")
    return GenerationOut.from_model(gen)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend\.venv\Scripts\python -m pytest backend/tests/test_generations_api.py -v`

Expected: all PASS (including pre-existing tests).

- [ ] **Step 5: Run full backend suite**

Run: `backend\.venv\Scripts\python -m pytest backend/tests -v`

Expected: 146+3 = 149+ tests, all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/generations.py backend/tests/test_generations_api.py
git commit -m "feat(backend): POST /generations/{id}/cancel route"
```

---

## Task 6: Frontend api.generations.cancel 客户端方法

**Files:**
- Modify: `frontend/src/services/api.ts:115` (after `create` method, before `remove`)

**Interfaces:**
- Produces: `api.generations.cancel(id: string) => Promise<GenerationSummary>` (POST `/generations/{id}/cancel`, no body)

- [ ] **Step 1: Add the method**

In `frontend/src/services/api.ts`, in the `generations:` object, after `create:` (lines 105-115) and before `remove:` (line 116), insert:

```ts
    cancel: (id: string) => request(`/generations/${id}/cancel`, { method: "POST" }),
```

This matches the existing `create` pattern (returns `Promise<Response>`; callers do `res.json()` / check `res.ok`).

- [ ] **Step 2: Typecheck**

Run: `npm --prefix frontend run typecheck`

Expected: PASS (no new errors). The return type matches `create`'s `Promise<Response>`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/services/api.ts
git commit -m "feat(frontend): api.generations.cancel"
```

---

## Task 7: GenerationCreateModal 两栏布局(width + empty state)

**Files:**
- Modify: `frontend/src/features/generations/GenerationCreateModal.vue` (template, styles; no script logic in this task)

**Interfaces:**
- Produces: Modal renders at 1200px wide with a two-column body (left = existing step form, right = image panel)
- Produces: Image panel shows empty-state placeholder when no active generation

- [ ] **Step 1: Update Modal width + add wrapper flex**

In `frontend/src/features/generations/GenerationCreateModal.vue`, replace the root `<Modal>` invocation (lines 282-286) with:

```html
  <Modal
    :title="props.preset ? '再生成' : '新建生成'"
    width="1200px"
    @close="emit('close')"
  >
```

Then wrap the existing `<div v-else>` body content (lines 307-477) with a flex container. Insert **before** `<div v-else>` at line 307 and **after** its closing `</div>` at line 477. Concretely:

Before the existing `<div v-else>` at line 307, add nothing (keep the loading/error/empty branches as they are).

Modify the `<div v-else>` at line 307 to look like:

```html
    <div v-else class="cc-modal-body">
      <div class="cc-modal-left">
        <div class="cc-step-header">
          第 {{ step }} 步 / 共 {{ totalSteps }} 步 — {{ stepTitle }}
        </div>

        <div v-if="step === 1" class="cc-step-body">
          <!-- existing step 1 content -->
        </div>

        <div v-else-if="step === 2 && needsFieldsStep" class="cc-step-body">
          <!-- existing step 2 content -->
        </div>

        <div v-else class="cc-step-body">
          <!-- existing step 3 (confirm) content -->
        </div>

        <el-alert
          v-if="submitError"
          :title="submitError"
          type="error"
          :closable="false"
          show-icon
        />
      </div>

      <div class="cc-modal-divider"></div>

      <div class="cc-modal-right">
        <div class="cc-image-panel">
          <div class="cc-image-main">
            <div class="cc-image-empty">
              <span class="cc-image-empty-icon">🖼</span>
              <p>点击「生成」开始</p>
            </div>
          </div>
        </div>
      </div>
    </div>
```

(Note: existing `<div v-else>` body is being **restructured** to put all left-column content inside `cc-modal-left`; the right column is the new image panel.)

In the `<style>` block (lines 503-583), add at the end (before closing `</style>`):

```scss
.cc-modal-body {
  display: flex;
  gap: 24px;
  min-height: 400px;
}
.cc-modal-left {
  width: 480px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.cc-modal-divider {
  width: 1px;
  background: #e2e8f0;
  flex-shrink: 0;
}
.cc-modal-right {
  flex: 1;
  min-width: 400px;
  display: flex;
  flex-direction: column;
}
.cc-image-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
}
.cc-image-main {
  flex: 1;
  background: #f8fafc;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  min-height: 360px;
}
.cc-image-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: #94a3b8;
}
.cc-image-empty-icon {
  font-size: 3rem;
  opacity: 0.6;
}
.cc-image-empty p {
  margin: 0;
  font-size: 0.9rem;
}
```

- [ ] **Step 2: Typecheck**

Run: `npm --prefix frontend run typecheck`

Expected: PASS. (No template binding changes; just structural.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/generations/GenerationCreateModal.vue
git commit -m "feat(frontend): GenerationCreateModal 1200px two-column layout"
```

---

## Task 8: GenerationCreateModal 状态机 — submit 不关弹窗 + 轮询 + 主图显示

**Files:**
- Modify: `frontend/src/features/generations/GenerationCreateModal.vue` (script section: add state, rewrite `submit()`, add `pollOnce()`, add `watchers`, lifecycle hooks; template: replace empty-state with conditional rendering, add status text line)

**Interfaces:**
- Produces: After successful `POST /generations`, modal stays open
- Produces: Right panel polls `GET /generations/{id}` every 2s; updates status text and shows main image on success
- Produces: `submitError` shown in left column only on initial POST failure (ComfyUI down, validation, etc.)

- [ ] **Step 1: Add new refs in `<script setup>`**

In `frontend/src/features/generations/GenerationCreateModal.vue`, after `const submitError = ref<string | null>(null);` (line 23) and before `const step = ref(1);` (line 24), insert:

```ts
const activeGenId = ref<string | null>(null);
const activeStatus = ref<GenerationStatus | null>(null);
const activeError = ref<string | null>(null);
const mainImageUrl = ref<string | null>(null);
const history = ref<Array<{ id: string; imageUrl: string }>>([]);
let pollTimer: number | undefined;
```

Add `GenerationStatus` to the type import on line 5:

```ts
import type { GenerationConfigSummary, GenerationField, GenerationStatus, GenerationSummary } from "@/types/api";
```

- [ ] **Step 2: Rewrite `submit()` to start polling**

Replace the existing `submit()` function (lines 245-269) with:

```ts
async function submit() {
  if (!workflowId.value) return;
  submitting.value = true;
  submitError.value = null;
  try {
    const parameters: Record<string, unknown> = {};
    for (const f of fields.value) {
      const isSeed = f.type === "seed";
      const isRandom = isSeed && randomFlags.value[`${f.key}_random`];
      if (isRandom) {
        parameters[`${f.key}_random`] = true;
      } else {
        parameters[f.key] = values.value[f.key];
        if (isSeed) parameters[`${f.key}_random`] = false;
      }
    }
    const res = await api.generations.create({ workflow_id: workflowId.value, parameters });
    if (res.status !== 201) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail ?? `创建失败:${res.status}`);
    }
    const gen = (await res.json()) as GenerationSummary;
    activeGenId.value = gen.id;
    activeStatus.value = gen.status;
    activeError.value = null;
    mainImageUrl.value = null;
    emit("generated");  // 通知父级刷新列表;不 emit close,弹窗保持打开
    startPolling();
  } catch (err) {
    submitError.value = err instanceof Error ? err.message : String(err);
  } finally {
    submitting.value = false;
  }
}
```

Note: removed `emit("close")` — modal stays open.

- [ ] **Step 3: Add polling functions after `submit()`**

After `submit()` (just before `function paramDisplay(...)` at line 271), insert:

```ts
function startPolling() {
  stopPolling();
  pollTimer = window.setInterval(pollOnce, 2000);
  pollOnce();
}

function stopPolling() {
  if (pollTimer !== undefined) {
    window.clearInterval(pollTimer);
    pollTimer = undefined;
  }
}

async function pollOnce() {
  if (!activeGenId.value) return;
  try {
    const gen = await api.generations.get(activeGenId.value);
    activeStatus.value = gen.status;
    activeError.value = gen.error;
    if (gen.status === "success" && gen.outputs.length > 0) {
      const filename = gen.outputs[0];
      mainImageUrl.value = api.generations.imageUrl(gen.id, filename);
      // 入栈历史(去重 + 最新在左)
      if (!history.value.some((h) => h.id === gen.id)) {
        history.value = [{ id: gen.id, imageUrl: mainImageUrl.value }, ...history.value];
      }
      stopPolling();
    } else if (gen.status === "failed") {
      stopPolling();
    }
  } catch {
    /* 单次失败静默忽略 */
  }
}
```

- [ ] **Step 4: Add lifecycle hook to clear timer**

After `onMounted` (lines 152-177), add:

```ts
import { onUnmounted } from "vue";
```

(Replace the existing `import { computed, onMounted, ref, watch } from "vue";` on line 2 with `import { computed, onMounted, onUnmounted, ref, watch } from "vue";`.)

Then after `onMounted(...)`, add:

```ts
onUnmounted(() => {
  stopPolling();
});
```

- [ ] **Step 5: Update right panel template to render active state**

Replace the empty-state `<div class="cc-image-empty">...</div>` block in the right column (added in Task 7) with conditional rendering. Find the line containing `<div class="cc-image-empty">` and replace the **entire** `<div class="cc-image-main">...</div>` block with:

```html
          <div class="cc-image-main">
            <el-icon v-if="activeGenId && (activeStatus === 'queued' || activeStatus === 'running')" class="is-loading cc-image-loading">
              <Loading />
            </el-icon>
            <img v-else-if="mainImageUrl" :src="mainImageUrl" alt="生成结果" class="cc-image-main-img" />
            <div v-else-if="activeGenId && activeStatus === 'failed' && activeError === '用户中止'" class="cc-image-cancelled">
              <span class="cc-image-cancelled-icon">⏹</span>
              <p>已中止</p>
            </div>
            <div v-else-if="activeGenId && activeStatus === 'failed'" class="cc-image-error">
              <p>{{ activeError || '生成失败' }}</p>
            </div>
            <div v-else class="cc-image-empty">
              <span class="cc-image-empty-icon">🖼</span>
              <p>点击「生成」开始</p>
            </div>
          </div>
          <div v-if="activeGenId" class="cc-image-status">
            <span v-if="activeStatus === 'queued'">排期中…</span>
            <span v-else-if="activeStatus === 'running'">生成中…</span>
            <span v-else-if="activeStatus === 'success'">完成</span>
            <span v-else-if="activeStatus === 'failed' && activeError === '用户中止'">已中止</span>
            <span v-else-if="activeStatus === 'failed'">失败</span>
          </div>
```

Add `Loading` to the icon import on line 4:

```ts
import { Loading } from "@element-plus/icons-vue";
```

(Existing file has no icon imports; this is the first one. If other icons are needed elsewhere in this file already, just merge.)

In `<style>`, add:

```scss
.cc-image-loading {
  font-size: 3rem;
  color: #0ea5e9;
}
.cc-image-main-img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}
.cc-image-cancelled,
.cc-image-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: #64748b;
  padding: 1rem;
  text-align: center;
}
.cc-image-cancelled-icon {
  font-size: 3rem;
  opacity: 0.6;
}
.cc-image-error {
  color: #ef4444;
}
.cc-image-status {
  font-size: 0.85rem;
  color: #475569;
  flex-shrink: 0;
}
```

- [ ] **Step 6: Typecheck**

Run: `npm --prefix frontend run typecheck`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/features/generations/GenerationCreateModal.vue
git commit -m "feat(frontend): submit keeps modal open + 2s polling + main image"
```

---

## Task 9: GenerationCreateModal 中止按钮 + 缩略图历史

**Files:**
- Modify: `frontend/src/features/generations/GenerationCreateModal.vue` (script: abort handler, thumbnail click handler; template: abort button in footer, thumbnail row in right panel; styles)

**Interfaces:**
- Produces: Footer shows「中止」button (red plain, with `CircleClose` icon) when `activeGenId && activeStatus in {queued, running}`. Click → optimistic UI update + `api.generations.cancel(id)`.
- Produces: Right panel renders a horizontal thumbnail strip below main image (only when `history.length > 0`). Each thumbnail 80×80; clicking sets `mainImageUrl` to that thumbnail's url.

- [ ] **Step 1: Add abort handler in script**

After `pollOnce()` (added in Task 8), insert:

```ts
const aborting = ref(false);
const abortError = ref<string | null>(null);

async function abort() {
  if (!activeGenId.value || aborting.value) return;
  aborting.value = true;
  abortError.value = null;
  const genId = activeGenId.value;
  try {
    const res = await api.generations.cancel(genId);
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail ?? `中止失败:${res.status}`);
    }
    // 后端会写 failed=用户中止,下一轮 pollOnce 命中即停止 + 显示「已中止」
  } catch (err) {
    abortError.value = err instanceof Error ? err.message : String(err);
  } finally {
    aborting.value = false;
  }
}

function showThumbnail(url: string) {
  mainImageUrl.value = url;
}
```

- [ ] **Step 2: Add abort button to footer + thumbnail row to right panel**

In the existing `<template #footer>` block (lines 479-499), find the `<el-button v-else type="primary" :loading="submitting" @click="submit">生成</el-button>` line (last button, line ~497) and add an abort button **before** it (or after — pick after for natural reading order):

After the existing 「生成」 button, insert:

```html
        <el-button
          v-if="activeGenId && (activeStatus === 'queued' || activeStatus === 'running')"
          type="danger"
          plain
          :loading="aborting"
          @click="abort"
        >
          <el-icon style="margin-right: 4px"><CircleClose /></el-icon>
          中止
        </el-button>
```

In the right column `<div class="cc-modal-right">` block (added in Task 7/8), **after** `<div class="cc-image-status">...</div>` block, append:

```html
        <div v-if="history.length > 0" class="cc-image-history">
          <div
            v-for="(item, idx) in history"
            :key="item.id"
            class="cc-image-thumb"
            :class="{ 'is-active': mainImageUrl === item.imageUrl }"
            @click="showThumbnail(item.imageUrl)"
          >
            <img :src="item.imageUrl" :alt="`结果 ${idx + 1}`" />
          </div>
        </div>
```

Add an `abortError` alert above the footer (or inside left column). Inside `<div class="cc-modal-left">`, after the `<el-alert v-if="submitError">` block, add:

```html
        <el-alert
          v-if="abortError"
          :title="abortError"
          type="error"
          :closable="false"
          show-icon
        />
```

Add `CircleClose` to icon imports:

```ts
import { CircleClose, Loading } from "@element-plus/icons-vue";
```

- [ ] **Step 3: Add styles**

In `<style>`, add:

```scss
.cc-image-history {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  flex-shrink: 0;
  padding: 4px 0;
}
.cc-image-thumb {
  width: 80px;
  height: 80px;
  border-radius: 6px;
  overflow: hidden;
  cursor: pointer;
  flex-shrink: 0;
  border: 2px solid transparent;
  transition: transform 0.15s;
}
.cc-image-thumb:hover {
  transform: scale(1.05);
}
.cc-image-thumb.is-active {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 2px rgba(14, 165, 233, 0.2);
}
.cc-image-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
```

- [ ] **Step 4: Typecheck**

Run: `npm --prefix frontend run typecheck`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/generations/GenerationCreateModal.vue
git commit -m "feat(frontend): abort button + thumbnail history"
```

---

## Task 10: 手动 smoke + 合并 main

**Files:** none (verification only)

**Prerequisites:** all 9 prior tasks merged into the feature branch's commit history; `scripts\start-dev.bat` available; ComfyUI running on `:8188` with at least one configured workflow.

- [ ] **Step 1: 启动 dev**

Run: `cmd /c scripts\start-dev.bat`

Expected: uvicorn on `:8000`, vite on `:5173`. Wait for 「前端就绪」 line.

- [ ] **Step 2: 验收清单** (逐一勾选)

- [ ] `/generations` 新建生成 → 第 3 步点「生成」 → 弹窗**不关闭**,右侧出现 loading → 数秒后图片显示在右栏
- [ ] 同一会话再点「再次生成」 → 主图区切 loading,旧图保留在缩略图,新图替换主图
- [ ] 生成中点「中止」 → 1-2 秒内主图区变「已中止」,缩略图不增加
- [ ] 中止后点「再次生成」 → 按钮可点,新一轮开始
- [ ] step 1/2 上一步在生成中可点 → 返回改参数后点「再次生成」正常工作
- [ ] 关闭弹窗后再打开 → 主图区重置回空态(history 不持久化)
- [ ] 从 `/workflows` 点击工作流名进入的同一弹窗:行为一致;成功后页面跳 `/generations`
- [ ] ComfyUI 离线时:点「生成」/「中止」→ el-alert 红色错误
- [ ] 失败(error 非「用户中止」):主图区显示红色错误框,缩略图不入栈
- [ ] 缩略图点击切换主图,激活态边框高亮

- [ ] **Step 3: 停 dev**

Run: `cmd /c scripts\stop-dev.bat`

- [ ] **Step 4: 合并到 main + 推送**

```bash
git checkout main
git merge --no-ff <feature-branch> -m "feat: GenerationCreateModal 生成中实时预览 + 中止按钮"
git push origin main
```

- [ ] **Step 5: 通知用户**

After merge, reply with one-line summary: feature branch name, merge commit SHA, and confirmation that smoke passed. Do not claim "tested" without ticking every box in Step 2.
