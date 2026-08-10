# LoRA 管理页搜索与筛选 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `/loras` 页面增加文件名关键字搜索、架构族下拉、绑定状态下拉三个筛选维度,前端即时过滤。依据 `docs/superpowers/specs/2026-08-10-lora-page-filter-design.md`。

**Architecture:** 单文件前端改动。`LorasView.vue` 新增 `search`/`familyFilter`/`boundFilter` 三个 ref;`familyOptions` 从 `items` 动态派生;`filteredItems` 用 computed 叠加三条件过滤;`el-table :data` 改用 `filteredItems`。无后端改动。

**Tech Stack:** Vue 3 + Vite + TypeScript + Element Plus 2.11+(仅前端)。

## Global Constraints

从 spec 与 AGENTS.md 拷贝的项目级规则,适用于本任务。

- **范围只动:**`frontend/src/features/loras/LorasView.vue`。其它文件(含后端全部、`types/api.ts`、`services/api.ts`)一律不动。
- **Element Plus 自动导入:**不写 `import { ElButton }` 等;图标(`Search`)从 `@element-plus/icons-vue` 显式导入。
- **SCSS 区块:**直接写即可,无需 `@use` 变量。
- **Workspace 约定:**Windows PowerShell;`frontend/.npmrc` 已配 npm 镜像;不要前台跑 `npm run dev`(用 `scripts/start-dev.ps1` / `stop-dev.ps1`)。
- **前端无测试框架:**验证靠 `npm --prefix frontend run typecheck` + `npm --prefix frontend run build` + 手动烟测。
- **PowerShell 不支持 `&&`:**链式命令用 `; if ($?) { … }` 或分多步。
- **不提交 secrets**。

---

## File Structure

| 文件 | 责任 | 操作 |
|---|---|---|
| `frontend/src/features/loras/LorasView.vue` | 搜索 + 架构族 + 绑定状态筛选 | 修改 |

---

## Task 1: LoRA 页搜索与筛选

**Files:**
- Modify: `frontend/src/features/loras/LorasView.vue`

**Interfaces:**
- Consumes: 现有 `api.loras.list()`(返回 `LoraSummary[]`,字段含 `name`、`base_family`、`models`)。
- Produces:无对外接口(页面内自洽)。

- [ ] **Step 1: 修改 `<script setup>` — 新增状态与计算属性**

`frontend/src/features/loras/LorasView.vue` 顶部:

- 第 2 行 `import { Refresh } from "@element-plus/icons-vue";` 改为:

```ts
import { Refresh, Search } from "@element-plus/icons-vue";
```

- 在 `const error = ref<string | null>(null);` 之后追加:

```ts
const search = ref("");
const familyFilter = ref("");
const boundFilter = ref("");
```

- 在 `fmtFamily` 函数之后追加:

```ts
const familyOptions = computed(() => {
  const set = new Set<string>();
  for (const it of items.value) set.add(it.base_family || "未知");
  return [...set].sort();
});

const filteredItems = computed(() => {
  const q = search.value.trim().toLowerCase();
  return items.value.filter((it) => {
    if (q && !it.name.toLowerCase().includes(q)) return false;
    if (familyFilter.value && (it.base_family || "未知") !== familyFilter.value) return false;
    if (boundFilter.value === "bound" && it.models.length === 0) return false;
    if (boundFilter.value === "unbound" && it.models.length > 0) return false;
    return true;
  });
});
```

- `import { onMounted, ref } from "vue";` 改为 `import { computed, onMounted, ref } from "vue";`

- [ ] **Step 2: 修改模板 — 加入筛选行**

在 `<el-alert v-if="error" ... />` 块之后、`<el-table` 之前插入:

```html
    <div class="cc-filters">
      <el-input
        v-model="search"
        placeholder="搜索名称…"
        :prefix-icon="Search"
        clearable
        style="width: 240px"
      />
      <el-select v-model="familyFilter" placeholder="全部架构族" clearable style="width: 160px">
        <el-option v-for="opt in familyOptions" :key="opt" :value="opt" :label="opt" />
      </el-select>
      <el-select v-model="boundFilter" placeholder="绑定状态" clearable style="width: 140px">
        <el-option value="bound" label="有绑定" />
        <el-option value="unbound" label="无绑定" />
      </el-select>
    </div>
```

- [ ] **Step 3: 修改模板 — 表格数据源**

`<el-table :data="items" ...>` 改为:

```html
    <el-table :data="filteredItems" v-loading="loading" stripe style="width: 100%">
```

- [ ] **Step 4: 修改样式 — 加 `.cc-filters`**

在 `<style lang="scss" scoped>` 内 `.cc-toolbar` 之后追加:

```scss
.cc-filters {
  display: flex;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
  align-items: center;
}
```

- [ ] **Step 5: 类型检查 + 构建**

```powershell
cd D:\learnAI\ComfyChat
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Expected: 两个都 PASS。

- [ ] **Step 6: 手动烟测**

启动 dev 服务:

```powershell
cd D:\learnAI\ComfyChat
powershell -ExecutionPolicy Bypass -File scripts\start-dev.ps1
```

浏览器打开 `http://127.0.0.1:5173/loras`,验证:

1. 搜索框输入 `mumu` → 只剩 `mumu_20.safetensors`。
2. 架构族下拉选 `SD1.5` → 只剩绑定了 SD1.5 主模型的 LoRA(如 `GuoFeng3.2_Lora`、`LCM_LoRA_SDv15` 等)。
3. 绑定状态下拉选 `无绑定` → 空列表显示「暂无 LoRA」(当前 20 个全绑定,预期无结果)。
4. 绑定状态下拉选 `有绑定` → 全部 20 个。
5. 搜索 + 架构族组合生效。
6. 各筛选 clearable 清空后恢复完整列表。

烟测完成后停止:

```powershell
cd D:\learnAI\ComfyChat
powershell -ExecutionPolicy Bypass -File scripts\stop-dev.ps1
```

- [ ] **Step 7: 提交**

```powershell
cd D:\learnAI\ComfyChat
git add frontend/src/features/loras/LorasView.vue; if ($?) { git commit -m "feat(frontend): search + filters on lora management page" }
```

---

## Self-Review Checklist

- [x] **Spec 覆盖:** 文件名搜索 → Step 1 `filteredItems` + Step 2 `el-input`;架构族下拉 → Step 1 `familyOptions` + Step 2 `el-select`;绑定状态 → Step 1 `boundFilter` + Step 2 两个 `el-option`;表格 `:data` 改 `filteredItems` → Step 3;`.cc-filters` 样式 → Step 4;空态复用现有 `el-empty` → Step 2 不改(已有 `#empty`)。
- [x] **Placeholder scan:** 无 TBD / TODO / "implement later"。
- [x] **类型一致性:** `search`/`familyFilter`/`boundFilter`/`familyOptions`/`filteredItems` 命名在 Step 1-3 一致;`boundFilter` 值 `"bound"`/`"unbound"` 与模板 `el-option :value` 一致;`familyOptions` 的「未知」占位与 `filteredItems` 的 `(it.base_family || "未知")` 一致。
- [x] **风险已记录:** 无(纯前端小改动,无后端/数据流风险)。
