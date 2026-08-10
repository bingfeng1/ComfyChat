# 工作流生成字段自动发现 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把生成配置从「手填 API 模板 JSON + node_id/input_name」改成「自动发现 + 中文勾选清单」,生成页按勾选字段动态渲染表单。

**Architecture:** 后端新增三个纯函数(`workflow_to_api_template` / `infer_field_type` / `discover_fields`)从 `Workflow.body`(UI 格式)解析出 API 格式模板和候选字段;新增 discover 接口返回候选;前端配置弹窗改为勾选清单,生成弹窗补 `number` 类型渲染。`api_template` 数据模型保留但不再由用户手填。

**Tech Stack:** FastAPI + SQLAlchemy(SQLite)、Vue 3.5 + Element Plus + SCSS、pytest(后端)、`vue-tsc` + `vite build`(前端)。

## 全局约束

[来源 spec: `docs/superpowers/specs/2026-08-10-workflow-field-discovery-design.md`]

- 字段类型 `type` 模式: `^(text|seed|number)$`(原来是 `^(text|seed)$`)。`text`→textarea,`seed`→input-number+随机框,`number`→input-number 无随机框。
- `Workflow.body` 是 **UI 格式**(`{"nodes":[{id,type,inputs,widgets_values,...}]}`),不是 API 格式。提交 ComfyUI `/prompt` 需要 API 格式 `{"<node_id>": {"class_type","inputs"}}`。
- 可填项 = `node.inputs[]` 里带 `"widget"` 的条目;带 `"link"` 的是连接关系,跳过。
- 中文标签优先用 `node.inputs[].localized_name`,兜底 `[node_type] name`。
- `key` 默认 = widget `name`;重复时路由层加后缀(`text`、`text_1`、…)。
- `api_template` 保留在数据模型里作为填充基底,但不再展示给用户。`apply_parameters` 加 `number` 分支。
- 现有保存路径 `PUT /workflows/{id}/generation-config` 不改。
- 后端测试:`backend\.venv\Scripts\python -m pytest backend/tests -v`,基线 90 pass + 1 已知 Windows fail。
- 前端验证:`npm --prefix frontend run typecheck` + `npm --prefix frontend run build`。
- 工作目录: 仓库根。不得在前台跑 `uvicorn` / `npm run dev`。dev 服务用 `scripts\start-dev.ps1` / `stop-dev.ps1` 管理,冒烟完即停。
- Python 3.13 venv:`backend\.venv\Scripts\python`。pip 镜像: 清华。

---

### Task 1: 后端纯函数 — UI→API 转换 + 字段发现

**Files:**
- Modify: `backend/app/services/generation.py`(新增 3 个模块级纯函数,放在 `apply_parameters` 之前)
- Test: `backend/tests/test_generation_service.py`(追加测试)

**Interfaces:**
- Consumes: 无(纯函数,只依赖 JSON 结构)。
- Produces:
  - `workflow_to_api_template(body_json: dict) -> dict` — 返回 API 格式 dict。
  - `infer_field_type(widget_name: str, value) -> str` — 返回 `"seed"` | `"number"` | `"text"`。
  - `discover_fields(body_json: dict) -> list[dict]` — 返回候选字段 dict 列表(每个 dict 与 `GenerationField` 字段同构:`key/label/type/node_id/input_name/default/required`)。

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_generation_service.py` 顶部 import 区追加:

```python
from app.services.generation import (
    GenerationService,
    apply_parameters,
    discover_fields,
    infer_field_type,
    workflow_to_api_template,
)
```

在文件末尾追加:

```python
UI_BODY = {
    "nodes": [
        {
            "id": 7,
            "type": "CLIPTextEncode",
            "inputs": [
                {"name": "clip", "localized_name": "clip", "link": 1},
                {"name": "text", "localized_name": "文本", "widget": {"name": "text"}},
            ],
            "widgets_values": ["一只猫"],
        },
        {
            "id": 16,
            "type": "KSampler",
            "inputs": [
                {"name": "model", "localized_name": "模型", "link": 2},
                {"name": "seed", "localized_name": "种子", "widget": {"name": "seed"}},
                {"name": "steps", "localized_name": "步数", "widget": {"name": "steps"}},
            ],
            "widgets_values": [42, 20],
        },
    ],
    "last_node_id": 16,
}


def test_workflow_to_api_template_converts_ui_format():
    api = workflow_to_api_template(UI_BODY)
    assert api["7"] == {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "一只猫"},
    }
    assert api["16"] == {
        "class_type": "KSampler",
        "inputs": {"seed": 42, "steps": 20},
    }


def test_workflow_to_api_template_handles_empty_body():
    assert workflow_to_api_template({}) == {}


def test_infer_field_type_seed_number_text():
    assert infer_field_type("seed", 42) == "seed"
    assert infer_field_type("seed", "42") == "seed"
    assert infer_field_type("steps", 20) == "number"
    assert infer_field_type("cfg", 1.5) == "number"
    assert infer_field_type("text", "a") == "text"
    assert infer_field_type("batch_size", True) == "text"


def test_discover_fields_returns_widget_candidates():
    fields = discover_fields(UI_BODY)
    assert len(fields) == 3
    text = next(f for f in fields if f["key"] == "text")
    assert text["label"] == "文本"
    assert text["node_id"] == "7"
    assert text["input_name"] == "text"
    assert text["default"] == "一只猫"
    assert text["type"] == "text"
    seed = next(f for f in fields if f["key"] == "seed")
    assert seed["label"] == "种子"
    assert seed["type"] == "seed"
    steps = next(f for f in fields if f["key"] == "steps")
    assert steps["type"] == "number"
    assert steps["default"] == 20


def test_discover_fields_skips_link_inputs():
    fields = discover_fields(UI_BODY)
    keys = {f["key"] for f in fields}
    assert "clip" not in keys
    assert "model" not in keys
```

- [ ] **Step 2: 运行测试确认失败**

Run: `backend\.venv\Scripts\python -m pytest backend/tests/test_generation_service.py -v`
Expected: 新测试报 `ImportError: cannot import name 'workflow_to_api_template'`(或 `NameError`),旧测试全过。

- [ ] **Step 3: 实现三个纯函数**

在 `backend/app/services/generation.py` 顶部(`apply_parameters` 之前)插入:

```python
def workflow_to_api_template(body_json: dict) -> dict:
    """把 ComfyUI UI 格式工作流 body 转成 API 格式 dict(/prompt 用)。"""
    result: dict = {}
    for node in body_json.get("nodes", []):
        node_id = str(node["id"])
        inputs: dict = {}
        widget_names = [i["name"] for i in node.get("inputs", []) if i.get("widget")]
        widget_values = node.get("widgets_values") or []
        for idx, name in enumerate(widget_names):
            value = widget_values[idx] if idx < len(widget_values) else None
            inputs[name] = value
        result[node_id] = {"class_type": node["type"], "inputs": inputs}
    return result


def infer_field_type(widget_name: str, value) -> str:
    """启发式推断字段类型: seed→'seed'; 数值→'number'; 否则 'text'。"""
    if widget_name.lower() == "seed":
        return "seed"
    if isinstance(value, bool):
        return "text"
    if isinstance(value, (int, float)):
        return "number"
    return "text"


def discover_fields(body_json: dict) -> list[dict]:
    """从 UI 格式 body 返回候选字段(形状与 GenerationField 一致)。

    只为值类型是标量(str/int/float/bool/None)的 widget 输入生成候选。
    连线输入(带 'link')跳过。
    """
    candidates: list[dict] = []
    for node in body_json.get("nodes", []):
        node_id = str(node["id"])
        node_type = node.get("type", "")
        widget_names = [i["name"] for i in node.get("inputs", []) if i.get("widget")]
        widget_values = node.get("widgets_values") or []
        for idx, name in enumerate(widget_names):
            value = widget_values[idx] if idx < len(widget_values) else None
            if not isinstance(value, (str, int, float, bool)) and value is not None:
                continue
            label = f"[{node_type}] {name}"
            for i in node.get("inputs", []):
                if i.get("name") == name and i.get("localized_name"):
                    label = i["localized_name"]
                    break
            candidates.append({
                "key": name,
                "label": label,
                "type": infer_field_type(name, value),
                "node_id": node_id,
                "input_name": name,
                "default": value,
                "required": False,
            })
    return candidates
```

- [ ] **Step 4: 运行测试确认通过**

Run: `backend\.venv\Scripts\python -m pytest backend/tests/test_generation_service.py -v`
Expected: 全部 PASS(旧 + 新)。

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/generation.py backend/tests/test_generation_service.py
git commit -m "feat(backend): UI→API 模板转换 + 字段自动发现纯函数"
```

---

### Task 2: schema 扩展 type + apply_parameters number 分支

**Files:**
- Modify: `backend/app/schemas/generation.py`(`type` pattern 扩展 + 新增 `GenerationDiscoverOut`)
- Modify: `backend/app/services/generation.py`(`apply_parameters` 加 `number` 分支)
- Test: `backend/tests/test_generation_service.py`(number 校验测试)

**Interfaces:**
- Consumes: Task 1 的三个函数(本任务只用它们做 apply_parameters 的 number 校验分支测试,不直接依赖)。
- Produces:
  - `GenerationField.type` 接受 `"number"`。
  - `apply_parameters` 对 `number` 类型做数值校验(拒绝 bool / 非数值)。
  - `GenerationDiscoverOut` schema(供 Task 3 路由用)。

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_generation_service.py` 末尾追加(先写"拒绝"类测试,确保它们在 number 分支不存在时失败;`test_apply_parameters_accepts_number` 在未实现时也会通过,但它不是红绿灯,仅作回归保护):

```python
NUMBER_FIELDS = [
    {"key": "steps", "label": "步数", "type": "number", "node_id": "16", "input_name": "steps", "default": 20, "required": True},
]


def test_apply_parameters_rejects_bad_number_type():
    with pytest.raises(ValueError):
        apply_parameters(
            {"16": {"class_type": "KSampler", "inputs": {"steps": 20}}},
            NUMBER_FIELDS,
            {"steps": "abc"},
        )


def test_apply_parameters_rejects_bool_as_number():
    with pytest.raises(ValueError):
        apply_parameters(
            {"16": {"class_type": "KSampler", "inputs": {"steps": 20}}},
            NUMBER_FIELDS,
            {"steps": True},
        )


def test_apply_parameters_accepts_number():
    filled, effective = apply_parameters(
        {"16": {"class_type": "KSampler", "inputs": {"steps": 20}}},
        NUMBER_FIELDS,
        {"steps": 30},
    )
    assert filled["16"]["inputs"]["steps"] == 30
    assert effective["steps"] == 30
```

- [ ] **Step 2: 运行测试确认失败**

Run: `backend\.venv\Scripts\python -m pytest backend/tests/test_generation_service.py -k "number or bool_as" -v`
Expected: `test_apply_parameters_rejects_bad_number_type` 和 `test_apply_parameters_rejects_bool_as_number` FAIL(当前 number 分支不存在,字符串/布尔被直接塞进 inputs,没抛 ValueError)。

- [ ] **Step 3: 实现 number 分支 + schema 扩展**

在 `backend/app/services/generation.py` 的 `apply_parameters` 里,`if field["type"] == "seed":` 分支之后、`elif field["required"]...` 之前,插入:

```python
        elif field["type"] == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"字段 {field['label']} 必须是数字")
```

在 `backend/app/schemas/generation.py`,把 `type` 的 pattern 从 `^(text|seed)$` 改成 `^(text|seed|number)$`,并在 `GenerationConfigSummaryOut` 之前新增:

```python
class GenerationDiscoverOut(BaseModel):
    api_template: dict
    fields: list[GenerationField]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `backend\.venv\Scripts\python -m pytest backend/tests/test_generation_service.py -v`
Expected: 全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/app/schemas/generation.py backend/app/services/generation.py backend/tests/test_generation_service.py
git commit -m "feat(backend): 字段类型支持 number + apply_parameters 数值校验"
```

---

### Task 3: discover 接口 + 路由测试

**Files:**
- Modify: `backend/app/api/routes/workflows.py`(新增 discover 路由)
- Test: `backend/tests/test_workflows_api.py`(discover 接口测试)

**Interfaces:**
- Consumes: Task 1 `workflow_to_api_template` + `discover_fields`;Task 2 `GenerationDiscoverOut`。
- Produces: `GET /workflows/{workflow_id}/generation-config/discover` → 200 `{api_template, fields}`,404(工作流不存在)。

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_workflows_api.py` 末尾追加:

```python
UI_BODY = json.dumps({
    "nodes": [
        {
            "id": 7,
            "type": "CLIPTextEncode",
            "inputs": [
                {"name": "clip", "localized_name": "clip", "link": 1},
                {"name": "text", "localized_name": "文本", "widget": {"name": "text"}},
            ],
            "widgets_values": ["a cat"],
        },
        {
            "id": 16,
            "type": "KSampler",
            "inputs": [
                {"name": "model", "localized_name": "模型", "link": 2},
                {"name": "seed", "localized_name": "种子", "widget": {"name": "seed"}},
            ],
            "widgets_values": [42],
        },
    ]
})


def test_discover_generation_config(tmp_path):
    import json as _json
    client, _ = _client(tmp_path)
    files = {"file": ("z.json", io.BytesIO(UI_BODY.encode("utf-8")), "application/json")}
    r = client.post("/workflows/import", files=files)
    wf_id = r.json()["id"]

    d = client.get(f"/workflows/{wf_id}/generation-config/discover")
    assert d.status_code == 200
    data = d.json()
    assert data["api_template"]["7"]["class_type"] == "CLIPTextEncode"
    assert data["api_template"]["7"]["inputs"]["text"] == "a cat"
    keys = {f["key"] for f in data["fields"]}
    assert keys == {"text", "seed"}
    text = next(f for f in data["fields"] if f["key"] == "text")
    assert text["label"] == "文本"
    assert text["type"] == "text"


def test_discover_generation_config_404_missing_workflow(tmp_path):
    client, _ = _client(tmp_path)
    r = client.get("/workflows/nope/generation-config/discover")
    assert r.status_code == 404


def test_discover_dedupes_same_name_keys(tmp_path):
    import json as _json
    body = _json.dumps({
        "nodes": [
            {
                "id": 7,
                "type": "CLIPTextEncode",
                "inputs": [{"name": "text", "localized_name": "正向", "widget": {"name": "text"}}],
                "widgets_values": ["x"],
            },
            {
                "id": 8,
                "type": "CLIPTextEncode",
                "inputs": [{"name": "text", "localized_name": "负向", "widget": {"name": "text"}}],
                "widgets_values": ["y"],
            },
        ]
    })
    client, _ = _client(tmp_path)
    files = {"file": ("z.json", io.BytesIO(body.encode("utf-8")), "application/json")}
    r = client.post("/workflows/import", files=files)
    wf_id = r.json()["id"]

    d = client.get(f"/workflows/{wf_id}/generation-config/discover")
    keys = [f["key"] for f in d.json()["fields"]]
    assert keys == ["text", "text_1"]
```

注意: 需要在测试文件顶部 `import json`(当前文件没有)。修改顶部为:

```python
import io
import json
from pathlib import Path
```

- [ ] **Step 2: 运行测试确认失败**

Run: `backend\.venv\Scripts\python -m pytest backend/tests/test_workflows_api.py -k discover -v`
Expected: FAIL — 路由不存在,返回 404(其实 TestClient 对未定义路径返回 404,但字段断言会失败)。`test_discover_dedupes_same_name_keys` 因无去重逻辑会返回 `["text","text"]` 导致断言失败。

- [ ] **Step 3: 实现 discover 路由**

在 `backend/app/api/routes/workflows.py`,新增 import:

```python
from app.schemas.generation import GenerationDiscoverOut
```

(它已在现有 import 列表里 import 了 GenerationConfigIn/Out 等,只需把 `GenerationDiscoverOut` 加进那个 from-import。)

在 `get_generation_config` 路由之后新增:

```python
@router.get("/{workflow_id}/generation-config/discover", response_model=GenerationDiscoverOut)
def discover_generation_config(
    workflow_id: str,
    repo: WorkflowRepository = Depends(_repo),
) -> GenerationDiscoverOut:
    wf = repo.get(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    body_json = json.loads(wf.body)
    api_template = workflow_to_api_template(body_json)
    fields = discover_fields(body_json)
    seen: set[str] = set()
    for f in fields:
        base = f["key"]
        key = base
        n = 1
        while key in seen:
            key = f"{base}_{n}"
            n += 1
        seen.add(key)
        f["key"] = key
    return GenerationDiscoverOut(api_template=api_template, fields=fields)
```

并在该文件顶部 import 区补:

```python
from app.services.generation import discover_fields, workflow_to_api_template
```

- [ ] **Step 4: 运行测试确认通过**

Run: `backend\.venv\Scripts\python -m pytest backend/tests/test_workflows_api.py -k discover -v`
Expected: 3 个 discover 测试全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/app/api/routes/workflows.py backend/tests/test_workflows_api.py
git commit -m "feat(backend): 工作流生成字段 discover 接口"
```

---

### Task 4: 前端配置弹窗改造为勾选清单

**Files:**
- Modify: `frontend/src/features/workflows/WorkflowGenerationConfigModal.vue`(全量重写)
- Modify: `frontend/src/services/api.ts`(加 `discoverGenerationConfig` 方法)

**Interfaces:**
- Consumes: `GET /workflows/{id}/generation-config/discover`(Task 3)、现有 `api.workflows.generationConfig.get/save`。
- Produces:
  - `api.workflows.generationConfig.discover(workflowId)` → `{api_template, fields}`
  - 弹窗保存 `{api_template, fields}` 到现有 `PUT` 接口。

- [ ] **Step 1: 加前端 API 方法**

读 `frontend/src/services/api.ts`,找到 `workflows` 对象里的 `generationConfig`(有 `get` / `save` 的地方),追加:

```ts
discover: (workflowId: string) =>
  apiFetch(`/workflows/${workflowId}/generation-config/discover`).then((r) => r.json()) as Promise<{
    api_template: unknown;
    fields: GenerationField[];
  }>,
```

(需要确保 `GenerationField` 类型已 import;`frontend/src/types/api.ts` 里有。)

- [ ] **Step 2: 重写 `WorkflowGenerationConfigModal.vue`**

保留脚本中现有的 `apiTemplate` / `fields` / `saving` / `error` / `save()` 逻辑,但:
- 去掉 `apiTemplate` 的文本编辑(删除 textarea)。
- `onMounted` 改成: 先 `removed.value = new Set()` 重置;然后尝试 `api.workflows.generationConfig.get(workflowId)`;若 404(未配置),调 `discover(workflowId)` 拿候选,`fields = candidates`,`apiTemplate = candidates.api_template`;若已有配置,用已有 `fields`。`apiTemplate` 在已有配置时用 `cfg.api_template`(从 get 返回),在未配置时用 discover 的 `api_template`。

模板改为:

```vue
<Modal :title="`生成配置 · ${props.title}`" @close="emit('close')">
  <div class="cc-form">
    <div class="cc-desc">
      <p>选择要让「生成」页面显示的参数。取消勾选 = 生成时不显示。</p>
    </div>

    <el-checkbox
      v-for="(f, i) in fields"
      :key="f.key"
      :model-value="!removed.has(f.key)"
      @update:model-value="(v) => toggleField(f.key, !!v)"
      class="cc-field-row"
    >
      <span class="cc-label">{{ f.label }}</span>
      <span class="cc-key">{{ f.key }}</span>
      <el-input
        v-model="f.label"
        size="small"
        class="cc-label-edit"
        placeholder="标签"
      />
      <el-checkbox v-model="f.required" class="cc-required" size="small">必填</el-checkbox>
    </el-checkbox>

    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
  </div>

  <template #footer>
    <el-button @click="emit('close')">取消</el-button>
    <el-button type="primary" :loading="saving" @click="save">
      {{ saving ? "保存中…" : "保存" }}
    </el-button>
  </template>
</Modal>
```

脚本里加 `removed` 集合控制勾选态:

```ts
const removed = ref<Set<string>>(new Set());

function toggleField(key: string, checked: boolean) {
  if (checked) removed.value.delete(key);
  else removed.value.add(key);
}
```

`save()` 发送时过滤掉 `removed` 里的字段:

```ts
const visibleFields = fields.value.filter((f) => !removed.value.has(f.key));
await api.workflows.generationConfig.save(props.workflowId, {
  api_template: apiTemplate.value,
  fields: visibleFields,
});
```

(注意 `apiTemplate` 现在只存 discover 返回的模板,不再有 textarea 编辑。)

- [ ] **Step 3: typecheck + build**

Run: `npm --prefix frontend run typecheck`
Expected: PASS。
Run: `npm --prefix frontend run build`
Expected: PASS。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/features/workflows/WorkflowGenerationConfigModal.vue frontend/src/services/api.ts
git commit -m "feat(frontend): 生成配置改为自动发现勾选清单"
```

---

### Task 5: 前端生成弹窗支持 number 字段

**Files:**
- Modify: `frontend/src/features/generations/GenerationCreateModal.vue`

**Interfaces:**
- Consumes: `fields[].type` 含 `"number"`。
- Produces: `number` 类型渲染为 `<el-input-number>`(无随机框),其余不变。

- [ ] **Step 1: 扩展生成表单渲染**

在 `GenerationCreateModal.vue` 模板里,`fields` 遍历的 `el-form-item` 内部,把 `seed` 分支改为同时覆盖 `number`:

把现有 `v-if="f.type === 'seed'"` 块改为:

```vue
<template v-if="f.type === 'seed'">
  <div class="cc-seed-row">
    <el-checkbox v-model="randomFlags[`${f.key}_random`]">随机</el-checkbox>
    <el-input-number
      v-if="!randomFlags[`${f.key}_random`]"
      :model-value="values[f.key] as number | undefined"
      @update:model-value="(v: number | undefined) => values[f.key] = (v ?? 0)"
      controls-position="right"
    />
  </div>
</template>
<el-input-number
  v-else-if="f.type === 'number'"
  :model-value="values[f.key] as number | undefined"
  @update:model-value="(v: number | undefined) => values[f.key] = (v ?? 0)"
  controls-position="right"
  style="width: 100%"
/>
<el-input
  v-else
  type="textarea"
  :rows="3"
  :model-value="values[f.key]"
  @update:model-value="(v: string) => values[f.key] = v ?? ''"
/>
```

`submit()` 里 `parameters` 构建已按 `fields` 遍历,`number` 字段走 `isSeed=false` 路径直接取值,无需改逻辑(校验已由后端 `apply_parameters` 兜底)。

- [ ] **Step 2: typecheck + build**

Run: `npm --prefix frontend run typecheck`
Expected: PASS。
Run: `npm --prefix frontend run build`
Expected: PASS。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/features/generations/GenerationCreateModal.vue
git commit -m "feat(frontend): 生成弹窗支持 number 字段渲染"
```

---

### Task 6: 端到端验证 + 手动冒烟

**Files:** 无改动。

- [ ] **Step 1: 后端全量测试**

Run: `backend\.venv\Scripts\python -m pytest backend/tests -v`
Expected: 90+ 通过 + 1 已知 Windows fail(`test_check_database_returns_false_when_path_unwritable`),无回归。

- [ ] **Step 2: 前端 typecheck + build**

Run: `npm --prefix frontend run typecheck`
Expected: PASS。
Run: `npm --prefix frontend run build`
Expected: PASS。

- [ ] **Step 3: 手动冒烟(start-dev.ps1)**

Start: `powershell -ExecutionPolicy Bypass -File scripts\start-dev.ps1`
打开 `http://127.0.0.1:5173/workflows`:

1. 找到 z-image-turbo 行,点 配置 → 弹窗列出字段,标签为中文(种子、文本、宽度、…),全部默认勾选。
2. 只保留 文本 + 种子,取消其余,点保存。
3. 切到 `/generations`,点 + 新建生成 → 弹窗选 z-image-turbo → 第 2 步只出现 提示词(textarea)+ 种子(input-number + 随机复选框)。
4. 填值,走完向导提交 → 生成记录出现在列表,状态从 queued → running → success。
5. 点 查看 → 图片预览。

Stop: `powershell -ExecutionPolicy Bypass -File scripts\stop-dev.ps1`

- [ ] **Step 4: 汇报**

告知用户:
- 提交哈希列表(本 plan 的 commit)
- pytest 结果(数量 + 已知 Windows fail)
- typecheck / build 结果
- 冒烟发现的任何问题及修复

---

## 自检记录(写完 plan 后)

**1. Spec 覆盖:**

| Spec 要求 | 对应 Task |
|---|---|
| `GenerationField.type` 支持 number | T2 |
| `workflow_to_api_template` | T1 |
| `infer_field_type` | T1 |
| `discover_fields`(过滤 link、用 localized_name) | T1 |
| `apply_parameters` number 分支 | T2 |
| discover 接口 + 404 + 去重 | T3 |
| `GenerationDiscoverOut` | T2 + T3 |
| 前端配置弹窗勾选清单、删 JSON textarea | T4 |
| 前端 discover API 方法 | T4 |
| 生成弹窗 number 渲染 | T5 |
| 保存路径沿用现有 PUT | T4 |
| 端到端验证 | T6 |

无缺口。✅

**2. 占位符扫描:** 无 TBD/TODO/「类似 Task N」引用。每个代码步骤带完整代码。

**3. 类型一致性:**
- `workflow_to_api_template(body_json: dict) -> dict` — T1 定义,T3 路由消费(名字一致)。
- `discover_fields(body_json: dict) -> list[dict]` — T1 定义,T3 消费。
- `GenerationDiscoverOut(api_template: dict, fields: list[GenerationField])` — T2 定义,T3 返回。
- `apply_parameters` 的 `number` 分支 — T2 实现,T2 测试覆盖。
- 前端 `api.workflows.generationConfig.discover(workflowId)` — T4 定义,T4 modal 消费。
- `removed: Set<string>` / `toggleField` / `visibleFields` — T4 定义 + 使用一致。
- 前端 `values[f.key]` 动态键绑定 + `(v: number | undefined)` / `(v: string)` 类型注解 — T5 沿用 T6 之前的既有模式。

**4. 风险点复核:**
- T2 第一个测试 `test_apply_parameters_accepts_number` 在未实现时会「假通过」——已在 Step 1 注释里明确指出并调整了顺序(先写拒绝类测试)。✅
- T3 测试需要 `import json`(test_workflows_api.py 顶部当前没有)——Step 1 明确要求补上。✅
- T4 `removed` 集合在 `onMounted` 里从已有配置 / discover 候选初始化——Step 2 的 `onMounted` 说明提到要重置 `removed`(在脚本实现时注意清空 `removed.value = new Set()`)。补充一条: 在 `onMounted` 里、填充 fields 前后各 `removed.value = new Set()`。
- T4 保存时 `apiTemplate` 必须来自 discover(否则 PUT 空模板会覆盖)——Step 2 明确 `apiTemplate` 只存 discover 返回值。✅
