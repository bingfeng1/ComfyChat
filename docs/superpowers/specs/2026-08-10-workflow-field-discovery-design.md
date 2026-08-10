# Workflow Generation Fields Auto-Discovery

**Date:** 2026-08-10
**Status:** Design — awaiting review
**Scope:** Replace the manual "API 模板 JSON + node_id/input_name fields" config experience with an auto-discovery checklist. User opens the workflow's 生成配置 modal, sees every fillable widget of the workflow listed with a clear Chinese label, checks the ones to expose, saves. The generation create page then renders a dynamic form with only the checked fields.

## Problem

Today's generation config (`WorkflowGenerationConfigModal.vue`) forces the user to:
1. Paste a ComfyUI API-format JSON into "API 模板 JSON" (opaque; user must know ComfyUI internals)
2. Manually build a field table with raw `node_id` / `input_name` strings (opaque; user can't tell which maps to what)

The user's real mental model: "I want to pick which inputs of my workflow appear in the generate form — e.g. z-image-turbo needs just 正面提示词 + seed 随机. Everything else I don't fill."

The `Workflow.body` stored in our DB already contains everything needed to auto-generate this, because ComfyUI's UI-format workflow files ship per-node `inputs[]` entries that include both the technical `name` and a Chinese `localized_name` (e.g. `KSampler.inputs.seed` → localized "种子"). It also carries `widgets_values` (the actual values) in the same order as the widget inputs.

## Verified facts (from inspecting the real z-image-turbo workflow)

- `Workflow.body` is **UI format** (`{"nodes":[{id, type, inputs, widgets_values, ...}]}`), NOT the API format `{"<id>":{"class_type","inputs"}}` that ComfyUI `/prompt` needs.
- Every user-fillable input appears in `node.inputs[]` with `"widget": {"name": <name>}`. Node-link inputs (`"link": N`) are connections, not fillable — exclude.
- `node.inputs[].localized_name` is the human-readable Chinese label ("种子", "文本", "宽度", ...).
- `node.widgets_values[]` aligns positionally with the `inputs[]` entries that have `widget` (i.e. widget inputs). Loader combos (e.g. `clip_name`, `unet_name`) also come through as widgets — model-selection combo boxes.
- The API-format structure we must submit to `/prompt` is `{"<node_id>": {"class_type": "<node.type>", "inputs": {"<widget_name>": <widget_value>}}}`. ComfyUI accepts node IDs as strings; both `int` keys from the file and `str` keys are acceptable, but we normalize to `str`.

## Design

### Field type extension

Extend `GenerationField.type` from `^(text|seed)$` to `^(text|seed|number)$`:
- `text` → rendered as `<el-input type="textarea">`
- `seed` → rendered as `<el-input-number>` + a "随机" checkbox (existing behavior)
- `number` → rendered as `<el-input-number>` with `:controls-position="right"`, no random checkbox. Validation: must be a number.

This matches how the user thinks: "文字,数字,种子" — and the discovery heuristic decides which.

### New backend helpers (in `backend/app/services/generation.py`)

```python
def workflow_to_api_template(body_json: dict) -> dict:
    """Convert a ComfyUI UI-format workflow body into the API-format dict ComfyUI /prompt expects."""
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
    """Heuristic: seed names → 'seed'; numeric-ish default → 'number'; else 'text'."""
    lowered = widget_name.lower()
    if lowered == "seed":
        return "seed"
    if isinstance(value, bool):
        return "text"
    if isinstance(value, (int, float)):
        return "number"
    return "text"


def discover_fields(body_json: dict) -> list[dict]:
    """Return candidate fields (dicts shaped like GenerationField) from a UI-format body.

    A candidate is generated for every widget input whose value is a scalar
    (str/int/float/bool). Node-link inputs are skipped. Combos (loader model
    selection) are included as `text` type; the user can uncheck them.
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

Notes:
- `key` defaults to the widget `name`. If two nodes expose the same widget name (e.g. two `CLIPTextEncode` nodes both exposing `text`), the second candidate gets a disambiguated key (`text`, `text_1`). The disambiguation pass runs in the route/service, not in `discover_fields` (keeps the pure function simple; the route dedups).
- `label` prefers `localized_name` (Chinese) over `[node_type] name`.

### `apply_parameters` change

`apply_parameters(api_template, fields, parameters)` already mutates `filled[node_id]["inputs"][input_name] = value`. After we extend `type` to allow `number`, add a `number` branch mirroring `seed`'s integer requirement (accept `int`/`float`, reject non-numeric):

```python
if field["type"] == "seed":
    ...  # unchanged
elif field["type"] == "number":
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"字段 {field['label']} 必须是数字")
elif field["required"] and (value is None or value == ""):
    raise ValueError(f"字段 {field['label']} 为必填")
```

### New discover endpoint

`GET /workflows/{workflow_id}/generation-config/discover` (in `backend/app/api/routes/workflows.py`):

- 404 if workflow missing.
- Loads `wf.body`, parses JSON.
- Calls `discover_fields`, dedups keys (`text`, `text_1`, ...) for collisions.
- Returns `{"api_template": <converted>, "fields": [<candidates>]}` (both computed fresh from `body`).

Response schema: a new `GenerationDiscoverOut` in `backend/app/schemas/generation.py`:

```python
class GenerationDiscoverOut(BaseModel):
    api_template: dict
    fields: list[GenerationField]
```

### Save path

The existing `PUT /workflows/{workflow_id}/generation-config` accepts `{api_template, fields}`. The frontend now sends the auto-computed `api_template` (from discovery) + the user's checked `fields`. **No backend change needed on save** — `api_template` is still stored as the fillable base. (It is not displayed to the user anymore; it is opaque plumbing.)

### Frontend: config modal (`WorkflowGenerationConfigModal.vue`)

Replace the current JSON textarea + raw field table with:

- **Load:** on mount, call `GET .../generation-config` (existing). If 404 (no config saved), call `GET .../generation-config/discover` and populate the checklist with all candidates **pre-checked**. If a config exists, load its `fields` and render the checklist with those checked.
- **Checklist UI:** for each candidate field, an `el-checkbox` row: `[label] ([key])`. The `label` is the Chinese `localized_name`; the bracketed `key` is the technical widget name, kept so the user can disambiguate two same-name fields.
- **Toggle:** unchecking a field removes it from the saved `fields` array. The user can also mark a field as "必填" (small toggle) and edit its label (inline `el-input`).
- **Save:** `PUT` with `{ api_template: <from discover>, fields: <checked> }`.
- **Fallback:** if `discover` returns zero candidates (unusual; empty workflow), show a hint that no fillable inputs were found.
- Remove the raw JSON textarea entirely. The `api_template` is no longer user-editable.

### Frontend: generate create modal (`GenerationCreateModal.vue`)

Existing dynamic form already iterates `fields` and renders per-type input. Extend:
- `number` type → `<el-input-number>` (same as seed minus random checkbox).
- Keep everything else unchanged. No other change needed.

### Non-Goals

- No migration of existing saved configs: existing `api_template`/`fields` values remain valid (they already use `text`/`seed`; `number` is additive). Users can re-run discovery to refresh.
- No UI→API conversion cache: `workflow_to_api_template` recomputes on every discover call and on every generation `create` (small body, negligible cost).
- No API-format template editing: the JSON textarea is removed; there is no power-user escape hatch to hand-edit the payload. (If later needed, a "show raw JSON" toggle can be added.)
- No per-field reorder; fields render in workflow node order.

## Files changed

Backend:
- `backend/app/schemas/generation.py` — `type` pattern → `text|seed|number`; add `GenerationDiscoverOut`.
- `backend/app/services/generation.py` — add `workflow_to_api_template`, `infer_field_type`, `discover_fields`; extend `apply_parameters` number branch.
- `backend/app/api/routes/workflows.py` — add `GET /{workflow_id}/generation-config/discover`.

Frontend:
- `frontend/src/features/workflows/WorkflowGenerationConfigModal.vue` — checklist UI + auto-discovery, remove JSON textarea.
- `frontend/src/features/generations/GenerationCreateModal.vue` — render `number` fields as `el-input-number`.

Tests (backend, existing pytest):
- `backend/tests/test_generation_service.py` — `workflow_to_api_template` (UI body → API dict), `infer_field_type` (seed/number/text), `discover_fields` (filters link inputs, labels via localized_name), `apply_parameters` number branch.
- `backend/tests/test_workflows_api.py` — discover endpoint (200 with fields, 404 missing workflow).
- Existing tests must stay green (91 collected, 1 known Windows fail).

## Verification

1. `backend\.venv\Scripts\python -m pytest backend/tests -v` → 90 pass + 1 known Windows fail (no regression).
2. `npm --prefix frontend run typecheck` → PASS.
3. `npm --prefix frontend run build` → PASS.
4. Manual smoke (start-dev.ps1):
   - Open `/workflows`, click 配置 on z-image-turbo → modal lists fields with Chinese labels (种子, 文本, 宽度, 高度, ...), all pre-checked.
   - Uncheck everything except 文本 (node 7) + seed (node 16); save.
   - Open `/generations`, 新建生成, pick z-image-turbo → only 提示词 (textarea) + 种子 (input-number + 随机 checkbox) appear.
   - Submit a generation; confirm ComfyUI receives a valid API-format payload and a success run returns an image.
