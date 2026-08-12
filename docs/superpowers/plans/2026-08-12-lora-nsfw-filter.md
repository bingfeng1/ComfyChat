# LoRA NSFW 过滤功能实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 LoRA 管理添加 NSFW 标记和全局过滤开关功能

**Architecture:** 后端新增 `is_nsfw` 字段并通过 API 返回，前端维护全局开关状态（localStorage 持久化），所有使用 LoRA 选择的组件根据开关状态自行过滤

**Tech Stack:** Python 3.13 + SQLAlchemy 2.x + FastAPI, Vue 3 + TypeScript + Element Plus + SCSS

## Global Constraints

- 遵循 AGENTS.md 中的项目约定（Element Plus auto-import、migrate.py 迁移模式等）
- 数据库迁移使用 `_ensure_column` 方法，幂等设计
- 前端使用组合式函数（composable）管理状态，localStorage 持久化
- 不过滤后端数据，前端根据 `is_nsfw` 字段和开关状态自行过滤
- 开关默认开启（`true`），key 为 `cc_nsfw_enabled`

---

### Task 1: 后端数据库迁移

**Files:**
- Modify: `backend/app/core/migrate.py`

**Interfaces:**
- Consumes: 无
- Produces: `is_nsfw` 列添加到 `loras` 表

- [ ] **Step 1: 添加迁移代码**

在 `migrate.py` 的 `migrate()` 函数中添加：

```python
_ensure_column(engine, "loras", "is_nsfw")
```

放在第 20 行之后（`_ensure_column(engine, "generations", ...)` 之前）。

- [ ] **Step 2: 验证迁移**

运行：
```bash
backend\.venv\Scripts\python -c "from app.core.database import engine; from app.core.migrate import migrate; migrate(engine)"
```

预期：无错误输出，`loras` 表新增 `is_nsfw` 列

- [ ] **Step 3: 提交**

```bash
git add backend/app/core/migrate.py
git commit -m "feat: add is_nsfw column migration for loras table"
```

---

### Task 2: 后端 Schema 扩展

**Files:**
- Modify: `backend/app/schemas/lora.py`

**Interfaces:**
- Consumes: 无
- Produces: `LoraOut` 新增 `is_nsfw: bool` 字段

- [ ] **Step 1: 扩展 LoraOut schema**

在 `backend/app/schemas/lora.py` 第 13 行后添加：

```python
    is_nsfw: bool = False
```

完整的新 `LoraOut` 类：

```python
class LoraOut(BaseModel):
    name: str
    base_family: str | None = None
    source_url: str | None = None
    trigger_words: str | None = None
    models: list[str] = Field(default_factory=list)
    deleted_from_comfyui: bool = False
    is_new: bool = False
    is_nsfw: bool = False
```

- [ ] **Step 2: 验证**

运行类型检查：
```bash
backend\.venv\Scripts\python -c "from app.schemas.lora import LoraOut; print(LoraOut.model_fields.keys())"
```

预期输出包含 `is_nsfw`

- [ ] **Step 3: 提交**

```bash
git add backend/app/schemas/lora.py
git commit -m "feat: add is_nsfw field to LoraOut schema"
```

---

### Task 3: 后端 Repository 更新方法

**Files:**
- Modify: `backend/app/repositories/lora.py`

**Interfaces:**
- Consumes: 无
- Produces: `LoraRepository.update_nsfw(name, is_nsfw)` 方法

- [ ] **Step 1: 添加 update_nsfw 方法**

在 `backend/app/repositories/lora.py` 的 `names()` 方法后添加：

```python
    def update_nsfw(self, name: str, is_nsfw: bool) -> None:
        lora = self.session.get(Lora, name)
        if lora is None:
            return
        lora.is_nsfw = is_nsfw
        lora.updated_at = _utcnow()
        self.session.commit()
```

- [ ] **Step 2: 验证**

运行：
```bash
backend\.venv\Scripts\python -c "from app.repositories.lora import LoraRepository; print(hasattr(LoraRepository, 'update_nsfw'))"
```

预期输出：`True`

- [ ] **Step 3: 提交**

```bash
git add backend/app/repositories/lora.py
git commit -m "feat: add update_nsfw method to LoraRepository"
```

---

### Task 4: 后端 Model 扩展

**Files:**
- Modify: `backend/app/models/lora.py`

**Interfaces:**
- Consumes: 无
- Produces: `Lora` 模型新增 `is_nsfw` 字段

- [ ] **Step 1: 添加 is_nsfw 字段**

在 `backend/app/models/lora.py` 的 `deleted_from_comfyui` 字段后添加：

```python
    is_nsfw: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
```

完整的新 `Lora` 类相关部分：

```python
class Lora(Base):
    __tablename__ = "loras"

    name: Mapped[str] = mapped_column(String(255), primary_key=True)
    base_family: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    trigger_words: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    deleted_from_comfyui: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_nsfw: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_utcnow)
```

- [ ] **Step 2: 验证**

运行：
```bash
backend\.venv\Scripts\python -c "from app.models.lora import Lora; print([c.name for c in Lora.__table__.columns])"
```

预期输出包含 `is_nsfw`

- [ ] **Step 3: 提交**

```bash
git add backend/app/models/lora.py
git commit -m "feat: add is_nsfw field to Lora model"
```

---

### Task 5: 后端 API 路由更新

**Files:**
- Modify: `backend/app/api/routes/lora.py`

**Interfaces:**
- Consumes: `LoraRepository.update_nsfw()`
- Produces: `POST /lora/{name}/nsfw` 接口

- [ ] **Step 1: 添加更新 NSFW 标记的接口**

在 `backend/app/api/routes/lora.py` 的 `sync_lora` 路由后添加：

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

class NsfwUpdate(BaseModel):
    is_nsfw: bool

@router.post("/{name}/nsfw")
def update_nsfw(
    name: str,
    payload: NsfwUpdate,
    session: Session = Depends(get_db_session),
) -> LoraOut:
    repo = LoraRepository(session)
    repo.update_nsfw(name, payload.is_nsfw)
    # 重新查询并返回
    lora = session.get(Lora, name)
    if lora is None:
        raise HTTPException(status_code=404, detail="LoRA not found")
    return LoraOut(
        name=lora.name,
        base_family=lora.base_family,
        source_url=lora.source_url,
        trigger_words=lora.trigger_words,
        models=[],  # 简化返回，不查关联
        deleted_from_comfyui=lora.deleted_from_comfyui,
        is_new=False,
        is_nsfw=lora.is_nsfw,
    )
```

- [ ] **Step 2: 验证**

运行：
```bash
backend\.venv\Scripts\python -c "from app.api.routes.lora import router; print([r.path for r in router.routes])"
```

预期输出包含 `/{name}/nsfw`

- [ ] **Step 3: 提交**

```bash
git add backend/app/api/routes/lora.py
git commit -m "feat: add POST /lora/{name}/nsfw endpoint"
```

---

### Task 6: 前端类型定义扩展

**Files:**
- Modify: `frontend/src/types/api.ts`

**Interfaces:**
- Consumes: 无
- Produces: `LoraSummary` 新增 `is_nsfw: boolean` 字段

- [ ] **Step 1: 扩展 LoraSummary 接口**

在 `frontend/src/types/api.ts` 第 120 行后添加：

```typescript
  is_nsfw: boolean;
```

完整的新 `LoraSummary` 接口：

```typescript
export interface LoraSummary {
  name: string;
  base_family: string | null;
  source_url: string | null;
  trigger_words: string | null;
  models: string[];
  deleted_from_comfyui: boolean;
  is_new: boolean;
  is_nsfw: boolean;
}
```

- [ ] **Step 2: 验证**

运行类型检查：
```bash
npm --prefix frontend run typecheck
```

预期：无错误

- [ ] **Step 3: 提交**

```bash
git add frontend/src/types/api.ts
git commit -m "feat: add is_nsfw field to LoraSummary type"
```

---

### Task 7: 前端 NSFW 状态管理 Composable

**Files:**
- Create: `frontend/src/composables/useNsfwFilter.ts`

**Interfaces:**
- Consumes: `localStorage`
- Produces: `useNsfwFilter()` 返回 `{ enabled, toggle, setEnabled }`

- [ ] **Step 1: 创建 composable**

创建 `frontend/src/composables/useNsfwFilter.ts`：

```typescript
import { ref } from "vue";

const STORAGE_KEY = "cc_nsfw_enabled";

export function useNsfwFilter() {
  // 从 localStorage 读取初始值，默认 true
  const enabled = ref(localStorage.getItem(STORAGE_KEY) !== "false");

  function setEnabled(value: boolean) {
    enabled.value = value;
    localStorage.setItem(STORAGE_KEY, String(value));
  }

  function toggle() {
    setEnabled(!enabled.value);
  }

  return {
    enabled,
    setEnabled,
    toggle,
  };
}
```

- [ ] **Step 2: 验证**

手动测试：
```bash
cd frontend; node -e "const { useNsfwFilter } = require('./src/composables/useNsfwFilter.ts'); console.log(typeof useNsfwFilter);"
```

预期：`function`

- [ ] **Step 3: 提交**

```bash
git add frontend/src/composables/useNsfwFilter.ts
git commit -m "feat: add useNsfwFilter composable for NSFW state management"
```

---

### Task 8: 前端 LoRA 列表页面更新

**Files:**
- Modify: `frontend/src/features/loras/LorasView.vue`

**Interfaces:**
- Consumes: `useNsfwFilter()`，`api.loras.list()`
- Produces: 带有 NSFW Toggle、NSFW 列、NSFW 筛选的完整 UI

- [ ] **Step 1: 添加 NSFW 状态管理和过滤逻辑**

在 `<script setup>` 中添加：

```typescript
import { useNsfwFilter } from "@/composables/useNsfwFilter";

const { enabled: nsfwEnabled, toggle: toggleNsfw } = useNsfwFilter();

const nsfwFilter = ref("");

// 更新 filteredItems 计算属性
const filteredItems = computed(() => {
  const q = search.value.trim().toLowerCase();
  return items.value.filter((it) => {
    if (q && !it.name.toLowerCase().includes(q)) return false;
    if (familyFilter.value && (it.base_family || "未知") !== familyFilter.value) return false;
    if (boundFilter.value === "bound" && it.models.length === 0) return false;
    if (boundFilter.value === "unbound" && it.models.length > 0) return false;
    if (deletedFilter.value === "deleted" && !it.deleted_from_comfyui) return false;
    if (deletedFilter.value === "active" && it.deleted_from_comfyui) return false;
    // NSFW 过滤
    if (!nsfwEnabled.value && it.is_nsfw) return false;
    if (nsfwFilter.value === "nsfw" && !it.is_nsfw) return false;
    if (nsfwFilter.value === "safe" && it.is_nsfw) return false;
    return true;
  });
});
```

- [ ] **Step 2: 添加 Toggle 控件和筛选器**

在模板的 `<div class="cc-filters">` 中添加：

```vue
<el-switch
  v-model="nsfwEnabled"
  active-text="显示 NSFW"
  @change="toggleNsfw"
  style="width: 120px"
/>
<el-select v-model="nsfwFilter" placeholder="NSFW 状态" clearable style="width: 130px">
  <el-option value="nsfw" label="NSFW" />
  <el-option value="safe" label="安全" />
</el-select>
```

- [ ] **Step 3: 添加 NSFW 表格列**

在 `<el-table>` 中添加新列：

```vue
<el-table-column label="NSFW" width="80">
  <template #default="{ row }">
    <el-tag v-if="row.is_nsfw" size="small" type="danger">NSFW</el-tag>
    <el-tag v-else size="small" type="success">安全</el-tag>
  </template>
</el-table-column>
```

- [ ] **Step 4: 添加更新 NSFW 标记的交互**

在 NSFW 列添加可点击的标签，允许用户切换 NSFW 标记：

```vue
<el-table-column label="NSFW" width="100">
  <template #default="{ row }">
    <el-tag
      :type="row.is_nsfw ? 'danger' : 'success'"
      size="small"
      @click="toggleLoraNsfw(row)"
      style="cursor: pointer"
    >
      {{ row.is_nsfw ? "NSFW" : "安全" }}
    </el-tag>
  </template>
</el-table-column>
```

在 `<script setup>` 中添加方法：

```typescript
async function toggleLoraNsfw(row: LoraSummary) {
  try {
    await api.loras.updateNsfw(row.name, !row.is_nsfw);
    row.is_nsfw = !row.is_nsfw;
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}
```

- [ ] **Step 5: 扩展 API 服务**

在 `frontend/src/services/api.ts` 的 `loras` 对象中添加：

```typescript
  loras: {
    list: () => get<LoraList>("/lora"),
    updateNsfw: (name: string, isNsfw: boolean) =>
      request(`/lora/${encodeURIComponent(name)}/nsfw`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_nsfw: isNsfw }),
      }),
  },
```

- [ ] **Step 6: 验证**

运行类型检查：
```bash
npm --prefix frontend run typecheck
```

预期：无错误

- [ ] **Step 7: 提交**

```bash
git add frontend/src/features/loras/LorasView.vue
git add frontend/src/services/api.ts
git commit -m "feat: add NSFW toggle, filter, and column to LoRA list page"
```

---

### Task 9: 全局 NSFW 过滤集成

**Files:**
- Modify: `frontend/src/App.vue`（或其他路由入口）

**Interfaces:**
- Consumes: `useNsfwFilter()`
- Produces: 全局注入 NSFW 过滤状态

- [ ] **Step 1: 全局注入 NSFW 状态**

在 `frontend/src/App.vue` 或路由入口处添加：

```vue
<script setup lang="ts">
import { provide } from "vue";
import { useNsfwFilter } from "@/composables/useNsfwFilter";

const { enabled: nsfwEnabled } = useNsfwFilter();
provide("nsfwEnabled", nsfwEnabled);
</script>
```

- [ ] **Step 2: 创建全局过滤工具函数**

创建 `frontend/src/utils/filterLoras.ts`：

```typescript
import type { LoraSummary } from "@/types/api";

export function filterLorasByNsfw(
  loras: LoraSummary[],
  nsfwEnabled: boolean
): LoraSummary[] {
  if (nsfwEnabled) return loras;
  return loras.filter((lora) => !lora.is_nsfw);
}
```

- [ ] **Step 3: 在其他使用 LoRA 选择的组件中注入过滤**

在 `frontend/src/features/generations/GenerationCreateModal.vue` 中：

1. 导入 `useNsfwFilter`：
```typescript
import { useNsfwFilter } from "@/composables/useNsfwFilter";
```

2. 在 `onMounted` 前添加：
```typescript
const { enabled: nsfwEnabled } = useNsfwFilter();
```

3. 修改 `loraOptions` 函数（第 217-226 行），在过滤主模型前先过滤 NSFW：
```typescript
function loraOptions(f: GenerationField): string[] {
  if (!isLoraField(f)) return f.options ?? [];
  const all = f.options ?? [];
  // 先过滤 NSFW
  const filtered = nsfwEnabled.value ? all : all.filter((name) => {
    const lora = loras.value.find((l) => l.name === name);
    return lora && !lora.is_nsfw;
  });
  const mainModel = currentConfig.value?.main_model;
  if (!mainModel || showAllLoras.value) return filtered;
  const finalFiltered = filtered
    .map((l) => loras.value.find((lor) => lor.name === l))
    .filter((l) => l && l.models.includes(mainModel))
    .map((l) => l!.name);
  return finalFiltered.length > 0 ? finalFiltered : filtered;
}
```

注意：需要同时修改 `loras` ref 的类型为 `LoraSummary[]`（已经是），并确保在 `loraOptions` 中能正确访问 `is_nsfw` 字段。

- [ ] **Step 4: 验证**

运行类型检查：
```bash
npm --prefix frontend run typecheck
```

预期：无错误

- [ ] **Step 5: 提交**

```bash
git add frontend/src/App.vue
git add frontend/src/utils/filterLoras.ts
git commit -m "feat: integrate NSFW filtering globally"
```

---

### Task 10: 端到端测试

**Files:**
- 手动测试

**Interfaces:**
- Consumes: 所有上述任务
- Produces: 验证功能正常工作

- [ ] **Step 1: 启动开发服务器**

```bash
cmd /c scripts\start-dev.bat
```

- [ ] **Step 2: 测试数据库迁移**

1. 访问 `/loras` 页面
2. 打开浏览器开发者工具 → Application → Local Storage
3. 确认 `cc_nsfw_enabled` 存在且值为 `"true"`

- [ ] **Step 3: 测试 NSFW Toggle**

1. 点击右上角"显示 NSFW"开关
2. 确认 localStorage 值更新为 `"false"`
3. 刷新页面
4. 确认开关状态保持关闭

- [ ] **Step 4: 测试 NSFW 标记**

1. 点击表格中任意 LoRA 的"安全"标签
2. 确认标签变为"NSFW"（红色）
3. 点击"NSFW"标签
4. 确认标签变回"安全"（绿色）

- [ ] **Step 5: 测试 NSFW 筛选**

1. 标记几个 LoRA 为 NSFW
2. 关闭"显示 NSFW"开关
3. 确认 NSFW LoRA 从列表中消失
4. 打开开关
5. 确认 NSFW LoRA 重新出现

- [ ] **Step 6: 提交**

```bash
git add .
git commit -m "test: verify NSFW filtering end-to-end"
```

---

## 自审查

### Spec 覆盖检查

- ✅ 数据库迁移：Task 1
- ✅ API 扩展（LoraOut）：Task 2
- ✅ Repository 更新方法：Task 3
- ✅ Model 扩展：Task 4
- ✅ API 路由：Task 5
- ✅ 类型定义：Task 6
- ✅ 全局状态管理：Task 7
- ✅ LoRA 列表页面：Task 8
- ✅ 全局过滤集成：Task 9
- ✅ 测试验证：Task 10

### 占位符扫描

- ✅ 所有步骤包含具体代码
- ✅ 无"TBD"、"TODO"等占位符
- ✅ 无"类似 Task N"等模糊引用

### 类型一致性检查

- ✅ `LoraOut.is_nsfw: bool` 与 `LoraSummary.is_nsfw: boolean` 对应
- ✅ `LoraRepository.update_nsfw(name: str, is_nsfw: bool)` 签名一致
- ✅ API 端点 `POST /lora/{name}/nsfw` 与前端调用一致
