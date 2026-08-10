# LoRA 管理页搜索与筛选

**Date:** 2026-08-10
**Status:** Design — awaiting review
**Scope:** Frontend only. Single file change (`frontend/src/features/loras/LorasView.vue`). No backend, data-flow, or schema changes.

## Goal

为 `/loras` 页面增加三个筛选维度,方便在 20 个 LoRA 中快速定位:文件名关键字搜索、架构族下拉、绑定状态下拉。全部前端过滤,即时生效。

## Non-Goals

- 不改后端(`GET /lora` 响应不变)。
- 不做分页(数据量小)。
- 不改 `WorkflowsView` / `GenerationsView` 的既有筛选模式(仅本页新增)。
- 不做「来源 URL」筛选(非用户需求)。

## Changes(`frontend/src/features/loras/LorasView.vue`)

### 状态
- 新增 `search = ref("")`(文件名关键字)。
- 新增 `familyFilter = ref("")`(架构族;空 = 全部)。
- 新增 `boundFilter = ref("")`(绑定状态:`"bound"` / `"unbound"`;空 = 全部)。
- `items` 保持完整列表不变。

### 计算属性
- `familyOptions`:从 `items` 动态取 `base_family` 去重、排序,空值标记为 `"未知"` 选项。
- `filteredItems`:`items.filter` 叠加三个条件:
  1. `search`: `row.name.toLowerCase().includes(search.toLowerCase())`。
  2. `familyFilter`:`(row.base_family || "未知") === familyFilter`。
  3. `boundFilter`:`"bound"` → `row.models.length > 0`;`"unbound"` → `row.models.length === 0`。

### 模板
- 工具栏「重新扫描」按钮前插入 `.cc-filters` 行,含:
  - `el-input`(搜索图标,placeholder `搜索名称…`,clearable,`v-model="search"`)。
  - `el-select v-model="familyFilter"`(options 来自 `familyOptions`,clearable,placeholder `全部架构族`)。
  - `el-select v-model="boundFilter"`(固定选项:有绑定 `bound` / 无绑定 `unbound`,clearable,placeholder `绑定状态`)。
- `el-table :data` 从 `items` 改为 `filteredItems`。
- `#empty` 文案保持「暂无 LoRA」(覆盖搜索无结果场景)。

### 样式
- 复用现有视图的 `.cc-filters` 模式(参照 `WorkflowsView.vue`:`display:flex; gap:0.75rem; margin-bottom:0.75rem; align-items:center`)。

## Edge Cases

- `base_family` 为空:架构族选项显示「未知」,选它过滤出未识别架构族的 LoRA。
- 搜索与下拉同时生效:AND 叠加。
- 搜索命中文件名中的子目录路径(如 `ip-adapter\ip-adapter-faceid_sd15_lora.safetensors`)。
- 筛选后无结果:`el-empty`「暂无 LoRA」。

## Verification

1. `npm --prefix frontend run typecheck` — 必须通过
2. `npm --prefix frontend run build` — 必须成功
3. 手动烟测(`start-dev.ps1` 起服):
   - 输入 `mumu` → 只剩 `mumu_20`。
   - 架构族选 `SD1.5` → 只剩绑定了 SD1.5 主模型的 LoRA。
   - 绑定状态选 `无绑定` → 只剩 models 为空的 LoRA(当前应为 0 个,因为已全绑定)。
   - 组合条件生效。
   - 清空各筛选恢复完整列表。

## Open Questions

None at design time.
