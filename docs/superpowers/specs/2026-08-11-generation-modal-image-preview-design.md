# 生成弹窗:生成中实时预览 + 中止按钮

日期：2026-08-11
状态：待用户复核
适用范围：ComfyChat 第四阶段增补——「生成」/「再生成」/「工作流页点击生成」共用弹窗的 UX 升级

## 1. 目标与范围

`GenerationCreateModal.vue` 共享组件被三处调用：

| 调用方 | 文件:行 | 用途 |
|---|---|---|
| 生成页新建 | `GenerationsView.vue:182` | 新建生成 |
| 生成页再生成 | `GenerationsView.vue:183` | 预填上一条参数二次生成 |
| 工作流页点击生成 | `WorkflowsView.vue:256` | 点工作流名 → 预选并跳到生成步 |

本次改动让三处的体验一致：

- **不再自动关闭**：点「生成」成功后弹窗保持打开，右侧实时显示生成的图片与历史。
- **多次生成可见历史**：同一会话内所有成功的生成以缩略图形式保留在右栏，可点击切换大图。
- **生成中可中止**：新增「中止」按钮，仅在生成中显示，调用 ComfyUI 官方中断 API。

明确**不**包含：
- 缩略图下载/全屏查看（已有 `GenerationDetailModal`）。
- 生成进度百分比（ComfyUI 无标准进度协议）。
- 并发多个生成任务（弹窗内一次只跑一个 active task）。
- 后端新增 SSE/WebSocket 推送（沿用 2s 轮询）。

## 2. 布局

**弹窗宽度**：640px → 1200px（`Modal` 的 `width` prop 即可，无需改 `Modal.vue`）。

**Body 两栏布局**：

```
┌─────────────────── header (title) ────────────────────┐
├─────────────────────┬─────────────────────────────────┤
│                     │  主图区（flex:1）                │
│  步骤导航(1/2/3)     │  ┌───────────────────────────┐  │
│  Step body          │  │  空态 / loading / 图片      │  │
│  el-form            │  │  / 失败 / 已中止           │  │
│                     │  └───────────────────────────┘  │
│  (width:480px)      │  状态文字行（排队/生成中/...）  │
│                     │  历史缩略图条（80×80,倒序）     │
├─────────────────────┴─────────────────────────────────┤
│           footer: 上一步  取消  [中止]  生成/再次生成     │
└──────────────────────────────────────────────────────┘
```

- 左栏 `width: 480px; flex-shrink: 0;`，保留现有 `cc-step-header` / `cc-step-body`。
- 分隔线 `border-right: 1px solid #e2e8f0;`。
- 右栏 `flex: 1; min-width: 400px;`，垂直三块：主图区 / 状态文字行 / 缩略图条。
- Header 与 footer 横跨整个 1200px。
- SCSS tokens 沿用 `$cc-*`，按钮样式沿用 Element Plus（`--el-color-primary: #0ea5e9`）。

## 3. 前端状态机

`GenerationCreateModal.vue` 新增/修改的本地 state：

```ts
// 现有保留
const step = ref(1);
const submitting = ref(false);      // POST /generations 调用中
const submitError = ref<string | null>(null);
const values = ref<Record<string, string | number>>({});
const workflowId = ref("");

// 新增
const activeGenId = ref<string | null>(null);     // 最近一次点「生成」创建的任务 ID
const activeStatus = ref<GenerationStatus | null>(null);
const activeError = ref<string | null>(null);
const mainImageUrl = ref<string | null>(null);
const history = ref<Array<{ id: string; imageUrl: string }>>([]);
let pollTimer: number | undefined;
```

**生命周期**：

1. 进入 step 3 且未生成过：`activeGenId=null`，主图区显示空态占位。
2. 点「生成」：
   - 同步调 `POST /generations` 拿 `GenerationSummary`
   - `activeGenId = res.id`、`activeStatus="queued"`、主图区切 loading
   - 启动 `setInterval(2000)` 轮询 `GET /generations/{id}`
   - 命中 `status==="success"` 且 `outputs.length>0`：
     - `mainImageUrl = api.generations.imageUrl(id, outputs[0])`
     - 推入 `history`，停止轮询，按钮解锁
   - 命中 `status==="failed"` 且 `error==="用户中止"`：主图区显示「已中止」，停止轮询，按钮解锁
   - 命中 `status==="failed"`（其他）：主图区显示 `error` 字段，停止轮询，按钮解锁
3. 点「中止」：调 `POST /generations/{id}/cancel` → 后端调 ComfyUI 对应端点 + 写 `failed=用户中止` → 轮询自然收尾。
4. 点「上一步」改参数后再次提交：清旧 `pollTimer`、`activeGenId/activeStatus/mainImageUrl` 重置，发起新任务；`history` 保留。
5. `onUnmounted`：`clearInterval(pollTimer)`。**不**主动停后端 ComfyUI 任务（用户未点中止的任务继续在 ComfyUI 跑，前端不感知）。

**轮询细节**：
- 每 2s `GET /generations/{id}`
- 仅当 `status/activeError/outputs` 变化时更新本地
- 单次网络失败静默忽略，连续 3 次失败显示「轮询中断」+ 重试按钮

**按钮可见性互斥**：

| 状态 | 生成按钮 | 中止按钮 |
|---|---|---|
| `submitting=true` | 显示且 loading | 隐藏 |
| `activeGenId=null` | 显示「生成」 | 隐藏 |
| `activeStatus in {queued, running}` | 隐藏 | 显示且可点（loading=aborting） |
| `activeStatus in {success, failed}` | 显示「再次生成」 | 隐藏 |
| 失败（ComfyUI 不可达） | 显示「再次生成」 | 显示但禁用 |

## 4. 缩略图历史

- 仅成功记录入栈；失败 / 中止 / 进行中均不入栈
- 倒序排列，最新在左；横向滚动条
- 单个 `80×80`，`border-radius: 6px`，`object-fit: cover`
- 激活态：`2px solid var(--el-color-primary); box-shadow: 0 0 0 2px rgba(14,165,233,0.2);`
- 点击切换主图，**不影响** `activeGenId/activeStatus`（已完成的项）
- 空时不渲染该区域

## 5. 后端:ComfyUIClient 新方法

`backend/app/integrations/comfyui/client.py` 新增两个方法（沿用 `_request` 风格，httpx 同步，抛 `ComfyUIError`）：

```python
def interrupt(self) -> None:
    """POST /interrupt — 中止当前正在运行的 job（无 request body）。"""
    self._request("post", "/interrupt")

def delete_queued(self, prompt_id: str) -> None:
    """POST /queue body {"delete":[prompt_id]} — 从队列删除 pending job。"""
    self._request("post", "/queue", json={"delete": [prompt_id]})
```

依据：ComfyUI 官方 API（`/comfy-org/docs`）支持这两个端点。

## 6. 后端:GenerationService.cancel

`backend/app/services/generation.py` 新增 `cancel(generation_id)`：

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
            pass  # ComfyUI 已不可达时,只更新 DB 状态;前端靠轮询收尾
        return repo.mark_failed(generation_id, "用户中止")
```

`mark_failed` 已存在于 `GenerationRepository`（见 `_poll_once` 中用法），无需新增。

## 7. 后端:_poll_once 兜底修复

**问题**：`_poll_once` 当前在 `get_history` 返回空 dict 时会把 `queued` 升级为 `running` 然后继续轮询。用户中止 + ComfyUI 把 prompt 从 history 清掉（版本差异存在）的边缘场景下，轮询死循环。

**修复**：在 `_poll_once` 开头检查 `gen.status == "running"` 时 `get_history` 是否返回空：

```python
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
```

需要 `Generation.poll_miss_count` 列（迁移见 §10）做计数；找到 entry 时清零。

## 8. 后端:新增 cancel 路由

`backend/app/api/routes/generations.py` 新增（沿用 Vite 代理约定，**无 `/api` 前缀**）：

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

错误码：
- 404：generation 不存在
- 409：已 success/failed，再取消无意义
- 503：ComfyUI 不可达

## 9. 前端:api 客户端

`frontend/src/services/api.ts` 在 `generations` 块新增一行：

```ts
cancel: (id: string) => request<GenerationSummary>(`/generations/${id}/cancel`, { method: "POST" }),
```

## 10. 数据库迁移

`Generation` 表新增列 `poll_miss_count INTEGER NOT NULL DEFAULT 0`。

`backend/app/core/migrate.py` 扩展 `_ensure_column` 接受列类型 + 默认值（当前硬编码 `BOOLEAN NOT NULL DEFAULT 0`）：

```python
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

`migrate()` 函数新增一行：

```python
_ensure_column(engine, "generations", "poll_miss_count", col_type="INTEGER", default="0")
```

`backend/app/models/generation.py` 新增列：

```python
poll_miss_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
```

`backend/app/repositories/generation.py` 新增方法（沿用 `update_status` 模式）：

```python
def update_poll_miss_count(self, generation_id: str, count: int) -> None:
    gen = self.get(generation_id)
    if gen is None:
        return
    gen.poll_miss_count = count
    gen.updated_at = _utcnow()
    self.session.commit()
```

## 11. 错误处理

| 场景 | 前端 | 后端 |
|---|---|---|
| ComfyUI 不可达（提交） | `submitError` 红框 + el-alert | 503 |
| ComfyUI 不可达（中止） | `abortError` 红框 + 轮询继续 | 503，DB 不写 |
| `cancel` 时已 success/failed | 不应触发（按钮已隐藏） | 409 |
| `cancel` 时 generation 不存在 | 不应触发（modal 持有 id） | 404 |
| `get_history` 中途网络失败 | 单次忽略；连续 3 次断连提示「轮询中断」 | 抛 `ComfyUIError` → `_poll_once` 返回 False 继续 |
| 缩略图加载失败 | `<img onerror>` 替换为灰色占位 + 「图片加载失败」 | — |

## 12. 测试策略

**后端 pytest**（沿用 `backend/tests/`，目标 145+ 测试全过）：

- `test_comfyui_client.py`：mock httpx，验证 `interrupt()` POST `/interrupt`（无 body）、`delete_queued(id)` POST `/queue` with `{"delete":[id]}`。
- `test_generation_service.py` 新增 4 用例：
  - `queued` 取消 → `comfyui.delete_queued(prompt_id)` 被调 + `mark_failed("用户中止")`
  - `running` 取消 → `comfyui.interrupt()` 被调 + `mark_failed("用户中止")`
  - success/failed 再取消 → `ValueError("already terminal")`
  - ComfyUI 不可达 → 异常被吞，`mark_failed` 仍执行
- `test_generations_api.py` 新增：200（queued + running）/ 404 / 409
- `_poll_once` 兜底测试：连续 2 次 get_history 空 → mark_failed；中途恢复 → 计数清零

**前端**（无测试框架）：
- `npm --prefix frontend run typecheck` 必须通过
- 手动 smoke（见 §13）

## 13. 验收标准

手动 smoke（dev 环境，分支合并前必做）：

- [ ] 启动 dev（`scripts\start-dev.bat`），ComfyUI 在线
- [ ] `/generations` 新建生成 → 第 3 步点「生成」 → 弹窗**不关闭**，右侧出现 loading → 数秒后图片显示在右栏
- [ ] 同一会话再点「再次生成」 → 主图区切 loading，旧图保留在缩略图，新图替换主图
- [ ] 生成中点「中止」 → 1-2 秒内主图区变「已中止」，缩略图不增加
- [ ] 中止后点「再次生成」 → 按钮可点，新一轮开始
- [ ] step 1/2 上一步在生成中**可点** → 返回改参数后点「再次生成」正常工作
- [ ] 关闭弹窗后再打开 → 主图区重置回空态（本地态，不持久化 history）
- [ ] 从 `/workflows` 点击工作流名进入的同一弹窗：行为一致；成功后 `generated` 事件触发跳 `/generations`
- [ ] ComfyUI 离线时：点「生成」/「中止」→ el-alert 红色错误
- [ ] 失败（error 非「用户中止」）：主图区显示红色错误框，缩略图不入栈

硬标准：

- 弹窗宽度 1200px，左右栏清晰可见
- 点「生成」后弹窗**不关闭**
- 中止按钮仅在生成中可见
- 历史缩略图只含成功记录
- 缩略图点击可切换主图
- 上一步/取消在生成中**仍可点**
- 三处调用方行为一致

## 14. 文件改动清单

| 文件 | 改动 |
|---|---|
| `frontend/src/features/generations/GenerationCreateModal.vue` | 改：width、两栏布局、状态机、中止按钮、轮询 |
| `frontend/src/services/api.ts` | 改：`generations.cancel` 一行 |
| `backend/app/integrations/comfyui/client.py` | 改：新增 `interrupt()` / `delete_queued()` |
| `backend/app/services/generation.py` | 改：新增 `cancel()` + `_poll_once` 兜底 |
| `backend/app/api/routes/generations.py` | 改：新增 `POST /generations/{id}/cancel` |
| `backend/app/repositories/generation.py` | 改：新增 `update_poll_miss_count` |
| `backend/app/models/generation.py` | 改：新增 `poll_miss_count` 列 |
| `backend/app/core/migrate.py` | 改：`_ensure_column("generations", "poll_miss_count", ...)` |
| `backend/tests/test_comfyui_client.py` | 改：新增 interrupt/delete_queued 用例 |
| `backend/tests/test_generation_service.py` | 改：新增 cancel 4 用例 + 兜底测试 |
| `backend/tests/test_generations_api.py` | 改：新增 cancel API 用例 |

不动的文件（明确范围外）：

- `frontend/src/components/Modal.vue`
- `frontend/src/types/api.ts`（已有 `GenerationStatus`，无需扩展）
- `frontend/src/features/generations/GenerationDetailModal.vue`
- `frontend/src/features/generations/useGenerations.ts`
- `frontend/src/features/generations/GenerationsView.vue` / `WorkflowsView.vue`（仅消费 emit，组件内部升级后自动受益）
