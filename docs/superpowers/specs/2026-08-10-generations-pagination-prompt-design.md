# 生成页分页 + 提示词多行展示

**日期：** 2026-08-10
**状态：** 设计 — 等待用户复核
**范围：** `GET /generations` 接口增加分页;`/generations` 页面增加分页器;提示词单元格改为可折叠多行。

## 目标

为 `/generations` 页面增加分页能力,避免生成记录增多后表格无止境变长;同时让提示词支持多行展示(默认折叠 3 行 + 展开按钮),充分利用已放大的缩略图(72×72)留下的视觉空间。

## 非目标

- 不改工作流页、配置页、其它页面的任何行为。
- 不引入游标分页、虚拟滚动、无限滚动(本期数据量不需要)。
- 不改轮询频率(保持 2 秒)。
- 不改图片存储路径、图片下载逻辑。
- 不改创建/删除接口。
- 不动 `WorkflowRepository`。

## 已确认的决策

| 决策项 | 选择 |
|---|---|
| 默认每页条数 | 15 |
| 分页器可选 sizes | 10 / 15 / 20 / 50 |
| 轮询范围 | 仅当前页 |
| 提示词展示 | 折叠 3 行 + 「展开全文」/「收起」按钮 |
| 提示词展开阈值 | 文本长度 > 60 字符才显示按钮 |
| 分页实现 | 后端 OFFSET/LIMIT + 前端 Element Plus `el-pagination` |

## 后端改动

### 1. 接口契约

`GET /generations?status={s}&page={n}&page_size={n}`

- `page`(int,默认 `1`,`ge=1`)
- `page_size`(int,默认 `15`,`ge=1`,`le=100`)
- `status`(沿用现有字符串过滤)

返回结构从 `{items: [...]}` 改为:

```json
{
  "items": [...],
  "total": 123,
  "page": 1,
  "page_size": 15
}
```

### 2. Schema (`backend/app/schemas/generation.py`)

`GenerationListOut` 三个新字段:

```python
class GenerationListOut(BaseModel):
    items: list[GenerationOut]
    total: int
    page: int
    page_size: int
```

### 3. 仓库 (`backend/app/repositories/generation.py`)

- `GenerationRepository.list(status, *, page=1, page_size=15)`:在现有 `select(Generation)` 查询基础上加 `OFFSET (page-1)*page_size LIMIT page_size`;排序保持 `created_at.desc()`。
- `GenerationRepository.count(status)`:新增方法,`select(func.count()).select_from(Generation)`,支持 status 过滤,无排序/分页。
- `list_pending()`、`get()`、`update_status()` 等其它方法不动。

### 4. 路由 (`backend/app/api/routes/generations.py`)

```python
from fastapi import Query

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

`reconcile()` 保持无条件调用 — 它独立扫 queued/running 状态,不受分页影响。

### 5. 后端测试 (`backend/tests/test_generation_repository.py`)

新增用例:

- `test_list_paginates_correctly`:插 20 行 → `list(page=1, page_size=15)` 返回前 15 行(按 created_at 倒序);`list(page=2, page_size=15)` 返回剩下 5 行。
- `test_count_ignores_pagination`:插 20 行 → `count()` 返回 20;不影响 page/page_size。
- `test_list_with_status_filter_paginates`:同时启用 status 过滤 + 分页,确认两者独立工作。
- `test_list_empty_page_returns_empty_list`:超出范围的 page(如 page=999)返回空列表,而不是抛错。

## 前端改动

### 1. 类型 (`frontend/src/types/api.ts`)

`GenerationList` 新增 `total`、`page`、`page_size` 三个数字字段。

```ts
export interface GenerationList {
  items: GenerationSummary[];
  total: number;
  page: number;
  page_size: number;
}
```

### 2. 接口客户端 (`frontend/src/services/api.ts`)

`api.generations.list` 接受 `page` 与 `page_size` 两个可选参数:

```ts
list: (params?: { status?: GenerationStatus; page?: number; page_size?: number }) => {
  const sp = new URLSearchParams();
  if (params?.status) sp.set("status", params.status);
  if (params?.page) sp.set("page", String(params.page));
  if (params?.page_size) sp.set("page_size", String(params.page_size));
  const qs = sp.toString() ? `?${sp.toString()}` : "";
  return get<GenerationList>(`/generations${qs}`);
},
```

### 3. 组合式函数 (`frontend/src/features/generations/useGenerations.ts`)

- 新增 ref:`page`(默认 1)、`pageSize`(默认 15)、`total`(默认 0)。
- `refresh()` 与 `poll()` 三个参数一起发给后端,返回后写入 `items` 与 `total`。
- 新增 `setPage(n)`、`setPageSize(n)`,各自调用 `refresh()`。
- 当 `statusFilter` 变化时,`page` 重置为 1 并 `refresh()`。
- `create()` 成功后:`page` 重置为 1 并 `refresh()`(新记录在第 1 页顶部)。
- `remove()` 成功后:不重置 page,只 `refresh()` 当前页。
- 轮询频率 2 秒不变;轮询范围仅当前页(用户确认)。

### 4. 视图 (`frontend/src/features/generations/GenerationsView.vue`)

#### 4.1 提示词单元格改造

- 新增 `expandedIds = ref<Set<string>>(new Set())`,跟踪展开的行 id。
- 新增 `togglePrompt(id)` 方法,在 set 中加/删。
- 模板替换 `<span class="cc-prompt">{{ promptText(row) || "—" }}</span>` 为:

```html
<template #default="{ row }">
  <div :class="['cc-prompt', { 'is-expanded': expandedIds.has(row.id) }]">
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
    {{ expandedIds.has(row.id) ? "收起" : "展开全文" }}
  </el-button>
</template>
```

#### 4.2 样式更新

替换原 `.cc-prompt` 样式:

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
```

- `white-space: pre-wrap` 保留用户输入的换行符。
- 折叠状态 `-webkit-line-clamp: 3` + `overflow: hidden` 实现 3 行截断。
- 展开状态解除截断,显示完整文本。
- 短文本(`<= 60` 字符)不渲染「展开全文」按钮。

#### 4.3 提示词列属性

```html
<el-table-column label="提示词" min-width="240" :show-overflow-tooltip="false">
```

加 `:show-overflow-tooltip="false"` 关闭 Element Plus 自带的省略号 tooltip(与我们的多行展示冲突)。

#### 4.4 分页器

`<el-table>` 之后追加:

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

样式:

```scss
.cc-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 1rem;
}
```

#### 4.5 视图其余部分

- 标题、过滤下拉、其它列、按钮、模态框等全部保持不变。
- `promptText` 函数保持现状(返回 `g.parameters["text"]`)。
- `refresh`、`create`、`remove` 的入口来自 `useGenerations`,签名不变。

## 错误处理

- 后端 `page` 或 `page_size` 越界由 `Query(ge=...)` 直接 422 拦截。
- 前端不存在的页(如 `page=999`)返回空列表,`el-empty` 自动渲染。
- 网络/接口失败仍走 `error` ref + `<el-alert type="error">`,无变化。
- 轮询失败仍静默(原 `catch {}` 行为)。
- 删除/创建失败抛出异常由前端弹 ElMessage(若已用),无新错误路径。

## 测试 / 验证

**后端:**

- `backend\.venv\Scripts\python -m pytest backend/tests -v`
- 期望:既有 111 个测试通过 + 新增 4 个分页测试通过(1 个已知 Windows 失败可接受)。

**前端:**

- `npm --prefix frontend run typecheck`
- `npm --prefix frontend run build`(可选,验证生产构建不报错)

**手动烟测:**

1. 启动 `scripts\start-dev.ps1`,打开 `http://127.0.0.1:5173/generations`。
2. 当生成记录 > 15 条时,表格下方出现分页器;切换页 / 切换 pageSize 工作正常。
3. 在第 2 页点击「+ 新建生成」,新建成功后自动跳回第 1 页,新记录显示在顶部。
4. 切换状态过滤后回到第 1 页;total 数与过滤结果一致。
5. 长提示词显示 3 行后省略,下方出现「展开全文」;点击展开,再点「收起」恢复。
6. 短提示词(< 60 字符)不出现「展开全文」按钮。
7. 2 秒轮询只刷当前页;停在第 2 页时第 1 页的新增不会跳出来(预期行为)。

## 风险

1. **轮询范围限定的影响:** 用户停在第 2 页时,如果后台生成新记录会落在第 1 页顶部,需要用户回到第 1 页才能看到。已在「已确认决策」中确认接受此行为。
2. **`-webkit-line-clamp` 浏览器兼容:** 现代 Chromium / Firefox / Safari 均支持;Element Plus 内部也用此方案。Windows Chrome / Edge 无问题。
3. **表格列高度变化:** 多行提示词会让单行高度从 ~80px 涨到 ~80-150px,这是用户主动要求的视觉调整。
4. **后端测试数据库:** 沿用现有 `tmp_path` 模式,新增测试用 `pytest` 标准 fixture。

## 范围之外(留给后续阶段)

- 按工作流名 / 提示词关键字过滤。
- 排序选项(目前固定按 `created_at.desc()`)。
- 导出 / 批量删除。
- 无限滚动 / 虚拟滚动。