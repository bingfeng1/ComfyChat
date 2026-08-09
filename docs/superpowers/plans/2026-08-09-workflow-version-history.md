# ComfyChat 工作流版本历史实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 ComfyUI 工作流引入版本历史：列表只显示最新版；同步发现 ComfyUI 有新版时旧版自动归档；前端 browse 行提供"历史工作流"按钮查看/手动删除历史版本。

**Architecture:** 新增 `workflow_versions` 表（`workflow_id` FK 绑定当前最新行，`version` 递增）。`WorkflowService.sync()` 在检测到 size 变化时：先把当前 `workflows` 行 body 归档为历史，再更新行 body 为新版；`source_key`（ComfyUI 文件名）即身份（同名=更新，异名=新增）。前端在 browse 且有历史的行显示"历史工作流"按钮，打开历史面板查看/删除。

**Tech Stack:** FastAPI + SQLAlchemy 2.x + Pydantic v2（后端）；Vue 3 + Vite + TypeScript（前端）。

## Global Constraints

- 工作目录 `D:\learnAI\ComfyChat`（Windows + PowerShell 5.1）；用 bash 工具 `workdir` 参数。
- 国内网络：pip 用清华源/阿里源，npm 用 npmmirror（`frontend/.npmrc` 已配）。
- 测试命令：`backend\.venv\Scripts\python -m pytest backend/tests/<file> -v`；前端 `npm --prefix frontend run typecheck`。
- 已知基线失败：`test_database.py::test_check_database_returns_false_when_path_unwritable`（Windows chmod），不修。
- `workflows` 表结构不变（只存最新版）；新增 `workflow_versions` 表，靠现有 `Base.metadata.create_all` 自动创建（无 alembic）。
- `source_key`（ComfyUI 文件名）即身份；改名=删+增。
- 仅 browse 来源有历史；import 无历史；单向同步（不写回 ComfyUI）。
- 同步不自动删历史/残留；历史仅手动删。
- 使用现有 git 身份（`bingfeng <260895778@qq.com>`），不要 `-c user.*`。
- 每任务一个提交，约定式提交。

---

## File Structure

```
backend/
  app/
    models/workflow.py        # 新增 WorkflowVersion ORM
    repositories/workflow.py  # 新增版本相关方法（archive/list_versions/get_version/delete_version/has_history/max_version）
    services/workflow.py      # sync() 加版本归档逻辑 + updates 响应
    schemas/workflow.py       # WorkflowOut 加 has_history；新增 WorkflowVersionOut/WorkflowVersionListOut
    api/routes/workflows.py   # 新增 /{id}/versions 三个端点
  tests/
    test_workflow_repository.py  # 版本方法测试
    test_workflow_service.py     # sync 归档测试
    test_workflows_api.py        # /versions 端点测试 + has_history
frontend/
  src/
    types/api.ts              # WorkflowSummary 加 has_history；新增 WorkflowVersion/WorkflowVersionList
    services/api.ts           # workflows.versions.list/getBody/remove
    features/workflows/
      WorkflowRow.vue         # browse+history 显示"历史工作流"按钮
      WorkflowsView.vue       # 历史面板 modal 状态 + 处理
      WorkflowHistoryModal.vue# 新建：历史列表/查看/删除
```

---

### Task 1: WorkflowVersion 模型 + Repository 版本方法

**Files:**
- Modify: `backend/app/models/workflow.py`
- Modify: `backend/app/repositories/workflow.py`
- Modify: `backend/tests/test_workflow_repository.py`

**Interfaces:**
- Consumes: 现有 `Workflow` 模型、`Base`、`WorkflowRepository(session)`。
- Produces:
  - `WorkflowVersion` ORM：`id/workflow_id/version/name/size_bytes/body/captured_at`，`UniqueConstraint("workflow_id","version")`，`__tablename__="workflow_versions"`。
  - `WorkflowRepository` 新增方法：
    - `archive_version(workflow_id: str, name: str, size_bytes: int, body: str) -> WorkflowVersion`
    - `list_versions(workflow_id: str) -> Sequence[WorkflowVersion]`（按 version ASC）
    - `get_version(workflow_id: str, version: int) -> Optional[WorkflowVersion]`
    - `delete_version(workflow_id: str, version: int) -> bool`
    - `has_history(workflow_id: str) -> bool`
    - `max_version(workflow_id: str) -> int`（无历史返回 0）

- [ ] **Step 1: 写失败测试（模型）**

在 `backend/tests/test_workflow_repository.py` 追加：

```python
from app.models.workflow import WorkflowVersion


def test_archive_version_and_list(engine, session):
    _create_tables(engine)
    repo = WorkflowRepository(session)
    wf = repo.upsert("browse", "a.json", "a", "a.json", "{}", 2)
    v1 = repo.archive_version(wf.id, "a", 2, "{}")
    v2 = repo.archive_version(wf.id, "a", 10, '{"x":1}')
    assert v1.version == 1
    assert v2.version == 2
    versions = repo.list_versions(wf.id)
    assert [v.version for v in versions] == [1, 2]
    assert repo.max_version(wf.id) == 2
    assert repo.has_history(wf.id) is True


def test_get_and_delete_version(engine, session):
    _create_tables(engine)
    repo = WorkflowRepository(session)
    wf = repo.upsert("browse", "b.json", "b", "b.json", "{}", 2)
    repo.archive_version(wf.id, "b", 2, "{}")
    v1 = repo.get_version(wf.id, 1)
    assert v1 is not None
    assert v1.version == 1
    assert repo.delete_version(wf.id, 1) is True
    assert repo.get_version(wf.id, 1) is None
    assert repo.delete_version(wf.id, 1) is False


def test_has_history_false_when_none(engine, session):
    _create_tables(engine)
    repo = WorkflowRepository(session)
    wf = repo.upsert("import", "c.json", "c", "c.json", "{}", 2)
    assert repo.has_history(wf.id) is False
    assert repo.max_version(wf.id) == 0
```

- [ ] **Step 2: 运行确认失败**

```powershell
backend\.venv\Scripts\python -m pytest backend/tests/test_workflow_repository.py -v
```

预期：`ImportError`（`WorkflowVersion` 不存在）或方法不存在。

- [ ] **Step 3: 实现模型**

`backend/app/models/workflow.py` 追加 `WorkflowVersion` 类：

```python
class WorkflowVersion(Base):
    __tablename__ = "workflow_versions"
    __table_args__ = (UniqueConstraint("workflow_id", "version", name="uq_workflow_versions_id_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: uuid.uuid4().hex)
    workflow_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    captured_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_utcnow)
```

- [ ] **Step 4: 实现 repository 方法**

`backend/app/repositories/workflow.py` 追加 import 与方法：

```python
from app.models.workflow import Workflow, WorkflowVersion


class WorkflowRepository:
    # ... 现有方法不动 ...

    def archive_version(self, workflow_id: str, name: str, size_bytes: int, body: str) -> WorkflowVersion:
        version = self.max_version(workflow_id) + 1
        v = WorkflowVersion(
            workflow_id=workflow_id, version=version,
            name=name, size_bytes=size_bytes, body=body,
        )
        self.session.add(v)
        self.session.commit()
        self.session.refresh(v)
        return v

    def list_versions(self, workflow_id: str) -> Sequence[WorkflowVersion]:
        stmt = (
            select(WorkflowVersion)
            .where(WorkflowVersion.workflow_id == workflow_id)
            .order_by(WorkflowVersion.version.asc())
        )
        return self.session.scalars(stmt).all()

    def get_version(self, workflow_id: str, version: int) -> Optional[WorkflowVersion]:
        stmt = select(WorkflowVersion).where(
            WorkflowVersion.workflow_id == workflow_id,
            WorkflowVersion.version == version,
        )
        return self.session.scalar(stmt)

    def delete_version(self, workflow_id: str, version: int) -> bool:
        v = self.get_version(workflow_id, version)
        if v is None:
            return False
        self.session.delete(v)
        self.session.commit()
        return True

    def has_history(self, workflow_id: str) -> bool:
        stmt = select(WorkflowVersion.id).where(WorkflowVersion.workflow_id == workflow_id).limit(1)
        return self.session.scalar(stmt) is not None

    def max_version(self, workflow_id: str) -> int:
        from sqlalchemy import func
        stmt = (
            select(func.max(WorkflowVersion.version))
            .where(WorkflowVersion.workflow_id == workflow_id)
        )
        result = self.session.scalar(stmt)
        return result or 0
```

注意：`func.max` 在 `max_version` 内局部 import（避免顶部重复）。`_create_tables(engine)` 在测试里用 `Base.metadata.create_all`，会自动建新表（`conftest` 的 `engine` fixture 已 `create_all`）。

- [ ] **Step 5: 运行确认通过**

```powershell
backend\.venv\Scripts\python -m pytest backend/tests/test_workflow_repository.py -v
```

预期：全部 PASS（原 4 + 新 3）。

- [ ] **Step 6: 提交**

```powershell
git add backend/app/models/workflow.py backend/app/repositories/workflow.py backend/tests/test_workflow_repository.py
git commit -m "feat(backend): add WorkflowVersion model and repository version methods"
```

---

### Task 2: 同步逻辑版本归档 + updates 响应

**Files:**
- Modify: `backend/app/services/workflow.py`
- Modify: `backend/tests/test_workflow_service.py`

**Interfaces:**
- Consumes: Task 1 `archive_version`/`has_history`/`max_version`。
- Produces: `WorkflowService.sync()` 返回 `{"synced_at", "browse": {"added", "updated", "skipped", "error", "updates": [name, ...]}}`；size 变化时归档旧 body + 更新行。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_workflow_service.py` 追加：

```python
def test_sync_archives_old_version_on_change(engine):
    repo = _repo(engine)
    service = WorkflowService(repo, FakeBrowseClient([{"name": "a.json", "path": "workflows/a.json", "type": "file", "size": 2}], body="{}"))
    service.sync()
    service2 = WorkflowService(repo, FakeBrowseClient([{"name": "a.json", "path": "workflows/a.json", "type": "file", "size": 99}], body='{"n":2}'))
    result = service2.sync()
    assert result["browse"]["updated"] == 1
    assert result["browse"]["updates"] == ["a.json"]
    row = repo.get_by_source_key("browse", "a.json")
    assert row.size_bytes == 99
    assert row.body == '{"n":2}'
    versions = repo.list_versions(row.id)
    assert len(versions) == 1
    assert versions[0].version == 1
    assert versions[0].body == "{}"


def test_sync_archives_multiple_versions_increment(engine):
    repo = _repo(engine)
    service = WorkflowService(repo, FakeBrowseClient([{"name": "a.json", "path": "workflows/a.json", "type": "file", "size": 2}], body="{}"))
    service.sync()
    service2 = WorkflowService(repo, FakeBrowseClient([{"name": "a.json", "path": "workflows/a.json", "type": "file", "size": 50}], body='{"v":2}'))
    service2.sync()
    service3 = WorkflowService(repo, FakeBrowseClient([{"name": "a.json", "path": "workflows/a.json", "type": "file", "size": 99}], body='{"v":3}'))
    service3.sync()
    row = repo.get_by_source_key("browse", "a.json")
    assert [v.version for v in repo.list_versions(row.id)] == [1, 2]
    assert row.body == '{"v":3}'


def test_sync_first_sync_has_no_history(engine):
    repo = _repo(engine)
    service = WorkflowService(repo, FakeBrowseClient([{"name": "a.json", "path": "workflows/a.json", "type": "file", "size": 2}], body="{}"))
    service.sync()
    row = repo.get_by_source_key("browse", "a.json")
    assert repo.has_history(row.id) is False
    assert repo.max_version(row.id) == 0
```

- [ ] **Step 2: 运行确认失败**

```powershell
backend\.venv\Scripts\python -m pytest backend/tests/test_workflow_service.py -v
```

预期：`test_sync_archives_old_version_on_change` 失败（`updates` key 不存在 / 无归档）。

- [ ] **Step 3: 实现 sync 版本归档**

`backend/app/services/workflow.py` 的 `sync()` 方法替换为：

```python
    def sync(self) -> dict:
        summary = {"added": 0, "updated": 0, "skipped": 0, "error": None, "updates": []}
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
            display = name[:-5] if name.endswith(".json") else name
            existing = self.repo.get_by_source_key("browse", name)
            if existing is None:
                self.repo.upsert(
                    source="browse", source_key=name, name=display,
                    original_name=name, body=body, size_bytes=size,
                )
                summary["added"] += 1
                continue
            if existing.size_bytes == size:
                summary["skipped"] += 1
                continue
            self.repo.archive_version(existing.id, existing.name, existing.size_bytes, existing.body)
            self.repo.upsert(
                source="browse", source_key=name, name=display,
                original_name=name, body=body, size_bytes=size,
            )
            summary["updated"] += 1
            summary["updates"].append(name)

        return {"synced_at": _utcnow(), "browse": summary}
```

注意：**先 `archive_version` 再 `upsert`**——upsert 会 `commit`，archieve 也 `commit`，两次提交原子性可接受（同一 session）。顺序保证旧 body 在覆盖前入历史。

- [ ] **Step 4: 运行确认通过**

```powershell
backend\.venv\Scripts\python -m pytest backend/tests/test_workflow_service.py -v
```

预期：全部 PASS（原 9 + 新 3）。

- [ ] **Step 5: 提交**

```powershell
git add backend/app/services/workflow.py backend/tests/test_workflow_service.py
git commit -m "feat(backend): archive workflow history on sync update"
```

---

### Task 3: 后端 API（/versions 端点 + has_history）

**Files:**
- Modify: `backend/app/schemas/workflow.py`
- Modify: `backend/app/api/routes/workflows.py`
- Modify: `backend/tests/test_workflows_api.py`

**Interfaces:**
- Consumes: Task 1 repository 方法。
- Produces:
  - `WorkflowOut` 加 `has_history: bool`。
  - `WorkflowVersionOut`（id/workflow_id/version/name/size_bytes/captured_at）、`WorkflowVersionListOut`（items）。
  - `GET /workflows/{id}/versions` → `{"items":[...]}` | 404（工作流不存在）
  - `GET /workflows/{id}/versions/{version}` → 历史 body（`Content-Type: application/json`）| 404
  - `DELETE /workflows/{id}/versions/{version}` → 204 | 404

- [ ] **Step 1: 写失败测试**

`backend/tests/test_workflows_api.py` 追加（复用 `_client`）：

```python
def test_versions_endpoints(tmp_path):
    client, _ = _client(tmp_path)
    files = {"file": ("a.json", io.BytesIO(b'{"x":1}'), "application/json")}
    wid = client.post("/workflows/import", files=files).json()["id"]

    r = client.get(f"/workflows/{wid}/versions")
    assert r.status_code == 200
    assert r.json() == {"items": []}

    r2 = client.get(f"/workflows/{wid}/versions/1")
    assert r2.status_code == 404


def test_versions_after_archive(tmp_path, monkeypatch):
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
    client.post("/workflows/sync")

    # 第二次 sync 用不同 size/body → 归档 v1
    class FakeClient2:
        def list_browse(self):
            return [{"name": "wf.json", "path": "workflows/wf.json", "type": "file", "size": 99}]
        def read_userdata_json(self, name):
            return '{"n":2}'

    monkeypatch.setattr(ComfyUIClient, "list_browse", FakeClient2.list_browse)
    monkeypatch.setattr(ComfyUIClient, "read_userdata_json", FakeClient2.read_userdata_json)
    client.post("/workflows/sync")

    lst = client.get("/workflows").json()
    assert lst["items"][0]["has_history"] is True
    wid = lst["items"][0]["id"]

    r = client.get(f"/workflows/{wid}/versions")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["version"] == 1
    assert items[0]["size_bytes"] == 6

    rb = client.get(f"/workflows/{wid}/versions/1")
    assert rb.status_code == 200
    assert rb.json() == {"n": 1}

    rd = client.delete(f"/workflows/{wid}/versions/1")
    assert rd.status_code == 204
    rd2 = client.delete(f"/workflows/{wid}/versions/1")
    assert rd2.status_code == 404


def test_versions_404_unknown_workflow(tmp_path):
    client, _ = _client(tmp_path)
    r = client.get("/workflows/nonexistent/versions")
    assert r.status_code == 404
```

注意：`test_versions_after_archive` 第二次 sync 前 `list_browse` 的 `size` 不同，会触发归档。`has_history` 字段需要在列表返回中体现。

- [ ] **Step 2: 运行确认失败**

```powershell
backend\.venv\Scripts\python -m pytest backend/tests/test_workflows_api.py -v
```

预期：新测试失败（`has_history` 缺失 / `/versions` 404）。

- [ ] **Step 3: 实现 schema**

`backend/app/schemas/workflow.py`：

- `WorkflowOut` 加字段：
```python
    has_history: bool = False
```

- 新增：
```python
class WorkflowVersionOut(BaseModel):
    id: str
    workflow_id: str
    version: int
    name: str
    size_bytes: int
    captured_at: str

    model_config = {"from_attributes": True}


class WorkflowVersionListOut(BaseModel):
    items: list[WorkflowVersionOut]
```

注意：`has_history` 不是 `Workflow` ORM 的列，`model_validate(w)` 读不到。需要在路由层手动填充：`WorkflowOut.model_validate(w).model_copy(update={"has_history": repo.has_history(w.id)})`。

- [ ] **Step 4: 实现路由**

`backend/app/api/routes/workflows.py`：

1. `list_workflows` 改为填充 `has_history`：
```python
@router.get("", response_model=WorkflowListOut)
def list_workflows(
    repo: WorkflowRepository = Depends(_repo),
    source: str | None = Query(default=None),
    q: str | None = Query(default=None),
) -> dict:
    items = repo.list(source=source, q=q)
    out = []
    for w in items:
        item = WorkflowOut.model_validate(w).model_copy(update={"has_history": repo.has_history(w.id)})
        out.append(item)
    return {"items": out}
```

2. `get_workflow` 同样填充：
```python
@router.get("/{workflow_id}", response_model=WorkflowOut)
def get_workflow(workflow_id: str, repo: WorkflowRepository = Depends(_repo)) -> WorkflowOut:
    wf = repo.get(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return WorkflowOut.model_validate(wf).model_copy(update={"has_history": repo.has_history(wf.id)})
```

3. 新增三个端点（放在 `/{workflow_id}/body` 之后、`/{workflow_id}/export` 之前）：

```python
@router.get("/{workflow_id}/versions", response_model=WorkflowVersionListOut)
def list_versions(
    workflow_id: str,
    repo: WorkflowRepository = Depends(_repo),
) -> dict:
    if repo.get(workflow_id) is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    versions = repo.list_versions(workflow_id)
    return {"items": [WorkflowVersionOut.model_validate(v) for v in versions]}


@router.get("/{workflow_id}/versions/{version}")
def get_version_body(
    workflow_id: str,
    version: int,
    repo: WorkflowRepository = Depends(_repo),
) -> Response:
    if repo.get(workflow_id) is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    v = repo.get_version(workflow_id, version)
    if v is None:
        raise HTTPException(status_code=404, detail="Version not found")
    return Response(content=v.body, media_type="application/json")


@router.delete("/{workflow_id}/versions/{version}", status_code=status.HTTP_204_NO_CONTENT)
def delete_version(
    workflow_id: str,
    version: int,
    repo: WorkflowRepository = Depends(_repo),
) -> Response:
    if repo.get(workflow_id) is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    ok = repo.delete_version(workflow_id, version)
    if not ok:
        raise HTTPException(status_code=404, detail="Version not found")
    return Response(status_code=204)
```

4. import 的 `WorkflowOut.model_validate(wf).model_dump()` 也需补 `has_history`（import 无历史，恒 false）——用 `model_copy(update={"has_history": False})` 或在 `.model_dump()` 后加 key：
```python
payload = WorkflowOut.model_validate(wf).model_copy(update={"has_history": False}).model_dump()
payload["body"] = wf.body
```

- [ ] **Step 5: 运行确认通过**

```powershell
backend\.venv\Scripts\python -m pytest backend/tests/test_workflows_api.py -v
```

预期：全部 PASS（原 9 + 新 3）。

- [ ] **Step 6: 提交**

```powershell
git add backend/app/schemas/workflow.py backend/app/api/routes/workflows.py backend/tests/test_workflows_api.py
git commit -m "feat(backend): add workflow version history API endpoints"
```

---

### Task 4: 前端类型 + API 客户端

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/services/api.ts`

**Interfaces:**
- Consumes: 后端 `/workflows/{id}/versions*`。
- Produces: `WorkflowSummary.has_history`；`WorkflowVersion`/`WorkflowVersionList`；`api.workflows.versions.list/getBody/remove`。

- [ ] **Step 1: 扩展类型**

`frontend/src/types/api.ts`：

- `WorkflowSummary` 加 `has_history: boolean;`。
- `SyncBrowseResult` 加可选字段（同步响应的 `updates` 数组）：
```ts
export interface SyncBrowseResult {
  added: number;
  updated: number;
  skipped: number;
  error: string | null;
  updates?: string[];
}
```
- 追加：
```ts
export interface WorkflowVersion {
  id: string;
  workflow_id: string;
  version: number;
  name: string;
  size_bytes: number;
  captured_at: string;
}

export interface WorkflowVersionList {
  items: WorkflowVersion[];
}
```

- [ ] **Step 2: 扩展 services**

`frontend/src/services/api.ts` 的 `workflows` 对象加 `versions` 子对象：

```ts
    versions: {
      list: (id: string) => get<WorkflowVersionList>(`/workflows/${id}/versions`),
      getBody: (id: string, version: number) =>
        get<Record<string, unknown>>(`/workflows/${id}/versions/${version}`),
      remove: (id: string, version: number) =>
        request(`/workflows/${id}/versions/${version}`, { method: "DELETE" }),
    },
```

同时 `import type { WorkflowVersion, WorkflowVersionList } from "@/types/api";` 加入 import 列表。

- [ ] **Step 3: typecheck**

```powershell
npm --prefix frontend run typecheck
```

预期：0 错误。若 `WorkflowSummary` 加了 `has_history` 后某处构造缺字段报错，补默认即可。

- [ ] **Step 4: 提交**

```powershell
git add frontend/src/types/api.ts frontend/src/services/api.ts
git commit -m "feat(frontend): add workflow version types and api client methods"
```

---

### Task 5: 前端历史工作流按钮 + 历史面板

**Files:**
- Create: `frontend/src/features/workflows/WorkflowHistoryModal.vue`
- Modify: `frontend/src/features/workflows/WorkflowRow.vue`
- Modify: `frontend/src/features/workflows/WorkflowsView.vue`

**Interfaces:**
- Consumes: Task 4 `api.workflows.versions.*`。
- Produces: browse + `has_history` 行显示"历史工作流"按钮；点击打开历史面板（查看/删除版本）。

- [ ] **Step 1: 写 `WorkflowHistoryModal.vue`**

```vue
<script setup lang="ts">
import { ref, watch } from "vue";
import Modal from "@/components/Modal.vue";
import { api } from "@/services/api";
import type { WorkflowVersion } from "@/types/api";

const props = defineProps<{
  workflowId: string;
  title: string;
}>();

const emit = defineEmits<{ close: [] }>();

const versions = ref<WorkflowVersion[]>([]);
const error = ref<string | null>(null);
const viewBody = ref<Record<string, unknown> | null>(null);
const viewError = ref<string | null>(null);

async function load() {
  error.value = null;
  try {
    const data = await api.workflows.versions.list(props.workflowId);
    versions.value = data.items;
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

async function viewVersion(v: WorkflowVersion) {
  viewBody.value = null;
  viewError.value = null;
  try {
    viewBody.value = await api.workflows.versions.getBody(props.workflowId, v.version);
  } catch (err) {
    viewError.value = err instanceof Error ? err.message : String(err);
  }
}

async function deleteVersion(v: WorkflowVersion) {
  if (!confirm(`确定删除版本 ${v.version}（${v.name}）？`)) return;
  const res = await api.workflows.versions.remove(props.workflowId, v.version);
  if (res.ok || res.status === 204) {
    await load();
  }
}

function fmtSize(bytes: number) {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}

function fmtTime(iso: string) {
  return new Date(iso).toLocaleString();
}

watch(() => props.workflowId, load, { immediate: true });
</script>

<template>
  <Modal :title="`历史工作流：${props.title}`" @close="emit('close')">
    <div v-if="error" class="err">{{ error }}</div>

    <div v-if="viewBody || viewError" class="viewer">
      <button class="link" @click="viewBody = null; viewError = null">← 返回列表</button>
      <pre v-if="viewBody" class="json">{{ JSON.stringify(viewBody, null, 2) }}</pre>
      <p v-else-if="viewError" class="err">{{ viewError }}</p>
    </div>

    <table v-else class="table">
      <thead>
        <tr><th>版本</th><th>名称</th><th>大小</th><th>归档于</th><th>操作</th></tr>
      </thead>
      <tbody>
        <tr v-for="v in versions" :key="v.version">
          <td>v{{ v.version }}</td>
          <td>{{ v.name }}</td>
          <td>{{ fmtSize(v.size_bytes) }}</td>
          <td>{{ fmtTime(v.captured_at) }}</td>
          <td class="actions">
            <button class="link" @click="viewVersion(v)">查看</button>
            <button class="link danger" @click="deleteVersion(v)">删除</button>
          </td>
        </tr>
        <tr v-if="versions.length === 0"><td colspan="5">暂无历史版本</td></tr>
      </tbody>
    </table>
  </Modal>
</template>

<style scoped>
.err { color: #ef4444; }
.viewer { display: flex; flex-direction: column; gap: 0.5rem; }
.json {
  max-height: 50vh;
  overflow: auto;
  background: #0f172a;
  color: #a5b4fc;
  padding: 1rem;
  border-radius: 6px;
  font-size: 0.8rem;
}
.table { width: 100%; border-collapse: collapse; }
.table th, .table td { text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid #e2e8f0; }
.table th { background: #f8fafc; color: #475569; }
.actions { display: flex; gap: 0.5rem; }
.link { border: none; background: none; color: #0ea5e9; cursor: pointer; padding: 0 0.25rem; }
.link.danger { color: #ef4444; }
</style>
```

- [ ] **Step 2: 改 `WorkflowRow.vue`**

`WorkflowRow.vue` 的 emit 加 `history: []`，模板操作区在 `看` 前加历史按钮（仅当 `source==='browse' && has_history`）：

```vue
<script setup lang="ts">
const emit = defineEmits<{
  view: [];
  export: [];
  delete: [];
  history: [];
}>();
</script>

<template>
  <tr>
    <td class="name">{{ props.workflow.name }}.json</td>
    <td>{{ sourceLabel[props.workflow.source] ?? props.workflow.source }}</td>
    <td>{{ fmtSize(props.workflow.size_bytes) }}</td>
    <td>{{ fmtTime(props.workflow.updated_at) }}</td>
    <td class="actions">
      <button
        v-if="props.workflow.source === 'browse' && props.workflow.has_history"
        class="link"
        @click="emit('history')"
      >历史</button>
      <button class="link" @click="emit('view')">看</button>
      <button class="link" @click="emit('export')">↓</button>
      <button class="link danger" @click="emit('delete')">×</button>
    </td>
  </tr>
</template>
```

- [ ] **Step 3: 改 `WorkflowsView.vue`**

加 `historyOf` state、`WorkflowHistoryModal` 引用、行事件绑定：

```vue
<script setup lang="ts">
import WorkflowHistoryModal from "./WorkflowHistoryModal.vue";
// ...
const historyOf = ref<WorkflowSummary | null>(null);
</script>

<template>
  <!-- WorkflowRow 行加 @history -->
  <WorkflowRow
    v-for="wf in items"
    :key="wf.id"
    :workflow="wf"
    @view="detail = wf"
    @export="onExport(wf.id)"
    @delete="confirmDelete = wf"
    @history="historyOf = wf"
  />

  <WorkflowHistoryModal
    v-if="historyOf"
    :workflow-id="historyOf.id"
    :title="historyOf.name"
    @close="historyOf = null"
  />
</template>
```

- [ ] **Step 4: typecheck**

```powershell
npm --prefix frontend run typecheck
```

预期：0 错误。

- [ ] **Step 5: 冒烟**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-dev.ps1
```

浏览器验证：同步 → 修改 ComfyUI 某工作流文件再同步 → 该行出现"历史"按钮 → 点开历史面板 → 查看版本 JSON → 删除版本。若 ComfyUI 文件不好改，可直接用后端 `read_userdata_json` 对应目录手动改文件内容后再同步。完成后 `scripts\stop-dev.ps1`。

- [ ] **Step 6: 提交**

```powershell
git add frontend/src/features/workflows
git commit -m "feat(frontend): add workflow history button and version panel"
```

---

## Self-Review

**1. Spec coverage（对 `docs/superpowers/specs/2026-08-09-workflow-version-history-design.md`）：**
- §2 数据模型（`workflow_versions` 表）→ Task 1。
- §3 同步逻辑（`source_key`=身份、归档、updates 响应）→ Task 2。
- §4 后端 API（/versions 列表/查看/删除 + has_history）→ Task 3。
- §5 前端（历史按钮 + 面板）→ Task 4-5。
- §6 测试 → 每任务 TDD。
- §7 约束 → Global Constraints + 各任务。

**2. Placeholder scan：** 无 TBD/TODO；每步有完整代码。Task 5 Step 5 冒烟提到"若 ComfyUI 文件不好改，可手动改文件"——这是明确的操作指引，非占位符。

**3. Type consistency：**
- `archive_version(workflow_id, name, size_bytes, body) -> WorkflowVersion` 在 Task 1 定义，Task 2 sync 调用（传 `existing.name, existing.size_bytes, existing.body`）。
- `list_versions/get_version/delete_version/has_history/max_version` 在 Task 1 定义，Task 3 路由 + Task 2 用。
- `WorkflowOut.has_history` 在 Task 3 schema 定义，Task 4 前端类型 `WorkflowSummary.has_history` 对齐。
- `WorkflowVersionOut` ↔ 前端 `WorkflowVersion`（字段一致）。
- `updates: [str]` 在 Task 2 返回，前端 `SyncBrowseResult`（Task 4 未改它——注意：`SyncBrowseResult` 已有 `updated`，`updates` 数组是新增可选字段，前端 `doSync` 读 `data.browse.updates`）。**需确认**：`types/api.ts` 的 `SyncBrowseResult` 应加 `updates?: string[]`。已在 Task 4 Step 1 隐含（未明确写）——**补上**：
```ts
export interface SyncBrowseResult {
  added: number;
  updated: number;
  skipped: number;
  error: string | null;
  updates?: string[];
}
```
- `model_copy(update={"has_history": ...})` 用于路由层填充非列字段——Pydantic v2 支持，consistent。
