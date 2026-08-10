# 工作流列表点击名称直接发起生成

**Date:** 2026-08-10
**Status:** Design — awaiting review
**Scope:** Frontend only. Reuses existing `GenerationCreateModal` and `WorkflowGenerationConfigModal`. No backend, data-flow, or schema changes.

## Goal

在工作流列表页,点击工作流名称即可直接进入生成流程——复用「生成」页已有的新建生成弹窗,不必先进入「生成」页再手动选择工作流。未配置生成参数的工作流,点击名称自动进入配置弹窗,保存后接着打开生成弹窗。

## Non-Goals

- 不改后端:新增任何 API、模型或路由。
- 不改「生成」页的既有打开/刷新逻辑(`GenerationsView` 保持不变)。
- 不做整行点击,仅名称可点击。
- 不改 `GenerationCreateModal` 的既有 step 流程和参数填充逻辑(仅新增"预选并跳步"入口)。
- 不做 `preset`(再生成)与 `preselectWorkflowId` 同时生效的场景——业务上二者互斥。

## User Flow

1. 工作流列表页,点击某行名称。
2. `GET /workflows/{id}/generation-config` 探测该工作流是否已配置(404 → null)。
   - **已配置** → 打开 `GenerationCreateModal`,传 `preselectWorkflowId=<id>`。
   - **未配置** → 打开 `WorkflowGenerationConfigModal`(带该工作流);其 `saved` 事件后接着打开 `GenerationCreateModal`(带 `preselectWorkflowId=<id>`)。
3. 生成弹窗内:已预选该工作流并跳过「选择工作流」第一步——若有参数直达「填写参数」步,无参数直达确认步。
4. 提交成功后,弹窗关闭并跳转到 `/generations` 页查看执行进度(生成页重新挂载,自带最新列表)。

## Changes

### 1. `frontend/src/features/workflows/WorkflowsView.vue`

- 名称列把只读 `<span class="cc-name">` 改为可点击的 `el-button link type="primary"`,点击调用 `openGenerateFor(row)`。
- 新增状态:
  - `createFor = ref<WorkflowSummary | null>(null)` — 打开生成弹窗的当前工作流
  - `configChainsToGenerate = ref(false)` — 标记当前打开的配置弹窗是否由"点击名称"触发,保存后需接着打开生成弹窗
- 复用现有 `configOf` 承载配置弹窗(不新增第二个配置弹窗实例)。
- 新增函数:
  - `async openGenerateFor(row)`:探测配置 → 已配置则 `createFor = row`;未配置则 `configOf = row` 且 `configChainsToGenerate = true`。
  - `onConfigSaved()`:`doSearch()`;若 `configChainsToGenerate` 为 true → `createFor = configOf` 并重置该标志。
  - `onConfigClosed()`:`configOf = null` 且 `configChainsToGenerate = false`(取消时不留残留标志)。
  - `onGenerated()`:关闭弹窗后 `router.push("/generations")`。
- 模板改动:
  - 现有 `<WorkflowGenerationConfigModal>` 的 `@saved` 从 `doSearch` 改为 `onConfigSaved`,`@close` 改为 `onConfigClosed`。
  - 新增 `<GenerationCreateModal v-if="createFor" :preselect-workflow-id="createFor.id" @close="createFor = null" @generated="onGenerated" />`。
- 引入 `useRouter`。

### 2. `frontend/src/features/generations/GenerationCreateModal.vue`

- 新增 prop `preselectWorkflowId?: string`(默认 `undefined`,不破坏现有用法)。
- 新增 emit `generated`。
- `onMounted` 加载 configs 后:若 `preselectWorkflowId` 存在且在 configs 中找到对应项 → `selectWorkflow(该 id)` 并把 `step` 置为 `needsFields ? 2 : totalSteps`(跳过第一步)。
- 若 `preselectWorkflowId` 不存在于 configs(边界)→ 回退到现有行为(第一步、默认选中第一条)。
- `submit()` 成功后先 `emit("generated")` 再 `emit("close")`。
- 标题保持 `props.preset ? '再生成' : '新建生成'`;`preselectWorkflowId` 场景仍显示「新建生成」。

### 3. `frontend/src/features/generations/GenerationsView.vue`

- 无改动(`@close` 已触发刷新;`generated` 事件仅工作流页监听)。

## Edge Cases

- **取消配置弹窗**:`onConfigClosed` 清空 `configOf` 并重置 `configChainsToGenerate`,停留原页,不打开生成弹窗。
- **探测请求失败**(网络/非 404 错误):`openGenerateFor` 捕获异常,以 `el-message` 或 `alert` 提示,不打开任何弹窗。
- **`preselectWorkflowId` 在 configs 中不存在**:回退到第一步默认行为,用户自行选择。
- **保存配置后打开生成弹窗**:刚保存必有配置,无需二次探测。
- **直接点「配置」按钮而非名称**:`configChainsToGenerate` 保持 false,保存后仅刷新列表,不打开生成弹窗。

## Verification

命令(cwd = repo root):

1. `npm --prefix frontend run typecheck` — 必须通过
2. `npm --prefix frontend run build` — 必须成功
3. `backend\.venv\Scripts\python -m pytest backend/tests -v` — 后端未改动,应全绿(1 个已知 Windows fail 可接受)
4. 手动冒烟(`scripts\start-dev.ps1` 起服):
   - 已配置工作流:点名称 → 弹窗直达「填写参数」步,下拉已选中该工作流,提交后跳转「生成」页
   - 未配置工作流:点名称 → 打开配置弹窗 → 保存 → 自动打开生成弹窗(预选该工作流) → 提交后跳转「生成」页
   - 取消配置弹窗 → 停留工作流页
   - 「生成」页「新建生成」「再生成」入口不受影响(仍停第一步/预填参数)

## Open Questions

None at design time.
