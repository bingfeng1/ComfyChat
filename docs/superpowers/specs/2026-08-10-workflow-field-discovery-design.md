# 工作流生成字段自动发现

**日期:** 2026-08-10
**状态:** 设计 — 待评审
**范围:** 把「手填 API 模板 JSON + node_id/input_name 字段表」的生成配置体验,改造成「自动发现 + 中文勾选清单」。用户打开工作流的"生成配置"弹窗,看到工作流所有可填写控件(带明确中文标签),勾选想暴露的,保存。生成创建页随后只渲染勾选过的字段,形成动态表单。

## 问题

现在的生成配置(`WorkflowGenerationConfigModal.vue`)逼着用户:
1. 往 "API 模板 JSON" 里粘贴 ComfyUI 的 API 格式 JSON(不透明;用户必须懂 ComfyUI 内部)
2. 手动建字段表,填裸 `node_id` / `input_name` 字符串(不透明;用户分不清哪个对应哪个)

用户的真实心智模型:"我想挑选工作流里哪些输入出现在生成表单中 — 比如 z-image-turbo 只需 正面提示词 + 种子随机。其他我都不填。"

我们库里的 `Workflow.body` 已经包含自动生成这一切所需的全部信息,因为 ComfyUI 的 UI 格式工作流文件里,每个节点的 `inputs[]` 既带技术名 `name`,也带中文 `localized_name`(如 `KSampler.inputs.seed` 本地化为"种子")。它还按与 widget 输入相同的顺序携带 `widgets_values`(真实值)。

## 已验证的事实(来自真实 z-image-turbo 工作流)

- `Workflow.body` 是 **UI 格式**(`{"nodes":[{id, type, inputs, widgets_values, ...}]}`),不是 ComfyUI `/prompt` 需要的 **API 格式** `{"<id>":{"class_type","inputs"}}`。
- 每个可填输入都出现在 `node.inputs[]` 中,带 `"widget": {"name": <name>}`。节点连线输入(`"link": N`)是连接关系,不可填 — 排除。
- `node.inputs[].localized_name` 是人类可读的中文标签("种子"、"文本"、"宽度"、…)。
- `node.widgets_values[]` 与带 `widget` 的 `inputs[]` 条目位置一一对应(即 widget 输入)。加载器的下拉框(如 `clip_name`、`unet_name`)也走 widget 进来 — 模型选择组合框。
- 提交给 `/prompt` 的 API 格式结构是 `{"<node_id>": {"class_type": "<node.type>", "inputs": {"<widget_name>": <widget_value>}}}`。ComfyUI 接受字符串节点 ID;文件里 int key 与 str key 都行,但我们统一规范为 str。

## 设计

### 字段类型扩展

把 `GenerationField.type` 从 `^(text|seed)$` 扩展为 `^(text|seed|number)$`:
- `text` → 渲染为 `<el-input type="textarea">`
- `seed` → 渲染为 `<el-input-number>` + "随机" 复选框(现有行为)
- `number` → 渲染为 `<el-input-number>` 带 `:controls-position="right"`,无随机复选框。校验:必须是数字。

这与用户想法吻合:"文字,数字,种子" — 自动发现启发式来定类型。

### 新增后端辅助函数(在 `backend/app/services/generation.py`)

```python
def workflow_to_api_template(body_json: dict) -> dict:
    """把 ComfyUI UI 格式工作流 body 转成 /prompt 需要的 API 格式 dict。"""
    result = {}
    for node in body_json.get("nodes", []):
        node_id = str(node["id"])
        node_type = node["type"]
        inputs = {}
        widget_names = [i["name"] for i in node.get("inputs", []) if i.get("widget")]
        widget_values = node.get("widgets_values") or []
        for idx, name in enumerate(widget_names):
            value = widget_values[idx] if idx < len(widget_values) else None
            inputs[name] = value
        result[node_id] = {"class_type": node_type, "inputs": inputs}
    return result


def infer_field_type(widget_name: str, value) -> str:
    """启发式: 名字是 seed → 'seed'; 数值型默认值 → 'number'; 否则 'text'。"""
    lowered = widget_name.lower()
    if lowered == "seed":
        return "seed"
    if isinstance(value, bool):
        return "text"
    if isinstance(value, (int, float)):
        return "number"
    return "text"


def discover_fields(body_json: dict) -> list[dict]:
    """从 UI 格式 body 返回候选字段(形状与 GenerationField 一致)。

    对每个值为标量(str/int/float/bool)的 widget 输入生成一个候选。
    节点连线输入跳过。组合框(加载器模型选择)按 text 类型包含进来;用户可取消勾选。
    """
    candidates = []
    api = workflow_to_api_template(body_json)
    for node in body_json.get("nodes", []):
        node_id = str(node["id"])
        node_type = node.get("type", "")
        widget_names = [i["name"] for i in node.get("inputs", []) if i.get("widget")]
        widget_values = node.get("widgets_values") or []
        for idx, name in enumerate(widget_names):
            value = widget_values[idx] if idx < len(widget_values) else None
            if isinstance(value, (str, int, float, bool)) or value is None:
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

说明:
- `key` 默认用 widget 名 `name`。若两个节点暴露同名 widget(如两个 `CLIPTextEncode` 都暴露 `text`),第二个候选在路由/服务层去重时加后缀(`text`、`text_1`)。
- `label` 优先用 `localized_name`(中文),兜底用 `[节点类型] name`。

### `apply_parameters` 改动

`apply_parameters(api_template, fields, parameters)` 已经做 `filled[node_id]["inputs"][input_name] = value`。扩展 `type` 允许 `number` 后,加一个 `number` 分支(镜像 seed 的整数要求,接受 `int`/`float`,拒绝非数字):

```python
if field["type"] == "seed":
    ...  # 不变
elif field["type"] == "number":
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"字段 {field['label']} 必须是数字")
elif field["required"] and (value is None or value == ""):
    raise ValueError(f"字段 {field['label']} 为必填")
```

### 新增 discover 接口

`GET /workflows/{workflow_id}/generation-config/discover`(在 `backend/app/api/routes/workflows.py`):

- 工作流不存在则 404。
- 读 `wf.body`,解析 JSON。
- 调 `discover_fields`,key 去重(重复加 `text`、`text_1`、…)。
- 返回 `{"api_template": <转换结果>, "fields": [<候选>]}`(两者都从 body 实时算)。

响应 schema: 在 `backend/app/schemas/generation.py` 新增 `GenerationDiscoverOut`:

```python
class GenerationDiscoverOut(BaseModel):
    api_template: dict
    fields: list[GenerationField]
```

### 保存路径

现有 `PUT /workflows/{workflow_id}/generation-config` 接受 `{api_template, fields}`。前端现在发送自动算出的 `api_template`(来自 discover)+ 用户勾选的 `fields`。**保存路径后端无需改动** — `api_template` 仍存为填充基底(不再展示给用户,是透明管道)。

### 前端: 配置弹窗(`WorkflowGenerationConfigModal.vue`)

把当前 JSON textarea + 裸字段表替换为:

- **加载:** 挂载时调 `GET .../generation-config`(现有)。若 404(未保存过配置),调 `GET .../generation-config/discover` 把所有候选 **预勾选** 填充进清单。若已有配置,加载其 `fields`,按已勾选状态渲染清单。
- **勾选清单 UI:** 每个候选字段一行 `el-checkbox`:`[label] ([key])`。`label` 是中文 `localized_name`;括号里 `key` 是技术 widget 名,保留用于区分两个同名字段。
- **切换:** 取消勾选即从保存的 `fields` 数组移除。用户还可把字段标为 "必填"(小开关)和改 label(行内 `el-input`)。
- **保存:** `PUT` 发送 `{ api_template: <来自 discover>, fields: <勾选的> }`。
- **兜底:** 若 `discover` 返回零候选(异常;空工作流),提示未发现可填输入。
- 彻底删除原始 JSON textarea。`api_template` 不再用户可编辑。

### 前端: 生成创建弹窗(`GenerationCreateModal.vue`)

现有动态表单已遍历 `fields` 并按类型渲染。扩展:
- `number` 类型 → `<el-input-number>`(同 seed 但去掉随机复选框)。
- 其余保持不变,无需其他改动。

### 非目标

- 不做存量配置迁移:现有 `api_template`/`fields` 值仍有效(已用 `text`/`seed`;`number` 是新增)。用户可重新跑 discover 刷新。
- 不做 UI→API 转换缓存:`workflow_to_api_template` 每次 discover 和每次 generation `create` 都重算(body 小,成本可忽略)。
- 不做 API 格式模板编辑:JSON textarea 删除,没有"手动改载荷"的专家逃生口。(以后需要可加 "显示原始 JSON" 开关。)
- 不做字段排序;字段按工作流节点顺序渲染。

## 改动文件

后端:
- `backend/app/schemas/generation.py` — `type` pattern → `text|seed|number`;新增 `GenerationDiscoverOut`。
- `backend/app/services/generation.py` — 新增 `workflow_to_api_template`、`infer_field_type`、`discover_fields`;扩展 `apply_parameters` number 分支。
- `backend/app/api/routes/workflows.py` — 新增 `GET /{workflow_id}/generation-config/discover`。

前端:
- `frontend/src/features/workflows/WorkflowGenerationConfigModal.vue` — 勾选清单 UI + 自动发现,删除 JSON textarea。
- `frontend/src/features/generations/GenerationCreateModal.vue` — `number` 字段渲染为 `el-input-number`。

测试(后端,现有 pytest):
- `backend/tests/test_generation_service.py` — `workflow_to_api_template`(UI body → API dict)、`infer_field_type`(seed/number/text)、`discover_fields`(过滤 link 输入、用 localized_name 做标签)、`apply_parameters` number 分支。
- `backend/tests/test_workflows_api.py` — discover 接口(200 带字段、404 缺失工作流)。
- 现有测试必须保持绿(91 collected,1 个已知 Windows fail)。

## 验证

1. `backend\.venv\Scripts\python -m pytest backend/tests -v` → 90 pass + 1 已知 Windows fail(无回归)。
2. `npm --prefix frontend run typecheck` → PASS。
3. `npm --prefix frontend run build` → PASS。
4. 手动冒烟(start-dev.ps1):
   - 打开 `/workflows`,在 z-image-turbo 上点 配置 → 弹窗列出带中文标签的字段(种子、文本、宽度、高度、…),全部预勾选。
   - 只保留 文本(node 7)+ 种子(node 16),取消其余;保存。
   - 打开 `/generations`,`新建生成`,选 z-image-turbo → 只出现 提示词(textarea)+ 种子(input-number + 随机复选框)。
   - 提交一次生成;确认 ComfyUI 收到合法 API 格式载荷,成功运行返回图片。
