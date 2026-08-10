# 工作流列表点击名称直接发起生成 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在工作流列表页点击工作流名称,直接进入生成流程——复用 `GenerationCreateModal`(预选该工作流并跳过第一步);未配置的工作流自动先打开配置弹窗,保存后接着打开生成弹窗;生成成功后跳转 `/generations` 页。依据 `docs/superpowers/specs/2026-08-10-workflow-click-to-generate-design.md`。

**Architecture:** 前端两个文件。`GenerationCreateModal` 新增可选 prop `preselectWorkflowId?: string` 与 emit `generated`:加载 configs 后若预选 id 存在则选中并跳到参数步,提交成功后先发 `generated` 再 `close`。`WorkflowsView` 把名称列改为可点击按钮,点击时用 `api.workflows.generationConfig.get(id)` 探测配置(404→null):已配置直接开生成弹窗,未配置开配置弹窗并标记 `configChainsToGenerate`,保存后转开生成弹窗;`generated` 时 `router.push("/generations")`。

**Tech Stack:** Vue 3 + Vite + TypeScript + Element Plus 2.11+(仅前端,后端零改动)。

## Global Constraints

从 spec 与 AGENTS.md 拷贝的项目级规则,适用于所有任务,除非任务中明确覆盖。

- **范围只动两个文件:**`frontend/src/features/generations/GenerationCreateModal.vue`、`frontend/src/features/workflows/WorkflowsView.vue`。其它文件(含后端全部、`GenerationsView.vue`、`useWorkflows.ts`、`useGenerations.ts`、`types/api.ts`、`services/api.ts`)一律不动。
- **Element Plus 自动导入:**不写 `import { ElButton }` 等;`@element-plus/icons-vue` 本期不新增图标。
- **SCSS 区块:**直接写即可,无需 `@use` 变量(本期不引新 token)。
- **Workspace 约定:**Windows PowerShell;`frontend/.npmrc` 已配 npm 镜像;不要全局 `npm config set`;不要前台跑 `uvicorn` / `npm run dev`(用 `scripts/start-dev.ps1` / `stop-dev.ps1`)。
- **前端无测试框架:**验证靠 `npm --prefix frontend run typecheck` + `npm --prefix frontend run build` + 手动烟测。不要新增 vitest 等。
- **PowerShell 不支持 `&&`:**链式命令用 `; if ($?) { … }` 或分多步。
- **行尾换行:**提交时如有 CRLF/LF 警告可忽略。
- **不提交 secrets:**不引入任何密钥或 `.env` 内容。

---

## File Structure

| 文件 | 责任 | 是否动 |
|---|---|---|
| `frontend/src/features/generations/GenerationCreateModal.vue` | 新增 `preselectWorkflowId` prop + `generated` emit + 预选跳步 + 提交后发 `generated` | 改 |
| `frontend/src/features/workflows/WorkflowsView.vue` | 名称可点击、探测配置分流、配置后接生成、生成成功跳转 | 改 |

---

## Task 1: `GenerationCreateModal` 支持预选工作流 + 跳步 + `generated` 事件

**Files:**
- Modify: `frontend/src/features/generations/GenerationCreateModal.vue`

**Interfaces:**
- Consumes: 现有 `api.workflows.generationConfigs()`(返回 `GenerationConfigSummary[]`)、现有 `props.preset?: GenerationSummary | null`。
- Produces:
  - 新 prop `preselectWorkflowId?: string`(可选,不提供时行为与现在完全一致)。
  - 新 emit `generated`(提交成功后、`close` 之前发出)。
  - 提供 `preselectWorkflowId` 且存在于 configs 时:选中该工作流并 `step = needsFields ? 2 : totalSteps`;不存在时回退到现有默认行为(第一步、默认第一条)。

- [ ] **Step 1: 扩展 props / emits 声明**

定位 `frontend/src/features/generations/GenerationCreateModal.vue` 第 7-8 行:

```ts
const props = defineProps<{ preset?: GenerationSummary | null }>();
const emit = defineEmits<{ close: [] }>();
```

替换为:

```ts
const props = defineProps<{
  preset?: GenerationSummary | null;
  preselectWorkflowId?: string;
}>();
const emit = defineEmits<{ close: []; generated: [] }>();
```

- [ ] **Step 2: 修改 `onMounted` 实现预选 + 跳步**

定位 `onMounted` 块(当前第 146-158 行):

```ts
onMounted(async () => {
  try {
    configs.value = (await api.workflows.generationConfigs()).items;
    if (configs.value.length > 0) {
      const presetId = props.preset?.workflow_id ?? configs.value[0].workflow_id;
      selectWorkflow(presetId);
    }
  } catch (err) {
    fetchError.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
});
```

替换为:

```ts
onMounted(async () => {
  try {
    configs.value = (await api.workflows.generationConfigs()).items;
    if (configs.value.length > 0) {
      if (
        props.preselectWorkflowId &&
        configs.value.some((c) => c.workflow_id === props.preselectWorkflowId)
      ) {
        selectWorkflow(props.preselectWorkflowId);
        step.value = needsFields.value ? 2 : totalSteps.value;
      } else {
        const presetId = props.preset?.workflow_id ?? configs.value[0].workflow_id;
        selectWorkflow(presetId);
      }
    }
  } catch (err) {
    fetchError.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
});
```

注:`selectWorkflow` 里 `props.preset` 分支只在 `preset.workflow_id === id` 时生效;预选场景不传 `preset`,走默认值填充分支,行为正确。

- [ ] **Step 3: `submit()` 成功后先发 `generated` 再 `close`**

定位 `submit()` 中的成功分支(当前第 227-228 行):

```ts
    await api.generations.create({ workflow_id: workflowId.value, parameters });
    emit("close");
```

替换为:

```ts
    await api.generations.create({ workflow_id: workflowId.value, parameters });
    emit("generated");
    emit("close");
```

- [ ] **Step 4: 类型检查**

```powershell
cd D:\learnAI\ComfyChat
npm --prefix frontend run typecheck
```

Expected: PASS(此时 `WorkflowsView.vue` 还没引用新 prop/emit,不应有错误)。

- [ ] **Step 5: 提交**

```powershell
cd D:\learnAI\ComfyChat
git add frontend/src/features/generations/GenerationCreateModal.vue; if ($?) { git commit -m "feat(frontend): GenerationCreateModal preselect workflow + skip step + generated event" }
```

---

## Task 2: `WorkflowsView` 名称可点击 + 配置后接生成 + 跳转生成页

**Files:**
- Modify: `frontend/src/features/workflows/WorkflowsView.vue`

**Interfaces:**
- Consumes: Task 1 产出的 `GenerationCreateModal` 新 prop `preselectWorkflowId` 与 emit `generated`;现有 `api.workflows.generationConfig.get(id)`(404→null);现有 `configOf`、`doSearch()`、`useWorkflows()` 返回项。
- Produces:
  - `openGenerateFor(row: WorkflowSummary)` — 探测配置并分流开弹窗。
  - `onConfigSaved()` — `doSearch()`;若 `configChainsToGenerate` 为 true 则转开生成弹窗并重置标志。
  - `onConfigClosed()` — `configOf = null` 且 `configChainsToGenerate = false`。
  - `onGenerated()` — 清空 `createFor` 后 `router.push("/generations")`。
  - 名称列从 `<span>` 改为 `el-button link`(点击调 `openGenerateFor(row)`)。

- [ ] **Step 1: 新增 import**

在 `frontend/src/features/workflows/WorkflowsView.vue` `<script setup lang="ts">` 顶部(现有第 1-11 行),`import type { WorkflowSummary }` 之后新增:

```ts
import { useRouter } from "vue-router";
import { api } from "@/services/api";
import GenerationCreateModal from "@/features/generations/GenerationCreateModal.vue";
```

- [ ] **Step 2: 新增状态与函数**

定位 `<script setup>` 中的状态声明区(当前第 30-34 行):

```ts
const detail = ref<WorkflowSummary | null>(null);
const historyOf = ref<WorkflowSummary | null>(null);
const configOf = ref<WorkflowSummary | null>(null);
const confirmDelete = ref<WorkflowSummary | null>(null);
const pendingFile = ref<File | null>(null);
```

在 `const pendingFile` 行后追加:

```ts
const router = useRouter();
const createFor = ref<WorkflowSummary | null>(null);
const configChainsToGenerate = ref(false);
```

在 `onExport` 函数之后(当前 `onExport` 结束于第 88 行 `}`),追加:

```ts
async function openGenerateFor(row: WorkflowSummary) {
  try {
    const cfg = await api.workflows.generationConfig.get(row.id);
    if (cfg) {
      createFor.value = row;
    } else {
      configOf.value = row;
      configChainsToGenerate.value = true;
    }
  } catch (err) {
    alert(err instanceof Error ? err.message : String(err));
  }
}

function onConfigSaved() {
  doSearch();
  if (configChainsToGenerate.value) {
    createFor.value = configOf.value;
    configChainsToGenerate.value = false;
  }
}

function onConfigClosed() {
  configOf.value = null;
  configChainsToGenerate.value = false;
}

function onGenerated() {
  createFor.value = null;
  router.push("/generations");
}
```

注:`WorkflowGenerationConfigModal` 保存时先 `emit("saved")` 再 `emit("close")`,因此 `onConfigSaved` 设置 `createFor` 后 `onConfigClosed` 随即清空 `configOf` 并重置标志,顺序正确。

- [ ] **Step 3: 名称列改为可点击**

定位模板名称列(当前第 151-155 行):

```html
      <el-table-column label="名称" min-width="240">
        <template #default="{ row }">
          <span class="cc-name">{{ row.name }}.json</span>
        </template>
      </el-table-column>
```

替换为:

```html
      <el-table-column label="名称" min-width="240">
        <template #default="{ row }">
          <el-button link type="primary" class="cc-name" @click="openGenerateFor(row)">
            {{ row.name }}.json
          </el-button>
        </template>
      </el-table-column>
```

- [ ] **Step 4: 配置弹窗事件改为新处理器**

定位配置弹窗(当前第 208-214 行):

```html
    <WorkflowGenerationConfigModal
      v-if="configOf"
      :workflow-id="configOf.id"
      :title="configOf.name"
      @close="configOf = null"
      @saved="doSearch"
    />
```

替换为:

```html
    <WorkflowGenerationConfigModal
      v-if="configOf"
      :workflow-id="configOf.id"
      :title="configOf.name"
      @close="onConfigClosed"
      @saved="onConfigSaved"
    />
```

- [ ] **Step 5: 新增生成弹窗**

定位删除确认 `<Modal v-if="confirmDelete" ...>` 之前(当前第 216 行),插入:

```html
    <GenerationCreateModal
      v-if="createFor"
      :preselect-workflow-id="createFor.id"
      @close="createFor = null"
      @generated="onGenerated"
    />
```

- [ ] **Step 6: 类型检查 + 构建**

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

浏览器打开 `http://127.0.0.1:5173/workflows`,验证:

1. 已配置生成参数的工作流:点名称 → 打开生成弹窗,直达「填写参数」步(无参数则直达确认步),工作流下拉已选中该工作流;点「生成」提交成功后自动跳转到 `/generations` 页,列表顶部出现新记录。
2. 未配置生成参数的工作流:点名称 → 打开「生成配置」弹窗;勾选若干参数并「保存」→ 自动接着打开生成弹窗(已预选该工作流、直达参数步)。
3. 未配置工作流:点名称 → 配置弹窗里点「取消」→ 停留工作流页,不打开生成弹窗。
4. 直接点「操作」列的「配置」按钮 → 保存后只刷新列表,**不**打开生成弹窗(与点击名称行为区分)。
5. 「生成」页「+ 新建生成」与「再生成」入口行为不受影响:新建仍停第一步,再生成仍预填参数。
6. 现有名称列样式看起来仍是可点击链接(带主题色)。

烟测完成后停止:

```powershell
cd D:\learnAI\ComfyChat
powershell -ExecutionPolicy Bypass -File scripts\stop-dev.ps1
```

- [ ] **Step 8: 提交**

```powershell
cd D:\learnAI\ComfyChat
git add frontend/src/features/workflows/WorkflowsView.vue; if ($?) { git commit -m "feat(frontend): workflow name click opens generation flow" }
```

---

## Task 3: 最终验证

**Files:**(只读,验证用)

- `frontend/`
- `backend/`(只跑既有测试确认无回归)

- [ ] **Step 1: 前端类型检查 + 构建**

```powershell
cd D:\learnAI\ComfyChat
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Expected: 两个都 PASS。

- [ ] **Step 2: 后端全量测试(确认零改动无回归)**

```powershell
cd D:\learnAI\ComfyChat
backend\.venv\Scripts\python -m pytest backend/tests -v
```

Expected: 原有测试通过(1 个已知 Windows 失败 `test_check_database_returns_false_when_path_unwritable` 跳过/失败可接受)。

- [ ] **Step 3: 检查 git 状态,确认改动范围**

```powershell
cd D:\learnAI\ComfyChat
git status
git diff --stat HEAD~2..HEAD
```

Expected: 总共 2 个文件被改动(`GenerationCreateModal.vue`、`WorkflowsView.vue`),均在本计划 `File Structure` 表中。无意外文件进入。

- [ ] **Step 4: 推送(可选,用户决定)**

```powershell
cd D:\learnAI\ComfyChat
git push origin main
```

只有当用户明确要求时才执行。

---

## Self-Review Checklist

- [x] **Spec 覆盖:**
  - 名称列点击 → Task 2 Step 3
  - 探测配置(404→null)→ Task 2 Step 2 `openGenerateFor`
  - 已配置直接开生成弹窗 → Task 2 Step 2
  - 未配置开配置弹窗 + 保存后接生成 → Task 2 Step 2 `onConfigSaved` + `configChainsToGenerate`
  - `preselectWorkflowId` prop → Task 1 Step 1
  - `generated` emit(提交成功先发)→ Task 1 Step 3
  - 预选并跳步(`needsFields ? 2 : totalSteps`)→ Task 1 Step 2
  - 预选 id 不在 configs 时回退 → Task 1 Step 2(else 分支)
  - 取消配置弹窗不接生成 → Task 2 Step 2 `onConfigClosed` 重置标志
  - 直接点「配置」按钮不接生成 → `configChainsToGenerate` 默认 false
  - 生成成功跳 `/generations` → Task 2 Step 2 `onGenerated`
  - `GenerationsView` 零改动 → Global Constraints
- [x] **Placeholder scan:** 无 TBD / TODO / "implement later" / "Similar to Task N"。
- [x] **类型一致性:** `preselectWorkflowId`、`createFor`、`configChainsToGenerate`、`onConfigSaved`、`onConfigClosed`、`onGenerated`、`openGenerateFor` 命名在 Task 1/2 间一致;props/emits 签名与现有 `defineProps` / `defineEmits` 风格一致。
- [x] **风险已记录:** config 弹窗先 `saved` 后 `close` 的触发顺序在 Task 2 Step 2 注释中说明;探测异常用 `alert` 兜底(spec 允许 `el-message` 或 `alert`)。
