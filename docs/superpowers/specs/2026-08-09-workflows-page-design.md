# ComfyChat 工作流页设计

日期：2026-08-09
状态：待用户复核
适用范围：ComfyChat 第二阶段（工作流页：浏览同步 + 导入/导出）

## 1. 目标与范围

在 ComfyChat 前端引入后台管理布局（侧栏 + 顶栏 + `<router-view/>`），并实现第一个业务页：**工作流页**。该页：
- 从本地 ComfyUI（:8188）浏览目录同步已有工作流；
- 支持用户上传（导入）与下载（导出）工作流文件；
- 所有操作仅针对工作流文件本身（不执行、不修改工作流 JSON、不做节点分析）。

明确**不**包含：
- 运行工作流（`POST /prompt`，留给"任务"页）。
- 向 ComfyUI input 目录上传文件。
- 工作流 JSON 解析、节点统计、重命名（导入时同名场景除外）。
- 标签 / 收藏 / 版本管理。
- 后台自动轮询同步（v1 用"手动同步"按钮）。
- 鉴权 / 多用户。

## 2. 架构

```
浏览器 (Vue 3)
    │  /api/workflows 等
    ▼
FastAPI ──  ──  ComfyUIClient ──  ComfyUI (:8188)
  │  │            ├─ /system_stats ──→ ping()（健康检查，沿用）
  │  │            └─ /v2/userdata?path=workflows ──→ list_browse()（仅元数据列表）
  │  │
  │  └─ read_userdata_json(name) ──→ 本地 FS: $COMFYUI_USERDATA_DIR/workflows/{name}
  │
  └─ WorkflowRepository ── SQLite (storage/data/comfychat.db)
```

关键决策：
- **单一来源浏览**：只同步 ComfyUI 浏览目录（`/v2/userdata?path=workflows`），不用 `/history`、`/workflow_templates`（用户明确只取"已有的"）。
- **v2 参数用 `path`**（不是 `dir`）：`GET /v2/userdata?path=workflows` 返回干净的文件列表（`name`、`path`、`type`、`size`、`modified`）。ComfyUI 0.31.0 源码中 v2 读取 `path` 查询参数，`dir` 会被忽略并退化为根目录递归列表。
- **读文件走文件系统**：`/userdata/{file}` 路由在 ComfyUI 0.31.0 中为单段路径匹配（`{file}` 无 `:.*` 正则），无法读取子目录文件（实测 404）。因此文件内容由后端直读 `$COMFYUI_USERDATA_DIR/workflows/{name}`。若该配置未设或目录不可达，browse 源在同步时**静默跳过**（不报错）。
- 后端需新增配置 `comfyui_userdata_dir`（默认 `None`），不破坏现有四个字段。

## 3. 数据模型

```sql
CREATE TABLE workflows (
  id              TEXT PRIMARY KEY,           -- uuid4 hex
  name            TEXT NOT NULL,              -- 显示名（= 文件名去后缀）
  source          TEXT NOT NULL,              -- 'browse' | 'import'
  source_key      TEXT NOT NULL,              -- 文件名（browse/import 都用文件名）
  original_name   TEXT NOT NULL,              -- 原始文件名
  size_bytes      INTEGER NOT NULL,
  body            TEXT NOT NULL,              -- 完整 JSON 字符串
  created_at      TEXT NOT NULL,              -- ISO8601 UTC
  updated_at      TEXT NOT NULL,              -- ISO8601 UTC
  UNIQUE(source, source_key)
);
CREATE INDEX idx_workflows_source     ON workflows(source);
CREATE INDEX idx_workflows_updated_at ON workflows(updated_at DESC);
```

- 去重键 `(source, source_key)`：sync 时 upsert——存在则更新 `body/size_bytes/updated_at`，否则插入。
- 命名：browse → `name = 文件名去后缀`，`source_key = 文件名`；import → 同规则。
- 无 `node_count`、`body_format` 列（不做解析）。
- `size_bytes = len(body 的 UTF-8 字节)`。
- 不做列内重命名（导入同名场景除外，见 §4）。

## 4. 后端 API

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET`    | `/api/workflows`                  | 列表；`?source=browse\|import` 过滤、`?q=` 按 `name`/`original_name` 大小写不敏感 LIKE。默认按 `updated_at DESC` 排序。无分页（v1 数据量小）。 |
| `GET`    | `/api/workflows/{id}`             | 单条元数据（不含 `body`）。404 若不存在。 |
| `GET`    | `/api/workflows/{id}/body`        | 原始 JSON 字符串，`Content-Type: application/json`。404 若不存在。 |
| `GET`    | `/api/workflows/{id}/export`      | 下载：`Content-Disposition: attachment; filename="<name>.json"`。 |
| `DELETE` | `/api/workflows/{id}`             | 物理删除该行。404 若不存在。 |
| `POST`   | `/api/workflows/import`           | multipart，单字段 `file`（`.json`）。见去重流程。400 非法 JSON。 |
| `POST`   | `/api/workflows/sync`             | 触发浏览目录同步。body 空。返回摘要。 |
| 保留     | `GET /`、`GET /health`            | 原骨架端点不变。 |

### import 去重流程

冲突判定 = **存在 `(source='import', source_key=<上传文件名>)` 的行**。browse 行是只读镜像，与 import 同名不视为冲突（靠 `(source, source_key)` 天然区分）。

| 请求 | 行为 |
|---|---|
| `POST /api/workflows/import`（首次） | 无冲突 → `201 {workflow}`；有冲突 → `409 {filename, existing:{id,name,created_at}}` |
| `POST /api/workflows/import?name=<新名>` | 用户选"重命名"后的重试；以 `(import, <新名>.json)` 建新行 → `201`。若 `<新名>.json` 也与现有 import 行冲突，返回 `409` 复用弹窗流程 |
| `POST /api/workflows/import?overwrite=true` | 用户选"覆盖"后的重试；替换现有 import 行 `body/size_bytes/updated_at`（保留 `id/source/source_key/original_name/created_at`）→ `200` |
| 前端"取消" | 不发请求 |

注意：`updated`/`skipped` 的判定仅以 `size_bytes` 是否变化为准（不读内容比对，避免 IO 开销）；同名同大小的改动会漏判，属可接受启发式。

### sync 响应

```json
{
  "synced_at": "2026-08-09T15:30:00Z",
  "browse": { "added": 0, "updated": 0, "skipped": 3, "error": null }
}
```

- browse 源独立、最努力：失败不影响其他（当前仅一个源，结构仍为将来扩展留位）。
- `skipped` = 库中已有且 `size_bytes` 未变；`updated` = 已有但 `size_bytes` 变化（仅以大小判定，不读内容，见 §4 注）。
- **不自动删除**：库中存在但 ComfyUI 目录已无的文件，保留。

### 错误约定

`400` 用户错（无效 ID / 文件类型 / 非 JSON）、`404` 不存在、`409` import 冲突、`500` 服务错、`502` ComfyUI 不可达（仅 sync 路径）。

## 5. 前端

### 目录与组件

```
frontend/src/
  app/
    layout/AppLayout.vue        # 整体布局：<Sidebar/><main><TopBar/><router-view/></main>
    router.ts                   # 加 /workflows；根路径重定向 / → /workflows
  components/
    Sidebar.vue
    TopBar.vue                  # logo + 健康指示灯（复用 api.health()）
    Modal.vue                   # 通用模态
  features/workflows/
    WorkflowsView.vue
    WorkflowRow.vue
    WorkflowImportButton.vue
    WorkflowSyncButton.vue
    WorkflowDetailModal.vue     # 只读展示 body JSON
    ImportConflictDialog.vue    # 同名冲突：重命名/覆盖/取消
    useWorkflows.ts             # 组合式逻辑
  services/api.ts               # 扩展 workflows 方法
  types/api.ts                  # 扩展类型
```

### 路由

- `/` → redirect `/workflows`
- `/workflows` → `WorkflowsView`

`App.vue` 改为挂 `<AppLayout>`；原"ComfyChat 前端就绪 + /health"的探活逻辑移到 `TopBar.vue`（健康指示灯 ok/error/unknown）。

### 页面与操作

```
TopBar: [ComfyChat] [健康指示灯: ok]
Sidebar: 工作流
主区： 工作流  [导入] [同步]   [搜索...] [源▾]
       名称                    源      大小    更新于     操作
       image_qwen_...json     browse  12.6KB  1m ago    [看][↓][×]
```

- 看 → `WorkflowDetailModal`（pretty-printed JSON，只读）。
- ↓ → `GET /{id}/export` 触发下载，文件名 `<name>.json`。
- × → 确认对话框 → `DELETE` → 刷新。
- 导入 → 文件选择 → `POST /import`；`409` → `ImportConflictDialog`（重命名/覆盖/取消，见 §4）。
- 同步 → `POST /sync` → toast 摘要（"已同步 X / 更新 Y / 跳过 Z"）→ 刷新。

### 类型

```ts
export type WorkflowSource = 'browse' | 'import';
export interface WorkflowSummary {
  id: string; name: string; source: WorkflowSource;
  source_key: string; original_name: string;
  size_bytes: number; created_at: string; updated_at: string;
}
export interface SyncBrowseResult { added: number; updated: number; skipped: number; error: string | null; }
export interface SyncResult { synced_at: string; browse: SyncBrowseResult; }
```

## 6. 测试策略

**后端（pytest）：**
- `ComfyUIClient.list_browse()`：mock httpx 返回 v2 结构（`?path=workflows`），验证解析；mock 网络/4xx/5xx → 返回错误信号。
- `WorkflowRepository`：临时 SQLite 测 `upsert` / `list`（过滤、排序、搜索）/ `get` / `delete` / `(source, source_key)` 唯一性。
- `WorkflowService.sync()`：mock `list_browse()` + 真实临时 `COMFYUI_USERDATA_DIR`（写 3 个假 `.json`）测 added/updated/skipped；验证残留不删。
- `POST /api/workflows/import`：TestClient multipart 上传合法/非法/重复 → 201/400/409；重命名、覆盖路径。
- `GET /api/workflows`、`/{id}`、`/{id}/body`、`/{id}/export`、`DELETE`：形状与错误码断言。

**前端：**
- v1 不引入前端测试框架；验证靠 `vue-tsc` typecheck + `scripts/start-dev.ps1` 冒烟 + 浏览器手动走一遍导入/同步/删除。

## 7. 部署/配置变更

- 后端 `Settings` 新增 `comfyui_userdata_dir: Path | None = None`。
- `.env.example`（根与 backend）新增 `COMFYUI_USERDATA_DIR=` 注释行。
- 后端 `pyproject.toml` 无新依赖（httpx 已装）。
- 前端无新 npm 依赖。
