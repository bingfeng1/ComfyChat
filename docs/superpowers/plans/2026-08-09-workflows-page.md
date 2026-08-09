# ComfyChat 工作流页实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 ComfyChat 前端加后台管理布局（侧栏 + 顶栏 + `<router-view/>`），实现第一个业务页——工作流页：从本地 ComfyUI 浏览目录同步、支持导入/导出/查看/删除工作流。

**Architecture:** 后端作为 ComfyUI 代理：`ComfyUIClient` 新增 `list_browse()`（调用 `GET /v2/userdata?path=workflows`）与 `read_userdata_json()`（直读 `COMFYUI_USERDATA_DIR` 文件系统，绕开 ComfyUI 0.31.0 的 userdata 子目录读 bug）；`WorkflowRepository` 管 SQLite `workflows` 表；`WorkflowService` 提供 sync/import 业务逻辑。前端 `App.vue` 改为挂 `<AppLayout>`，新增 `/workflows` 路由与 `features/workflows/` 组件。

**Tech Stack:** FastAPI + SQLAlchemy 2.x + Pydantic v2（后端）；Vue 3 + Vite + TypeScript + Vue Router + Pinia（前端）。

## Global Constraints

- 工作目录 `D:\learnAI\ComfyChat`（Windows + PowerShell 5.1）；用 bash 工具 `workdir` 参数，不在命令内 `cd`。
- 国内网络：pip 用清华源（`$env:PIP_INDEX_URL = 'https://pypi.tuna.tsinghua.edu.cn/simple'`），npm 用 npmmirror（`frontend/.npmrc` 已配）。
- 测试命令：`backend\.venv\Scripts\python -m pytest backend/tests/<file> -v`；前端 `npm --prefix frontend run typecheck`。
- `storage/` 与 `backend/.venv/`、`frontend/node_modules/` 不入库；`workflows` 表数据存 `storage/data/comfychat.db`。
- `Settings` 现有四个字段（`comfyui_base_url`、`comfyui_api_key`、`database_url`、`storage_root`）不可破坏；新增字段必须带默认值。
- 工作流 JSON 不解析、不修改、不重命名（导入同名冲突场景除外，走 409 弹窗流程）。
- `backend/app/{models,schemas,repositories,services}/` 为新增空包，需 `__init__.py` 空文件。
- 提交粒度：每任务一个提交，使用约定式提交；用现有 git 身份（`bingfeng <260895778@qq.com>`），不要 `-c user.*`。

---

## File Structure

```
backend/
  app/
    core/config.py                # 新增 comfyui_userdata_dir: Path | None
    models/
      __init__.py                 # 空
      workflow.py                 # Workflow ORM 模型
    schemas/
      __init__.py                 # 空
      workflow.py                 # Pydantic 响应/请求模型
    repositories/
      __init__.py                 # 空
      workflow.py                 # WorkflowRepository
    services/
      __init__.py                 # 空
      workflow.py                 # WorkflowService（sync/import）
    integrations/comfyui/client.py# 新增 list_browse()/read_userdata_json()
    api/deps.py                   # 新增 get_db_session（per-request session）
    api/routes/workflows.py       # /api/workflows* 路由
    main.py                       # 挂新路由
  tests/
    test_workflow_repository.py
    test_workflow_service.py
    test_workflows_api.py
    conftest.py                   # 共享 engine/session fixture
frontend/
  src/
    App.vue                       # 改挂 <AppLayout>
    app/router.ts                 # 加 /workflows，/ → redirect
    app/layout/AppLayout.vue      # 新建
    components/Sidebar.vue        # 新建
    components/TopBar.vue         # 新建（含健康指示灯）
    components/Modal.vue          # 新建
    features/workflows/
      WorkflowsView.vue
      WorkflowRow.vue
      WorkflowImportButton.vue
      WorkflowSyncButton.vue
      WorkflowDetailModal.vue
      ImportConflictDialog.vue
      useWorkflows.ts
    services/api.ts               # 扩 workflows 方法
    types/api.ts                  # 扩类型
```

---

### Task 1: 后端配置 + 空包占位 + 共享测试 fixture

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Create: `backend/app/models/__init__.py`、`backend/app/schemas/__init__.py`、`backend/app/repositories/__init__.py`、`backend/app/services/__init__.py`（全部空文件）
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_config.py`（新增一个断言，或新建 `backend/tests/test_workflow_config.py`）

**Interfaces:**
- Consumes: 现有 `Settings`（pydantic-settings）。
- Produces: `Settings.comfyui_userdata_dir: Path | None = None`；pytest `engine` fixture（内存 SQLite）。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_workflow_config.py`：

```python
from pathlib import Path

from app.core.config import Settings


def test_settings_comfyui_userdata_dir_defaults_to_none():
    settings = Settings()
    assert settings.comfyui_userdata_dir is None


def test_settings_comfyui_userdata_dir_override():
    settings = Settings(comfyui_userdata_dir="./comfy-user")
    assert settings.comfyui_userdata_dir == Path("./comfy-user")
```

- [ ] **Step 2: 运行确认失败**

```powershell
backend\.venv\Scripts\python -m pytest backend/tests/test_workflow_config.py -v
```

预期：`ImportError`（`comfyui_userdata_dir` 不存在于 Settings）。

- [ ] **Step 3: 实现配置**

在 `backend/app/core/config.py` 的 `Settings` 类中，`storage_root` 之后加一行：

```python
    comfyui_userdata_dir: Optional[Path] = Field(default=None)
```

同时 `backend/.env.example` 追加：

```env
COMFYUI_USERDATA_DIR=
```

- [ ] **Step 4: 创建空包**

创建 `backend/app/models/__init__.py`、`backend/app/schemas/__init__.py`、`backend/app/repositories/__init__.py`、`backend/app/services/__init__.py`（4 个 0 字节文件）。

- [ ] **Step 5: 写共享 fixture**

创建 `backend/tests/conftest.py`：

```python
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.models.workflow import Base, Workflow


@pytest.fixture()
def engine(tmp_path: Path):
    db_path = tmp_path / "test.db"
    eng = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine):
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = Session()
    yield s
    s.close()
```

注意：`conftest.py` 引用了 `app.models.workflow.Base`——该模块在 Task 2 才创建。因此 Task 1 的 `conftest.py` **先不要包含模型 import**（Task 1 先写一个最小 conftest，Task 2 再补模型 fixture）。**本步骤修改：** 把上面的 `from app.models.workflow import Base, Workflow` 两行删掉，conftest 只提供 `engine`/`session`（空 sessionmaker 绑定临时库）；Task 2 会重写 conftest 让它 import 模型并建表。

写最小版：

```python
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture()
def engine(tmp_path: Path):
    db_path = tmp_path / "test.db"
    eng = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine):
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = Session()
    yield s
    s.close()
```

- [ ] **Step 6: 运行测试确认通过**

```powershell
backend\.venv\Scripts\python -m pytest backend/tests/test_workflow_config.py backend/tests/test_config.py -v
```

预期：`test_config` 两个 + `test_workflow_config` 两个 = 4 PASS。

- [ ] **Step 7: 提交**

```powershell
git add backend/app/core/config.py backend/.env.example backend/app/models backend/app/schemas backend/app/repositories backend/app/services backend/tests/conftest.py backend/tests/test_workflow_config.py
git commit -m "feat(backend): add comfyui_userdata_dir setting and empty package scaffolding"
```

---

### Task 2: Workflow ORM 模型 + Repository

**Files:**
- Create: `backend/app/models/workflow.py`
- Create: `backend/app/repositories/workflow.py`
- Create: `backend/tests/test_workflow_repository.py`
- Modify: `backend/tests/conftest.py`（补模型 import + 建表）

**Interfaces:**
- Consumes: Task 1 的 `Settings`、`conftest.engine` fixture。
- Produces:
  - `Workflow` ORM：字段 `id/name/source/source_key/original_name/size_bytes/body/created_at/updated_at`，`UNIQUE(source, source_key)`，`__tablename__ = "workflows"`。
  - `Base = declarative_base()`（在 `app/models/workflow.py` 内定义，或独立 `app/models/base.py`——用独立 `base.py` 更清晰）。
  - `WorkflowRepository` 类：`__init__(self, session)`；方法 `upsert(source, source_key, body, name, original_name, size_bytes) -> Workflow`、`list(source=None, q=None) -> list[Workflow]`、`get(id) -> Workflow | None`、`get_by_source_key(source, source_key) -> Workflow | None`、`delete(id) -> bool`。

- [ ] **Step 1: 写失败测试 `test_workflow_repository.py`**

```python
from app.models.workflow import Base, Workflow
from app.repositories.workflow import WorkflowRepository


def _create_tables(engine):
    Base.metadata.create_all(engine)


def test_upsert_inserts_new(engine, session):
    _create_tables(engine)
    repo = WorkflowRepository(session)
    wf = repo.upsert(
        source="browse", source_key="a.json", name="a",
        original_name="a.json", body='{"nodes":[]}', size_bytes=13,
    )
    assert wf.id
    assert wf.source == "browse"
    assert wf.source_key == "a.json"
    assert wf.name == "a"


def test_upsert_updates_existing(engine, session):
    _create_tables(engine)
    repo = WorkflowRepository(session)
    wf = repo.upsert(source="browse", source_key="a.json", name="a",
                     original_name="a.json", body="{}", size_bytes=2)
    first_id = wf.id
    wf2 = repo.upsert(source="browse", source_key="a.json", name="a",
                      original_name="a.json", body='{"nodes":[1]}', size_bytes=15)
    assert wf2.id == first_id
    assert wf2.size_bytes == 15


def test_list_filters_by_source_and_search(engine, session):
    _create_tables(engine)
    repo = WorkflowRepository(session)
    repo.upsert("browse", "aa.json", "aa", "aa.json", "{}", 2)
    repo.upsert("browse", "bb.json", "bb", "bb.json", "{}", 2)
    repo.upsert("import", "cc.json", "cc", "cc.json", "{}", 2)
    assert len(repo.list(source="browse")) == 2
    assert len(repo.list(q="aa")) == 1
    assert len(repo.list(source="browse", q="bb")) == 1
    assert repo.list(q="zz") == []


def test_get_and_delete(engine, session):
    _create_tables(engine)
    repo = WorkflowRepository(session)
    wf = repo.upsert("import", "x.json", "x", "x.json", "{}", 2)
    assert repo.get(wf.id) is not None
    assert repo.delete(wf.id) is True
    assert repo.get(wf.id) is None
    assert repo.delete(wf.id) is False
```

- [ ] **Step 2: 运行确认失败**

```powershell
backend\.venv\Scripts\python -m pytest backend/tests/test_workflow_repository.py -v
```

预期：`ModuleNotFoundError: No module named 'app.models.workflow'`。

- [ ] **Step 3: 实现模型**

创建 `backend/app/models/base.py`：

```python
from sqlalchemy.orm import declarative_base

Base = declarative_base()
```

创建 `backend/app/models/workflow.py`：

```python
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Workflow(Base):
    __tablename__ = "workflows"
    __table_args__ = (UniqueConstraint("source", "source_key", name="uq_workflows_source_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: uuid.uuid4().hex)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    source_key: Mapped[str] = mapped_column(String(255), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_utcnow)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_utcnow, onupdate=_utcnow)
```

- [ ] **Step 4: 实现 Repository**

创建 `backend/app/repositories/workflow.py`：

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.workflow import Workflow


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkflowRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(
        self,
        source: str,
        source_key: str,
        name: str,
        original_name: str,
        body: str,
        size_bytes: int,
    ) -> Workflow:
        existing = self.get_by_source_key(source, source_key)
        if existing is not None:
            existing.body = body
            existing.size_bytes = size_bytes
            existing.original_name = original_name
            existing.updated_at = _utcnow()
            wf = existing
        else:
            wf = Workflow(
                name=name,
                source=source,
                source_key=source_key,
                original_name=original_name,
                body=body,
                size_bytes=size_bytes,
            )
            self.session.add(wf)
        self.session.commit()
        self.session.refresh(wf)
        return wf

    def list(self, source: Optional[str] = None, q: Optional[str] = None) -> Sequence[Workflow]:
        stmt = select(Workflow)
        if source:
            stmt = stmt.where(Workflow.source == source)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                (Workflow.name.ilike(like)) | (Workflow.original_name.ilike(like))
            )
        stmt = stmt.order_by(Workflow.updated_at.desc())
        return self.session.scalars(stmt).all()

    def get(self, workflow_id: str) -> Optional[Workflow]:
        return self.session.get(Workflow, workflow_id)

    def get_by_source_key(self, source: str, source_key: str) -> Optional[Workflow]:
        stmt = select(Workflow).where(
            Workflow.source == source, Workflow.source_key == source_key
        )
        return self.session.scalar(stmt)

    def delete(self, workflow_id: str) -> bool:
        wf = self.get(workflow_id)
        if wf is None:
            return False
        self.session.delete(wf)
        self.session.commit()
        return True
```

- [ ] **Step 5: 更新 conftest 建表**

`backend/tests/conftest.py` 改为：

```python
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base


@pytest.fixture()
def engine(tmp_path: Path):
    db_path = tmp_path / "test.db"
    eng = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine):
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = Session()
    yield s
    s.close()
```

注意：`conftest.py` 现在 import `Base` 并建表，模型里的表在 fixture 中创建。测试文件里 `Base.metadata.create_all(engine)` 重复调用也无害（幂等）。

- [ ] **Step 6: 运行测试确认通过**

```powershell
backend\.venv\Scripts\python -m pytest backend/tests/test_workflow_repository.py -v
```

预期：4 个测试 PASS。

- [ ] **Step 7: 提交**

```powershell
git add backend/app/models backend/app/repositories backend/tests/conftest.py backend/tests/test_workflow_repository.py
git commit -m "feat(backend): add Workflow model and repository"
```

---

### Task 3: ComfyUIClient 扩展

**Files:**
- Modify: `backend/app/integrations/comfyui/client.py`
- Create: `backend/tests/test_comfyui_list_browse.py`

**Interfaces:**
- Consumes: `Settings`（现有 `comfyui_base_url`、`comfyui_api_key` + Task 1 的 `comfyui_userdata_dir`）。
- Produces:
  - `ComfyUIClient.list_browse() -> dict`，调用 `GET /v2/userdata?path=workflows`，返回原始响应 dict；异常时 raise `ComfyUIError`。
  - `ComfyUIClient.read_userdata_json(filename: str) -> str | None`，从 `settings.comfyui_userdata_dir/workflows/{filename}` 读文件返回字符串；目录未配置/文件不存在返回 `None`。

- [ ] **Step 1: 写失败测试 `test_comfyui_list_browse.py`**

```python
from pathlib import Path

import pytest

from app.core.config import Settings
from app.integrations.comfyui.client import ComfyUIClient, ComfyUIError


def test_list_browse_calls_v2_path_param(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url):
            captured["url"] = url
            return FakeResponse()

    class FakeHttpx:
        Client = FakeClient

    monkeypatch.setattr("app.integrations.comfyui.client.httpx", FakeHttpx)
    client = ComfyUIClient(Settings(comfyui_base_url="http://x:8188/"))
    client.list_browse()
    assert captured["url"] == "http://x:8188/v2/userdata?path=workflows"


def test_read_userdata_json_returns_none_when_unconfigured(tmp_path: Path):
    settings = Settings(comfyui_userdata_dir=None)
    client = ComfyUIClient(settings)
    assert client.read_userdata_json("a.json") is None


def test_read_userdata_json_reads_file(tmp_path: Path):
    userdata = tmp_path / "user"
    (userdata / "workflows").mkdir(parents=True)
    (userdata / "workflows" / "a.json").write_text('{"x":1}', encoding="utf-8")
    settings = Settings(comfyui_userdata_dir=userdata)
    client = ComfyUIClient(settings)
    assert client.read_userdata_json("a.json") == '{"x":1}'


def test_read_userdata_json_rejects_path_traversal(tmp_path: Path):
    userdata = tmp_path / "user"
    (userdata / "workflows").mkdir(parents=True)
    settings = Settings(comfyui_userdata_dir=userdata)
    client = ComfyUIClient(settings)
    assert client.read_userdata_json("../secret.json") is None
    assert client.read_userdata_json("sub/../x.json") is None
```

- [ ] **Step 2: 运行确认失败**

```powershell
backend\.venv\Scripts\python -m pytest backend/tests/test_comfyui_list_browse.py -v
```

预期：`ImportError`（`ComfyUIError` 不存在）或属性错误。

- [ ] **Step 3: 实现**

在 `backend/app/integrations/comfyui/client.py` 顶部加异常类，并在 `ComfyUIClient` 内加两个方法：

```python
class ComfyUIError(Exception):
    """Raised when a ComfyUI API call fails."""


class ComfyUIClient:
    # ... 现有 __init__ 和 ping() 保持不动 ...

    def list_browse(self) -> dict:
        if not self._base_url:
            raise ComfyUIError("ComfyUI not configured")
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else None
        try:
            with httpx.Client(timeout=self._timeout, headers=headers) as client:
                response = client.get(f"{self._base_url}/v2/userdata", params={"path": "workflows"})
                response.raise_for_status()
                return response.json()
        except Exception as exc:
            raise ComfyUIError(f"Failed to list workflows: {exc}") from exc

    def read_userdata_json(self, filename: str) -> str | None:
        root = self._userdata_dir
        if root is None:
            return None
        workflows_dir = root / "workflows"
        candidate = (workflows_dir / filename).resolve()
        if candidate.parent != workflows_dir.resolve():
            return None
        if not candidate.is_file():
            return None
        try:
            return candidate.read_text(encoding="utf-8")
        except OSError:
            return None
```

在 `__init__` 中新增属性（`self._userdata_dir`），并把 `Settings` 的 `comfyui_userdata_dir` 转 `Path`：

```python
        self._userdata_dir = settings.comfyui_userdata_dir
```

（`pydantic-settings` 会把 `Path | None` 字段转成 `Path`；若为 None 保持 None。）

- [ ] **Step 4: 运行确认通过**

```powershell
backend\.venv\Scripts\python -m pytest backend/tests/test_comfyui_list_browse.py -v
```

预期：4 个测试 PASS。

- [ ] **Step 5: 提交**

```powershell
git add backend/app/integrations/comfyui/client.py backend/tests/test_comfyui_list_browse.py
git commit -m "feat(backend): extend ComfyUIClient with browse listing and userdata file read"
```

---

### Task 4: WorkflowService（sync/import 逻辑）

**Files:**
- Create: `backend/app/services/workflow.py`
- Create: `backend/tests/test_workflow_service.py`

**Interfaces:**
- Consumes: `WorkflowRepository`、`ComfyUIClient`。
- Produces:
  - `WorkflowService.__init__(self, repo: WorkflowRepository, comfyui: ComfyUIClient)`
  - `WorkflowService.sync() -> dict`：返回 `{"synced_at": str, "browse": {"added": int, "updated": int, "skipped": int, "error": str | None}}`。遍历 `comfyui.list_browse()` 的列表，逐个 `read_userdata_json(name)`；文件可读则 upsert；统计 added/updated/skipped。不删残留。
  - `WorkflowService.import_workflow(filename: str, body: str, overwrite: bool = False, new_name: str | None = None) -> tuple[str, Workflow | None]`：返回 `(status, workflow)`，`status ∈ {"created", "conflict", "replaced"}`。`new_name` 用于重命名后建新行。

- [ ] **Step 1: 写失败测试 `test_workflow_service.py`**

```python
from pathlib import Path

import pytest

from app.core.config import Settings
from app.integrations.comfyui.client import ComfyUIClient, ComfyUIError
from app.models.base import Base
from app.repositories.workflow import WorkflowRepository
from app.services.workflow import WorkflowService


class FakeBrowseClient:
    def __init__(self, listing, body="{}"):
        self.listing = listing
        self.body = body

    def list_browse(self):
        return self.listing

    def read_userdata_json(self, filename):
        if filename in {e["name"] for e in self.listing}:
            return self.body
        return None


def _repo(engine):
    Base.metadata.create_all(engine)
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return WorkflowRepository(Session())


def test_sync_adds_and_counts(engine):
    repo = _repo(engine)
    service = WorkflowService(repo, FakeBrowseClient([
        {"name": "a.json", "path": "workflows/a.json", "type": "file", "size": 2},
        {"name": "b.json", "path": "workflows/b.json", "type": "file", "size": 2},
    ]))
    result = service.sync()
    assert result["browse"]["added"] == 2
    assert result["browse"]["skipped"] == 0
    assert len(repo.list()) == 2


def test_sync_skips_unchanged(engine):
    repo = _repo(engine)
    service = WorkflowService(repo, FakeBrowseClient([{"name": "a.json", "path": "workflows/a.json", "type": "file", "size": 2}]))
    service.sync()
    service2 = WorkflowService(repo, FakeBrowseClient([{"name": "a.json", "path": "workflows/a.json", "type": "file", "size": 2}]))
    result = service2.sync()
    assert result["browse"]["skipped"] == 1
    assert result["browse"]["added"] == 0


def test_sync_updates_when_size_changes(engine):
    repo = _repo(engine)
    service = WorkflowService(repo, FakeBrowseClient([{"name": "a.json", "path": "workflows/a.json", "type": "file", "size": 2}], body="{}"))
    service.sync()
    service2 = WorkflowService(repo, FakeBrowseClient([{"name": "a.json", "path": "workflows/a.json", "type": "file", "size": 99}], body='{"n":2}'))
    result = service2.sync()
    assert result["browse"]["updated"] == 1
    row = repo.get_by_source_key("browse", "a.json")
    assert row.size_bytes == 99


def test_sync_does_not_delete_stale(engine):
    repo = _repo(engine)
    service = WorkflowService(repo, FakeBrowseClient([{"name": "a.json", "path": "workflows/a.json", "type": "file", "size": 2}]))
    service.sync()
    service2 = WorkflowService(repo, FakeBrowseClient([]))
    service2.sync()
    assert len(repo.list()) == 1  # a.json 残留，不删


def test_sync_returns_error_on_comfy_failure(engine):
    repo = _repo(engine)

    class BoomClient:
        def list_browse(self):
            raise ComfyUIError("boom")

    service = WorkflowService(repo, BoomClient())
    result = service.sync()
    assert result["browse"]["error"] is not None
    assert result["browse"]["added"] == 0


def test_import_creates(engine):
    repo = _repo(engine)
    service = WorkflowService(repo, object())
    status, wf = service.import_workflow("a.json", '{"x":1}')
    assert status == "created"
    assert wf.source_key == "a.json"


def test_import_conflict(engine):
    repo = _repo(engine)
    service = WorkflowService(repo, object())
    service.import_workflow("a.json", '{"x":1}')
    status, wf = service.import_workflow("a.json", '{"x":2}')
    assert status == "conflict"
    assert wf is None


def test_import_overwrite(engine):
    repo = _repo(engine)
    service = WorkflowService(repo, object())
    service.import_workflow("a.json", '{"x":1}')
    status, wf = service.import_workflow("a.json", '{"x":2}', overwrite=True)
    assert status == "replaced"
    assert wf.body == '{"x":2}'
    assert wf.id is not None


def test_import_rename(engine):
    repo = _repo(engine)
    service = WorkflowService(repo, object())
    service.import_workflow("a.json", '{"x":1}')
    status, wf = service.import_workflow("a.json", '{"x":2}', new_name="b")
    assert status == "created"
    assert wf.source_key == "b.json"
    assert wf.name == "b"
    assert len(repo.list()) == 2
```

- [ ] **Step 2: 运行确认失败**

```powershell
backend\.venv\Scripts\python -m pytest backend/tests/test_workflow_service.py -v
```

预期：`ModuleNotFoundError: No module named 'app.services.workflow'`。

- [ ] **Step 3: 实现**

创建 `backend/app/services/workflow.py`：

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Union

from app.integrations.comfyui.client import ComfyUIClient, ComfyUIError
from app.models.workflow import Workflow
from app.repositories.workflow import WorkflowRepository

SyncResult = dict
ImportResult = tuple[str, Optional[Workflow]]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkflowService:
    def __init__(self, repo: WorkflowRepository, comfyui: ComfyUIClient) -> None:
        self.repo = repo
        self.comfyui = comfyui

    def sync(self) -> dict:
        summary = {"added": 0, "updated": 0, "skipped": 0, "error": None}
        try:
            listing = self.comfyui.list_browse()
        except ComfyUIError as exc:
            summary["error"] = str(exc)
            return {"synced_at": _utcnow(), "browse": summary}

        for entry in listing:
            name = entry.get("name", "")
            if not name or not name.endswith(".json"):
                continue
            size = int(entry.get("size", 0) or 0)
            body = self.comfyui.read_userdata_json(name)
            if body is None:
                continue
            existing = self.repo.get_by_source_key("browse", name)
            if existing is not None and existing.size_bytes == size:
                summary["skipped"] += 1
                continue
            display = name[:-5] if name.endswith(".json") else name
            self.repo.upsert(
                source="browse", source_key=name, name=display,
                original_name=name, body=body, size_bytes=size,
            )
            if existing is not None:
                summary["updated"] += 1
            else:
                summary["added"] += 1

        return {"synced_at": _utcnow(), "browse": summary}

    def import_workflow(
        self,
        filename: str,
        body: str,
        overwrite: bool = False,
        new_name: Optional[str] = None,
    ) -> ImportResult:
        display = filename[:-5] if filename.endswith(".json") else filename
        existing = self.repo.get_by_source_key("import", filename)

        if new_name:
            new_filename = new_name if new_name.endswith(".json") else f"{new_name}.json"
            wf = self.repo.upsert(
                source="import", source_key=new_filename, name=new_name,
                original_name=new_filename, body=body, size_bytes=len(body.encode("utf-8")),
            )
            return "created", wf

        if existing is not None:
            if overwrite:
                existing.body = body
                existing.size_bytes = len(body.encode("utf-8"))
                existing.updated_at = _utcnow()
                self.repo.session.commit()
                self.repo.session.refresh(existing)
                return "replaced", existing
            return "conflict", None

        wf = self.repo.upsert(
            source="import", source_key=filename, name=display,
            original_name=filename, body=body, size_bytes=len(body.encode("utf-8")),
        )
        return "created", wf
```

- [ ] **Step 4: 运行确认通过**

```powershell
backend\.venv\Scripts\python -m pytest backend/tests/test_workflow_service.py -v
```

预期：9 个测试 PASS。

- [ ] **Step 5: 提交**

```powershell
git add backend/app/services/workflow.py backend/tests/test_workflow_service.py
git commit -m "feat(backend): add WorkflowService sync and import logic"
```

---

### Task 5: Workflow API 路由

**Files:**
- Create: `backend/app/api/routes/workflows.py`
- Create: `backend/app/schemas/workflow.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_workflows_api.py`

**Interfaces:**
- Consumes: `WorkflowRepository`、`WorkflowService`、Task 1 `Settings`。
- Produces:
  - `GET /api/workflows?source=&q=` → `200` 列表（`{"items": [...]}`）
  - `GET /api/workflows/{id}` → `200` 单条 | `404`
  - `GET /api/workflows/{id}/body` → `200` 原始 JSON | `404`
  - `GET /api/workflows/{id}/export` → `200` 附件下载 | `404`
  - `DELETE /api/workflows/{id}` → `204` | `404`
  - `POST /api/workflows/import`（multipart `file`）→ `201 | 200 | 409 | 400`
  - `POST /api/workflows/sync` → `200` 摘要

- [ ] **Step 1: 写 Pydantic schema**

创建 `backend/app/schemas/workflow.py`：

```python
from __future__ import annotations

from pydantic import BaseModel


class WorkflowOut(BaseModel):
    id: str
    name: str
    source: str
    source_key: str
    original_name: str
    size_bytes: int
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class WorkflowListOut(BaseModel):
    items: list[WorkflowOut]


class SyncResultOut(BaseModel):
    synced_at: str
    browse: dict


class ConflictOut(BaseModel):
    filename: str
    existing: WorkflowOut
```

- [ ] **Step 2: 写失败测试 `test_workflows_api.py`**

```python
import io
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.deps import get_services, get_settings
from app.main import create_app


def _client(tmp_path: Path, monkeypatch):
    settings = __import__("app.core.config", fromlist=["Settings"]).Settings(
        database_url=f"sqlite:///{tmp_path}/api.db",
        storage_root=tmp_path / "storage",
        comfyui_userdata_dir=tmp_path / "user",
    )
    (settings.comfyui_userdata_dir / "workflows").mkdir(parents=True, exist_ok=True)
    app = create_app(settings)
    return TestClient(app), settings


def test_list_empty(tmp_path):
    client, _ = _client(tmp_path)
    r = client.get("/api/workflows")
    assert r.status_code == 200
    assert r.json() == {"items": []}


def test_import_and_list(tmp_path):
    client, _ = _client(tmp_path)
    files = {"file": ("a.json", io.BytesIO(b'{"x":1}'), "application/json")}
    r = client.post("/api/workflows/import", files=files)
    assert r.status_code == 201
    data = r.json()
    assert data["source_key"] == "a.json"
    assert data["name"] == "a"

    r2 = client.get("/api/workflows")
    assert len(r2.json()["items"]) == 1


def test_import_duplicate_conflict(tmp_path):
    client, _ = _client(tmp_path)
    files = {"file": ("a.json", io.BytesIO(b'{"x":1}'), "application/json")}
    client.post("/api/workflows/import", files=files)
    r = client.post("/api/workflows/import", files=files)
    assert r.status_code == 409
    assert r.json()["filename"] == "a.json"
    assert r.json()["existing"]["name"] == "a"


def test_import_overwrite(tmp_path):
    client, _ = _client(tmp_path)
    files = {"file": ("a.json", io.BytesIO(b'{"x":1}'), "application/json")}
    client.post("/api/workflows/import", files=files)
    r = client.post("/api/workflows/import", files=files, params={"overwrite": "true"})
    assert r.status_code == 200
    assert r.json()["body"] == '{"x":1}'


def test_import_rename(tmp_path):
    client, _ = _client(tmp_path)
    files = {"file": ("a.json", io.BytesIO(b'{"x":1}'), "application/json")}
    client.post("/api/workflows/import", files=files)
    r = client.post("/api/workflows/import", files=files, params={"name": "b"})
    assert r.status_code == 201
    assert r.json()["source_key"] == "b.json"


def test_import_invalid_json(tmp_path):
    client, _ = _client(tmp_path)
    files = {"file": ("bad.json", io.BytesIO(b"not json"), "application/json")}
    r = client.post("/api/workflows/import", files=files)
    assert r.status_code == 400


def test_get_body_and_export(tmp_path):
    client, _ = _client(tmp_path)
    files = {"file": ("a.json", io.BytesIO(b'{"x":1}'), "application/json")}
    wid = client.post("/api/workflows/import", files=files).json()["id"]

    rb = client.get(f"/api/workflows/{wid}/body")
    assert rb.status_code == 200
    assert rb.json() == {"x": 1}

    re = client.get(f"/api/workflows/{wid}/export")
    assert re.status_code == 200
    assert re.headers["content-disposition"].startswith("attachment")
    assert re.content == b'{"x":1}'


def test_delete(tmp_path):
    client, _ = _client(tmp_path)
    files = {"file": ("a.json", io.BytesIO(b'{"x":1}'), "application/json")}
    wid = client.post("/api/workflows/import", files=files).json()["id"]
    r = client.delete(f"/api/workflows/{wid}")
    assert r.status_code == 204
    r2 = client.delete(f"/api/workflows/{wid}")
    assert r2.status_code == 404


def test_sync(tmp_path, monkeypatch):
    client, settings = _client(tmp_path)
    (settings.comfyui_userdata_dir / "workflows" / "wf.json").write_text('{"n":1}', encoding="utf-8")

    from app.integrations.comfyui.client import ComfyUIClient

    class FakeClient:
        def __init__(self, s): pass
        def ping(self): return "ok"
        def list_browse(self):
            return [{"name": "wf.json", "path": "workflows/wf.json", "type": "file", "size": 6}]
        def read_userdata_json(self, name):
            return '{"n":1}'

    monkeypatch.setattr(ComfyUIClient, "list_browse", FakeClient.list_browse)
    monkeypatch.setattr(ComfyUIClient, "read_userdata_json", FakeClient.read_userdata_json)
    r = client.post("/api/workflows/sync")
    assert r.status_code == 200
    body = r.json()
    assert body["browse"]["added"] == 1
    assert len(client.get("/api/workflows").json()["items"]) == 1
```

- [ ] **Step 3: 运行确认失败**

```powershell
backend\.venv\Scripts\python -m pytest backend/tests/test_workflows_api.py -v
```

预期：`ImportError`（`workflows` 路由不存在）或 404。

- [ ] **Step 4: 实现路由**

创建 `backend/app/api/routes/workflows.py`：

```python
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_services
from app.integrations.comfyui.client import ComfyUIClient
from app.repositories.workflow import WorkflowRepository
from app.schemas.workflow import ConflictOut, SyncResultOut, WorkflowListOut, WorkflowOut
from app.services.workflow import WorkflowService

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


def _repo(session: Session = Depends(get_db_session)) -> WorkflowRepository:
    return WorkflowRepository(session)


def _service(
    session: Session = Depends(get_db_session),
    services: dict = Depends(get_services),
) -> WorkflowService:
    return WorkflowService(WorkflowRepository(session), services["comfyui"])


@router.get("", response_model=WorkflowListOut)
def list_workflows(
    repo: WorkflowRepository = Depends(_repo),
    source: str | None = Query(default=None),
    q: str | None = Query(default=None),
) -> dict:
    items = repo.list(source=source, q=q)
    return {"items": [WorkflowOut.model_validate(w) for w in items]}


@router.get("/{workflow_id}", response_model=WorkflowOut)
def get_workflow(
    workflow_id: str,
    repo: WorkflowRepository = Depends(_repo),
) -> WorkflowOut:
    wf = repo.get(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return WorkflowOut.model_validate(wf)


@router.get("/{workflow_id}/body")
def get_workflow_body(
    workflow_id: str,
    repo: WorkflowRepository = Depends(_repo),
) -> Response:
    wf = repo.get(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return Response(content=wf.body, media_type="application/json")


@router.get("/{workflow_id}/export")
def export_workflow(
    workflow_id: str,
    repo: WorkflowRepository = Depends(_repo),
) -> Response:
    wf = repo.get(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    filename = wf.name if wf.name.endswith(".json") else f"{wf.name}.json"
    return Response(
        content=wf.body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow(
    workflow_id: str,
    repo: WorkflowRepository = Depends(_repo),
) -> Response:
    ok = repo.delete(workflow_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return Response(status_code=204)


@router.post("/import", status_code=status.HTTP_201_CREATED)
def import_workflow(
    service: WorkflowService = Depends(_service),
    file: UploadFile = File(...),
    overwrite: bool = Query(default=False),
    name: str | None = Query(default=None),
) -> Response:
    filename = file.filename or ""
    if not filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Only .json files are supported")
    body_bytes = file.file.read()
    try:
        json.loads(body_bytes)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="File is not valid JSON")
    body = body_bytes.decode("utf-8")

    result_status, wf = service.import_workflow(
        filename, body, overwrite=overwrite, new_name=name
    )
    if result_status == "conflict":
        existing = service.repo.get_by_source_key("import", filename)
        payload = ConflictOut(
            filename=filename,
            existing=WorkflowOut.model_validate(existing),
        ).model_dump()
        return Response(content=json.dumps(payload), status_code=409, media_type="application/json")
    if result_status == "replaced":
        return Response(
            content=WorkflowOut.model_validate(wf).model_dump_json(),
            status_code=200,
            media_type="application/json",
        )
    return Response(
        content=WorkflowOut.model_validate(wf).model_dump_json(),
        status_code=201,
        media_type="application/json",
    )


@router.post("/sync", response_model=SyncResultOut)
def sync_workflows(service: WorkflowService = Depends(_service)) -> dict:
    return service.sync()
```

修改 `backend/app/api/deps.py`，新增 per-request session 依赖（SQLAlchemy `Session` 非线程安全，FastAPI sync handler 跑在线程池，必须每请求一个新 session）：

```python
from __future__ import annotations

from typing import Iterator

from fastapi import Request
from sqlalchemy.orm import Session


def get_settings(request: Request):
    return request.app.state.settings


def get_services(request: Request):
    return request.app.state.services


def get_db_session(request: Request) -> Iterator[Session]:
    database = get_services(request)["database"]
    with database.get_session() as session:
        yield session
```

注意：`database` 模块在 `app.state.services["database"]` 里（Task 5 之前的骨架就是如此，见 `main.py`），所以这里从 `get_services(request)["database"]` 取，复用其 `get_session()` 上下文管理器（Task 3 已有）。不要直接 `request.app.state.database`——那不存在。

修改 `backend/app/main.py`——不再创建共享 session，把 `database` 模块放进 `app.state.services`，repo/service 由路由层用 `Depends` 每请求构建：

```python
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI

from app.api.routes import health, workflows
from app.core import database
from app.core.config import Settings
from app.integrations.comfyui.client import ComfyUIClient


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or Settings()
    database.configure(settings)

    app = FastAPI(title="ComfyChat API", version="0.1.0")
    app.state.settings = settings
    app.state.services = {
        "database": database,
        "comfyui": ComfyUIClient(settings),
    }

    app.include_router(health.router)
    app.include_router(workflows.router)
    return app


app = create_app()
```

`workflows.py` 路由改为用 `Depends(get_db_session)` 每请求建 repo/service：

```python
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_services
from app.integrations.comfyui.client import ComfyUIClient
from app.repositories.workflow import WorkflowRepository
from app.schemas.workflow import ConflictOut, SyncResultOut, WorkflowListOut, WorkflowOut
from app.services.workflow import WorkflowService

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


def _repo(session: Session = Depends(get_db_session)) -> WorkflowRepository:
    return WorkflowRepository(session)


def _service(
    session: Session = Depends(get_db_session),
    services: dict = Depends(get_services),
) -> WorkflowService:
    return WorkflowService(WorkflowRepository(session), services["comfyui"])
```

随后每个 handler 用 `repo: WorkflowRepository = Depends(_repo)` 或 `service: WorkflowService = Depends(_service)` 作为参数。**本计划中 `workflows.py` 的全部 handler 签名改为用这些 `Depends`，不再从 `request.app.state.services` 取 repo/service。**（`list_workflows`、`get_workflow`、`get_workflow_body`、`export_workflow`、`delete_workflow` 用 `repo`；`import_workflow`、`sync_workflows` 用 `service`。）

- [ ] **Step 6: 运行测试确认通过**

```powershell
backend\.venv\Scripts\python -m pytest backend/tests/test_workflows_api.py backend/tests/test_workflow_service.py backend/tests/test_workflow_repository.py backend/tests/test_config.py backend/tests/test_health.py backend/tests/test_comfyui_list_browse.py -v
```

预期：全部 PASS（Windows chmod 测试仍失败是已知）。

注意：`test_workflows_api.py` 的 `_client` 用了 `create_app(settings)`，这会调用 `database.configure(settings)` 重配全局单例。测试间用不同 `tmp_path` 隔离。`test_health.py` 已有类似模式，应该兼容。

- [ ] **Step 7: 提交**

```powershell
git add backend/app/api/routes/workflows.py backend/app/api/deps.py backend/app/schemas/workflow.py backend/app/main.py backend/tests/test_workflows_api.py
git commit -m "feat(backend): add workflows REST API endpoints"
```

---

### Task 6: 前端类型与 API 客户端扩展

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/services/api.ts`

**Interfaces:**
- Consumes: 后端 `/api/workflows*` 端点。
- Produces: `api.workflows.list()`、`api.workflows.get(id)`、`api.workflows.getBody(id)`、`api.workflows.export(id)`、`api.workflows.remove(id)`、`api.workflows.import(file, opts)`、`api.workflows.sync()`；类型 `WorkflowSource/WorkflowSummary/SyncResult`。

- [ ] **Step 1: 扩展类型**

`frontend/src/types/api.ts` 追加：

```ts
export type WorkflowSource = "browse" | "import";

export interface WorkflowSummary {
  id: string;
  name: string;
  source: WorkflowSource;
  source_key: string;
  original_name: string;
  size_bytes: number;
  created_at: string;
  updated_at: string;
}

export interface WorkflowList {
  items: WorkflowSummary[];
}

export interface SyncBrowseResult {
  added: number;
  updated: number;
  skipped: number;
  error: string | null;
}

export interface SyncResult {
  synced_at: string;
  browse: SyncBrowseResult;
}

export interface ImportConflict {
  filename: string;
  existing: WorkflowSummary;
}
```

- [ ] **Step 2: 扩展 services**

`frontend/src/services/api.ts` 替换为：

```ts
import type {
  ApiInfo,
  HealthStatus,
  ImportConflict,
  SyncResult,
  WorkflowList,
  WorkflowSummary,
} from "@/types/api";

const API_BASE = "/api";

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

async function request(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${API_BASE}${path}`, init);
}

export const api = {
  root: () => get<ApiInfo>("/"),
  health: () => get<HealthStatus>("/health"),
  workflows: {
    list: (params?: { source?: WorkflowSource; q?: string }) => {
      const sp = new URLSearchParams();
      if (params?.source) sp.set("source", params.source);
      if (params?.q) sp.set("q", params.q);
      const qs = sp.toString() ? `?${sp.toString()}` : "";
      return get<WorkflowList>(`/workflows${qs}`);
    },
    get: (id: string) => get<WorkflowSummary>(`/workflows/${id}`),
    getBody: (id: string) => get<Record<string, unknown>>(`/workflows/${id}/body`),
    export: (id: string) => request(`/workflows/${id}/export`),
    remove: (id: string) => request(`/workflows/${id}`, { method: "DELETE" }),
    import: async (file: File, opts?: { overwrite?: boolean; name?: string }) => {
      const form = new FormData();
      form.append("file", file);
      const sp = new URLSearchParams();
      if (opts?.overwrite) sp.set("overwrite", "true");
      if (opts?.name) sp.set("name", opts.name);
      const qs = sp.toString() ? `?${sp.toString()}` : "";
      return request(`/workflows/import${qs}`, { method: "POST", body: form });
    },
    sync: () => request(`/workflows/sync`, { method: "POST" }),
  },
};
```

注意：`import` 需要区分 `201/200/409/400` 响应，返回 `Response` 由调用方处理（`useWorkflows.ts` 解析）。所以 `import` 返回原始 `Response`，不自动 json。

- [ ] **Step 3: typecheck**

```powershell
npm --prefix frontend run typecheck
```

预期：0 错误。

- [ ] **Step 4: 提交**

```powershell
git add frontend/src/types/api.ts frontend/src/services/api.ts
git commit -m "feat(frontend): add workflow types and api client methods"
```

---

### Task 7: 前端布局（AppLayout/Sidebar/TopBar/Modal/路由）

**Files:**
- Create: `frontend/src/app/layout/AppLayout.vue`
- Create: `frontend/src/components/Sidebar.vue`
- Create: `frontend/src/components/TopBar.vue`
- Create: `frontend/src/components/Modal.vue`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/app/router.ts`

**Interfaces:**
- Consumes: `api.health()`（TopBar 健康指示灯）、`router`。
- Produces: `<AppLayout/>` 挂载于 App.vue；`/workflows` 路由；`<Sidebar/>` 含"工作流"入口；`<TopBar/>` 显示 logo + 健康；`<Modal/>` 通用弹窗。

- [ ] **Step 1: 写 `AppLayout.vue`**

```vue
<script setup lang="ts">
import Sidebar from "@/components/Sidebar.vue";
import TopBar from "@/components/TopBar.vue";
</script>

<template>
  <div class="layout">
    <Sidebar />
    <div class="main-col">
      <TopBar />
      <main class="content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<style scoped>
.layout {
  display: flex;
  height: 100vh;
}
.main-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.content {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem;
}
</style>
```

- [ ] **Step 2: 写 `Sidebar.vue`**

```vue
<script setup lang="ts">
import { useRoute } from "vue-router";

const route = useRoute();

const items = [{ to: "/workflows", label: "工作流", icon: "📁" }];

function isActive(to: string) {
  return route.path.startsWith(to);
}
</script>

<template>
  <aside class="sidebar">
    <div class="brand">ComfyChat</div>
    <nav>
      <router-link
        v-for="item in items"
        :key="item.to"
        :to="item.to"
        class="nav-item"
        :class="{ active: isActive(item.to) }"
      >
        <span>{{ item.icon }}</span>
        <span>{{ item.label }}</span>
      </router-link>
    </nav>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 220px;
  background: #1e293b;
  color: #e2e8f0;
  display: flex;
  flex-direction: column;
  padding: 1rem;
  gap: 1rem;
}
.brand {
  font-size: 1.1rem;
  font-weight: 700;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  color: inherit;
  text-decoration: none;
}
.nav-item:hover {
  background: #334155;
}
.nav-item.active {
  background: #0ea5e9;
  color: #fff;
}
</style>
```

- [ ] **Step 3: 写 `TopBar.vue`**

```vue
<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api } from "@/services/api";
import type { HealthStatus } from "@/types/api";

const health = ref<HealthStatus | null>(null);
const error = ref<string | null>(null);

async function check() {
  try {
    health.value = await api.health();
    error.value = null;
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

onMounted(check);
</script>

<template>
  <header class="topbar">
    <h1>ComfyChat</h1>
    <div class="health">
      <template v-if="error">
        <span class="dot error"></span>
        <span>后端不可达</span>
      </template>
      <template v-else-if="health">
        <span class="dot" :class="health.status === 'ok' ? 'ok' : 'error'"></span>
        <span>{{ health.status === "ok" ? "运行正常" : "异常" }}</span>
        <span class="sub">{{ health.comfyui }}</span>
      </template>
      <template v-else>
        <span class="dot loading"></span>
        <span>检查中…</span>
      </template>
      <button class="refresh" title="重新检查" @click="check">↻</button>
    </div>
  </header>
</template>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1.5rem;
  border-bottom: 1px solid #e2e8f0;
}
.topbar h1 {
  font-size: 1rem;
  margin: 0;
  color: #334155;
}
.health {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.85rem;
  color: #64748b;
}
.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
}
.dot.ok { background: #22c55e; }
.dot.error { background: #ef4444; }
.dot.loading { background: #94a3b8; }
.sub { color: #94a3b8; }
.refresh {
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 1rem;
}
</style>
```

- [ ] **Step 4: 写 `Modal.vue`**

```vue
<script setup lang="ts">
defineProps<{
  title: string;
}>();
const emit = defineEmits<{ close: [] }>();
</script>

<template>
  <div class="overlay" @click.self="emit('close')">
    <div class="modal">
      <div class="head">
        <h3>{{ title }}</h3>
        <button class="x" @click="emit('close')">✕</button>
      </div>
      <div class="body">
        <slot />
      </div>
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}
.modal {
  background: #fff;
  border-radius: 8px;
  width: min(680px, 92vw);
  max-height: 85vh;
  display: flex;
  flex-direction: column;
}
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid #e2e8f0;
}
.head h3 { margin: 0; }
.x {
  border: none;
  background: transparent;
  font-size: 1rem;
  cursor: pointer;
}
.body {
  padding: 1rem;
  overflow-y: auto;
}
</style>
```

- [ ] **Step 5: 改 `App.vue`**

```vue
<script setup lang="ts">
import AppLayout from "@/app/layout/AppLayout.vue";
</script>

<template>
  <AppLayout />
</template>
```

（原健康探活逻辑已在 TopBar.vue 中实现，删除。）

- [ ] **Step 6: 改 `router.ts`**

```ts
import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";

const routes: RouteRecordRaw[] = [
  { path: "/", redirect: "/workflows" },
  {
    path: "/workflows",
    name: "workflows",
    component: () => import("@/features/workflows/WorkflowsView.vue"),
  },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
});
```

- [ ] **Step 7: typecheck**

```powershell
npm --prefix frontend run typecheck
```

预期：0 错误。若报 `WorkflowsView` 不存在，先创建占位文件（Task 8 会实现）：

```vue
<template><div>工作流</div></template>
```

- [ ] **Step 8: 提交**

```powershell
git add frontend/src/App.vue frontend/src/app/router.ts frontend/src/app/layout/AppLayout.vue frontend/src/components frontend/src/features/workflows/WorkflowsView.vue
git commit -m "feat(frontend): add admin layout shell with sidebar, topbar, and workflows route"
```

---

### Task 8: 前端工作流页功能

**Files:**
- Create: `frontend/src/features/workflows/WorkflowsView.vue`
- Create: `frontend/src/features/workflows/WorkflowRow.vue`
- Create: `frontend/src/features/workflows/WorkflowImportButton.vue`
- Create: `frontend/src/features/workflows/WorkflowSyncButton.vue`
- Create: `frontend/src/features/workflows/WorkflowDetailModal.vue`
- Create: `frontend/src/features/workflows/ImportConflictDialog.vue`
- Create: `frontend/src/features/workflows/useWorkflows.ts`

**Interfaces:**
- Consumes: Task 6 `api.workflows.*`、Task 7 `Modal`。
- Produces: 完整的工作流页（列表/同步/导入/查看/导出/删除）。

- [ ] **Step 1: 写组合式逻辑 `useWorkflows.ts`**

```ts
import { computed, onMounted, ref } from "vue";
import { api } from "@/services/api";
import type { WorkflowSummary, WorkflowSource } from "@/types/api";

export function useWorkflows() {
  const items = ref<WorkflowSummary[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const sourceFilter = ref<WorkflowSource | "">("");
  const search = ref("");
  const importing = ref(false);
  const syncing = ref(false);
  const syncMsg = ref<string | null>(null);
  const conflict = ref<{ filename: string } | null>(null);

  async function refresh() {
    loading.value = true;
    error.value = null;
    try {
      const data = await api.workflows.list({
        source: sourceFilter.value || undefined,
        q: search.value || undefined,
      });
      items.value = data.items;
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err);
    } finally {
      loading.value = false;
    }
  }

  async function doSync() {
    syncing.value = true;
    syncMsg.value = null;
    try {
      const res = await api.workflows.sync();
      const data = await res.json();
      const b = data.browse;
      syncMsg.value = b.error
        ? `同步失败：${b.error}`
        : `已同步 ${b.added} / 更新 ${b.updated} / 跳过 ${b.skipped}`;
      await refresh();
    } catch (err) {
      syncMsg.value = err instanceof Error ? err.message : String(err);
    } finally {
      syncing.value = false;
    }
  }

  async function onFileChosen(file: File, opts?: { overwrite?: boolean; name?: string }) {
    importing.value = true;
    error.value = null;
    try {
      const res = await api.workflows.import(file, opts);
      if (res.status === 201 || res.status === 200) {
        await refresh();
        return { ok: true as const };
      }
      if (res.status === 409) {
        const data = (await res.json()) as { filename: string };
        conflict.value = { filename: data.filename };
        return { ok: false as const, status: 409 };
      }
      const data = await res.json();
      error.value = data.detail ?? `导入失败：${res.status}`;
      return { ok: false as const, status: res.status };
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err);
      return { ok: false as const, status: 0 };
    } finally {
      importing.value = false;
    }
  }

  async function removeWorkflow(id: string) {
    const res = await api.workflows.remove(id);
    if (res.ok || res.status === 204) {
      await refresh();
    }
  }

  function clearConflict() {
    conflict.value = null;
  }

  onMounted(refresh);

  return {
    items,
    loading,
    error,
    sourceFilter,
    search,
    importing,
    syncing,
    syncMsg,
    conflict,
    refresh,
    doSync,
    onFileChosen,
    removeWorkflow,
    clearConflict,
  };
}
```

- [ ] **Step 2: 写 `WorkflowImportButton.vue`**

```vue
<script setup lang="ts">
import { ref } from "vue";
import ImportConflictDialog from "./ImportConflictDialog.vue";

const props = defineProps<{
  importing: boolean;
  conflict: { filename: string } | null;
}>();

const emit = defineEmits<{
  chosen: [file: File];
  "conflict-resolve": [action: "rename" | "overwrite" | "cancel", name?: string];
}>();

const input = ref<HTMLInputElement | null>(null);
const renameValue = ref("");
const showRename = ref(false);

function onInput(e: Event) {
  const el = e.target as HTMLInputElement;
  const file = el.files?.[0];
  if (file) {
    emit("chosen", file);
  }
  el.value = "";
}

function resolve(action: "overwrite" | "cancel") {
  showRename.value = false;
  emit("conflict-resolve", action);
}

function confirmRename() {
  const name = renameValue.value.trim();
  if (name) {
    emit("conflict-resolve", "rename", name);
    showRename.value = false;
  }
}
</script>

<template>
  <div>
    <button class="btn primary" :disabled="importing" @click="input?.click()">
      {{ importing ? "上传中…" : "导入" }}
    </button>
    <input
      ref="input"
      type="file"
      accept=".json,application/json"
      style="display: none"
      @change="onInput"
    />

    <ImportConflictDialog
      v-if="props.conflict"
      :filename="props.conflict.filename"
      @overwrite="resolve('overwrite')"
      @cancel="resolve('cancel')"
      @rename-click="showRename = true"
    />

    <div v-if="showRename" class="rename-box">
      <input v-model="renameValue" placeholder="新文件名" />
      <button class="btn" @click="confirmRename">确定</button>
      <button class="btn" @click="showRename = false">取消</button>
    </div>
  </div>
</template>

<style scoped>
.btn {
  padding: 0.4rem 0.9rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
}
.btn.primary {
  background: #0ea5e9;
  border-color: #0ea5e9;
  color: #fff;
}
.rename-box {
  margin-top: 0.5rem;
  display: flex;
  gap: 0.5rem;
}
.rename-box input {
  flex: 1;
  padding: 0.4rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
}
</style>
```

- [ ] **Step 3: 写 `WorkflowSyncButton.vue`**

```vue
<script setup lang="ts">
const props = defineProps<{
  syncing: boolean;
}>();
const emit = defineEmits<{ sync: [] }>();
</script>

<template>
  <button class="btn" :disabled="props.syncing" @click="emit('sync')">
    {{ props.syncing ? "同步中…" : "同步" }}
  </button>
</template>

<style scoped>
.btn {
  padding: 0.4rem 0.9rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
}
</style>
```

- [ ] **Step 4: 写 `WorkflowDetailModal.vue`**

```vue
<script setup lang="ts">
import { ref, watch } from "vue";
import Modal from "@/components/Modal.vue";

const props = defineProps<{
  workflowId: string;
  title: string;
}>();

const emit = defineEmits<{ close: [] }>();

const json = ref<unknown>(null);
const loadError = ref<string | null>(null);

watch(
  () => props.workflowId,
  async (id) => {
    if (!id) return;
    loadError.value = null;
    try {
      json.value = await (await import("@/services/api")).api.workflows.getBody(id);
    } catch (err) {
      loadError.value = err instanceof Error ? err.message : String(err);
    }
  },
  { immediate: true }
);
</script>

<template>
  <Modal :title="props.title" @close="emit('close')">
    <pre v-if="json" class="json">{{ JSON.stringify(json, null, 2) }}</pre>
    <p v-else-if="loadError" class="err">加载失败：{{ loadError }}</p>
    <p v-else>加载中…</p>
  </Modal>
</template>

<style scoped>
.json {
  max-height: 60vh;
  overflow: auto;
  background: #0f172a;
  color: #a5b4fc;
  padding: 1rem;
  border-radius: 6px;
  font-size: 0.8rem;
}
.err { color: #ef4444; }
</style>
```

- [ ] **Step 5: 写 `ImportConflictDialog.vue`**

```vue
<script setup lang="ts">
import Modal from "@/components/Modal.vue";

const props = defineProps<{ filename: string }>();
const emit = defineEmits<{
  overwrite: [];
  cancel: [];
  "rename-click": [];
}>();
</script>

<template>
  <Modal :title="`文件重名：${props.filename}`" @close="emit('cancel')">
    <p>已存在同名工作流。请选择如何处理：</p>
    <div class="actions">
      <button class="btn" @click="emit('rename-click')">重命名</button>
      <button class="btn danger" @click="emit('overwrite')">覆盖</button>
      <button class="btn" @click="emit('cancel')">取消</button>
    </div>
  </Modal>
</template>

<style scoped>
.actions {
  display: flex;
  gap: 0.75rem;
  justify-content: flex-end;
}
.btn {
  padding: 0.4rem 0.9rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
}
.btn.danger {
  background: #ef4444;
  border-color: #ef4444;
  color: #fff;
}
</style>
```

- [ ] **Step 6: 写 `WorkflowRow.vue`**

```vue
<script setup lang="ts">
import type { WorkflowSummary } from "@/types/api";

const props = defineProps<{
  workflow: WorkflowSummary;
}>();

const emit = defineEmits<{
  view: [];
  export: [];
  delete: [];
}>();

function fmtSize(bytes: number) {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}

function fmtTime(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString();
}

const sourceLabel: Record<string, string> = {
  browse: "ComfyUI",
  import: "导入",
};
</script>

<template>
  <tr>
    <td class="name">{{ props.workflow.name }}.json</td>
    <td>{{ sourceLabel[props.workflow.source] ?? props.workflow.source }}</td>
    <td>{{ fmtSize(props.workflow.size_bytes) }}</td>
    <td>{{ fmtTime(props.workflow.updated_at) }}</td>
    <td class="actions">
      <button class="link" @click="emit('view')">看</button>
      <button class="link" @click="emit('export')">↓</button>
      <button class="link danger" @click="emit('delete')">×</button>
    </td>
  </tr>
</template>

<style scoped>
.name { font-weight: 500; }
.actions { display: flex; gap: 0.5rem; }
.link {
  border: none;
  background: none;
  color: #0ea5e9;
  cursor: pointer;
  padding: 0 0.25rem;
}
.link.danger { color: #ef4444; }
</style>
```

- [ ] **Step 7: 写 `WorkflowsView.vue`**

```vue
<script setup lang="ts">
import { ref } from "vue";
import Modal from "@/components/Modal.vue";
import WorkflowImportButton from "./WorkflowImportButton.vue";
import WorkflowSyncButton from "./WorkflowSyncButton.vue";
import WorkflowDetailModal from "./WorkflowDetailModal.vue";
import WorkflowRow from "./WorkflowRow.vue";
import { useWorkflows } from "./useWorkflows";
import type { WorkflowSummary } from "@/types/api";

const {
  items,
  loading,
  error,
  sourceFilter,
  search,
  importing,
  syncing,
  syncMsg,
  conflict,
  onFileChosen,
  doSync,
  removeWorkflow,
  clearConflict,
} = useWorkflows();

const detail = ref<WorkflowSummary | null>(null);
const confirmDelete = ref<WorkflowSummary | null>(null);

const pendingFile = ref<File | null>(null);

async function handleChosen(file: File) {
  pendingFile.value = file;
  const r = await onFileChosen(file);
  if (r && r.ok) {
    pendingFile.value = null;
    clearConflict();
  }
}

async function resolveConflict(action: "rename" | "overwrite" | "cancel", name?: string) {
  if (action === "cancel") {
    pendingFile.value = null;
    clearConflict();
    return;
  }
  const file = pendingFile.value;
  if (!file) {
    clearConflict();
    alert("文件已失效，请重新选择。");
    return;
  }
  if (action === "rename") {
    if (!name) return;
    const r = await onFileChosen(file, { name });
    if (r?.ok) {
      pendingFile.value = null;
      clearConflict();
    }
  } else {
    const r = await onFileChosen(file, { overwrite: true });
    if (r?.ok) {
      pendingFile.value = null;
      clearConflict();
    }
  }
}

async function onExport(id: string) {
  const res = await (await import("@/services/api")).api.workflows.export(id);
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") ?? "";
  const m = cd.match(/filename="?([^";]+)"?/);
  const filename = m ? m[1] : "workflow.json";
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
</script>

<template>
  <div class="page">
    <div class="toolbar">
      <h2>工作流</h2>
      <div class="spacer" />
      <WorkflowImportButton
        :importing="importing"
        :conflict="conflict"
        @chosen="handleChosen"
        @conflict-resolve="resolveConflict"
      />
      <WorkflowSyncButton :syncing="syncing" @sync="doSync" />
    </div>

    <div v-if="syncMsg" class="sync-msg">{{ syncMsg }}</div>
    <div v-if="error" class="err">{{ error }}</div>

    <div class="filters">
      <input v-model="search" placeholder="搜索名称…" class="search" @input="doSearch" />
      <select v-model="sourceFilter" class="source">
        <option value="">全部来源</option>
        <option value="browse">ComfyUI</option>
        <option value="import">导入</option>
      </select>
    </div>

    <table v-if="loading" class="table"><tbody><tr><td>加载中…</td></tr></tbody></table>
    <table v-else class="table">
      <thead>
        <tr><th>名称</th><th>来源</th><th>大小</th><th>更新于</th><th>操作</th></tr>
      </thead>
      <tbody>
        <WorkflowRow
          v-for="wf in items"
          :key="wf.id"
          :workflow="wf"
          @view="detail = wf"
          @export="onExport(wf.id)"
          @delete="confirmDelete = wf"
        />
      </tbody>
    </table>

    <WorkflowDetailModal
      v-if="detail"
      :workflow-id="detail.id"
      :title="detail.name"
      @close="detail = null"
    />

    <Modal v-if="confirmDelete" title="删除工作流" @close="confirmDelete = null">
      <p>确定删除「{{ confirmDelete.name }}」？</p>
      <div class="actions">
        <button class="btn" @click="confirmDelete = null">取消</button>
        <button class="btn danger" @click="removeWorkflow(confirmDelete.id); confirmDelete = null">删除</button>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.page { max-width: 1100px; }
.toolbar {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}
.spacer { flex: 1; }
.sync-msg {
  padding: 0.5rem 0.75rem;
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
  border-radius: 6px;
  margin-bottom: 0.75rem;
  color: #065f46;
}
.err { color: #ef4444; margin: 0.5rem 0; }
.filters {
  display: flex;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}
.search { flex: 1; padding: 0.4rem; border: 1px solid #cbd5e1; border-radius: 6px; }
.source { padding: 0.4rem; border: 1px solid #cbd5e1; border-radius: 6px; }
.table { width: 100%; border-collapse: collapse; }
.table th, .table td {
  text-align: left;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid #e2e8f0;
}
.table th { background: #f8fafc; color: #475569; }
.actions { display: flex; gap: 0.5rem; justify-content: flex-end; }
.btn {
  padding: 0.4rem 0.9rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
}
.btn.danger { background: #ef4444; border-color: #ef4444; color: #fff; }
</style>
```

- [ ] **Step 8: typecheck + 冒烟**

```powershell
npm --prefix frontend run typecheck
```

预期：0 错误。

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-dev.ps1
```

浏览器打开 `http://127.0.0.1:5173/`，确认：
- 侧栏"工作流"高亮，默认进 `/workflows`；
- 点"同步"→ toast 显示"已同步 3 / 更新 0 / 跳过 0"（你本地 ComfyUI 有 3 个工作流），表格出现 3 行；
- 点"导入"→ 选一个 `.json` 文件 → 列表新增；
- 行操作"看"打开 JSON、"↓"下载、"×"删除。

完成后 `scripts\stop-dev.ps1`。

- [ ] **Step 9: 提交**

```powershell
git add frontend/src/features/workflows
git commit -m "feat(frontend): implement workflows page with sync/import/view/export/delete"
```

---

## Self-Review

**1. Spec coverage（对 `docs/superpowers/specs/2026-08-09-workflows-page-design.md`）：**
- §1 范围/非范围 → Task 1-8（无运行、无解析、无 history/templates 源）。
- §2 架构（browse 源 + FS 旁路）→ Task 3（`list_browse` 用 `?path=workflows`）、Task 4（sync）。
- §3 数据模型 → Task 2（`workflows` 表 + `UNIQUE(source, source_key)`）。
- §4 API → Task 5（全部端点 + import 409 流程 + sync 不删残留）。
- §5 前端布局 → Task 7；工作流页 → Task 6/8。
- §6 测试 → 每个任务内 TDD。
- §7 配置 → Task 1。

**2. Placeholder scan：** 无 TBD/TODO；每步有可粘贴代码。Task 8 Step 7 的"重传"用 `alert` 提示简化——这是明确标注的简化（v1 允许），不是占位符。

**3. Type consistency：** `WorkflowService.sync() -> dict`（含 `browse`）、`import_workflow() -> tuple[str, Workflow|None]` 在 Task 4 定义，Task 5 路由按此消费。`WorkflowOut/SyncResultOut/ConflictOut` 在 Task 5 schema 定义，前端 Task 6 类型与之对齐（`WorkflowSummary/SyncResult/ImportConflict`）。`ComfyUIClient.list_browse()/read_userdata_json()` 在 Task 3 定义，Task 4 消费。方法名无漂移。
