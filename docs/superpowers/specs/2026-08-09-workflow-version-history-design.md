# ComfyChat 工作流版本历史设计

日期：2026-08-09
状态：待用户复核
适用范围：ComfyChat 第三阶段（工作流版本历史：最新版 + 历史归档）

## 1. 目标与范围

在现有工作流页基础上，引入**版本历史**：列表只显示每个 ComfyUI 工作流的最新版本；当同步发现 ComfyUI 有新版时，旧版本自动归档为历史，用户可查看/手动删除历史版本。

明确**不**包含：
- 自动轮询同步（仍手动点"同步"）。
- 同步自动删除历史或残留（残留/历史均需手动删）。
- ComfyUI 写回（仍单向：ComfyUI → ComfyChat）。
- 双版本并存显示（列表只显示最新版）。
- import 来源的版本历史（仅 browse 来源有历史）。

## 2. 数据模型

```sql
workflows          -- 只存最新版（现有表不变）
  id, name, source, source_key, original_name,
  size_bytes, body, created_at, updated_at
  UNIQUE(source, source_key)

workflow_versions  -- 新增：历史版本
  id            TEXT PRIMARY KEY      -- uuid4 hex
  workflow_id   TEXT NOT NULL         -- FK → workflows.id，绑定当前最新行
  version       INTEGER NOT NULL      -- 递增版本号
  name          TEXT NOT NULL
  size_bytes    INTEGER NOT NULL
  body          TEXT NOT NULL         -- 历史版本完整 JSON
  captured_at   TEXT NOT NULL         -- 归档时间 ISO8601 UTC
```

- `workflows.id` 在更新时**不变**（id 稳定），只替换 body；旧 body 归档到 `workflow_versions`。
- `workflow_versions` 按 `(workflow_id, version)` 唯一；version 从 1 起，每次归档取当前最大 version + 1。
- 已有 SQLite 库无需迁移脚本（v1 用 `Base.metadata.create_all`，新表自动创建；`workflows` 表结构不变）。

## 3. 同步逻辑（`sync()`）

新增/更新的判定：**`source_key`（ComfyUI 文件名）即身份**——同名=同一工作流（变化即更新），异名=不同工作流（新增），改名=删+增。

```
对每个 ComfyUI 条目 (name, size, body):
  existing = repo.get_by_source_key("browse", name)
  if existing 不存在:
      → 新增：主表插新行（version 1，无历史）
  else:
      if existing.size_bytes != size:
          # 版本变更：旧最新版归档为历史，行更新为新版
          next_version = repo 当前 workflow_versions 该 workflow 的最大 version + 1
          插入 workflow_versions(workflow_id=existing.id, version=next_version, body=existing.body, name=existing.name, size_bytes=existing.size_bytes)
          更新 existing.body / size_bytes / updated_at = 新版
      else:
          → skipped
```

同步响应：

```json
{
  "synced_at": "...",
  "browse": { "added": 0, "updated": 2, "skipped": 3, "error": null,
              "updates": ["foo.json", "bar.json"] }
}
```

`updates` 数组 = 本次发生版本更新的工作流文件名（不塞 body，按需拉取）。

## 4. 后端 API 新增

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/workflows` | 不变：只返回最新版（含 `has_history` 布尔字段，见下） |
| `GET` | `/api/workflows/{id}/versions` | 历史版本列表（version, size_bytes, captured_at，不含 body）|
| `GET` | `/api/workflows/{id}/versions/{version}` | 某历史版本 body（查看）|
| `DELETE` | `/api/workflows/{id}/versions/{version}` | 手动删除某历史版本（204/404）|

- `WorkflowSummary` 新增 `has_history: bool`（该 browse 行是否有历史版本），前端据此显示"历史工作流"按钮。
- import 来源：`has_history` 恒为 false（无版本历史）。

## 5. 前端

- 列表：仍只显示最新版。
- **browse 来源且 `has_history=true` 的行**：多一个"历史工作流"按钮（import 或无历史不显示）。
- 点击 → 打开历史面板（复用 `Modal`）：列出历史版本（版本号、大小、归档时间），每个可"查看"（只读 JSON）和"删除"。
- 删除历史 → 确认对话框 → `DELETE /versions/{version}` → 刷新面板。
- `useWorkflows.ts` 增加 `versions`/`viewVersion`/`deleteVersion` 相关逻辑与状态。

## 6. 测试策略

**后端（pytest）：**
- `WorkflowVersionRepository`（或扩展 `WorkflowRepository`）：归档插入、`(workflow_id, version)` 唯一、`list_versions`/`get_version`/`delete_version`。
- `WorkflowService.sync()`：
  - 首次同步 → added，无历史。
  - 同 size → skipped。
  - size 变化 → 旧版入历史（version 递增）、主表换新版、`updates` 列出 name。
  - 改名 → 新名新增（v1 无历史）、旧名残留不动。
- API：`/versions` 列表/查看/删除（200/404）、列表含 `has_history`、import 无历史。
- 前端：typecheck（无前端测试框架）。

## 7. 约束

- 仅 browse 来源有历史；import 无。
- 历史版本绑定当前最新行（`workflow_id` FK）。
- 手动删除历史；同步不自动删。
- 单向同步不变；`source_key`=文件名即身份。
- 复用现有 `create_all`（无 alembic）。
