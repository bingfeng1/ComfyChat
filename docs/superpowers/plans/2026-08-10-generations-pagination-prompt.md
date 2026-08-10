# 生成页分页 + 提示词多行展示 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `/generations` 页面加分页(`el-pagination`,默认 15/页)+ 提示词单元格改为可折叠多行(默认 3 行,长文本带「展开全文」/「收起」按钮),依据 `docs/superpowers/specs/2026-08-10-generations-pagination-prompt-design.md`。

**Architecture:** 后端 `GenerationRepository` 增加 `list(status, page, page_size)` + `count(status)`,路由 `GET /generations` 增 `page`/`page_size` Query 参数并返回 `{items, total, page, page_size}`;前端 `GenerationList` 类型同步加字段,`api.generations.list` 接受新参数;`useGenerations` 持有 `page/pageSize/total` 状态;视图用 `<el-pagination>` 与 `-webkit-line-clamp: 3` + 按钮切换展开。

**Tech Stack:** FastAPI + SQLAlchemy 2.x + SQLite(后端);Vue 3 + Vite + TypeScript + Element Plus 2.11+(前端)。

## Global Constraints

从 spec 与 AGENTS.md 拷贝的项目级规则,适用于所有任务,除非任务中明确覆盖。

- **后端范围只动:**`backend/app/schemas/generation.py`、`backend/app/repositories/generation.py`、`backend/app/api/routes/generations.py`、`backend/tests/test_generation_repository.py`。其它后端文件(包含 `services/generation.py`)一律不动。
- **前端范围只动:**`frontend/src/types/api.ts`、`frontend/src/services/api.ts`、`frontend/src/features/generations/useGenerations.ts`、`frontend/src/features/generations/GenerationsView.vue`。其它前端文件(包含 `useWorkflows.ts`、`GenerationCreateModal.vue`、`GenerationDetailModal.vue`)一律不动。
- **Vite 代理约定保持不变:**前端调用 `/api/generations/...`;后端路由前缀 `/generations`(无 `/api`)。
- **Element Plus 自动导入:**不写 `import { ElButton }` 之类的语句(自动导入已配);`@element-plus/icons-vue` 图标本期不引入新图标,可忽略。
- **SCSS 区块:**新增/修改的 `<style lang="scss">` 直接写即可,无需 `@use` 变量(本期不引新 token)。
- **Workspace 约定:**Windows PowerShell,后端 venv 在 `backend/.venv/Scripts/python`;`frontend/.npmrc` 已配 npm 镜像;不要全局 `npm config set`;不要前台跑 `uvicorn` / `npm run dev`(用 `scripts/start-dev.ps1` / `stop-dev.ps1`)。
- **后端无 alembic:**新增字段靠 `Base.metadata.create_all`;不改 `models/`。本任务不改表结构。
- **前端无测试框架:**验证靠 `npm --prefix frontend run typecheck` + `npm --prefix frontend run build`(可选)+ 手动烟测。不要新增 vitest 等。
- **TDD:**后端任务先写失败测试,跑确认失败,再实现。`session` fixture 已存在于 `backend/tests/conftest.py`,直接用。
- **PowerShell 不支持 `&&`:**链式命令用 `; if ($?) { … }` 或分多步。
- **行尾换行:**提交时如有 CRLF/LF 警告可忽略。

---

## File Structure

| 文件 | 责任 | 是否动 |
|---|---|---|
| `backend/app/schemas/generation.py` | 定义 `GenerationListOut` 出参形状 | 改 |
| `backend/app/repositories/generation.py` | `list(...)` 分页 + `count(...)` | 改 |
| `backend/app/api/routes/generations.py` | `GET /generations` 接 page/page_size | 改 |
| `backend/tests/test_generation_repository.py` | 新增 4 个分页/计数测试 | 改 |
| `frontend/src/types/api.ts` | `GenerationList` 新增字段 | 改 |
| `frontend/src/services/api.ts` | `api.generations.list` 新增可选参数 | 改 |
| `frontend/src/features/generations/useGenerations.ts` | 新增 `page/pageSize/total` + setter;`create` 重置 page | 改 |
| `frontend/src/features/generations/GenerationsView.vue` | 提示词多行 + `el-pagination` | 改 |

---

## Task 1: 后端仓库分页 + 计数 (TDD)

**Files:**
- Modify: `backend/tests/test_generation_repository.py`
- Modify: `backend/app/repositories/generation.py`

**Interfaces:**
- Consumes: 现有 `GenerationRepository.list(status)` 调用方(不动);现有 `session` 测试 fixture(`backend/tests/conftest.py`)。
- Produces:
  - `GenerationRepository.list(status: Optional[str], *, page: int = 1, page_size: int = 15) -> Sequence[Generation]`
  - `GenerationRepository.count(status: Optional[str]) -> int`

- [ ] **Step 1: 写失败测试 — 切片**

在 `backend/tests/test_generation_repository.py` 末尾追加:

```python
def test_list_paginates_correctly(session):
    repo = _mk_repo(session)
    for i in range(20):
        repo.create("wf1", "z-image", {"i": i}, "success", f"p{i}")
    # 排序按 created_at 倒序,后插入的在前
    all_ids = [g.id for g in repo.list()]
    assert len(all_ids) == 20

    page1 = repo.list(page=1, page_size=15)
    page2 = repo.list(page=2, page_size=15)
    page3 = repo.list(page=3, page_size=15)
    assert [g.id for g in page1] == all_ids[:15]
    assert [g.id for g in page2] == all_ids[15:20]
    assert [g.id for g in page3] == []


def test_count_ignores_pagination(session):
    repo = _mk_repo(session)
    for i in range(20):
        repo.create("wf1", "z-image", {"i": i}, "success", f"p{i}")
    assert repo.count() == 20
    assert repo.count() == 20  # 与 page/page_size 无关


def test_list_with_status_filter_paginates(session):
    repo = _mk_repo(session)
    for i in range(10):
        repo.create("wf1", "z-image", {"i": i}, "success", f"p{i}")
    for i in range(10):
        repo.create("wf1", "z-image", {"i": i}, "queued", f"q{i}")

    success_all = repo.list(status="success")
    assert len(success_all) == 10
    success_page1 = repo.list(status="success", page=1, page_size=5)
    success_page2 = repo.list(status="success", page=2, page_size=5)
    assert len(success_page1) == 5
    assert len(success_page2) == 5
    assert {g.id for g in success_page1}.isdisjoint({g.id for g in success_page2})


def test_list_empty_page_returns_empty(session):
    repo = _mk_repo(session)
    for i in range(3):
        repo.create("wf1", "z-image", {"i": i}, "success", f"p{i}")
    assert repo.list(page=999, page_size=15) == []
```

- [ ] **Step 2: 跑测试确认失败**

```powershell
cd D:\learnAI\ComfyChat
backend\.venv\Scripts\python -m pytest backend/tests/test_generation_repository.py::test_list_paginates_correctly -v
```

Expected: FAIL,`TypeError: list() got an unexpected keyword argument 'page'` 或 `AttributeError: 'GenerationRepository' object has no attribute 'count'`。

- [ ] **Step 3: 修改 `backend/app/repositories/generation.py`**

在文件顶部把 `from sqlalchemy import select` 改成 `from sqlalchemy import func, select`。

替换 `GenerationRepository.list` 方法:

```python
def list(
    self,
    status: Optional[str] = None,
    *,
    page: int = 1,
    page_size: int = 15,
) -> Sequence[Generation]:
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 15
    stmt = select(Generation)
    if status:
        stmt = stmt.where(Generation.status == status)
    stmt = stmt.order_by(Generation.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    return self.session.scalars(stmt).all()

def count(self, status: Optional[str] = None) -> int:
    stmt = select(func.count()).select_from(Generation)
    if status:
        stmt = stmt.where(Generation.status == status)
    return int(self.session.scalar(stmt) or 0)
```

`list_pending()` 等其它方法原样不动。

- [ ] **Step 4: 跑新增测试,确认通过**

```powershell
cd D:\learnAI\ComfyChat
backend\.venv\Scripts\python -m pytest backend/tests/test_generation_repository.py -v
```

Expected: 全部通过(原有 4 个 + 新增 4 个 = 8 个)。

- [ ] **Step 5: 跑全套后端测试,确认无回归**

```powershell
cd D:\learnAI\ComfyChat
backend\.venv\Scripts\python -m pytest backend/tests -v
```

Expected: 111 + 4 = 115 个测试通过(1 个已知 Windows 失败 `test_check_database_returns_false_when_path_unwritable` 可接受)。

- [ ] **Step 6: 提交**

```powershell
cd D:\learnAI\ComfyChat
git add backend/app/repositories/generation.py backend/tests/test_generation_repository.py; if ($?) { git commit -m "feat(backend): paginate generations list + add count" }
```

---

## Task 2: 后端 schema + 路由

**Files:**
- Modify: `backend/app/schemas/generation.py`
- Modify: `backend/app/api/routes/generations.py`

**Interfaces:**
- Consumes:Task 1 产出的 `GenerationRepository.list(status, *, page, page_size)`、`GenerationRepository.count(status)`。
- Produces:`GET /generations` 返回 `GenerationListOut(items, total, page, page_size)`;新增 `Query` 参数 `page`(默认 1, `ge=1`)、`page_size`(默认 15, `ge=1`, `le=100`)。

- [ ] **Step 1: 修改 `backend/app/schemas/generation.py`**

把 `GenerationListOut` 替换为:

```python
class GenerationListOut(BaseModel):
    items: list[GenerationOut]
    total: int
    page: int
    page_size: int
```

- [ ] **Step 2: 修改 `backend/app/api/routes/generations.py`**

在文件顶部 `from fastapi import ...` 行增加 `Query`:

```python
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
```

替换 `list_generations` 函数:

```python
@router.get("", response_model=GenerationListOut)
def list_generations(
    status_filter: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=100),
    service: GenerationService = Depends(_service),
) -> GenerationListOut:
    service.reconcile()
    items = service.gen_repo.list(
        status=status_filter, page=page, page_size=page_size
    )
    total = service.gen_repo.count(status=status_filter)
    return GenerationListOut(
        items=[GenerationOut.from_model(g) for g in items],
        total=total,
        page=page,
        page_size=page_size,
    )
```

- [ ] **Step 3: 跑 API 测试,确认通过**

```powershell
cd D:\learnAI\ComfyChat
backend\.venv\Scripts\python -m pytest backend/tests -v -k "generation"
```

Expected: 既有 `test_generations_api.py` 的用例继续通过(它调 `GET /generations` 但不校验新增字段,只要不报 422 即可)。如果发现 API 测试断言旧的 `{items: [...]}` 形状而失败,把那个断言改成读取 `body["items"]`(向后兼容)即可。

- [ ] **Step 4: 跑全套后端测试**

```powershell
cd D:\learnAI\ComfyChat
backend\.venv\Scripts\python -m pytest backend/tests -v
```

Expected: 同 Task 1 Step 5。

- [ ] **Step 5: 提交**

```powershell
cd D:\learnAI\ComfyChat
git add backend/app/schemas/generation.py backend/app/api/routes/generations.py; if ($?) { git commit -m "feat(backend): add page/page_size to GET /generations response" }
```

---

## Task 3: 前端类型 + API 客户端

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/services/api.ts`

**Interfaces:**
- Consumes: 后端 Task 2 产出的新响应形状。
- Produces:
  - `GenerationList` 类型含 `total: number; page: number; page_size: number`。
  - `api.generations.list({status?, page?, page_size?})` URL 带可选 query 参数。

- [ ] **Step 1: 修改 `frontend/src/types/api.ts`**

替换 `GenerationList` 接口:

```ts
export interface GenerationList {
  items: GenerationSummary[];
  total: number;
  page: number;
  page_size: number;
}
```

- [ ] **Step 2: 修改 `frontend/src/services/api.ts`**

`api.generations.list` 替换为:

```ts
list: (params?: {
  status?: GenerationStatus;
  page?: number;
  page_size?: number;
}) => {
  const sp = new URLSearchParams();
  if (params?.status) sp.set("status", params.status);
  if (params?.page) sp.set("page", String(params.page));
  if (params?.page_size) sp.set("page_size", String(params.page_size));
  const qs = sp.toString() ? `?${sp.toString()}` : "";
  return get<GenerationList>(`/generations${qs}`);
},
```

- [ ] **Step 3: 跑类型检查**

```powershell
cd D:\learnAI\ComfyChat
npm --prefix frontend run typecheck
```

Expected: PASS(此时 `useGenerations.ts` 还没改,可能因为新 `GenerationList` 字段不匹配产生新错误,看下个任务)。

- [ ] **Step 4: 提交**

```powershell
cd D:\learnAI\ComfyChat
git add frontend/src/types/api.ts frontend/src/services/api.ts; if ($?) { git commit -m "feat(frontend): extend GenerationList type + list api with page/page_size" }
```

---

## Task 4: 前端组合式函数

**Files:**
- Modify: `frontend/src/features/generations/useGenerations.ts`

**Interfaces:**
- Consumes:Task 3 的 `api.generations.list({status?, page?, page_size?})` + `GenerationList`。
- Produces:
  - 三个新 ref:`page`(默认 1)、`pageSize`(默认 15)、`total`(默认 0)。
  - `setPage(n: number)` 与 `setPageSize(n: number)`,各自调用 `refresh()`。
  - `refresh()` 与 `poll()` 都把 `page`、`pageSize` 一起发出去。
  - `statusFilter` 变化时:`page = 1` 然后 `refresh()`(在 `refresh` 之外加一个 `watch`,或在模板 `@change` 里改)。
  - `create()` 成功后:`page = 1` 然后 `refresh()`。
  - `remove()` 成功后:只 `refresh()`(不重置 page)。

- [ ] **Step 1: 重写 `useGenerations.ts`**

完整替换 `frontend/src/features/generations/useGenerations.ts`:

```ts
import { onMounted, onUnmounted, ref, watch } from "vue";
import { api } from "@/services/api";
import type { GenerationStatus, GenerationSummary } from "@/types/api";

export function useGenerations() {
  const items = ref<GenerationSummary[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const statusFilter = ref<GenerationStatus | "">("");
  const page = ref(1);
  const pageSize = ref(15);
  const total = ref(0);
  let timer: number | undefined;

  async function refresh(silent = false) {
    if (!silent) loading.value = true;
    error.value = null;
    try {
      const data = await api.generations.list({
        status: statusFilter.value || undefined,
        page: page.value,
        page_size: pageSize.value,
      });
      items.value = data.items;
      total.value = data.total;
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err);
    } finally {
      if (!silent) loading.value = false;
    }
  }

  async function poll() {
    try {
      const data = await api.generations.list({
        status: statusFilter.value || undefined,
        page: page.value,
        page_size: pageSize.value,
      });
      items.value = data.items;
      total.value = data.total;
    } catch {
      /* 静默轮询失败不打扰用户 */
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
    page.value = 1;
    await refresh();
    return (await res.json()) as GenerationSummary;
  }

  async function remove(id: string) {
    const res = await api.generations.remove(id);
    if (res.status !== 204) throw new Error(`删除失败：${res.status}`);
    await refresh();
  }

  function setPage(n: number) {
    page.value = n;
    refresh();
  }

  function setPageSize(n: number) {
    pageSize.value = n;
    page.value = 1;
    refresh();
  }

  watch(statusFilter, () => {
    page.value = 1;
    refresh();
  });

  onMounted(() => {
    refresh();
    timer = window.setInterval(poll, 2000);
  });
  onUnmounted(() => {
    if (timer) window.clearInterval(timer);
  });

  return {
    items,
    loading,
    error,
    statusFilter,
    page,
    pageSize,
    total,
    refresh,
    create,
    remove,
    setPage,
    setPageSize,
  };
}
```

注意 `GenerationsView.vue` 当前 `statusFilter` 模板里写了 `@change="() => refresh()"`(手动刷新),由本任务的 `watch` 接管后需要删除那行(在 Task 5 改)。

- [ ] **Step 2: 跑类型检查**

```powershell
cd D:\learnAI\ComfyChat
npm --prefix frontend run typecheck
```

Expected: PASS。注意此时 `GenerationsView.vue` 还引用旧的 `statusFilter` + `refresh` 用法但没有用到 `page/pageSize/total/setPage/setPageSize`,应该没有类型错误。如果有,只是临时性的,Task 5 会清掉。

- [ ] **Step 3: 提交**

```powershell
cd D:\learnAI\ComfyChat
git add frontend/src/features/generations/useGenerations.ts; if ($?) { git commit -m "feat(frontend): paginated useGenerations composable" }
```

---

## Task 5: 前端视图 — 提示词多行 + el-pagination

**Files:**
- Modify: `frontend/src/features/generations/GenerationsView.vue`

**Interfaces:**
- Consumes:Task 4 的 `useGenerations()` 新返回项(`page`, `pageSize`, `total`, `setPage`, `setPageSize`)。
- Produces:
  - 提示词列用 `<div class="cc-prompt">` + 可选「展开全文」按钮;展开状态用组件内 `Set<string>` 跟踪。
  - 表格下方加 `<el-pagination>` 与 `@current-change` / `@size-change` 绑定。
  - 删除模板里 `@change="() => refresh()"`(由 composable 的 `watch` 接管)。

- [ ] **Step 1: 修改 `<script setup>`**

替换 `frontend/src/features/generations/GenerationsView.vue` 顶部 `<script setup lang="ts">` 段:

```ts
<script setup lang="ts">
import { ref } from "vue";
import Modal from "@/components/Modal.vue";
import GenerationCreateModal from "./GenerationCreateModal.vue";
import GenerationDetailModal from "./GenerationDetailModal.vue";
import { useGenerations } from "./useGenerations";
import { api } from "@/services/api";
import type { GenerationSummary } from "@/types/api";

const {
  items,
  loading,
  error,
  statusFilter,
  page,
  pageSize,
  total,
  refresh,
  remove,
  setPage,
  setPageSize,
} = useGenerations();

const showCreate = ref(false);
const detail = ref<GenerationSummary | null>(null);
const regenerate = ref<GenerationSummary | null>(null);
const confirmDelete = ref<GenerationSummary | null>(null);
const expandedPrompts = ref<Set<string>>(new Set());

async function doDelete() {
  if (!confirmDelete.value) return;
  await remove(confirmDelete.value.id);
  confirmDelete.value = null;
}

function togglePrompt(id: string) {
  const next = new Set(expandedPrompts.value);
  if (next.has(id)) {
    next.delete(id);
  } else {
    next.add(id);
  }
  expandedPrompts.value = next;
}

const statusLabel: Record<string, string> = {
  queued: "排队中",
  running: "执行中",
  success: "成功",
  failed: "失败",
};

function statusType(status: string): "success" | "warning" | "danger" | "info" {
  if (status === "success") return "success";
  if (status === "failed") return "danger";
  if (status === "running" || status === "queued") return "warning";
  return "info";
}

function fmtTime(iso: string) {
  return new Date(iso).toLocaleString();
}

function thumbUrl(g: GenerationSummary): string | null {
  const first = g.outputs[0];
  return first ? api.generations.imageUrl(g.id, first) : null;
}

function promptText(g: GenerationSummary): string {
  const p = g.parameters["text"];
  return typeof p === "string" ? p : "";
}
</script>
```

- [ ] **Step 2: 修改模板 — 状态过滤下拉**

找到:

```html
<el-select v-model="statusFilter" placeholder="全部状态" clearable style="width: 200px" @change="() => refresh()">
```

改为(去掉手动 `@change`,由 composable 的 `watch` 接管):

```html
<el-select v-model="statusFilter" placeholder="全部状态" clearable style="width: 200px">
```

- [ ] **Step 3: 修改模板 — 提示词列**

找到:

```html
<el-table-column label="提示词" min-width="240">
  <template #default="{ row }">
    <span class="cc-prompt">{{ promptText(row) || "—" }}</span>
  </template>
</el-table-column>
```

替换为:

```html
<el-table-column label="提示词" min-width="240" :show-overflow-tooltip="false">
  <template #default="{ row }">
    <div :class="['cc-prompt', { 'is-expanded': expandedPrompts.has(row.id) }]">
      {{ promptText(row) || "—" }}
    </div>
    <el-button
      v-if="promptText(row).length > 60"
      link
      type="primary"
      size="small"
      class="cc-prompt-toggle"
      @click="togglePrompt(row.id)"
    >
      {{ expandedPrompts.has(row.id) ? "收起" : "展开全文" }}
    </el-button>
  </template>
</el-table-column>
```

- [ ] **Step 4: 修改模板 — 在表格后加分页器**

找到 `<el-table>` 结束标签 `</el-table>`(在 GenerationCreateModal 之前)。在它后面插入:

```html
<div class="cc-pagination">
  <el-pagination
    v-model:current-page="page"
    v-model:page-size="pageSize"
    :total="total"
    :page-sizes="[10, 15, 20, 50]"
    layout="total, sizes, prev, pager, next"
    background
    @current-change="setPage"
    @size-change="setPageSize"
  />
</div>
```

- [ ] **Step 5: 替换样式**

把 `<style lang="scss" scoped>` 里的 `.cc-prompt` 整段替换为:

```scss
.cc-prompt {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  white-space: pre-wrap;
  word-break: break-word;
  max-width: 100%;
  line-height: 1.5;
}
.cc-prompt.is-expanded {
  display: block;
  overflow: visible;
  -webkit-line-clamp: unset;
}
.cc-prompt-toggle {
  padding: 0;
  margin-top: 2px;
}
.cc-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 1rem;
}
.cc-thumb-placeholder {
  display: inline-block;
  width: 72px;
  height: 72px;
  background: #e2e8f0;
  border-radius: 6px;
}
```

注意保留原有的 `.cc-toolbar`、`.cc-spacer`、`.cc-filters` 不动;`.cc-thumb-placeholder` 也保留(表格里还用到)。

- [ ] **Step 6: 跑类型检查 + 构建**

```powershell
cd D:\learnAI\ComfyChat
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Expected: 两个都 PASS。

- [ ] **Step 7: 手动烟测**

启动 dev 服务:

```powershell
cd D:\learnAI\ComfyChat
powershell -ExecutionPolicy Bypass -File scripts\start-dev.ps1
```

浏览器打开 `http://127.0.0.1:5173/generations`,验证:

1. 表格下方出现 `<el-pagination>`,显示 `total` 与「15」页大小。
2. 如果当前有 > 15 条记录,会出现翻页按钮;点击翻页工作正常。
3. 切换 page size 到 20/50,记录数与 total 一致。
4. 切到第 2 页,点击「+ 新建生成」(用现有工作流),创建成功后自动跳回第 1 页,新记录显示在顶部。
5. 切换状态过滤,自动回到第 1 页。
6. 长提示词(> 60 字符)显示 3 行后省略,下方出现「展开全文」;点击展开,再点「收起」恢复。
7. 短提示词(< 60 字符)不出现「展开全文」按钮。
8. 2 秒轮询只刷新当前页;停在第 2 页时,后台新建一条记录不会跳到第 1 页(预期)。

烟测完成后停止:

```powershell
cd D:\learnAI\ComfyChat
powershell -ExecutionPolicy Bypass -File scripts\stop-dev.ps1
```

- [ ] **Step 8: 提交**

```powershell
cd D:\learnAI\ComfyChat
git add frontend/src/features/generations/GenerationsView.vue; if ($?) { git commit -m "feat(frontend): multi-line prompt clamp + el-pagination on /generations" }
```

---

## Task 6: 最终验证

**Files:**(只读,验证用)

- `backend/tests/`
- `frontend/`

- [ ] **Step 1: 后端全量测试**

```powershell
cd D:\learnAI\ComfyChat
backend\.venv\Scripts\python -m pytest backend/tests -v
```

Expected: 115 个测试通过(原有 111 + Task 1 新增 4);1 个已知 Windows 失败 `test_check_database_returns_false_when_path_unwritable` 跳过/失败可接受。

- [ ] **Step 2: 前端类型检查 + 构建**

```powershell
cd D:\learnAI\ComfyChat
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Expected: 两个都 PASS。

- [ ] **Step 3: 检查 git 状态,确认改动范围**

```powershell
cd D:\learnAI\ComfyChat
git status
git diff --stat HEAD~4..HEAD
```

Expected: 总共 8 个文件被改动,均在本计划 `File Structure` 表中。无意外文件进入。

- [ ] **Step 4: 推送(可选,用户决定)**

```powershell
cd D:\learnAI\ComfyChat
git push origin main
```

只有当用户明确要求时才执行。

---

## Self-Review Checklist

- [x] **Spec 覆盖:**
  - 后端 `page/page_size` Query 参数 → Task 2
  - 后端响应形状 `{items, total, page, page_size}` → Task 2
  - 仓库 `list` 分页 + `count` → Task 1
  - 后端 4 个测试 → Task 1 Step 1
  - 前端 `GenerationList` 新字段 → Task 3
  - 前端 `api.generations.list` 新参数 → Task 3
  - 前端 `useGenerations` 新状态 + setter → Task 4
  - `create` 后重置 page → Task 4
  - `remove` 不重置 page → Task 4
  - `statusFilter` 变化重置 page → Task 4(`watch`)+ Task 5(模板移除手动 `@change`)
  - 提示词 3 行 clamp + 展开按钮 → Task 5
  - 阈值 > 60 字符 → Task 5
  - `<el-pagination>` + sizes 10/15/20/50 → Task 5
  - 默认 15/页 → Task 4 + Task 5
  - 仅当前页轮询 → Task 4
  - 列 `show-overflow-tooltip="false"` → Task 5
- [x] **Placeholder scan:** 无 TBD / TODO / "implement later" / "Similar to Task N"。
- [x] **类型一致性:** 全部 `page` / `pageSize` / `total` 名字一致;后端 Query 参数名 `page_size` 与 schema 字段、TS 字段、URL 查询参数名一致。
- [x] **风险已记录:** 轮询范围限定的影响在 spec §风险 已记录;浏览器兼容性 `-webkit-line-clamp` 已记录。