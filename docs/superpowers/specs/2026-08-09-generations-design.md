# ComfyChat 文生图生成功能设计

日期：2026-08-09
状态：待用户复核
适用范围：ComfyChat 第四阶段（文生图：基于已配置工作流的生成记录列表 + 增删查 + 再生成）

## 1. 目标与范围

新增「生成」页面：通过后端链接 ComfyUI，基于已有工作流（如 z-image）执行文生图。提供完整的生成记录列表，支持新增、查询、删除，以及基于历史参数的二次生成（修改提示词/随机数等）。参数以「工作流独立配置」方式维护，可扩展更多参数类型。

明确**不**包含：
- SSE/WebSocket 实时推送（前端 2 秒轮询）。
- 任务队列持久化/断点重跑（进程重启后未完成任务仅靠 reconcile 兜底标记，不自动重跑）。
- 批量操作与分页（列表全量返回，暂不引入分页）。
- 普通画布工作流自动转换为 API 格式（须在配置弹窗手动补充 API 模板）。
- 参数类型的自动推断（配置弹窗手动指定 node_id / input_name）。

## 2. 数据模型

### 2.1 generations（生成记录，新增表）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | TEXT PRIMARY KEY | uuid4 hex |
| `workflow_id` | TEXT NOT NULL | FK → workflows.id，级联删除 |
| `workflow_name` | TEXT NOT NULL | 工作流名快照，便于列表展示 |
| `parameters_json` | TEXT NOT NULL | 任意参数对象 `{"positive_prompt":"...","seed":12345,"seed_random":false,...}`，向前可扩展 |
| `status` | TEXT NOT NULL | `queued` / `running` / `success` / `failed` |
| `prompt_id` | TEXT NOT NULL | ComfyUI `/prompt` 返回的任务 ID |
| `error` | TEXT NULL | 失败原因 |
| `outputs_json` | TEXT NULL | 成功后输出文件清单 `["ComfyUI_00001_.png", ...]` |
| `created_at` | TEXT NOT NULL | ISO8601 UTC |
| `updated_at` | TEXT NOT NULL | ISO8601 UTC |

### 2.2 workflow_generation_configs（工作流生成配置，新增表）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | TEXT PRIMARY KEY | uuid4 hex |
| `workflow_id` | TEXT NOT NULL | FK → workflows.id，级联删除，`UNIQUE(workflow_id)`（1:1） |
| `api_template` | TEXT NOT NULL | 可执行的 API 格式工作流 JSON |
| `fields_json` | TEXT NOT NULL | 参数定义数组（见下） |
| `updated_at` | TEXT NOT NULL | ISO8601 UTC |

`fields_json` 结构：

```json
[
  {
    "key": "positive_prompt",
    "label": "正面提示词",
    "type": "text",
    "node_id": "6",
    "input_name": "text",
    "default": "",
    "required": true
  },
  {
    "key": "seed",
    "label": "随机数",
    "type": "seed",
    "node_id": "3",
    "input_name": "seed",
    "default": 0,
    "required": true
  }
]
```

- `type` 首版支持 `text` 与 `seed`；`seed` 内置「是否随机」开关，扩展类型（number/select/checkbox 等）后续通过前端表单渲染器与后端校验扩展，`fields_json` 结构不变。
- `key` 用于读写 `generations.parameters_json`。

### 2.3 设计说明

- 配置挂在**独立表**而非给 `workflows` 加列：现有 SQLite 库已建好 `workflows` 表，`Base.metadata.create_all` 不会给已存在表补列；新表会被自动创建（与无 alembic 约束一致）。
- 1:1 关系：每个工作流最多一条生成配置；配置弹窗首次=新建，之后=编辑。只有已配置工作流可选入生成。
- 配置后期可直接在弹窗中编辑 `api_template` 与 `fields_json`（增删字段/改类型/改默认值），无需迁移脚本。

## 3. 后端 API

`backend/app/api/routes/generations.py`，`router = APIRouter(prefix="/generations")`（无 `/api`，沿用 Vite 代理约定）。

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/generations` | 新建生成任务。入参 `{workflow_id, parameters}`；校验参数、填入模板、提交 ComfyUI、落库 queued、启动后台轮询、返回记录 |
| GET | `/generations` | 列表（按 created_at 倒序），可选 `status` 过滤；顺带一次状态收编 reconcile |
| GET | `/generations/{id}` | 单条详情（含 outputs 文件清单） |
| GET | `/generations/{id}/images/{filename}` | 读取本地保存图片（FileResponse） |
| DELETE | `/generations/{id}` | 删除记录 + 级联删除本地图片目录 |

配置路由（挂在 `workflows.py` 的 router 下，路径无 `/api`）：

| 方法 | 路径 | 说明 |
|---|---|---|
| PUT | `/workflows/{id}/generation-config` | 保存/更新配置（api_template + fields） |
| GET | `/workflows/{id}/generation-config` | 读取配置（编辑弹窗用） |
| GET | `/workflows/generation-configs` | 所有已配置工作流列表（生成弹窗下拉用） |

### 3.1 生成参数校验

按该工作流配置的 `fields_json` 逐字段校验：
- 必填字段缺失 → 400。
- `seed` 类字段在 `seed_random=false` 时必须为整数 → 400。
- `seed_random=true` 时忽略用户值，提交时服务端生成随机 seed 写入参数。

### 3.2 执行流程（后台任务）

1. `POST /generations`：读 `workflow_generation_configs.api_template` → 按 `fields_json` 将参数写入对应 `node_id/input_name` → `ComfyUIClient.submit_prompt()` 得 `prompt_id` → 落库 `queued` → 立即返回。
2. FastAPI `BackgroundTasks` 启动后台轮询：每 2 秒 `ComfyUIClient.get_history(prompt_id)`，状态机 `queued → running → success/failed`。
3. 成功后：解析 history 输出图片列表 → `ComfyUIClient.get_image()` 下载 → 写入 `storage/outputs/{YYYY-MM}/{gen_id}/{filename}` → 更新 `outputs_json`、`status=success`。失败记录 `error`。
4. 前端每 2 秒轮询列表自动刷新。

### 3.3 图片存储路径

```
storage/outputs/{YYYY-MM}/{gen_id}/{filename}
```

例如 `storage/outputs/2026-08/{uuid4}/ComfyUI_00001_.png`。年月取自该生成 `created_at`（UTC，格式 `%Y-%m`）。读取与删除按同一规则定位目录；目录不存在时删除静默忽略（幂等）。

### 3.4 状态收编（reconcile）

`GET /generations` 时对仍处于 `queued/running` 且后台任务已丢失（进程重启）的记录做兜底查询，避免状态卡死。

## 4. ComfyUI 客户端新增方法

`backend/app/integrations/comfyui/client.py`（沿用现有 httpx 同步风格）：

| 方法 | 调用 | 返回 |
|---|---|---|
| `submit_prompt(prompt: dict)` | POST `/prompt` `{"prompt": ...}` | `prompt_id` (str) |
| `get_history(prompt_id: str)` | GET `/history/{id}` | dict |
| `get_image(filename, subfolder, type)` | GET `/view` | bytes |

## 5. 前端设计

新增 `frontend/src/features/generations/`：

| 文件 | 说明 |
|---|---|
| `GenerationsView.vue` | 列表页：标题 + 新建按钮 + 状态过滤下拉 + 错误横幅 + 表格（缩略图/提示词摘要/工作流名/状态/时间/操作） |
| `useGenerations.ts` | composable：items/loading/error/statusFilter + refresh()/create()/remove()；onMounted(refresh)，每 2 秒轮询 |
| `GenerationRow.vue` | 表格行，操作：查看详情 / 再生成 / 删除；成功且有缩略图时显示缩略图 |
| `GenerationCreateModal.vue` | 新建/再生成共用：顶部工作流下拉（已配置列表），下方按配置动态渲染参数表单（text 输入 + seed 输入 + 是否随机开关），提交新增一条 |
| `GenerationDetailModal.vue` | 查看详情：大图预览、参数展示、状态、失败原因 |
| `WorkflowGenerationConfigModal.vue` | 工作流页打开：粘贴 API 模板 + 动态字段编辑器（增删字段、node_id/input_name/type/label/默认值） |

### 5.1 导航与路由

- `Sidebar.vue` 增加 `{ to: "/generations", label: "生成", icon: "🖼" }`。
- `router.ts` 增加懒加载路由 `/generations`。
- `WorkflowsView.vue` 操作列增加「生成配置」按钮。

### 5.2 类型与 API 客户端

- `types/api.ts`：`GenerationSummary` / `GenerationDetail` / `GenerationStatus` / `GenerationConfig` / `GenerationField`。
- `services/api.ts`：`api.generations.{list,get,create,remove,imageUrl}`、`api.workflows.generationConfig.{get,save}`。

### 5.3 关键交互

- 再生成＝打开 `GenerationCreateModal` 预填上一条 `parameters_json`，可改提示词/随机开关/seed，提交生成新记录。
- 种子随机开关：开 → 隐藏 seed 输入框，提交时服务端生成随机 seed；关 → 显示输入框必填。
- 列表缩略图用 `GET /generations/{id}/images/{第一张}`。

## 6. 错误处理

- ComfyUI 提交失败（连接/校验错误）→ status=failed + error，前端展示。
- ComfyUI 执行中节点报错 → 从 history 捕获并记录 error。
- 未配置的工作流提交生成 → 409/400，提示先配置。
- 图片下载失败 → status=failed，error 记录文件名。
- 删除时图片目录不存在 → 静默忽略（幂等）。

## 7. 测试策略（后端 pytest）

- `test_generation_repository.py`：配置表 upsert/get/delete、generations CRUD。
- `test_generation_service.py`：参数填入模板、seed 随机生成、状态机转换、图片下载写盘（tmp_path + mock ComfyUI）。
- `test_generations_api.py`：TestClient 全流程——创建、列表、详情、删除、未配置 400、配置接口增删改查。
- ComfyUI 客户端新方法单独测试（mock httpx）。
- 前端无测试框架，仅 `npm run typecheck` 验证。

## 8. 验收标准

1. 工作流页可对某工作流配置生成参数（z-image：正面提示词 + seed + 随机开关）。
2. 生成页可新建生成：选工作流 → 填参数 → 提交 → 列表出现 queued → 自动刷新至 success 并显示缩略图。
3. 再生成：预填上一条参数，修改后提交，生成新记录。
4. 删除：记录与本地图片一并删除。
5. ComfyUI 不可达或参数非法时，有明确错误提示。
