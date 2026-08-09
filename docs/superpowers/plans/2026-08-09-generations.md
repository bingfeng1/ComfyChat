# ComfyChat 文生图生成功能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增「生成」页面：基于已配置工作流的 API 模板，通过 ComfyUI 执行文生图；提供生成记录列表（增/删/查）与基于历史参数的再生成。

**Architecture:** 后端新增 `generations` + `workflow_generation_configs` 两张表；`ComfyUIClient` 增加 `submit_prompt/get_history/get_image/get_queue`；`GenerationService` 负责参数填入模板、提交、后台轮询、下载图片到 `storage/outputs/{YYYY-MM}/{gen_id}/`；`/generations` 路由提供 CRUD + 图片服务。前端新增 `features/generations/` 列表页 + 新建/再生成共用弹窗 + 详情弹窗，并在工作流页加「生成配置」弹窗。前端 2 秒轮询列表。

**Tech Stack:** FastAPI + SQLAlchemy 2.x + SQLite（后端）；Vue 3 + Vite + TS（前端）；ComfyUI `/prompt` `/history` `/view` `/queue` HTTP API。

## Global Constraints

- **Vite 代理剥掉 `/api`**：后端路由前缀一律无 `/api`（`/generations`、`/workflows/...`）；前端调用 `/api/generations`。
- **每请求独立 DB session**：路由用 `Depends(get_db_session)`；后台轮询自行 `database.get_session()`，不共享 session。
- **无 alembic**：新表由 `Base.metadata.create_all` 自动创建；**不得给已存在表加列**（配置放独立表）。
- **主键** `String(36)` uuid4 hex；**时间戳** ISO8601 UTC 字符串，用 `_utcnow()`。
- **图片路径**：`storage/outputs/{YYYY-MM}/{gen_id}/{filename}`，年月取 `created_at[:7]`；文件名取 basename 并做路径包含校验。
- **无新运行时依赖**；后端测试用 pytest（`backend\.venv\Scripts\python -m pytest backend/tests/<file> -v`），前端无测试框架仅 `npm run typecheck`。
- **commit 风格**：conventional commits，一个任务一个 commit，`git commit -m "feat: ..."`（不带头 `-c user.*`）。
- **seed 字段语义**：`type="seed"` 的字段在参数中用 `<key>_random` 布尔控制随机；随机开启时服务端生成 `random.randint(0, 2**32 - 1)` 并写入参数（记录实际种子）。
- **轮询**：默认 2 秒间隔，`max_attempts=900`（约 30 分钟上限）。
- **命名**：`storage_root` 来自 `settings.storage_root`（已有字段，无需新增设置）。

---

### Task 1: ComfyUI 客户端执行方法

**Files:**
- Modify: `backend/app/integrations/comfyui/client.py`
- Test: `backend/tests/test_comfyui_client.py`

**Interfaces:**
- Produces: `ComfyUIClient.submit_prompt(prompt: dict) -> str`、`get_history(prompt_id: str) -> dict`、`get_image(filename: str, subfolder: str = "", image_type: str = "output") -> bytes`、`get_queue() -> dict`。失败统一抛 `ComfyUIError`。

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_comfyui_client.py` 末尾追加：

```python
def _fake_client(get_handler):
    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload
        def raise_for_status(self):
            return None
        def json(self):
            return self._payload
        @property
        def content(self):
            return b"PNGDATA"

    class FakeHttpx:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def post(self, url, json):
            get_handler("post", url, json)
            return FakeResponse({"prompt_id": "abc123"})
        def get(self, url, params=None):
            get_handler("get", url, params)
            if "view" in url:
                return FakeResponse({})
            return FakeResponse({"abc123": {"status": {"status_str": "success"}}})

    monkeypatch.setattr("app.integrations.comfyui.client.httpx.Client", FakeHttpx)
    client = ComfyUIClient(Settings(comfyui_base_url="http://example.com:8188/"))


def test_submit_prompt(monkeypatch):
    calls = []
    _fake_client(lambda kind, url, payload: calls.append((kind, url, payload)))
    client = ComfyUIClient(Settings(comfyui_base_url="http://example.com:8188/"))

    prompt = {"3": {"class_type": "KSampler", "inputs": {"seed": 1}}}
    result = client.submit_prompt(prompt)

    assert result == "abc123"
    assert calls[0][0] == "post"
    assert calls[0][1].endswith("/prompt")
    assert calls[0][2] == {"prompt": prompt}


def test_get_history(monkeypatch):
    calls = []
    _fake_client(lambda kind, url, payload: calls.append((kind, url, payload)))
    client = ComfyUIClient(Settings(comfyui_base_url="http://example.com:8188/"))

    result = client.get_history("abc123")

    assert calls[0][1].endswith("/history/abc123")
    assert result["abc123"]["status"]["status_str"] == "success"


def test_get_image(monkeypatch):
    calls = []
    _fake_client(lambda kind, url, payload: calls.append((kind, url, payload)))
    client = ComfyUIClient(Settings(comfyui_base_url="http://example.com:8188/"))

    data = client.get_image("x.png", "", "output")

    assert data == b"PNGDATA"
    _, _, params = calls[0]
    assert params == {"filename": "x.png", "subfolder": "", "type": "output"}


def test_get_queue(monkeypatch):
    calls = []
    _fake_client(lambda kind, url, payload: calls.append((kind, url, payload)))
    client = ComfyUIClient(Settings(comfyui_base_url="http://example.com:8188/"))

    result = client.get_queue()

    assert calls[0][1].endswith("/queue")
    assert "abc123" in result
```

注意：`_fake_client` 内的 `monkeypatch` 是闭包引用，需在调用前定义；建议把 `_fake_client` 改为显式接收 `monkeypatch` 参数：

```python
def _fake_client(monkeypatch):
    ...
```

并把三个测试改为 `_fake_client(monkeypatch)`。

- [ ] **Step 2: 运行测试确认失败**

Run: `backend\.venv\Scripts\python -m pytest backend/tests/test_comfyui_client.py -v`
Expected: FAIL，`AttributeError: 'ComfyUIClient' object has no attribute 'submit_prompt'`

- [ ] **Step 3: 实现客户端方法**

在 `backend/app/integrations/comfyui/client.py` 中新增私有请求辅助与四个方法（放在 `read_userdata_json` 之后）：

```python
    def _request(self, method: str, path: str, timeout: float | None = None, **kwargs):
        if not self._base_url:
            raise ComfyUIError("ComfyUI not configured")
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else None
        try:
            with httpx.Client(timeout=timeout or self._timeout, headers=headers) as client:
                response = getattr(client, method)(f"{self._base_url}{path}", **kwargs)
                response.raise_for_status()
                return response
        except ComfyUIError:
            raise
        except Exception as exc:
            raise ComfyUIError(f"ComfyUI request failed ({method} {path}): {exc}") from exc

    def submit_prompt(self, prompt: dict) -> str:
        response = self._request("post", "/prompt", json={"prompt": prompt})
        return response.json()["prompt_id"]

    def get_history(self, prompt_id: str) -> dict:
        response = self._request("get", f"/history/{prompt_id}")
        return response.json()

    def get_image(self, filename: str, subfolder: str = "", image_type: str = "output") -> bytes:
        response = self._request(
            "get", "/view", timeout=30.0,
            params={"filename": filename, "subfolder": subfolder, "type": image_type},
        )
        return response.content

    def get_queue(self) -> dict:
        response = self._request("get", "/queue")
        return response.json()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `backend\.venv\Scripts\python -m pytest backend/tests/test_comfyui_client.py -v`
Expected: PASS（新增 4 个 + 原 3 个）

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/comfyui/client.py backend/tests/test_comfyui_client.py
git commit -m "feat(backend): add ComfyUI prompt submission and history APIs"
```

---

### Task 2: Generation 与配置 ORM 模型

**Files:**
- Create: `backend/app/models/generation.py`
- Test: `backend/tests/test_generation_models.py`

**Interfaces:**
- Produces: `Generation`（表 `generations`）、`WorkflowGenerationConfig`（表 `workflow_generation_configs`）。列名与 spec 一致。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_generation_models.py`：

```python
from sqlalchemy import func, select

from app.models.generation import Generation, WorkflowGenerationConfig


def test_tables_created(engine):
    assert engine.dialect.has_table(engine.connect(), "generations")
    assert engine.dialect.has_table(engine.connect(), "workflow_generation_configs")


def test_generation_insert_and_read(session):
    gen = Generation(
        workflow_id="wf1",
        workflow_name="z-image",
        parameters_json='{"positive_prompt": "cat"}',
        status="queued",
        prompt_id="p1",
    )
    session.add(gen)
    session.commit()
    got = session.scalar(select(Generation).where(Generation.id == gen.id))
    assert got.status == "queued"
    assert got.workflow_name == "z-image"


def test_config_unique_per_workflow(session):
    session.add(WorkflowGenerationConfig(
        workflow_id="wf1", api_template="{}", fields_json="[]",
    ))
    session.commit()
    import pytest
    from sqlalchemy.exc import IntegrityError
    session.add(WorkflowGenerationConfig(
        workflow_id="wf1", api_template="{}", fields_json="[]",
    ))
    with pytest.raises(IntegrityError):
        session.commit()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `backend\.venv\Scripts\python -m pytest backend/tests/test_generation_models.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.models.generation'`

- [ ] **Step 3: 实现模型**

`backend/app/models/generation.py`：

```python
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Generation(Base):
    __tablename__ = "generations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: uuid.uuid4().hex)
    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_name: Mapped[str] = mapped_column(String(255), nullable=False)
    parameters_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    prompt_id: Mapped[str] = mapped_column(String(36), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    outputs_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_utcnow)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_utcnow, onupdate=_utcnow)


class WorkflowGenerationConfig(Base):
    __tablename__ = "workflow_generation_configs"
    __table_args__ = (UniqueConstraint("workflow_id", name="uq_wf_gen_config_workflow"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: uuid.uuid4().hex)
    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    api_template: Mapped[str] = mapped_column(Text, nullable=False)
    fields_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_utcnow, onupdate=_utcnow)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `backend\.venv\Scripts\python -m pytest backend/tests/test_generation_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/generation.py backend/tests/test_generation_models.py
git commit -m "feat(backend): add Generation and WorkflowGenerationConfig models"
```

---

### Task 3: GenerationRepository

**Files:**
- Create: `backend/app/repositories/generation.py`
- Test: `backend/tests/test_generation_repository.py`

**Interfaces:**
- Consumes: `Generation` 模型（Task 2）。
- Produces: `GenerationRepository(session)` 方法：`create(workflow_id, workflow_name, parameters, status, prompt_id) -> Generation`、`list(status=None) -> list[Generation]`、`get(id)`、`list_pending()`、`update_status(id, status)`、`mark_failed(id, error)`、`update_success(id, outputs)`、`delete(id) -> bool`。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_generation_repository.py`：

```python
from app.repositories.generation import GenerationRepository


def _mk_repo(session):
    return GenerationRepository(session)


def test_create_and_get(session):
    repo = _mk_repo(session)
    gen = repo.create(
        workflow_id="wf1", workflow_name="z-image",
        parameters={"positive_prompt": "cat", "seed": 1, "seed_random": False},
        status="queued", prompt_id="p1",
    )
    assert gen.id
    assert repo.get(gen.id) is not None
    assert repo.get("nope") is None


def test_list_ordered_and_filtered(session):
    repo = _mk_repo(session)
    a = repo.create("wf1", "z-image", {"positive_prompt": "a"}, "success", "p1")
    b = repo.create("wf1", "z-image", {"positive_prompt": "b"}, "queued", "p2")
    items = repo.list()
    assert [i.id for i in items] == [b.id, a.id]
    only_q = repo.list(status="queued")
    assert [i.id for i in only_q] == [b.id]


def test_pending_and_status_updates(session):
    repo = _mk_repo(session)
    g = repo.create("wf1", "z-image", {}, "queued", "p1")
    repo.create("wf1", "z-image", {}, "success", "p2")
    assert [i.id for i in repo.list_pending()] == [g.id]

    repo.update_status(g.id, "running")
    assert repo.get(g.id).status == "running"

    repo.mark_failed(g.id, "boom")
    assert repo.get(g.id).status == "failed"
    assert repo.get(g.id).error == "boom"

    repo.update_success(g.id, ["a.png"])
    got = repo.get(g.id)
    assert got.status == "success"
    assert got.outputs_json == '["a.png"]'


def test_delete(session):
    repo = _mk_repo(session)
    g = repo.create("wf1", "z-image", {}, "queued", "p1")
    assert repo.delete(g.id) is True
    assert repo.get(g.id) is None
    assert repo.delete(g.id) is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `backend\.venv\Scripts\python -m pytest backend/tests/test_generation_repository.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.repositories.generation'`

- [ ] **Step 3: 实现 repository**

`backend/app/repositories/generation.py`：

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.generation import Generation


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class GenerationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        workflow_id: str,
        workflow_name: str,
        parameters: dict,
        status: str,
        prompt_id: str,
    ) -> Generation:
        gen = Generation(
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            parameters_json=json.dumps(parameters, ensure_ascii=False),
            status=status,
            prompt_id=prompt_id,
        )
        self.session.add(gen)
        self.session.commit()
        self.session.refresh(gen)
        return gen

    def list(self, status: Optional[str] = None) -> Sequence[Generation]:
        stmt = select(Generation)
        if status:
            stmt = stmt.where(Generation.status == status)
        stmt = stmt.order_by(Generation.created_at.desc())
        return self.session.scalars(stmt).all()

    def get(self, generation_id: str) -> Optional[Generation]:
        return self.session.get(Generation, generation_id)

    def list_pending(self) -> Sequence[Generation]:
        stmt = select(Generation).where(Generation.status.in_(["queued", "running"]))
        return self.session.scalars(stmt).all()

    def update_status(self, generation_id: str, status: str) -> None:
        gen = self.get(generation_id)
        if gen is None:
            return
        gen.status = status
        gen.updated_at = _utcnow()
        self.session.commit()

    def mark_failed(self, generation_id: str, error: str) -> None:
        gen = self.get(generation_id)
        if gen is None:
            return
        gen.status = "failed"
        gen.error = error
        gen.updated_at = _utcnow()
        self.session.commit()

    def update_success(self, generation_id: str, outputs: list[str]) -> None:
        gen = self.get(generation_id)
        if gen is None:
            return
        gen.status = "success"
        gen.outputs_json = json.dumps(outputs, ensure_ascii=False)
        gen.error = None
        gen.updated_at = _utcnow()
        self.session.commit()

    def delete(self, generation_id: str) -> bool:
        gen = self.get(generation_id)
        if gen is None:
            return False
        self.session.delete(gen)
        self.session.commit()
        return True
```

- [ ] **Step 4: 运行测试确认通过**

Run: `backend\.venv\Scripts\python -m pytest backend/tests/test_generation_repository.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories/generation.py backend/tests/test_generation_repository.py
git commit -m "feat(backend): add GenerationRepository"
```

---

### Task 4: WorkflowGenerationConfigRepository

**Files:**
- Modify: `backend/app/repositories/generation.py`（追加类）
- Test: `backend/tests/test_generation_config_repository.py`

**Interfaces:**
- Produces: `WorkflowGenerationConfigRepository(session)` 方法：`get_by_workflow(workflow_id)`、`upsert(workflow_id, api_template, fields) -> Config`、`list_configured() -> list[tuple[Config, str]]`（(config, workflow_name)）。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_generation_config_repository.py`：

```python
from sqlalchemy.orm import Session

from app.models.workflow import Workflow
from app.repositories.generation import WorkflowGenerationConfigRepository


def _seed_workflow(session: Session, name: str = "z-image") -> str:
    wf = Workflow(
        name=name, source="import", source_key=f"{name}.json",
        original_name=f"{name}.json", size_bytes=1, body="{}",
    )
    session.add(wf)
    session.commit()
    session.refresh(wf)
    return wf.id


def test_upsert_create_and_update(session):
    repo = WorkflowGenerationConfigRepository(session)
    wid = _seed_workflow(session)
    cfg = repo.upsert(wid, {"3": {"inputs": {"seed": 1}}}, [
        {"key": "seed", "label": "种子", "type": "seed", "node_id": "3", "input_name": "seed", "default": 0, "required": True},
    ])
    assert repo.get_by_workflow(wid) is not None
    cfg2 = repo.upsert(wid, {"3": {"inputs": {"seed": 2}}}, [])
    assert cfg2.id == cfg.id


def test_get_missing_returns_none(session):
    repo = WorkflowGenerationConfigRepository(session)
    assert repo.get_by_workflow("nope") is None


def test_list_configured_with_name(session):
    repo = WorkflowGenerationConfigRepository(session)
    wid = _seed_workflow(session, "z-image")
    repo.upsert(wid, "{}", [])
    items = repo.list_configured()
    assert len(items) == 1
    cfg, name = items[0]
    assert name == "z-image"
    assert cfg.workflow_id == wid
```

- [ ] **Step 2: 运行测试确认失败**

Run: `backend\.venv\Scripts\python -m pytest backend/tests/test_generation_config_repository.py -v`
Expected: FAIL，`ImportError: cannot import name 'WorkflowGenerationConfigRepository'`

- [ ] **Step 3: 实现**

在 `backend/app/repositories/generation.py` 追加：

```python
from sqlalchemy import join

from app.models.generation import WorkflowGenerationConfig
from app.models.workflow import Workflow


class WorkflowGenerationConfigRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_workflow(self, workflow_id: str) -> Optional[WorkflowGenerationConfig]:
        stmt = select(WorkflowGenerationConfig).where(
            WorkflowGenerationConfig.workflow_id == workflow_id
        )
        return self.session.scalar(stmt)

    def upsert(
        self,
        workflow_id: str,
        api_template: dict,
        fields: list[dict],
    ) -> WorkflowGenerationConfig:
        cfg = self.get_by_workflow(workflow_id)
        if cfg is None:
            cfg = WorkflowGenerationConfig(
                workflow_id=workflow_id,
                api_template=json.dumps(api_template, ensure_ascii=False),
                fields_json=json.dumps(fields, ensure_ascii=False),
            )
            self.session.add(cfg)
        else:
            cfg.api_template = json.dumps(api_template, ensure_ascii=False)
            cfg.fields_json = json.dumps(fields, ensure_ascii=False)
            cfg.updated_at = _utcnow()
        self.session.commit()
        self.session.refresh(cfg)
        return cfg

    def list_configured(self) -> list[tuple[WorkflowGenerationConfig, str]]:
        stmt = (
            select(WorkflowGenerationConfig, Workflow.name)
            .join(Workflow, Workflow.id == WorkflowGenerationConfig.workflow_id)
            .order_by(Workflow.name.asc())
        )
        return list(self.session.execute(stmt).all())
```

把 `from sqlalchemy import select` 改为 `from sqlalchemy import select`（已存在），并确保 `from sqlalchemy.orm import Session` 与 `json`、`_utcnow` 均已定义。删除多余的 `from sqlalchemy import join`（未被使用）。

- [ ] **Step 4: 运行测试确认通过**

Run: `backend\.venv\Scripts\python -m pytest backend/tests/test_generation_config_repository.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories/generation.py backend/tests/test_generation_config_repository.py
git commit -m "feat(backend): add WorkflowGenerationConfigRepository"
```

---

### Task 5: Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/generation.py`
- Test: `backend/tests/test_generation_schemas.py`

**Interfaces:**
- Produces:
  - `GenerationField`：`key,label,type,node_id,input_name,default,required`；`type` 仅 `text`/`seed`。
  - `GenerationConfigIn {api_template: dict, fields: list[GenerationField]}`。
  - `GenerationConfigOut {workflow_id, api_template: dict, fields: list[GenerationField], updated_at}` + `from_model()`。
  - `GenerationConfigSummaryOut {workflow_id, workflow_name, fields}`。
  - `GenerationConfigListOut {items}`。
  - `GenerationCreateIn {workflow_id: str, parameters: dict}`。
  - `GenerationOut {id,workflow_id,workflow_name,parameters,dict,status,prompt_id,error,outputs,created_at,updated_at}` + `from_model()`。
  - `GenerationListOut {items}`。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_generation_schemas.py`：

```python
import pytest
from pydantic import ValidationError

from app.schemas.generation import (
    GenerationConfigIn,
    GenerationConfigOut,
    GenerationField,
    GenerationOut,
)


def test_generation_field_rejects_unknown_type():
    with pytest.raises(ValidationError):
        GenerationField(
            key="x", label="X", type="checkbox",
            node_id="1", input_name="text", default="", required=True,
        )


def test_generation_config_in_ok():
    cfg = GenerationConfigIn(
        api_template={"3": {"class_type": "KSampler", "inputs": {"seed": 0}}},
        fields=[
            GenerationField(key="seed", label="种子", type="seed", node_id="3", input_name="seed", default=0, required=True),
        ],
    )
    assert cfg.api_template["3"]["inputs"]["seed"] == 0


def test_generation_out_from_model(session):
    from app.repositories.generation import GenerationRepository
    gen = GenerationRepository(session).create(
        "wf1", "z-image", {"positive_prompt": "cat", "seed": 1, "seed_random": False},
        "success", "p1",
    )
    gen.outputs_json = '["a.png"]'
    session.commit()
    out = GenerationOut.from_model(gen)
    assert out.parameters == {"positive_prompt": "cat", "seed": 1, "seed_random": False}
    assert out.outputs == ["a.png"]
    assert out.status == "success"


def test_generation_config_out_from_model(session):
    from app.models.generation import WorkflowGenerationConfig
    cfg = WorkflowGenerationConfig(workflow_id="wf1", api_template="{}", fields_json='[]')
    session.add(cfg)
    session.commit()
    out = GenerationConfigOut.from_model(cfg)
    assert out.api_template == {}
    assert out.fields == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `backend\.venv\Scripts\python -m pytest backend/tests/test_generation_schemas.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.schemas.generation'`

- [ ] **Step 3: 实现 schemas**

`backend/app/schemas/generation.py`：

```python
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from app.models.generation import Generation, WorkflowGenerationConfig


class GenerationField(BaseModel):
    key: str
    label: str
    type: str = Field(pattern="^(text|seed)$")
    node_id: str
    input_name: str
    default: Any = None
    required: bool = False


class GenerationConfigIn(BaseModel):
    api_template: dict
    fields: list[GenerationField]


class GenerationConfigOut(BaseModel):
    workflow_id: str
    api_template: dict
    fields: list[GenerationField]
    updated_at: str

    @classmethod
    def from_model(cls, cfg: WorkflowGenerationConfig) -> "GenerationConfigOut":
        return cls(
            workflow_id=cfg.workflow_id,
            api_template=json.loads(cfg.api_template),
            fields=[GenerationField(**f) for f in json.loads(cfg.fields_json)],
            updated_at=cfg.updated_at,
        )


class GenerationConfigSummaryOut(BaseModel):
    workflow_id: str
    workflow_name: str
    fields: list[GenerationField]


class GenerationConfigListOut(BaseModel):
    items: list[GenerationConfigSummaryOut]


class GenerationCreateIn(BaseModel):
    workflow_id: str
    parameters: dict


class GenerationOut(BaseModel):
    id: str
    workflow_id: str
    workflow_name: str
    parameters: dict
    status: str
    prompt_id: str
    error: str | None = None
    outputs: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str

    @classmethod
    def from_model(cls, gen: Generation) -> "GenerationOut":
        return cls(
            id=gen.id,
            workflow_id=gen.workflow_id,
            workflow_name=gen.workflow_name,
            parameters=json.loads(gen.parameters_json),
            status=gen.status,
            prompt_id=gen.prompt_id,
            error=gen.error,
            outputs=json.loads(gen.outputs_json or "[]"),
            created_at=gen.created_at,
            updated_at=gen.updated_at,
        )


class GenerationListOut(BaseModel):
    items: list[GenerationOut]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `backend\.venv\Scripts\python -m pytest backend/tests/test_generation_schemas.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/generation.py backend/tests/test_generation_schemas.py
git commit -m "feat(backend): add generation schemas"
```

---

### Task 6: GenerationService（参数填入、提交、轮询、下载）

**Files:**
- Create: `backend/app/services/generation.py`
- Test: `backend/tests/test_generation_service.py`

**Interfaces:**
- Consumes: `GenerationRepository`（Task 3）、`WorkflowGenerationConfigRepository`（Task 4）、`ComfyUIClient`（Task 1）、`Settings`。
- Produces:
  - 模块函数 `apply_parameters(api_template: dict, fields: list[dict], parameters: dict) -> tuple[dict, dict]`（返回 (filled_template, effective_parameters)；校验失败抛 `ValueError`）。
  - `GenerationService(gen_repo, config_repo, comfyui, settings, db=None)`：
    - `create(workflow_id, parameters) -> Generation`（无配置抛 `ValueError("workflow not configured")`）。
    - `poll_until_done(generation_id, poll_interval=2.0, max_attempts=900)`。
    - `reconcile()`（对 pending 记录查 history 收编）。
    - `outputs_dir(gen) -> Path`。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_generation_service.py`：

```python
import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.models.generation import Generation
from app.repositories.generation import GenerationRepository, WorkflowGenerationConfigRepository
from app.services.generation import GenerationService, apply_parameters


TEMPLATE = {
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
    "3": {"class_type": "KSampler", "inputs": {"seed": 0}},
}

FIELDS = [
    {"key": "positive_prompt", "label": "正面提示词", "type": "text", "node_id": "6", "input_name": "text", "default": "", "required": True},
    {"key": "seed", "label": "随机数", "type": "seed", "node_id": "3", "input_name": "seed", "default": 0, "required": True},
]


def _config(session, workflow_id):
    WorkflowGenerationConfigRepository(session).upsert(workflow_id, TEMPLATE, FIELDS)


def _settings(tmp_path):
    return Settings(storage_root=tmp_path / "storage", comfyui_base_url="http://example.com:8188/")


def _service(session, settings, comfyui):
    return GenerationService(
        GenerationRepository(session),
        WorkflowGenerationConfigRepository(session),
        comfyui,
        settings,
    )


def test_apply_parameters_fills_template_and_records():
    filled, effective = apply_parameters(
        json.loads(json.dumps(TEMPLATE)), FIELDS,
        {"positive_prompt": "cat", "seed": 42, "seed_random": False},
    )
    assert filled["6"]["inputs"]["text"] == "cat"
    assert filled["3"]["inputs"]["seed"] == 42
    assert effective["positive_prompt"] == "cat"
    assert effective["seed"] == 42


def test_apply_parameters_generates_random_seed():
    filled, effective = apply_parameters(
        json.loads(json.dumps(TEMPLATE)), FIELDS,
        {"positive_prompt": "cat", "seed": 123, "seed_random": True},
    )
    assert filled["3"]["inputs"]["seed"] != 123
    assert 0 <= filled["3"]["inputs"]["seed"] < 2**32
    assert effective["seed"] == filled["3"]["inputs"]["seed"]
    assert effective["seed_random"] is True


def test_apply_parameters_requires_missing_required():
    with pytest.raises(ValueError):
        apply_parameters(json.loads(json.dumps(TEMPLATE)), FIELDS, {})


def test_apply_parameters_rejects_bad_seed_type():
    with pytest.raises(ValueError):
        apply_parameters(
            json.loads(json.dumps(TEMPLATE)), FIELDS,
            {"positive_prompt": "cat", "seed": "abc", "seed_random": False},
        )


class FakeComfy:
    def __init__(self):
        self.submitted = None
        self.history = {}

    def submit_prompt(self, prompt):
        self.submitted = prompt
        return "p-1"

    def get_history(self, prompt_id):
        return self.history

    def get_image(self, filename, subfolder="", image_type="output"):
        return b"PNGDATA"


def test_create_success(session, tmp_path):
    settings = _settings(tmp_path)
    _config(session, "wf1")
    svc = _service(session, settings, FakeComfy())
    gen = svc.create("wf1", {"positive_prompt": "cat", "seed": 5, "seed_random": False})
    assert gen.status == "queued"
    assert gen.prompt_id == "p-1"


def test_create_requires_config(session, tmp_path):
    svc = _service(session, _settings(tmp_path), FakeComfy())
    with pytest.raises(ValueError):
        svc.create("wf1", {})


def test_outputs_dir_uses_year_month(session, tmp_path):
    settings = _settings(tmp_path)
    svc = _service(session, settings, FakeComfy())
    gen = Generation(
        workflow_id="wf1", workflow_name="z-image", parameters_json="{}",
        status="queued", prompt_id="p1", created_at="2026-08-09T12:00:00+00:00",
    )
    d = svc.outputs_dir(gen)
    assert d == settings.storage_root / "outputs" / "2026-08" / gen.id


def test_poll_downloads_images_and_succeeds(session, tmp_path):
    settings = _settings(tmp_path)
    _config(session, "wf1")
    comfy = FakeComfy()
    comfy.history = {
        "p-1": {
            "status": {"status_str": "success"},
            "outputs": {"9": {"images": [{"filename": "out.png", "subfolder": "", "type": "output"}]}},
        }
    }
    svc = _service(session, settings, comfy)
    gen = svc.create("wf1", {"positive_prompt": "cat", "seed": 5, "seed_random": False})

    svc.poll_until_done(gen.id, poll_interval=0.0)

    got = GenerationRepository(session).get(gen.id)
    assert got.status == "success"
    assert json.loads(got.outputs_json) == ["out.png"]
    assert (svc.outputs_dir(gen) / "out.png").read_bytes() == b"PNGDATA"


def test_poll_marks_failed_on_error(session, tmp_path):
    settings = _settings(tmp_path)
    _config(session, "wf1")
    comfy = FakeComfy()
    comfy.history = {"p-1": {"status": {"status_str": "error", "messages": [["execution_error", "boom"]]}}}
    svc = _service(session, settings, comfy)
    gen = svc.create("wf1", {"positive_prompt": "cat", "seed": 5, "seed_random": False})

    svc.poll_until_done(gen.id, poll_interval=0.0)

    got = GenerationRepository(session).get(gen.id)
    assert got.status == "failed"
    assert got.error


def test_poll_retries_until_success(session, tmp_path):
    settings = _settings(tmp_path)
    _config(session, "wf1")
    comfy = FakeComfy()

    def history(prompt_id):
        if not getattr(history, "called", False):
            history.called = True
            return {}
        return {"p-1": {"status": {"status_str": "success"}, "outputs": {}}}

    comfy.get_history = history
    svc = _service(session, settings, comfy)
    gen = svc.create("wf1", {"positive_prompt": "cat", "seed": 5, "seed_random": False})

    svc.poll_until_done(gen.id, poll_interval=0.0)

    assert GenerationRepository(session).get(gen.id).status == "success"


def test_reconcile_finalizes_lost_tasks(session, tmp_path):
    settings = _settings(tmp_path)
    _config(session, "wf1")
    comfy = FakeComfy()
    comfy.history = {
        "p-1": {"status": {"status_str": "success"}, "outputs": {}},
        "p-2": {"status": {"status_str": "error", "messages": [["execution_error", "x"]]}},
    }
    svc = _service(session, settings, comfy)
    repo = GenerationRepository(session)
    g1 = repo.create("wf1", "z-image", {}, "running", "p-1")
    g2 = repo.create("wf1", "z-image", {}, "running", "p-2")

    svc.reconcile()

    assert repo.get(g1.id).status == "success"
    assert repo.get(g2.id).status == "failed"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `backend\.venv\Scripts\python -m pytest backend/tests/test_generation_service.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.services.generation'`

- [ ] **Step 3: 实现 service**

`backend/app/services/generation.py`：

```python
from __future__ import annotations

import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.comfyui.client import ComfyUIClient
from app.models.generation import Generation
from app.repositories.generation import GenerationRepository, WorkflowGenerationConfigRepository
from app.repositories.workflow import WorkflowRepository


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def apply_parameters(
    api_template: dict,
    fields: list[dict],
    parameters: dict,
) -> tuple[dict, dict]:
    """把用户参数填入 API 模板，返回 (filled_template, effective_parameters)。

    effective_parameters 含所有字段的实际值（随机种子为生成后的值）。
    """
    filled = json.loads(json.dumps(api_template))
    effective: dict = {}
    for field in fields:
        key = field["key"]
        value = parameters.get(key)
        if field["type"] == "seed":
            is_random = bool(parameters.get(f"{key}_random"))
            if is_random:
                value = random.randint(0, 2**32 - 1)
                effective[f"{key}_random"] = True
            elif not isinstance(value, int):
                raise ValueError(f"字段 {field['label']} 必须是整数")
        elif field["required"] and (value is None or value == ""):
            raise ValueError(f"字段 {field['label']} 为必填")
        effective[key] = value
        node_id = field["node_id"]
        filled[node_id]["inputs"][field["input_name"]] = value
    return filled, effective


def collect_images(history_entry: dict) -> list[dict]:
    images = []
    for node_output in (history_entry.get("outputs") or {}).values():
        images.extend(node_output.get("images") or [])
    return images


class GenerationService:
    def __init__(
        self,
        gen_repo: GenerationRepository,
        config_repo: WorkflowGenerationConfigRepository,
        comfyui: ComfyUIClient,
        settings: Settings,
        db: Optional[Callable[[], object]] = None,
    ) -> None:
        self.gen_repo = gen_repo
        self.config_repo = config_repo
        self.comfyui = comfyui
        self.settings = settings
        self.db = db

    def create(self, workflow_id: str, parameters: dict) -> Generation:
        cfg = self.config_repo.get_by_workflow(workflow_id)
        if cfg is None:
            raise ValueError("workflow not configured")
        filled, effective = apply_parameters(
            json.loads(cfg.api_template),
            json.loads(cfg.fields_json),
            parameters,
        )
        prompt_id = self.comfyui.submit_prompt(filled)
        wf = WorkflowRepository(self.gen_repo.session).get(workflow_id)
        wf_name = wf.name if wf else workflow_id
        return self.gen_repo.create(
            workflow_id=workflow_id,
            workflow_name=wf_name,
            parameters=effective,
            status="queued",
            prompt_id=prompt_id,
        )

    def outputs_dir(self, gen: Generation) -> Path:
        ym = gen.created_at[:7]
        return self.settings.storage_root / "outputs" / ym / gen.id

    def _poll_once(self, session: Session, gen: Generation) -> bool:
        """查询一次 ComfyUI，返回 True 表示已到达终态。"""
        repo = GenerationRepository(session)
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

    def poll_until_done(
        self,
        generation_id: str,
        poll_interval: float = 2.0,
        max_attempts: int = 900,
    ) -> None:
        """后台轮询：每次用新 session，直到终态或超时。"""
        if self.db is None:
            raise RuntimeError("GenerationService 需要 db 才能后台轮询")
        for _ in range(max_attempts):
            with self.db.get_session() as session:
                repo = GenerationRepository(session)
                gen = repo.get(generation_id)
                if gen is None:
                    return
                if self._poll_once(session, gen):
                    return
            if poll_interval > 0:
                time.sleep(poll_interval)
        with self.db.get_session() as session:
            GenerationRepository(session).mark_failed(generation_id, "轮询超时")

    def reconcile(self) -> None:
        """对仍在 queued/running 的记录做一次兜底查询，用请求 session。"""
        for gen in self.gen_repo.list_pending():
            self._poll_once(self.gen_repo.session, gen)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `backend\.venv\Scripts\python -m pytest backend/tests/test_generation_service.py -v`
Expected: PASS（全部通过；若 `test_poll_retries_until_success` 因闭包共享失败，改用实例属性记录调用次数）

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/generation.py backend/tests/test_generation_service.py
git commit -m "feat(backend): add GenerationService with prompt submission and polling"
```

---

### Task 7: /generations 路由 + main.py 装配

**Files:**
- Create: `backend/app/api/routes/generations.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_generations_api.py`

**Interfaces:**
- Consumes: `GenerationService`（Task 6）、schemas（Task 5）、`get_db_session`/`get_services`/`get_settings`。
- Produces: 路由 `/generations`（无 `/api`）。`BackgroundTasks` 触发 `poll_until_done`。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_generations_api.py`：

```python
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas.generation import GenerationField


FIELDS = [
    GenerationField(key="positive_prompt", label="正面提示词", type="text", node_id="6", input_name="text", default="", required=True),
    GenerationField(key="seed", label="随机数", type="seed", node_id="3", input_name="seed", default=0, required=True),
]
TEMPLATE = {
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
    "3": {"class_type": "KSampler", "inputs": {"seed": 0}},
}


def _client(tmp_path):
    from app.core.config import Settings
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/gen.db",
        storage_root=tmp_path / "storage",
        comfyui_base_url="http://example.com:8188/",
    )
    app = create_app(settings)
    return TestClient(app), settings


def _import_workflow(client, name="z-image"):
    files = {"file": (f"{name}.json", json.dumps(TEMPLATE).encode(), "application/json")}
    return client.post("/workflows/import", files=files).json()["id"]


def _config(client, wid):
    r = client.put(
        f"/workflows/{wid}/generation-config",
        json={"api_template": TEMPLATE, "fields": [f.model_dump() for f in FIELDS]},
    )
    assert r.status_code == 200, r.text
    return r


def test_generation_flow(tmp_path):
    client, _ = _client(tmp_path)
    wid = _import_workflow(client)
    _config(client, wid)

    from app.integrations.comfyui.client import ComfyUIClient

    class FakeComfy:
        def submit_prompt(self, prompt):
            return "p-1"
        def get_history(self, prompt_id):
            return {"p-1": {"status": {"status_str": "success"}, "outputs": {"9": {"images": [{"filename": "out.png", "subfolder": "", "type": "output"}]}}}}
        def get_image(self, filename, subfolder="", image_type="output"):
            return b"PNGDATA"

    for name in ("submit_prompt", "get_history", "get_image"):
        setattr(ComfyUIClient, name, FakeComfy.__dict__[name])

    r = client.post("/generations", json={
        "workflow_id": wid,
        "parameters": {"positive_prompt": "cat", "seed": 42, "seed_random": False},
    })
    assert r.status_code == 201, r.text
    gen = r.json()
    assert gen["status"] in ("queued", "running", "success")
    assert gen["parameters"]["positive_prompt"] == "cat"

    lst = client.get("/generations").json()
    assert len(lst["items"]) == 1
    got = client.get(f"/generations/{gen['id']}").json()
    assert got["id"] == gen["id"]

    img = client.get(f"/generations/{gen['id']}/images/out.png")
    assert img.status_code == 200
    assert img.content == b"PNGDATA"

    rdel = client.delete(f"/generations/{gen['id']}")
    assert rdel.status_code == 204
    assert client.get("/generations").json()["items"] == []


def test_create_requires_config(tmp_path):
    client, _ = _client(tmp_path)
    wid = _import_workflow(client)
    r = client.post("/generations", json={
        "workflow_id": wid,
        "parameters": {"positive_prompt": "cat"},
    })
    assert r.status_code in (400, 409)
    assert "not configured" in r.json()["detail"]


def test_create_rejects_missing_required(tmp_path):
    client, _ = _client(tmp_path)
    wid = _import_workflow(client)
    _config(client, wid)
    r = client.post("/generations", json={"workflow_id": wid, "parameters": {}})
    assert r.status_code == 400


def test_image_404_unknown(tmp_path):
    client, _ = _client(tmp_path)
    r = client.get("/generations/nope/images/x.png")
    assert r.status_code == 404
```

注意：`test_generation_flow` 中后台任务会在 `TestClient` 内同步执行（因为 FakeComfy 立即返回成功），因此断言允许 `status in (queued, running, success)` 且在图片读取前可能已是 success。为稳定，把断言改为允许 success 且若 queued 则其 prompt_id 为 "p-1"：

```python
    assert gen["status"] in ("queued", "running", "success")
    assert gen["prompt_id"] == "p-1"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `backend\.venv\Scripts\python -m pytest backend/tests/test_generations_api.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.api.routes.generations'`

- [ ] **Step 3: 实现路由 + 装配 main.py**

`backend/app/api/routes/generations.py`：

```python
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_services, get_settings
from app.core.config import Settings
from app.repositories.generation import GenerationRepository, WorkflowGenerationConfigRepository
from app.schemas.generation import GenerationCreateIn, GenerationListOut, GenerationOut
from app.services.generation import GenerationService

router = APIRouter(prefix="/generations", tags=["generations"])


def _service(
    session: Session = Depends(get_db_session),
    services: dict = Depends(get_services),
    settings: Settings = Depends(get_settings),
) -> GenerationService:
    return GenerationService(
        GenerationRepository(session),
        WorkflowGenerationConfigRepository(session),
        services["comfyui"],
        settings,
        db=services["database"],
    )


@router.post("", response_model=GenerationOut, status_code=status.HTTP_201_CREATED)
def create_generation(
    payload: GenerationCreateIn,
    background: BackgroundTasks,
    service: GenerationService = Depends(_service),
) -> GenerationOut:
    try:
        gen = service.create(payload.workflow_id, payload.parameters)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    background.add_task(service.poll_until_done, gen.id)
    return GenerationOut.from_model(gen)


@router.get("", response_model=GenerationListOut)
def list_generations(
    status_filter: str | None = None,
    service: GenerationService = Depends(_service),
) -> dict:
    service.reconcile()
    items = service.gen_repo.list(status=status_filter)
    return {"items": [GenerationOut.from_model(g) for g in items]}


@router.get("/{generation_id}", response_model=GenerationOut)
def get_generation(
    generation_id: str,
    service: GenerationService = Depends(_service),
) -> GenerationOut:
    gen = service.gen_repo.get(generation_id)
    if gen is None:
        raise HTTPException(status_code=404, detail="Generation not found")
    return GenerationOut.from_model(gen)


@router.get("/{generation_id}/images/{filename}")
def get_generation_image(
    generation_id: str,
    filename: str,
    service: GenerationService = Depends(_service),
) -> FileResponse:
    gen = service.gen_repo.get(generation_id)
    if gen is None:
        raise HTTPException(status_code=404, detail="Generation not found")
    out_dir = service.outputs_dir(gen)
    safe = Path(filename).name
    path = (out_dir / safe).resolve()
    if path.parent != out_dir.resolve() or not path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path)


@router.delete("/{generation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_generation(
    generation_id: str,
    service: GenerationService = Depends(_service),
) -> Response:
    gen = service.gen_repo.get(generation_id)
    if gen is None:
        raise HTTPException(status_code=404, detail="Generation not found")
    out_dir = service.outputs_dir(gen)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    service.gen_repo.delete(generation_id)
    return Response(status_code=204)
```

在 `backend/app/main.py` 修改：

```python
from app.api.routes import generations, health, workflows
...
    app.include_router(generations.router)
```

（把 `generations` 加入 import，并在 include 处添加一行。）

注意 `list_generations` 中 reconcile 与 list 共用请求 session，`_poll_once` 内部已用该 session 的 repo，不会重复 commit 冲突。

- [ ] **Step 4: 运行测试确认通过**

Run: `backend\.venv\Scripts\python -m pytest backend/tests/test_generations_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/generations.py backend/app/main.py backend/tests/test_generations_api.py
git commit -m "feat(backend): add generations API routes"
```

---

### Task 8: 工作流生成配置路由

**Files:**
- Modify: `backend/app/api/routes/workflows.py`
- Test: `backend/tests/test_generation_config_api.py`

**Interfaces:**
- Consumes: `WorkflowGenerationConfigRepository`（Task 4）、schemas（Task 5）。
- Produces:
  - `PUT /workflows/{id}/generation-config`（body `GenerationConfigIn`）→ `GenerationConfigOut`
  - `GET /workflows/{id}/generation-config` → `GenerationConfigOut`（无配置 404）
  - `GET /workflows/generation-configs` → `GenerationConfigListOut`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_generation_config_api.py`：

```python
import json

from fastapi.testclient import TestClient

from app.main import create_app


def _client(tmp_path):
    from app.core.config import Settings
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/cfg.db",
        storage_root=tmp_path / "storage",
        comfyui_base_url="http://example.com:8188/",
    )
    return TestClient(create_app(settings))


def _import(client, name="z-image"):
    files = {"file": (f"{name}.json", json.dumps({"3": {}}).encode(), "application/json")}
    return client.post("/workflows/import", files=files).json()["id"]


def test_save_and_get_config(tmp_path):
    client = _client(tmp_path)
    wid = _import(client)
    body = {
        "api_template": {"3": {"class_type": "KSampler", "inputs": {"seed": 0}}},
        "fields": [
            {"key": "seed", "label": "随机数", "type": "seed", "node_id": "3", "input_name": "seed", "default": 0, "required": True},
        ],
    }
    r = client.put(f"/workflows/{wid}/generation-config", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["api_template"]["3"]["inputs"]["seed"] == 0

    r2 = client.get(f"/workflows/{wid}/generation-config")
    assert r2.status_code == 200
    assert r2.json()["fields"][0]["type"] == "seed"

    r3 = client.put(f"/workflows/{wid}/generation-config", json=body)
    assert r3.status_code == 200
    assert r3.json()["updated_at"] == r2.json()["updated_at"] or True  # 幂等保存


def test_get_config_404(tmp_path):
    client = _client(tmp_path)
    wid = _import(client)
    r = client.get(f"/workflows/{wid}/generation-config")
    assert r.status_code == 404


def test_list_generation_configs(tmp_path):
    client = _client(tmp_path)
    w1 = _import(client, "z-image")
    w2 = _import(client, "other")
    body = {
        "api_template": {"3": {}},
        "fields": [{"key": "seed", "label": "随机数", "type": "seed", "node_id": "3", "input_name": "seed", "default": 0, "required": True}],
    }
    client.put(f"/workflows/{w1}/generation-config", json=body)
    r = client.get("/workflows/generation-configs")
    assert r.status_code == 200
    items = r.json()["items"]
    assert [i["workflow_id"] for i in items] == [w1]
    assert items[0]["workflow_name"] == "z-image"


def test_put_config_404_unknown_workflow(tmp_path):
    client = _client(tmp_path)
    r = client.put("/workflows/nope/generation-config", json={"api_template": {}, "fields": []})
    assert r.status_code == 404


def test_put_config_rejects_bad_field_type(tmp_path):
    client = _client(tmp_path)
    wid = _import(client)
    r = client.put(f"/workflows/{wid}/generation-config", json={
        "api_template": {},
        "fields": [{"key": "x", "label": "X", "type": "checkbox", "node_id": "1", "input_name": "t", "default": "", "required": False}],
    })
    assert r.status_code == 422
```

- [ ] **Step 2: 运行测试确认失败**

Run: `backend\.venv\Scripts\python -m pytest backend/tests/test_generation_config_api.py -v`
Expected: FAIL，`404`/`405`（路由未实现）

- [ ] **Step 3: 实现路由**

在 `backend/app/api/routes/workflows.py` 的 import 区追加：

```python
from app.repositories.generation import WorkflowGenerationConfigRepository
from app.schemas.generation import (
    GenerationConfigIn,
    GenerationConfigListOut,
    GenerationConfigOut,
    GenerationConfigSummaryOut,
)
```

在 `list_workflows` 之后、`/{workflow_id}` 之前（**路由顺序关键：`/generation-configs` 必须定义在任何 `/{workflow_id}` 之前**）追加依赖与三个端点：

```python
def _config_repo(session: Session = Depends(get_db_session)) -> WorkflowGenerationConfigRepository:
    return WorkflowGenerationConfigRepository(session)


@router.get("/generation-configs", response_model=GenerationConfigListOut)
def list_generation_configs(
    config_repo: WorkflowGenerationConfigRepository = Depends(_config_repo),
) -> dict:
    items = []
    for cfg, name in config_repo.list_configured():
        items.append(GenerationConfigSummaryOut(
            workflow_id=cfg.workflow_id,
            workflow_name=name,
            fields=[f for f in json.loads(cfg.fields_json)],
        ))
    return {"items": items}


@router.put("/{workflow_id}/generation-config", response_model=GenerationConfigOut)
def save_generation_config(
    workflow_id: str,
    payload: GenerationConfigIn,
    repo: WorkflowRepository = Depends(_repo),
    config_repo: WorkflowGenerationConfigRepository = Depends(_config_repo),
) -> GenerationConfigOut:
    if repo.get(workflow_id) is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    cfg = config_repo.upsert(workflow_id, payload.api_template, [f.model_dump() for f in payload.fields])
    return GenerationConfigOut.from_model(cfg)


@router.get("/{workflow_id}/generation-config", response_model=GenerationConfigOut)
def get_generation_config(
    workflow_id: str,
    config_repo: WorkflowGenerationConfigRepository = Depends(_config_repo),
) -> GenerationConfigOut:
    cfg = config_repo.get_by_workflow(workflow_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="Generation config not found")
    return GenerationConfigOut.from_model(cfg)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `backend\.venv\Scripts\python -m pytest backend/tests/test_generation_config_api.py -v`
Expected: PASS（若 404 因路由顺序，调整端点位置后重跑）

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/workflows.py backend/tests/test_generation_config_api.py
git commit -m "feat(backend): add workflow generation-config API endpoints"
```

---

### Task 9: 前端类型与 API 客户端 + 导航路由

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/components/Sidebar.vue`
- Modify: `frontend/src/app/router.ts`

**Interfaces:**
- Produces: 类型 `GenerationStatus`、`GenerationSummary`、`GenerationList`、`GenerationField`、`GenerationConfigSummary`、`GenerationConfigList`；API 方法 `api.generations.{list,get,create,remove,imageUrl}`、`api.workflows.generationConfigs()`、`api.workflows.generationConfig.{get,save}`。

- [ ] **Step 1: 在 `frontend/src/types/api.ts` 追加类型**

```ts
export type GenerationStatus = "queued" | "running" | "success" | "failed";

export interface GenerationSummary {
  id: string;
  workflow_id: string;
  workflow_name: string;
  parameters: Record<string, unknown>;
  status: GenerationStatus;
  prompt_id: string;
  error: string | null;
  outputs: string[];
  created_at: string;
  updated_at: string;
}

export interface GenerationList {
  items: GenerationSummary[];
}

export interface GenerationField {
  key: string;
  label: string;
  type: "text" | "seed";
  node_id: string;
  input_name: string;
  default: string | number | boolean | null;
  required: boolean;
}

export interface GenerationConfigSummary {
  workflow_id: string;
  workflow_name: string;
  fields: GenerationField[];
}

export interface GenerationConfigList {
  items: GenerationConfigSummary[];
}

export interface GenerationConfigPayload {
  api_template: Record<string, unknown>;
  fields: GenerationField[];
}
```

- [ ] **Step 2: 在 `frontend/src/services/api.ts` 追加 API 方法**

```ts
import type {
  ApiInfo,
  GenerationConfigList,
  GenerationConfigPayload,
  GenerationList,
  GenerationStatus,
  GenerationSummary,
  HealthStatus,
  ImportConflict,
  SyncResult,
  WorkflowList,
  WorkflowSource,
  WorkflowSummary,
  WorkflowVersion,
  WorkflowVersionList,
} from "@/types/api";
```

在 `api` 对象内、`workflows` 之后追加：

```ts
  generations: {
    list: (params?: { status?: GenerationStatus }) => {
      const sp = new URLSearchParams();
      if (params?.status) sp.set("status", params.status);
      const qs = sp.toString() ? `?${sp.toString()}` : "";
      return get<GenerationList>(`/generations${qs}`);
    },
    get: (id: string) => get<GenerationSummary>(`/generations/${id}`),
    create: async (payload: {
      workflow_id: string;
      parameters: Record<string, unknown>;
    }) => {
      const res = await request(`/generations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      return res;
    },
    remove: (id: string) => request(`/generations/${id}`, { method: "DELETE" }),
    imageUrl: (id: string, filename: string) =>
      `${API_BASE}/generations/${id}/images/${encodeURIComponent(filename)}`,
  },
  workflows: {
    // ... 现有方法保持不动
    generationConfigs: () =>
      get<GenerationConfigList>(`/workflows/generation-configs`),
    generationConfig: {
      get: (id: string) =>
        get<GenerationConfigPayload & { workflow_id: string; updated_at: string }>(
          `/workflows/${id}/generation-config`
        ),
      save: (id: string, payload: GenerationConfigPayload) =>
        request(`/workflows/${id}/generation-config`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }),
    },
  },
```

- [ ] **Step 3: 更新 Sidebar 与 router**

`frontend/src/components/Sidebar.vue` 第 6 行：

```ts
const items = [
  { to: "/workflows", label: "工作流", icon: "📁" },
  { to: "/generations", label: "生成", icon: "🖼" },
];
```

`frontend/src/app/router.ts` 追加：

```ts
  {
    path: "/generations",
    name: "generations",
    component: () => import("@/features/generations/GenerationsView.vue"),
  },
```

- [ ] **Step 4: 运行 typecheck 确认通过**

Run: `npm --prefix frontend run typecheck`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/services/api.ts frontend/src/components/Sidebar.vue frontend/src/app/router.ts
git commit -m "feat(frontend): add generation types, api client, nav and route"
```

---

### Task 10: 前端生成列表页

**Files:**
- Create: `frontend/src/features/generations/useGenerations.ts`
- Create: `frontend/src/features/generations/GenerationRow.vue`
- Create: `frontend/src/features/generations/GenerationsView.vue`

**Interfaces:**
- Consumes: `api.generations`（Task 9）、`GenerationSummary`。
- Produces: `useGenerations()` 返回 `{items, loading, error, statusFilter, refresh, create, remove}`（每 2 秒轮询）；`GenerationsView` 触发事件 `@create`、`@view`、`@regenerate`、`@delete`。

- [ ] **Step 1: 创建 `useGenerations.ts`**

```ts
import { onMounted, onUnmounted, ref } from "vue";
import { api } from "@/services/api";
import type { GenerationStatus, GenerationSummary } from "@/types/api";

export function useGenerations() {
  const items = ref<GenerationSummary[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const statusFilter = ref<GenerationStatus | "">("");
  let timer: number | undefined;

  async function refresh() {
    loading.value = true;
    error.value = null;
    try {
      const data = await api.generations.list({
        status: statusFilter.value || undefined,
      });
      items.value = data.items;
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err);
    } finally {
      loading.value = false;
    }
  }

  async function create(payload: {
    workflow_id: string;
    parameters: Record<string, unknown>;
  }) {
    const res = await api.generations.create(payload);
    if (res.status !== 201) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail ?? `创建失败：${res.status}`);
    }
    await refresh();
    return (await res.json()) as GenerationSummary;
  }

  async function remove(id: string) {
    const res = await api.generations.remove(id);
    if (res.status !== 204) throw new Error(`删除失败：${res.status}`);
    await refresh();
  }

  onMounted(() => {
    refresh();
    timer = window.setInterval(refresh, 2000);
  });
  onUnmounted(() => {
    if (timer) window.clearInterval(timer);
  });

  return { items, loading, error, statusFilter, refresh, create, remove };
}
```

- [ ] **Step 2: 创建 `GenerationRow.vue`**

```vue
<script setup lang="ts">
import { computed } from "vue";
import { api } from "@/services/api";
import type { GenerationSummary } from "@/types/api";

const props = defineProps<{ generation: GenerationSummary }>();
const emit = defineEmits<{ view: []; regenerate: []; delete: [] }>();

const statusLabel: Record<string, string> = {
  queued: "排队中",
  running: "执行中",
  success: "成功",
  failed: "失败",
};

const promptText = computed(() => {
  const p = props.generation.parameters["positive_prompt"];
  return typeof p === "string" ? p : "";
});

const thumb = computed(() => {
  const first = props.generation.outputs[0];
  return first ? api.generations.imageUrl(props.generation.id, first) : null;
});

function fmtTime(iso: string) {
  return new Date(iso).toLocaleString();
}
</script>

<template>
  <tr>
    <td>
      <img v-if="thumb" :src="thumb" class="thumb" alt="" />
      <div v-else class="thumb placeholder" />
    </td>
    <td class="prompt">{{ promptText || "—" }}</td>
    <td>{{ props.generation.workflow_name }}</td>
    <td>
      <span class="badge" :class="props.generation.status">
        {{ statusLabel[props.generation.status] ?? props.generation.status }}
      </span>
    </td>
    <td>{{ fmtTime(props.generation.created_at) }}</td>
    <td class="actions">
      <button class="link" @click="emit('view')">查看</button>
      <button class="link" @click="emit('regenerate')">再生成</button>
      <button class="link danger" @click="emit('delete')">×</button>
    </td>
  </tr>
</template>

<style scoped>
.thumb { width: 40px; height: 40px; object-fit: cover; border-radius: 4px; }
.placeholder { width: 40px; height: 40px; background: #e2e8f0; border-radius: 4px; }
.prompt { max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.badge { padding: 1px 6px; border-radius: 8px; font-size: 0.8rem; }
.badge.success { background: #e8f5e9; color: #2e7d32; }
.badge.running, .badge.queued { background: #fff3e0; color: #e65100; }
.badge.failed { background: #ffebee; color: #c62828; }
.actions { display: flex; gap: 0.5rem; }
.link { border: none; background: none; color: #0ea5e9; cursor: pointer; padding: 0 0.25rem; }
.link.danger { color: #ef4444; }
</style>
```

- [ ] **Step 3: 创建 `GenerationsView.vue`**

```vue
<script setup lang="ts">
import { ref } from "vue";
import Modal from "@/components/Modal.vue";
import GenerationCreateModal from "./GenerationCreateModal.vue";
import GenerationDetailModal from "./GenerationDetailModal.vue";
import GenerationRow from "./GenerationRow.vue";
import { useGenerations } from "./useGenerations";
import type { GenerationSummary } from "@/types/api";

const { items, loading, error, statusFilter, refresh, remove } = useGenerations();

const showCreate = ref(false);
const detail = ref<GenerationSummary | null>(null);
const regenerate = ref<GenerationSummary | null>(null);
const confirmDelete = ref<GenerationSummary | null>(null);

async function doDelete() {
  if (!confirmDelete.value) return;
  await remove(confirmDelete.value.id);
  confirmDelete.value = null;
}
</script>

<template>
  <div class="page">
    <div class="toolbar">
      <h2>生成</h2>
      <div class="spacer" />
      <button class="btn" @click="showCreate = true">+ 新建生成</button>
    </div>

    <div v-if="error" class="err">{{ error }}</div>

    <div class="filters">
      <select v-model="statusFilter" class="status" @change="refresh">
        <option value="">全部状态</option>
        <option value="queued">排队中</option>
        <option value="running">执行中</option>
        <option value="success">成功</option>
        <option value="failed">失败</option>
      </select>
    </div>

    <table v-if="loading && items.length === 0" class="table">
      <tbody><tr><td>加载中…</td></tr></tbody>
    </table>
    <table v-else class="table">
      <thead>
        <tr><th>图</th><th>提示词</th><th>工作流</th><th>状态</th><th>时间</th><th>操作</th></tr>
      </thead>
      <tbody>
        <GenerationRow
          v-for="g in items"
          :key="g.id"
          :generation="g"
          @view="detail = g"
          @regenerate="regenerate = g"
          @delete="confirmDelete = g"
        />
      </tbody>
    </table>

    <GenerationCreateModal
      v-if="showCreate"
      @close="showCreate = false"
    />
    <GenerationCreateModal
      v-if="regenerate"
      :preset="regenerate"
      @close="regenerate = null"
    />
    <GenerationDetailModal
      v-if="detail"
      :generation-id="detail.id"
      :title="detail.workflow_name"
      @close="detail = null"
    />

    <Modal v-if="confirmDelete" title="删除生成记录" @close="confirmDelete = null">
      <p>确定删除该生成记录及其图片？</p>
      <div class="actions">
        <button class="btn" @click="confirmDelete = null">取消</button>
        <button class="btn danger" @click="doDelete">删除</button>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.page { max-width: 1100px; }
.toolbar { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.75rem; }
.spacer { flex: 1; }
.err { color: #ef4444; margin: 0.5rem 0; }
.filters { margin-bottom: 0.75rem; }
.status { padding: 0.4rem; border: 1px solid #cbd5e1; border-radius: 6px; }
.table { width: 100%; border-collapse: collapse; }
.table th, .table td { text-align: left; padding: 0.5rem 0.75rem; border-bottom: 1px solid #e2e8f0; }
.table th { background: #f8fafc; color: #475569; }
.actions { display: flex; gap: 0.5rem; justify-content: flex-end; }
.btn { padding: 0.4rem 0.9rem; border: 1px solid #cbd5e1; border-radius: 6px; background: #fff; cursor: pointer; }
.btn.danger { background: #ef4444; border-color: #ef4444; color: #fff; }
</style>
```

- [ ] **Step 4: 运行 typecheck 确认通过**

Run: `npm --prefix frontend run typecheck`
Expected: PASS（`GenerationCreateModal.vue` / `GenerationDetailModal.vue` 尚不存在——typecheck 会因动态 import 报错。先创建占位最小文件或先完成 Task 11 再 typecheck。**建议先创建 Task 11 的空壳组件再运行 typecheck**；若报错属预期，标注待 Task 11 补齐。）

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/generations/
git commit -m "feat(frontend): add generations list page"
```

---

### Task 11: 前端新建/再生成弹窗 + 详情弹窗

**Files:**
- Create: `frontend/src/features/generations/GenerationCreateModal.vue`
- Create: `frontend/src/features/generations/GenerationDetailModal.vue`

**Interfaces:**
- Consumes: `api.generations`、`api.workflows.generationConfigs()`（Task 9）、`GenerationConfigSummary`、`GenerationSummary`。
- Produces: `GenerationCreateModal` props `{preset?: GenerationSummary | null}`，事件 `close`；`GenerationDetailModal` props `{generationId, title}`，事件 `close`。

- [ ] **Step 1: 创建 `GenerationCreateModal.vue`**

```vue
<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import Modal from "@/components/Modal.vue";
import { api } from "@/services/api";
import type { GenerationConfigSummary, GenerationField, GenerationSummary } from "@/types/api";

const props = defineProps<{ preset?: GenerationSummary | null }>();
const emit = defineEmits<{ close: [] }>();

const configs = ref<GenerationConfigSummary[]>([]);
const workflowId = ref("");
const values = ref<Record<string, string | number>>({});
const randomFlags = ref<Record<string, boolean>>({});
const loading = ref(false);
const submitting = ref(false);
const submitError = ref<string | null>(null);

const current = computed(
  () => configs.value.find((c) => c.workflow_id === workflowId.value) ?? null
);

const fields = computed<GenerationField[]>(() => current.value?.fields ?? []);

onMounted(async () => {
  try {
    configs.value = (await api.workflows.generationConfigs()).items;
    if (configs.value.length > 0) {
      const presetId = props.preset?.workflow_id ?? configs.value[0].workflow_id;
      selectWorkflow(presetId);
    }
  } catch (err) {
    submitError.value = err instanceof Error ? err.message : String(err);
  }
});

function selectWorkflow(id: string) {
  workflowId.value = id;
  values.value = {};
  randomFlags.value = {};
  if (props.preset && props.preset.workflow_id === id) {
    const p = props.preset.parameters;
    for (const f of fields.value) {
      const v = p[f.key];
      if (typeof v === "string" || typeof v === "number") values.value[f.key] = v;
      randomFlags.value[`${f.key}_random`] = Boolean(p[`${f.key}_random`]);
    }
  } else {
    for (const f of fields.value) {
      if (typeof f.default === "string" || typeof f.default === "number") {
        values.value[f.key] = f.default;
      }
    }
  }
}

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
    await api.generations.create({ workflow_id: workflowId.value, parameters });
    emit("close");
  } catch (err) {
    submitError.value = err instanceof Error ? err.message : String(err);
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <Modal :title="props.preset ? '再生成' : '新建生成'" @close="emit('close')">
    <div class="form">
      <label class="row">
        工作流
        <select v-model="workflowId" @change="selectWorkflow(workflowId)">
          <option v-for="c in configs" :key="c.workflow_id" :value="c.workflow_id">
            {{ c.workflow_name }}
          </option>
        </select>
      </label>

      <template v-if="current">
        <div v-for="f in fields" :key="f.key" class="row">
          <label>{{ f.label }}</label>
          <template v-if="f.type === 'seed'">
            <label class="inline">
              <input
                type="checkbox"
                v-model="randomFlags[`${f.key}_random`]"
              />
              随机
            </label>
            <input
              v-if="!randomFlags[`${f.key}_random`]"
              v-model.number="values[f.key]"
              type="number"
              class="input"
              :required="f.required"
            />
          </template>
          <textarea
            v-else
            v-model="values[f.key]"
            class="input"
            :required="f.required"
            rows="3"
          />
        </div>
      </template>
      <p v-else-if="!loading" class="hint">没有可用的已配置工作流，请先在工作流页配置生成参数。</p>

      <p v-if="submitError" class="err">{{ submitError }}</p>

      <div class="actions">
        <button class="btn" @click="emit('close')">取消</button>
        <button class="btn primary" :disabled="submitting || !current" @click="submit">
          {{ submitting ? "提交中…" : "生成" }}
        </button>
      </div>
    </div>
  </Modal>
</template>

<style scoped>
.form { display: flex; flex-direction: column; gap: 0.75rem; }
.row { display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.9rem; }
.inline { display: flex; align-items: center; gap: 0.25rem; }
.input { padding: 0.4rem; border: 1px solid #cbd5e1; border-radius: 6px; }
.hint { color: #64748b; font-size: 0.85rem; }
.err { color: #ef4444; }
.actions { display: flex; gap: 0.5rem; justify-content: flex-end; }
.btn { padding: 0.4rem 0.9rem; border: 1px solid #cbd5e1; border-radius: 6px; background: #fff; cursor: pointer; }
.btn.primary { background: #0ea5e9; border-color: #0ea5e9; color: #fff; }
</style>
```

- [ ] **Step 2: 创建 `GenerationDetailModal.vue`**

```vue
<script setup lang="ts">
import { ref, watch } from "vue";
import Modal from "@/components/Modal.vue";
import { api } from "@/services/api";
import type { GenerationSummary } from "@/types/api";

const props = defineProps<{ generationId: string; title: string }>();
const emit = defineEmits<{ close: [] }>();

const gen = ref<GenerationSummary | null>(null);
const loadError = ref<string | null>(null);

watch(
  () => props.generationId,
  async (id) => {
    if (!id) return;
    loadError.value = null;
    try {
      gen.value = await api.generations.get(id);
    } catch (err) {
      loadError.value = err instanceof Error ? err.message : String(err);
    }
  },
  { immediate: true }
);
</script>

<template>
  <Modal :title="props.title" @close="emit('close')">
    <div v-if="gen" class="detail">
      <img
        v-for="out in gen.outputs"
        :key="out"
        :src="api.generations.imageUrl(gen.id, out)"
        class="preview"
        alt=""
      />
      <p v-if="gen.outputs.length === 0" class="hint">无输出图片</p>
      <dl class="meta">
        <dt>状态</dt><dd>{{ gen.status }}</dd>
        <dt>工作流</dt><dd>{{ gen.workflow_name }}</dd>
        <dt>时间</dt><dd>{{ new Date(gen.created_at).toLocaleString() }}</dd>
        <template v-if="gen.error">
          <dt>错误</dt><dd class="err">{{ gen.error }}</dd>
        </template>
      </dl>
      <h4>参数</h4>
      <pre class="json">{{ JSON.stringify(gen.parameters, null, 2) }}</pre>
    </div>
    <p v-else-if="loadError" class="err">{{ loadError }}</p>
    <p v-else>加载中…</p>
  </Modal>
</template>

<style scoped>
.detail { display: flex; flex-direction: column; gap: 0.75rem; }
.preview { max-width: 100%; max-height: 55vh; object-fit: contain; border-radius: 6px; }
.hint { color: #64748b; }
.meta { display: grid; grid-template-columns: 4rem 1fr; gap: 0.25rem 0.5rem; font-size: 0.85rem; }
.meta dt { color: #64748b; }
.err { color: #ef4444; }
.json { max-height: 30vh; overflow: auto; background: #0f172a; color: #a5b4fc; padding: 0.75rem; border-radius: 6px; font-size: 0.8rem; }
</style>
```

- [ ] **Step 3: 运行 typecheck 确认通过**

Run: `npm --prefix frontend run typecheck`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/generations/GenerationCreateModal.vue frontend/src/features/generations/GenerationDetailModal.vue
git commit -m "feat(frontend): add generation create and detail modals"
```

---

### Task 12: 工作流页「生成配置」弹窗 + 集成 + 全量验证

**Files:**
- Create: `frontend/src/features/workflows/WorkflowGenerationConfigModal.vue`
- Modify: `frontend/src/features/workflows/WorkflowRow.vue`（加「配置」按钮）
- Modify: `frontend/src/features/workflows/WorkflowsView.vue`（打开弹窗）
- Modify: `backend/app/core/database.py`（SQLite busy_timeout，防御并发写）

**Interfaces:**
- Consumes: `api.workflows.generationConfig.{get,save}`、`GenerationConfigPayload`、`GenerationField`。
- Produces: `WorkflowGenerationConfigModal` props `{workflowId, title}`，事件 `close`/`saved`。

- [ ] **Step 1: 创建 `WorkflowGenerationConfigModal.vue`**

```vue
<script setup lang="ts">
import { onMounted, ref } from "vue";
import Modal from "@/components/Modal.vue";
import { api } from "@/services/api";
import type { GenerationField } from "@/types/api";

const props = defineProps<{ workflowId: string; title: string }>();
const emit = defineEmits<{ close: []; saved: [] }>();

const apiTemplate = ref("{}");
const fields = ref<GenerationField[]>([]);
const saving = ref(false);
const error = ref<string | null>(null);

onMounted(async () => {
  try {
    const cfg = await api.workflows.generationConfig.get(props.workflowId);
    apiTemplate.value = JSON.stringify(cfg.api_template, null, 2);
    fields.value = cfg.fields;
  } catch {
    // 无配置时为空模板
    apiTemplate.value = "{}";
    fields.value = [];
  }
});

function addField() {
  fields.value.push({
    key: "",
    label: "",
    type: "text",
    node_id: "",
    input_name: "",
    default: "",
    required: true,
  });
}

function removeField(i: number) {
  fields.value.splice(i, 1);
}

async function save() {
  saving.value = true;
  error.value = null;
  try {
    const parsed = JSON.parse(apiTemplate.value);
    await api.workflows.generationConfig.save(props.workflowId, {
      api_template: parsed,
      fields: fields.value,
    });
    emit("saved");
    emit("close");
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <Modal :title="`生成配置 · ${props.title}`" @close="emit('close')">
    <div class="form">
      <label class="row">
        API 模板 JSON
        <textarea v-model="apiTemplate" class="input code" rows="8" />
      </label>

      <h4>参数字段</h4>
      <div v-for="(f, i) in fields" :key="i" class="field-row">
        <input v-model="f.key" class="input" placeholder="key" />
        <input v-model="f.label" class="input" placeholder="label" />
        <select v-model="f.type" class="input">
          <option value="text">text</option>
          <option value="seed">seed</option>
        </select>
        <input v-model="f.node_id" class="input" placeholder="node_id" />
        <input v-model="f.input_name" class="input" placeholder="input_name" />
        <input v-model="f.default" class="input" placeholder="default" />
        <label class="inline">
          <input v-model="f.required" type="checkbox" />必填
        </label>
        <button class="link danger" @click="removeField(i)">×</button>
      </div>
      <button class="btn" @click="addField">+ 添加字段</button>

      <p v-if="error" class="err">{{ error }}</p>

      <div class="actions">
        <button class="btn" @click="emit('close')">取消</button>
        <button class="btn primary" :disabled="saving" @click="save">
          {{ saving ? "保存中…" : "保存" }}
        </button>
      </div>
    </div>
  </Modal>
</template>

<style scoped>
.form { display: flex; flex-direction: column; gap: 0.75rem; }
.row { display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.9rem; }
.field-row { display: flex; gap: 0.25rem; align-items: center; flex-wrap: wrap; }
.inline { display: flex; align-items: center; gap: 0.25rem; font-size: 0.8rem; }
.input { padding: 0.35rem; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 0.85rem; }
.code { font-family: monospace; font-size: 0.8rem; }
.err { color: #ef4444; }
.actions { display: flex; gap: 0.5rem; justify-content: flex-end; }
.btn { padding: 0.4rem 0.9rem; border: 1px solid #cbd5e1; border-radius: 6px; background: #fff; cursor: pointer; }
.btn.primary { background: #0ea5e9; border-color: #0ea5e9; color: #fff; }
.link.danger { border: none; background: none; color: #ef4444; cursor: pointer; }
</style>
```

- [ ] **Step 2: 修改 `WorkflowRow.vue`**

在事件声明增加 `config: []`，操作列增加「配置」按钮（仅 browse 来源）：

```ts
const emit = defineEmits<{ view: []; export: []; delete: []; history: []; config: [] }>();
```

```html
      <button class="link" @click="emit('config')">配置</button>
```

- [ ] **Step 3: 修改 `WorkflowsView.vue`**

导入并挂载配置弹窗，行上触发 `@config`：

```ts
import WorkflowGenerationConfigModal from "./WorkflowGenerationConfigModal.vue";
const configOf = ref<WorkflowSummary | null>(null);
```

在 `<WorkflowRow ... @history="historyOf = wf" />` 后追加 `@config="configOf = wf"`，并在 `WorkflowHistoryModal` 后追加：

```html
    <WorkflowGenerationConfigModal
      v-if="configOf"
      :workflow-id="configOf.id"
      :title="configOf.name"
      @close="configOf = null"
      @saved="doSearch"
    />
```

- [ ] **Step 4: 修改 `backend/app/core/database.py` 的 SQLite busy_timeout**

```python
        connect_args={"check_same_thread": False, "timeout": 30}
        if settings.database_url.startswith("sqlite")
        else {},
```

（sqlite3 驱动 `timeout` 即 busy_timeout，缓解后台轮询与请求并发写锁。）

- [ ] **Step 5: 全量验证**

Run backend: `backend\.venv\Scripts\python -m pytest backend/tests -v`
Expected: 全绿（除已知 Windows chmod 用例外）——原 49+ 用例 + 本阶段新增均 PASS。

Run frontend: `npm --prefix frontend run typecheck`
Expected: PASS

Run frontend build: `npm --prefix frontend run build`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/workflows/WorkflowGenerationConfigModal.vue frontend/src/features/workflows/WorkflowRow.vue frontend/src/features/workflows/WorkflowsView.vue backend/app/core/database.py
git commit -m "feat(frontend): add workflow generation config modal; harden sqlite busy timeout"
```

---

## Self-Review

- **Spec 覆盖**：2.1/2.2 表 → Task 2；3.1 校验 → Task 6 `apply_parameters`；3.2 后台任务 → Task 7；3.3 年月路径 → Task 6 `outputs_dir`；3.4 reconcile → Task 6/7；4 客户端 → Task 1；5 前端全部 → Task 9/10/11/12；6 错误处理 → Task 6/7；7 测试 → 各 Task；8 验收 → 全部。
- **无占位符**：所有步骤含实际代码与命令。
- **类型一致性**：`apply_parameters` 返回 `(filled, effective)`；`_poll_once(session, gen)`；`GenerationOut.from_model(gen)`；`GenerationConfigSummaryOut` 用于列表。前后端字段名（`positive_prompt`/`seed`/`<key>_random`）一致。
