# LoRA 管理页 + 生成界面按主模型过滤 LoRA 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 LoRA 管理页(`/loras`),自动识别每个 LoRA 适用的主模型(多对多)并持久化;生成界面 `lora_name` 下拉按当前工作流主模型过滤(可切「全部」)。依据 `docs/superpowers/specs/2026-08-10-lora-management-design.md`。

**Architecture:** 后端新增 `loras` + `lora_model_links` 两表(模型在 `models/lora.py`),`LoraRepository` 持久化,`services/lora.py` 提供识别纯函数与同步编排;新路由 `GET /lora`、`POST /lora/sync`;`GET /workflows/generation-configs` 每个 config 追加 `main_model`。前端新增 `LorasView.vue` + 路由 + 侧边栏项,`GenerationCreateModal` 的 lora_name select 按主模型过滤。

**Tech Stack:** FastAPI + SQLAlchemy 2.x + SQLite(后端);Vue 3 + Vite + TypeScript + Element Plus 2.11+(前端)。联网识别用 httpx(已有依赖)。

## Global Constraints

从 spec 与 AGENTS.md 拷贝的项目级规则,适用于所有任务,除非任务中明确覆盖。

- **后端范围:**新增 `backend/app/models/lora.py`、`backend/app/repositories/lora.py`、`backend/app/services/lora.py`、`backend/app/schemas/lora.py`、`backend/app/api/routes/lora.py`、`backend/tests/test_lora_service.py`、`backend/tests/test_lora_repository.py`、`backend/tests/test_lora_api.py`;修改 `backend/app/core/config.py`、`backend/app/main.py`、`backend/app/schemas/generation.py`、`backend/app/api/routes/workflows.py`、`backend/tests/test_generation_config_api.py`。其它后端文件一律不动。
- **前端范围:**新增 `frontend/src/features/loras/LorasView.vue`;修改 `frontend/src/types/api.ts`、`frontend/src/services/api.ts`、`frontend/src/app/router.ts`、`frontend/src/components/Sidebar.vue`、`frontend/src/features/generations/GenerationCreateModal.vue`。其它前端文件一律不动。
- **Vite 代理约定:**前端调用 `/api/lora/...`;后端路由前缀 `/lora`(无 `/api`)。
- **Element Plus 自动导入:**不写 `import { ElButton }` 等;图标(`@element-plus/icons-vue`)需显式导入,本期新增导航图标时用现有 `Picture`/`Folder` 同款或 `MagicStick`(显式 `import { MagicStick } from "@element-plus/icons-vue"`)。
- **SCSS 区块:**直接写即可,无需 `@use` 变量(如需 token 用 `@use "@/styles/variables" as *;`)。
- **Settings:**新增字段必须带默认值,不破坏现有五个字段(`comfyui_base_url`/`comfyui_api_key`/`database_url`/`storage_root`/`comfyui_userdata_dir`)。
- **无 alembic:**新表靠 `Base.metadata.create_all()` 在建 app 时自动创建。不写迁移。
- **前端无测试框架:**验证靠 `npm --prefix frontend run typecheck` + `npm --prefix frontend run build`。
- **TDD:**后端任务先写失败测试,跑确认失败,再实现。`engine`/`session` fixture 在 `backend/tests/conftest.py` 已存在。
- **PowerShell 不支持 `&&`:**链式命令用 `; if ($?) { … }` 或分多步。
- **不要前台跑 dev 服务:**`uvicorn`/`npm run dev` 会挂起;用 `scripts/start-dev.ps1`/`stop-dev.ps1` 或短超时。手动烟测后立即停止。
- **不提交 secrets**。
- **行尾换行:**提交时 CRLF/LF 警告可忽略。

---

## File Structure

| 文件 | 责任 | 操作 |
|---|---|---|
| `backend/app/models/lora.py` | `Lora` + `LoraModelLink` 模型 | 新增 |
| `backend/app/repositories/lora.py` | `LoraRepository` upsert/list/清理 | 新增 |
| `backend/app/services/lora.py` | 识别纯函数 + `LoraService.sync` | 新增 |
| `backend/app/schemas/lora.py` | `LoraOut`/`LoraListOut` | 新增 |
| `backend/app/api/routes/lora.py` | `GET /lora`、`POST /lora/sync` | 新增 |
| `backend/tests/test_lora_service.py` | 识别函数 + sync 测试 | 新增 |
| `backend/tests/test_lora_repository.py` | 仓库测试 | 新增 |
| `backend/tests/test_lora_api.py` | 路由测试 | 新增 |
| `backend/app/core/config.py` | 新增 `comfyui_loras_dir` | 修改 |
| `backend/app/main.py` | 注册 lora router | 修改 |
| `backend/app/schemas/generation.py` | `GenerationConfigSummaryOut` 加 `main_model` | 修改 |
| `backend/app/api/routes/workflows.py` | `list_generation_configs` 计算 `main_model` | 修改 |
| `backend/tests/test_generation_config_api.py` | `main_model` 断言 | 修改 |
| `frontend/src/types/api.ts` | `LoraSummary`/`LoraList`;`GenerationConfigSummary` 加 `main_model` | 修改 |
| `frontend/src/services/api.ts` | 新增 `api.loras.list()` | 修改 |
| `frontend/src/app/router.ts` | 新增 `/loras` 路由 | 修改 |
| `frontend/src/components/Sidebar.vue` | 新增「LoRA」导航项 | 修改 |
| `frontend/src/features/loras/LorasView.vue` | LoRA 管理页 | 新增 |
| `frontend/src/features/generations/GenerationCreateModal.vue` | lora_name 下拉按主模型过滤 | 修改 |

---

## Task 1: 模型层 + Settings 字段

**Files:**
- Create: `backend/app/models/lora.py`
- Modify: `backend/app/core/config.py`

**Interfaces:**
- Consumes: `app.models.base.Base`。
- Produces:
  - `Lora`:字段 `name`(PK)、`base_family`(nullable str)、`source_url`(nullable str)、`trigger_words`(nullable str)、`updated_at`。
  - `LoraModelLink`:字段 `lora_name`(FK→loras.name,PK)、`model_name`(PK)、`source`(str)、`updated_at`;复合主键 `(lora_name, model_name)`。
  - `Settings.comfyui_loras_dir: Optional[Path] = Field(default=None)`。

- [ ] **Step 1: 创建模型文件**

创建 `backend/app/models/lora.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Lora(Base):
    __tablename__ = "loras"

    name: Mapped[str] = mapped_column(String(255), primary_key=True)
    base_family: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    trigger_words: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_utcnow)


class LoraModelLink(Base):
    __tablename__ = "lora_model_links"
    __table_args__ = (
        UniqueConstraint("lora_name", "model_name", name="uq_lora_model_link"),
    )

    lora_name: Mapped[str] = mapped_column(
        String(255), ForeignKey("loras.name", ondelete="CASCADE"), primary_key=True
    )
    model_name: Mapped[str] = mapped_column(String(255), primary_key=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_utcnow)
```

- [ ] **Step 2: Settings 加字段**

`backend/app/core/config.py` 末尾 `comfyui_userdata_dir` 行后追加:

```python
    comfyui_loras_dir: Optional[Path] = Field(default=None)
```

- [ ] **Step 3: 冒烟验证建表**

```powershell
cd D:\learnAI\ComfyChat
backend\.venv\Scripts\python -c "from app.models.base import Base; from app.models import lora; from app.core.database import get_engine; import sqlalchemy; print([t.name for t in Base.metadata.sorted_tables])"
```

Expected: 输出含 `loras`、`lora_model_links`(及既有表)。

- [ ] **Step 4: 提交**

```powershell
cd D:\learnAI\ComfyChat
git add backend/app/models/lora.py backend/app/core/config.py; if ($?) { git commit -m "feat(backend): add Lora + LoraModelLink models and comfyui_loras_dir setting" }
```

---

## Task 2: 识别纯函数(TDD)

**Files:**
- Create: `backend/tests/test_lora_service.py`
- Create: `backend/app/services/lora.py`

**Interfaces:**
- Consumes: `app.integrations.comfyui.client`(不直接依赖,纯函数自包含)。
- Produces(全部纯函数,供 Task 4 的 `LoraService` 与 Task 6 的路由使用):
  - `lora_model_pairs_from_body(body: dict) -> list[tuple[str, str]]` — 从 UI-format body 提取 `(lora_name, model_name)` 对。
  - `lora_model_pairs_from_template(api_template: dict) -> list[tuple[str, str]]` — 从 API-format 模板提取同上。
  - `main_model_from_template(api_template: dict) -> str | None` — 返回第一个 LoRA 的主模型文件名。
  - `detect_base_family(header: dict) -> str | None` — 从 safetensors header 判定架构族。
  - `tensor_family(keys: list[str]) -> str | None` — 从张量键名判定架构族。
  - 模块常量 `BASE_LOADERS: set[str]`、`LOADER_MODEL_FIELDS: dict[str, str]`、`LORA_TYPES: set[str]`。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_lora_service.py`:

```python
from app.services.lora import (
    BASE_LOADERS,
    detect_base_family,
    lora_model_pairs_from_body,
    lora_model_pairs_from_template,
    main_model_from_template,
    tensor_family,
)


def _body_with_lora():
    # UI-format: node 2 UNETLoader, node 6 LoraLoaderModelOnly 经 link 3 相连
    return {
        "nodes": [
            {
                "id": 2, "type": "UNETLoader",
                "inputs": [{"name": "unet_name", "widget": {}, "type": "COMBO"}],
                "widgets_values": ["z_image_turbo_int8_convrot.safetensors", "default"],
            },
            {
                "id": 6, "type": "LoraLoaderModelOnly",
                "inputs": [
                    {"name": "model", "type": "MODEL", "link": 3},
                    {"name": "lora_name", "widget": {}, "type": "COMBO"},
                    {"name": "strength_model", "widget": {}, "type": "FLOAT"},
                ],
                "widgets_values": ["mumu_20.safetensors", 0],
            },
        ],
        "links": [[3, 2, 0, 6, 0, "MODEL"]],
    }


def test_body_extracts_lora_model_pair():
    pairs = lora_model_pairs_from_body(_body_with_lora())
    assert pairs == [("mumu_20.safetensors", "z_image_turbo_int8_convrot.safetensors")]


def test_body_without_lora_returns_empty():
    body = {"nodes": [{"id": 1, "type": "KSampler", "inputs": [], "widgets_values": []}], "links": []}
    assert lora_model_pairs_from_body(body) == []


def test_template_extracts_lora_model_pair():
    template = {
        "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "z_image_turbo_int8_convrot.safetensors"}},
        "6": {"class_type": "LoraLoaderModelOnly", "inputs": {
            "model": ["2", 0], "lora_name": "mumu_20.safetensors", "strength_model": 0}},
    }
    assert lora_model_pairs_from_template(template) == [("mumu_20.safetensors", "z_image_turbo_int8_convrot.safetensors")]
    assert main_model_from_template(template) == "z_image_turbo_int8_convrot.safetensors"


def test_main_model_none_without_lora():
    template = {"3": {"class_type": "KSampler", "inputs": {"seed": 0}}}
    assert main_model_from_template(template) is None


def test_base_loaders_contains_common_loaders():
    assert {"CheckpointLoaderSimple", "UNETLoader", "CLIPLoader"} <= BASE_LOADERS


def test_tensor_family_detects_families():
    assert tensor_family(["lora_te_text_model_encoder_layers_0_mlp_fc1.lora_down.weight"]) == "SD1.5"
    assert tensor_family(["lora_unet_down_blocks_0_downsamplers_0_conv.lora_down.weight"]) == "SDXL"
    assert tensor_family(["diffusion_model.transformer_blocks.0.attn.add_k_proj.lora_A.weight"]) == "Qwen-Image"
    assert tensor_family(["diffusion_model.blocks.0.adaln_proj.linear.lora_A.weight"]) == "MiniMax-H3"
    assert tensor_family(["context_refiner.0.attention.to_k.lora_A.default.weight"]) == "Z-Image"
    assert tensor_family(["unknown_key.weight"]) is None


def test_detect_base_family_uses_metadata_first():
    header = {"__metadata__": {"base_model": "MiniMax-H3"}, "x": {"dtype": "F32"}}
    assert detect_base_family(header) == "MiniMax-H3"
    header2 = {"__metadata__": {"compatible_base": "MiniMax-H3 non-pruned bf16"}, "x": {"dtype": "F32"}}
    assert detect_base_family(header2) == "MiniMax-H3"


def test_detect_base_family_falls_back_to_tensors():
    header = {"a": {"dtype": "F32"}, "b": {"dtype": "F32"}}
    assert detect_base_family(header) is None
```

- [ ] **Step 2: 跑测试确认失败**

```powershell
cd D:\learnAI\ComfyChat
backend\.venv\Scripts\python -m pytest backend/tests/test_lora_service.py -v
```

Expected: FAIL,`ModuleNotFoundError: No module named 'app.services.lora'`。

- [ ] **Step 3: 实现 `services/lora.py`**

创建 `backend/app/services/lora.py`:

```python
from __future__ import annotations

BASE_LOADERS: set[str] = {
    "CheckpointLoaderSimple", "UNETLoader", "DiffusionLoader",
    "CLIPLoader", "DualCLIPLoader", "TripleCLIPLoader", "VAELoader",
}

LOADER_MODEL_FIELDS: dict[str, str] = {
    "CheckpointLoaderSimple": "ckpt_name",
    "UNETLoader": "unet_name",
    "DiffusionLoader": "model_name",
    "CLIPLoader": "clip_name",
    "DualCLIPLoader": "clip_name1",
    "TripleCLIPLoader": "clip_name1",
    "VAELoader": "vae_name",
}

LORA_TYPES: set[str] = {"LoraLoader", "LoraLoaderModelOnly"}


def lora_model_pairs_from_body(body: dict) -> list[tuple[str, str]]:
    """从 UI-format body 提取 (lora_name, model_name) 对。"""
    links = body.get("links", [])
    link_map = {int(l[0]): l for l in links if l}
    nodes: dict[str, dict] = {str(n.get("id")): n for n in body.get("nodes", []) if n.get("id") is not None}
    pairs: list[tuple[str, str]] = []
    for node in nodes.values():
        if node.get("type") not in LORA_TYPES:
            continue
        lora = _node_widget(node, "lora_name")
        if not lora:
            continue
        model_link = None
        for inp in node.get("inputs", []):
            if inp.get("name") == "model" and inp.get("link") is not None:
                model_link = inp["link"]
                break
        if model_link is None:
            continue
        link = link_map.get(int(model_link))
        if link is None:
            continue
        src = nodes.get(str(link[1]))
        if src is None or src.get("type") not in BASE_LOADERS:
            continue
        model = _node_widget(src)
        if model:
            pairs.append((lora, model))
    return pairs


def _node_widget(node: dict, name: str | None = None) -> str | None:
    """读节点第一个 widget 值;name 提供时按 inputs 对齐位置。"""
    widgets = node.get("widgets_values") or []
    if not widgets:
        return None
    if name is None:
        val = widgets[0]
    else:
        idx = None
        for i, inp in enumerate(node.get("inputs", [])):
            if inp.get("name") == name and inp.get("widget"):
                idx = i
                break
        if idx is None or idx >= len(widgets):
            return None
        val = widgets[idx]
    return val if isinstance(val, str) and val else None


def lora_model_pairs_from_template(api_template: dict) -> list[tuple[str, str]]:
    """从 API-format 模板提取 (lora_name, model_name) 对。"""
    pairs: list[tuple[str, str]] = []
    for node in api_template.values():
        ct = node.get("class_type")
        if ct not in LORA_TYPES:
            continue
        inputs = node.get("inputs") or {}
        lora = inputs.get("lora_name")
        model_ref = inputs.get("model")
        if not isinstance(lora, str) or not isinstance(model_ref, list) or len(model_ref) != 2:
            continue
        src = api_template.get(str(model_ref[0]))
        if not src:
            continue
        field = LOADER_MODEL_FIELDS.get(src.get("class_type", ""))
        if not field:
            continue
        val = (src.get("inputs") or {}).get(field)
        if isinstance(val, str) and val:
            pairs.append((lora, val))
    return pairs


def main_model_from_template(api_template: dict) -> str | None:
    pairs = lora_model_pairs_from_template(api_template)
    return pairs[0][1] if pairs else None


def tensor_family(keys: list[str]) -> str | None:
    """从张量键名判定架构族。命中顺序即优先级。"""
    s = " ".join(keys).lower()
    if "lora_te_text_model_encoder" in s:
        return "SD1.5"
    if "diffusion_model.transformer_blocks" in s or "transformer_blocks.0.attn" in s:
        return "Qwen-Image"
    if "diffusion_model.blocks." in s and "adaln_proj" in s:
        return "MiniMax-H3"
    if "diffusion_model.layers." in s and "adaLN_modulation" in s:
        return "Z-Image"
    if "context_refiner" in s or "noise_refiner" in s:
        return "Z-Image"
    if "lora_unet_down_blocks" in s and "downsamplers" in s:
        return "SDXL"
    if "lora_te_" in s or ("lora_unet_" in s and "attn1" in s):
        return "SD1.5"
    return None


def detect_base_family(header: dict) -> str | None:
    """从 safetensors header 判定架构族:metadata 优先,张量回退。"""
    meta = header.get("__metadata__") or {}
    for key in ("base_model", "compatible_base"):
        val = meta.get(key)
        if val:
            low = val.lower()
            for family, markers in _FAMILY_MARKERS.items():
                if any(m in low for m in markers):
                    return family
    keys = [k for k in header.keys() if k != "__metadata__"]
    return tensor_family(keys)


_FAMILY_MARKERS: dict[str, list[str]] = {
    "SD1.5": ["sd1.5", "sd15", "stable diffusion 1.5", "runwayml/stable-diffusion-v1"],
    "SDXL": ["sdxl", "sd_xl", "stabilityai/stable-diffusion-xl"],
    "Qwen-Image": ["qwen-image", "qwen_image", "tongyi-mai/qwen-image"],
    "MiniMax-H3": ["minimax-h3", "minimax_h3", "minimax"],
    "Z-Image": ["z-image", "z_image", "zimage", "tongyi-mai/z-image"],
}
```

- [ ] **Step 4: 跑测试确认通过**

```powershell
cd D:\learnAI\ComfyChat
backend\.venv\Scripts\python -m pytest backend/tests/test_lora_service.py -v
```

Expected: 全部 PASS(9 个)。

- [ ] **Step 5: 提交**

```powershell
cd D:\learnAI\ComfyChat
git add backend/tests/test_lora_service.py backend/app/services/lora.py; if ($?) { git commit -m "feat(backend): lora-model extraction + base family detection pure functions" }
```

---

## Task 3: LoraRepository(TDD)

**Files:**
- Create: `backend/tests/test_lora_repository.py`
- Create: `backend/app/repositories/lora.py`

**Interfaces:**
- Consumes: Task 1 的 `Lora` / `LoraModelLink` 模型、`engine` fixture。
- Produces:
  - `LoraRepository(session)`:
    - `upsert_lora(name, base_family=None, source_url=None, trigger_words=None) -> None`
    - `replace_links(lora_name, models: list[str], source: str) -> None` — 先删该 lora 旧链接再插入。
    - `list_all() -> list[tuple[Lora, list[str]]]` — 每行 lora + 其 model_name 列表。
    - `clear_stale(known_names: set[str]) -> None` — 删除不在 known_names 中的 lora(及其链接,靠 FK 显式删)。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_lora_repository.py`:

```python
from app.models.lora import Lora
from app.repositories.lora import LoraRepository


def _repo(session):
    return LoraRepository(session)


def test_upsert_and_list(session):
    repo = _repo(session)
    repo.upsert_lora("mumu_20.safetensors", base_family="Z-Image", source_url="https://x")
    repo.upsert_lora("coser-z_20.safetensors")
    items = repo.list_all()
    assert {name for name, _ in items} == {"mumu_20.safetensors", "coser-z_20.safetensors"}
    by_name = dict(items)
    assert by_name["mumu_20.safetensors"] == []
    lora = session.get(Lora, "mumu_20.safetensors")
    assert lora.base_family == "Z-Image"
    assert lora.source_url == "https://x"


def test_replace_links(session):
    repo = _repo(session)
    repo.upsert_lora("mumu_20.safetensors")
    repo.replace_links("mumu_20.safetensors", ["a.safetensors", "b.safetensors"], "workflow")
    items = dict(repo.list_all())
    assert sorted(items["mumu_20.safetensors"]) == ["a.safetensors", "b.safetensors"]
    # 二次替换应覆盖
    repo.replace_links("mumu_20.safetensors", ["c.safetensors"], "workflow")
    items = dict(repo.list_all())
    assert items["mumu_20.safetensors"] == ["c.safetensors"]


def test_clear_stale(session):
    repo = _repo(session)
    repo.upsert_lora("keep.safetensors")
    repo.upsert_lora("drop.safetensors")
    repo.clear_stale({"keep.safetensors"})
    names = {n for n, _ in repo.list_all()}
    assert names == {"keep.safetensors"}
```

- [ ] **Step 2: 跑测试确认失败**

```powershell
cd D:\learnAI\ComfyChat
backend\.venv\Scripts\python -m pytest backend/tests/test_lora_repository.py -v
```

Expected: FAIL,`ModuleNotFoundError`。

- [ ] **Step 3: 实现仓库**

创建 `backend/app/repositories/lora.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.lora import Lora, LoraModelLink


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class LoraRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_lora(
        self,
        name: str,
        base_family: Optional[str] = None,
        source_url: Optional[str] = None,
        trigger_words: Optional[str] = None,
    ) -> None:
        lora = self.session.get(Lora, name)
        if lora is None:
            lora = Lora(name=name)
            self.session.add(lora)
        if base_family is not None:
            lora.base_family = base_family
        if source_url is not None:
            lora.source_url = source_url
        if trigger_words is not None:
            lora.trigger_words = trigger_words
        lora.updated_at = _utcnow()
        self.session.commit()

    def replace_links(self, lora_name: str, models: list[str], source: str) -> None:
        self.session.execute(
            sa_delete(LoraModelLink).where(LoraModelLink.lora_name == lora_name)
        )
        for model in models:
            self.session.add(
                LoraModelLink(lora_name=lora_name, model_name=model, source=source)
            )
        self.session.commit()

    def list_all(self) -> list[tuple[Lora, list[str]]]:
        rows = self.session.execute(
            select(Lora, LoraModelLink.model_name)
            .outerjoin(LoraModelLink, LoraModelLink.lora_name == Lora.name)
            .order_by(Lora.name.asc())
        ).all()
        grouped: dict[str, tuple[Lora, list[str]]] = {}
        for lora, model_name in rows:
            if lora.name not in grouped:
                grouped[lora.name] = (lora, [])
            if model_name is not None:
                grouped[lora.name][1].append(model_name)
        return list(grouped.values())

    def clear_stale(self, known_names: set[str]) -> None:
        stmt = select(Lora.name).where(Lora.name.notin_(known_names))
        stale = [n for (n,) in self.session.execute(stmt).all()]
        if not stale:
            return
        self.session.execute(
            sa_delete(LoraModelLink).where(LoraModelLink.lora_name.in_(stale))
        )
        self.session.execute(sa_delete(Lora).where(Lora.name.in_(stale)))
        self.session.commit()
```

- [ ] **Step 4: 跑测试确认通过**

```powershell
cd D:\learnAI\ComfyChat
backend\.venv\Scripts\python -m pytest backend/tests/test_lora_repository.py -v
```

Expected: 全部 PASS(3 个)。

- [ ] **Step 5: 提交**

```powershell
cd D:\learnAI\ComfyChat
git add backend/tests/test_lora_repository.py backend/app/repositories/lora.py; if ($?) { git commit -m "feat(backend): LoraRepository upsert/list/replace/clear" }
```

---

## Task 4: LoraService 同步编排(TDD)

**Files:**
- Modify: `backend/tests/test_lora_service.py`(追加 sync + metadata 测试)
- Modify: `backend/app/services/lora.py`(追加 `LoraService`)

**Interfaces:**
- Consumes: Task 2 的纯函数、Task 3 的 `LoraRepository`;`ComfyUIClient`(提供 `get_object_info`)、`Settings`(提供 `comfyui_loras_dir`)。
- Produces:
  - `LoraService(repo, workflow_repo, comfyui, settings)` 构造器,字段同名。
  - `LoraService.list_installed() -> list[str]` — 从 ComfyUI object_info 的 LoraLoader/LoraLoaderModelOnly lora_name COMBO 取全部 LoRA 文件名。
  - `LoraService.read_metadata(path) -> dict | None` — 读 safetensors 文件头 JSON(前 8 字节长度 + JSON),失败返回 None。
  - `LoraService.sync() -> dict` — 返回 `{"total": n}`;编排全流程(见下)。

- [ ] **Step 1: 追加失败测试**

在 `backend/tests/test_lora_service.py` 末尾追加:

```python
import json
import struct

import pytest

from app.models.lora import Lora
from app.repositories.lora import LoraRepository
from app.services.lora import LoraService


class FakeComfy:
    def __init__(self, loras):
        self._loras = loras

    def get_object_info(self, node_types=None):
        return {
            "LoraLoader": {"input": {"required": {"lora_name": [self._loras]}}},
            "LoraLoaderModelOnly": {"input": {"required": {"lora_name": [self._loras]}}},
        }


def _mk_service(session, loras, settings_overrides=None):
    from app.core.config import Settings
    settings = Settings(comfyui_loras_dir=None, **(settings_overrides or {}))
    return LoraService(
        LoraRepository(session),
        workflow_repo=None,
        comfyui=FakeComfy(loras),
        settings=settings,
    )


def _write_safetensors(path, header: dict):
    payload = json.dumps(header).encode("utf-8")
    with open(path, "wb") as f:
        f.write(struct.pack("<Q", len(payload)))
        f.write(payload)


def test_list_installed_from_object_info(session):
    service = _mk_service(session, ["a.safetensors", "b.safetensors", "a.safetensors"])
    assert sorted(service.list_installed()) == ["a.safetensors", "b.safetensors"]


def test_sync_populates_and_clears_stale(session):
    from app.repositories.workflow import WorkflowRepository
    service = _mk_service(session, ["mumu_20.safetensors", "gone.safetensors"])
    # 预先留一条陈旧 lora
    service.repo.upsert_lora("stale.safetensors")
    # 插入一个带 LoRA 的工作流 body
    repo = WorkflowRepository(session)
    body = {
        "nodes": [
            {"id": 2, "type": "UNETLoader", "inputs": [{"name": "unet_name", "widget": {}, "type": "COMBO"}],
             "widgets_values": ["z_image_turbo_int8_convrot.safetensors", "default"]},
            {"id": 6, "type": "LoraLoaderModelOnly", "inputs": [
                {"name": "model", "type": "MODEL", "link": 3},
                {"name": "lora_name", "widget": {}, "type": "COMBO"},
                {"name": "strength_model", "widget": {}, "type": "FLOAT"}],
             "widgets_values": ["mumu_20.safetensors", 0]},
        ],
        "links": [[3, 2, 0, 6, 0, "MODEL"]],
    }
    repo.upsert("browse", "z.json", "z", "z.json", json.dumps(body), 10)

    result = service.sync()
    assert result["total"] == 2
    items = dict(service.repo.list_all())
    assert items["mumu_20.safetensors"] == ["z_image_turbo_int8_convrot.safetensors"]
    assert "stale.safetensors" not in items


def test_sync_reads_metadata_when_loras_dir_configured(session, tmp_path):
    lora_dir = tmp_path / "loras"
    lora_dir.mkdir()
    _write_safetensors(
        lora_dir / "coser-z_20.safetensors",
        {"__metadata__": {"repoId": "jcplus/coser-z", "url": "https://www.modelscope.cn/aigc/home"}},
    )
    _write_safetensors(
        lora_dir / "minimax_h3_turbo_4step_comfyui.safetensors",
        {"__metadata__": {"base_model": "MiniMax-H3", "compatible_base": "MiniMax-H3 non-pruned bf16"}},
    )
    service = _mk_service(
        session,
        ["coser-z_20.safetensors", "minimax_h3_turbo_4step_comfyui.safetensors"],
        {"comfyui_loras_dir": lora_dir},
    )
    service.sync()
    items = dict(service.repo.list_all())
    assert items["minimax_h3_turbo_4step_comfyui.safetensors"] == []
    lora = session.get(Lora, "minimax_h3_turbo_4step_comfyui.safetensors")
    assert lora.base_family == "MiniMax-H3"
    lora2 = session.get(Lora, "coser-z_20.safetensors")
    assert lora2.source_url == "https://www.modelscope.cn/aigc/home"
    assert lora2.trigger_words == "jcplus/coser-z"


def test_sync_read_metadata_missing_file_ok(session, tmp_path):
    lora_dir = tmp_path / "loras"
    lora_dir.mkdir()
    service = _mk_service(session, ["a.safetensors"], {"comfyui_loras_dir": lora_dir})
    service.sync()
    lora = session.get(Lora, "a.safetensors")
    assert lora.base_family is None
```

注意:测试里用到 `Lora` 模型,需在测试文件顶部 import。`test_sync_reads_metadata_when_loras_dir_configured` 依赖 `from app.models.lora import Lora`。

- [ ] **Step 2: 跑测试确认失败**

```powershell
cd D:\learnAI\ComfyChat
backend\.venv\Scripts\python -m pytest backend/tests/test_lora_service.py -v
```

Expected: FAIL,`ImportError: cannot import name 'LoraService'`(及后续断言失败)。

- [ ] **Step 3: 实现 `LoraService`**

在 `backend/app/services/lora.py` 末尾追加(文件顶部已有的 `from __future__ import annotations` 保留;补充需要的 import):

```python
import json
import struct
from pathlib import Path
from typing import Optional

from app.repositories.lora import LoraRepository


class LoraService:
    def __init__(self, repo: LoraRepository, workflow_repo, comfyui, settings) -> None:
        self.repo = repo
        self.workflow_repo = workflow_repo
        self.comfyui = comfyui
        self.settings = settings

    def list_installed(self) -> list[str]:
        """从 ComfyUI object_info 拉全部已安装 LoRA 文件名(去重)。"""
        names: set[str] = set()
        try:
            info = self.comfyui.get_object_info(["LoraLoader", "LoraLoaderModelOnly"])
        except Exception:
            return sorted(names)
        for node_type in ("LoraLoader", "LoraLoaderModelOnly"):
            node = (info or {}).get(node_type) or {}
            entry = (((node.get("input") or {}).get("required") or {}).get("lora_name") or [])
            if entry and isinstance(entry[0], list):
                names.update(str(x) for x in entry[0])
        return sorted(names)

    def read_metadata(self, path: Path) -> Optional[dict]:
        """读 safetensors 头 JSON(8 字节长度前缀)。失败返回 None。"""
        try:
            with open(path, "rb") as f:
                size_bytes = f.read(8)
                if len(size_bytes) != 8:
                    return None
                (length,) = struct.unpack("<Q", size_bytes)
                if length > 8 * 1024 * 1024:
                    return None
                header = json.loads(f.read(length))
            return header if isinstance(header, dict) else None
        except Exception:
            return None

    def _metadata_for(self, name: str) -> dict:
        """按文件名在 loras 目录里找文件并读 header;找不到返回 {}。"""
        lora_dir = self.settings.comfyui_loras_dir
        if not lora_dir:
            return {}
        root = Path(lora_dir).resolve()
        candidate = (root / name).resolve()
        if candidate.parent != root:
            return {}
        header = self.read_metadata(candidate)
        return header if header is not None else {}

    def sync(self) -> dict:
        installed = self.list_installed()
        known: set[str] = set()
        collected: dict[str, set[str]] = {}
        if self.workflow_repo is not None:
            for wf in self.workflow_repo.list():
                try:
                    body = json.loads(wf.body)
                except Exception:
                    continue
                for lora, model in lora_model_pairs_from_body(body):
                    collected.setdefault(lora, set()).add(model)
        for name in installed:
            known.add(name)
            header = self._metadata_for(name)
            meta = header.get("__metadata__") or {}
            base_family = detect_base_family(header)
            source_url = meta.get("url")
            trigger = meta.get("repoId")
            self.repo.upsert_lora(
                name,
                base_family=base_family,
                source_url=source_url,
                trigger_words=trigger,
            )
            pairs = collected.get(name)
            if pairs:
                self.repo.replace_links(name, sorted(pairs), "workflow")
        self.repo.clear_stale(known)
        return {"total": len(installed)}
```

- [ ] **Step 4: 跑测试确认通过**

```powershell
cd D:\learnAI\ComfyChat
backend\.venv\Scripts\python -m pytest backend/tests/test_lora_service.py -v
```

Expected: 全部 PASS(原有 9 + 新增 4 = 13)。

- [ ] **Step 5: 提交**

```powershell
cd D:\learnAI\ComfyChat
git add backend/tests/test_lora_service.py backend/app/services/lora.py; if ($?) { git commit -m "feat(backend): LoraService sync from object_info + workflow bodies + metadata" }
```

---

## Task 5: 路由 + schema + main.py(TDD)

**Files:**
- Create: `backend/tests/test_lora_api.py`
- Create: `backend/app/schemas/lora.py`
- Create: `backend/app/api/routes/lora.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: Task 3 `LoraRepository`、Task 4 `LoraService`;`get_db_session`/`get_services`/`get_settings`。
- Produces:
  - `LoraOut(name, base_family, source_url, trigger_words, models: list[str])`
  - `LoraListOut(items: list[LoraOut])`
  - `GET /lora` — 触发一次 sync 后返回列表。
  - `POST /lora/sync` — 同步后返回列表。
  - `main.py` 注册 `lora.router`。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_lora_api.py`:

```python
import json

from fastapi.testclient import TestClient

from app.main import create_app


def _client(tmp_path):
    from app.core.config import Settings
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/lora.db",
        storage_root=tmp_path / "storage",
        comfyui_base_url="http://example.com:8188/",
    )
    return TestClient(create_app(settings))


def _patch_comfy(monkeypatch, loras):
    class FakeComfy:
        def get_object_info(self, node_types=None):
            return {
                "LoraLoader": {"input": {"required": {"lora_name": [loras]}}},
                "LoraLoaderModelOnly": {"input": {"required": {"lora_name": [loras]}}},
            }
    from app.integrations.comfyui.client import ComfyUIClient
    monkeypatch.setattr(ComfyUIClient, "get_object_info", FakeComfy.get_object_info)


def test_get_lora_returns_items(tmp_path, monkeypatch):
    _patch_comfy(monkeypatch, ["a.safetensors"])
    client = _client(tmp_path)
    r = client.get("/lora")
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [i["name"] for i in items] == ["a.safetensors"]
    assert items[0]["models"] == []


def test_sync_endpoint(tmp_path, monkeypatch):
    _patch_comfy(monkeypatch, ["x.safetensors", "y.safetensors"])
    client = _client(tmp_path)
    r = client.post("/lora/sync")
    assert r.status_code == 200, r.text
    names = {i["name"] for i in r.json()["items"]}
    assert names == {"x.safetensors", "y.safetensors"}
```

- [ ] **Step 2: 跑测试确认失败**

```powershell
cd D:\learnAI\ComfyChat
backend\.venv\Scripts\python -m pytest backend/tests/test_lora_api.py -v
```

Expected: FAIL,`No module named 'app.api.routes.lora'` 或 404。

- [ ] **Step 3: 创建 schema**

创建 `backend/app/schemas/lora.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, Field


class LoraOut(BaseModel):
    name: str
    base_family: str | None = None
    source_url: str | None = None
    trigger_words: str | None = None
    models: list[str] = Field(default_factory=list)


class LoraListOut(BaseModel):
    items: list[LoraOut]
```

- [ ] **Step 4: 创建路由**

创建 `backend/app/api/routes/lora.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_services, get_settings
from app.core.config import Settings
from app.repositories.lora import LoraRepository
from app.repositories.workflow import WorkflowRepository
from app.schemas.lora import LoraListOut, LoraOut
from app.services.lora import LoraService

router = APIRouter(prefix="/lora", tags=["lora"])


def _service(
    session: Session = Depends(get_db_session),
    services: dict = Depends(get_services),
    settings: Settings = Depends(get_settings),
) -> LoraService:
    return LoraService(
        LoraRepository(session),
        WorkflowRepository(session),
        services["comfyui"],
        settings,
    )


def _out(session: Session) -> LoraListOut:
    items = []
    for lora, models in LoraRepository(session).list_all():
        items.append(LoraOut(
            name=lora.name,
            base_family=lora.base_family,
            source_url=lora.source_url,
            trigger_words=lora.trigger_words,
            models=models,
        ))
    return LoraListOut(items=items)


@router.get("", response_model=LoraListOut)
def list_lora(service: LoraService = Depends(_service)) -> LoraListOut:
    service.sync()
    return _out(service.repo.session)


@router.post("/sync", response_model=LoraListOut)
def sync_lora(service: LoraService = Depends(_service)) -> LoraListOut:
    service.sync()
    return _out(service.repo.session)
```

- [ ] **Step 5: main.py 注册路由**

`backend/app/main.py` 中,`from app.api.routes import generations, health, workflows` 改为:

```python
from app.api.routes import generations, health, lora, workflows
```

并在 `app.include_router(generations.router)` 之后加:

```python
    app.include_router(lora.router)
```

- [ ] **Step 6: 跑测试确认通过**

```powershell
cd D:\learnAI\ComfyChat
backend\.venv\Scripts\python -m pytest backend/tests/test_lora_api.py backend/tests/test_lora_repository.py backend/tests/test_lora_service.py -v
```

Expected: 全部 PASS(2 + 3 + 11 = 16)。

- [ ] **Step 7: 提交**

```powershell
cd D:\learnAI\ComfyChat
git add backend/tests/test_lora_api.py backend/app/schemas/lora.py backend/app/api/routes/lora.py backend/app/main.py; if ($?) { git commit -m "feat(backend): /lora routes + schema + router registration" }
```

---

## Task 6: generation-configs 追加 main_model

**Files:**
- Modify: `backend/app/schemas/generation.py`
- Modify: `backend/app/api/routes/workflows.py`
- Modify: `backend/tests/test_generation_config_api.py`

**Interfaces:**
- Consumes: Task 2 的 `main_model_from_template`。
- Produces:
  - `GenerationConfigSummaryOut.main_model: str | None = None`。
  - `GET /workflows/generation-configs` 每个 item 含 `main_model`。
  - `GET /workflows/{id}/generation-config` 响应含 `main_model`。

- [ ] **Step 1: 追加失败测试**

在 `backend/tests/test_generation_config_api.py` 末尾追加:

```python
def test_list_configs_include_main_model(tmp_path):
    client = _client(tmp_path)
    wid = _import(client)
    body = {
        "api_template": {
            "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "z_image_turbo_int8_convrot.safetensors"}},
            "6": {"class_type": "LoraLoaderModelOnly", "inputs": {
                "model": ["2", 0], "lora_name": "mumu_20.safetensors", "strength_model": 0}},
        },
        "fields": [],
    }
    client.put(f"/workflows/{wid}/generation-config", json=body)
    r = client.get("/workflows/generation-configs")
    assert r.status_code == 200
    item = r.json()["items"][0]
    assert item["main_model"] == "z_image_turbo_int8_convrot.safetensors"

    r2 = client.get(f"/workflows/{wid}/generation-config")
    assert r2.json()["main_model"] == "z_image_turbo_int8_convrot.safetensors"


def test_list_configs_main_model_null_without_lora(tmp_path):
    client = _client(tmp_path)
    wid = _import(client)
    body = {"api_template": {"3": {"class_type": "KSampler", "inputs": {"seed": 0}}}, "fields": []}
    client.put(f"/workflows/{wid}/generation-config", json=body)
    r = client.get("/workflows/generation-configs")
    assert r.json()["items"][0]["main_model"] is None
```

- [ ] **Step 2: 跑测试确认失败**

```powershell
cd D:\learnAI\ComfyChat
backend\.venv\Scripts\python -m pytest backend/tests/test_generation_config_api.py -v -k main_model
```

Expected: FAIL,`KeyError: 'main_model'`。

- [ ] **Step 3: schema 加字段**

`backend/app/schemas/generation.py` 的 `GenerationConfigSummaryOut` 改为:

```python
class GenerationConfigSummaryOut(BaseModel):
    workflow_id: str
    workflow_name: str
    fields: list[GenerationField]
    main_model: str | None = None
```

`GenerationConfigOut` 追加:

```python
    main_model: str | None = None
```

- [ ] **Step 4: 路由计算 main_model**

`backend/app/api/routes/workflows.py`:
- 顶部 import 处,把 `from app.services.generation import discover_fields, workflow_to_api_template` 改为:

```python
from app.services.generation import discover_fields, workflow_to_api_template
from app.services.lora import main_model_from_template
```

- `list_generation_configs`(当前第 63-74 行)替换为:

```python
@router.get("/generation-configs", response_model=GenerationConfigListOut)
def list_generation_configs(
    config_repo: WorkflowGenerationConfigRepository = Depends(_config_repo),
) -> dict:
    items = []
    for cfg, name in config_repo.list_configured():
        items.append(GenerationConfigSummaryOut(
            workflow_id=cfg.workflow_id,
            workflow_name=name,
            fields=[f for f in json.loads(cfg.fields_json)],
            main_model=main_model_from_template(json.loads(cfg.api_template)),
        ))
    return {"items": items}
```

- `get_generation_config`(当前第 90-98 行)替换为:

```python
@router.get("/{workflow_id}/generation-config", response_model=GenerationConfigOut)
def get_generation_config(
    workflow_id: str,
    config_repo: WorkflowGenerationConfigRepository = Depends(_config_repo),
) -> GenerationConfigOut:
    cfg = config_repo.get_by_workflow(workflow_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="Generation config not found")
    out = GenerationConfigOut.from_model(cfg)
    out.main_model = main_model_from_template(json.loads(cfg.api_template))
    return out
```

- [ ] **Step 5: 跑测试确认通过**

```powershell
cd D:\learnAI\ComfyChat
backend\.venv\Scripts\python -m pytest backend/tests/test_generation_config_api.py -v
```

Expected: 全部 PASS(原有 5 + 新增 2 = 7)。

- [ ] **Step 6: 跑全套后端测试**

```powershell
cd D:\learnAI\ComfyChat
backend\.venv\Scripts\python -m pytest backend/tests -v
```

Expected: 原有测试全绿(1 个已知 Windows 失败 `test_check_database_returns_false_when_path_unwritable` 可接受)。

- [ ] **Step 7: 提交**

```powershell
cd D:\learnAI\ComfyChat
git add backend/app/schemas/generation.py backend/app/api/routes/workflows.py backend/tests/test_generation_config_api.py; if ($?) { git commit -m "feat(backend): add main_model to generation config responses" }
```

---

## Task 7: 前端类型 + API 客户端 + 路由 + 侧边栏

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/app/router.ts`
- Modify: `frontend/src/components/Sidebar.vue`

**Interfaces:**
- Consumes: 后端 Task 5 `LoraOut`/`LoraListOut`、Task 6 `main_model`。
- Produces:
  - `LoraSummary {name, base_family, source_url, trigger_words, models: string[]}`、`LoraList {items: LoraSummary[]}`。
  - `GenerationConfigSummary.main_model?: string | null`。
  - `api.loras.list()` → `GET /api/lora`。
  - 路由 `/loras`;侧边栏「LoRA」导航。

- [ ] **Step 1: 修改 `frontend/src/types/api.ts`**

在 `GenerationConfigSummary`(当前第 97-101 行)中追加字段:

```ts
export interface GenerationConfigSummary {
  workflow_id: string;
  workflow_name: string;
  fields: GenerationField[];
  main_model?: string | null;
}
```

文件末尾追加:

```ts
export interface LoraSummary {
  name: string;
  base_family: string | null;
  source_url: string | null;
  trigger_words: string | null;
  models: string[];
}

export interface LoraList {
  items: LoraSummary[];
}
```

- [ ] **Step 2: 修改 `frontend/src/services/api.ts`**

顶部 import 块中,`GenerationConfigList,` 行后追加 `LoraList,`。

在 `api` 对象 `generations` 之后(第 118 行 `},` 后)追加:

```ts
  loras: {
    list: () => get<LoraList>("/lora"),
  },
```

- [ ] **Step 3: 修改 `frontend/src/app/router.ts`**

`routes` 数组 `generations` 项之后追加:

```ts
  {
    path: "/loras",
    name: "loras",
    component: () => import("@/features/loras/LorasView.vue"),
  },
```

- [ ] **Step 4: 修改 `frontend/src/components/Sidebar.vue`**

- `import { Folder, Picture } from "@element-plus/icons-vue";` 改为 `import { Folder, MagicStick, Picture } from "@element-plus/icons-vue";`
- `items` 数组追加:

```ts
  { to: "/loras", label: "LoRA", icon: MagicStick, match: "/loras" },
```

- [ ] **Step 5: 类型检查**

```powershell
cd D:\learnAI\ComfyChat
npm --prefix frontend run typecheck
```

Expected: 此时 `LorasView.vue` 尚不存在,`router.ts` 的动态 import 会报 TS2307(找不到模块)。这是临时性错误,Task 8 创建该文件后消除。若报错仅此一处,继续。

- [ ] **Step 6: 提交**

```powershell
cd D:\learnAI\ComfyChat
git add frontend/src/types/api.ts frontend/src/services/api.ts frontend/src/app/router.ts frontend/src/components/Sidebar.vue; if ($?) { git commit -m "feat(frontend): lora types + api client + route + sidebar nav" }
```

---

## Task 8: LoRA 管理页

**Files:**
- Create: `frontend/src/features/loras/LorasView.vue`

**Interfaces:**
- Consumes: `api.loras.list()`、`LoraSummary`。
- Produces:页面组件(无对外接口)。

- [ ] **Step 1: 创建 `LorasView.vue`**

创建 `frontend/src/features/loras/LorasView.vue`:

```vue
<script setup lang="ts">
import { onMounted, ref } from "vue";
import { Refresh } from "@element-plus/icons-vue";
import { api } from "@/services/api";
import type { LoraSummary } from "@/types/api";

const items = ref<LoraSummary[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const data = await api.loras.list();
    items.value = data.items;
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

function fmtFamily(f: string | null): string {
  return f || "未知";
}

onMounted(load);
</script>

<template>
  <div>
    <div class="cc-toolbar">
      <h2>LoRA 管理</h2>
      <div class="cc-spacer" />
      <el-button :icon="Refresh" :loading="loading" @click="load">重新扫描</el-button>
    </div>

    <el-alert
      v-if="error"
      :title="`无法加载 LoRA：${error}`"
      type="error"
      :closable="false"
      show-icon
    />

    <el-table :data="items" v-loading="loading" stripe style="width: 100%">
      <el-table-column label="文件名" min-width="280">
        <template #default="{ row }">
          <span class="cc-name">{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column label="主模型" min-width="260">
        <template #default="{ row }">
          <template v-if="row.models.length">
            <el-tag v-for="m in row.models" :key="m" size="small" class="cc-model-tag">
              {{ m }}
            </el-tag>
          </template>
          <span v-else class="cc-muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="架构族" width="130">
        <template #default="{ row }">{{ fmtFamily(row.base_family) }}</template>
      </el-table-column>
      <el-table-column label="来源" min-width="220">
        <template #default="{ row }">
          <a
            v-if="row.source_url"
            :href="row.source_url"
            target="_blank"
            rel="noopener"
            class="cc-url"
          >{{ row.source_url }}</a>
          <span v-else class="cc-muted">—</span>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="暂无 LoRA" />
      </template>
    </el-table>
  </div>
</template>

<style lang="scss" scoped>
.cc-toolbar {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}
.cc-spacer {
  flex: 1;
}
.cc-name {
  font-weight: 500;
}
.cc-muted {
  color: #cbd5e1;
}
.cc-model-tag {
  margin: 2px 6px 2px 0;
}
.cc-url {
  color: #0ea5e9;
  text-decoration: none;
  word-break: break-all;
}
.cc-url:hover {
  text-decoration: underline;
}
</style>
```

- [ ] **Step 2: 类型检查 + 构建**

```powershell
cd D:\learnAI\ComfyChat
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Expected: 两个都 PASS(Task 7 的 TS2307 消失)。

- [ ] **Step 3: 提交**

```powershell
cd D:\learnAI\ComfyChat
git add frontend/src/features/loras/LorasView.vue; if ($?) { git commit -m "feat(frontend): lora management page" }
```

---

## Task 9: 生成界面 lora_name 下拉按主模型过滤

**Files:**
- Modify: `frontend/src/features/generations/GenerationCreateModal.vue`

**Interfaces:**
- Consumes: `api.loras.list()`、`GenerationConfigSummary.main_model`(Task 7 类型)。
- Produces:lora_name select 过滤逻辑 +「全部」切换。

- [ ] **Step 1: 修改 `<script setup>`**

`frontend/src/features/generations/GenerationCreateModal.vue` 中:

- 第 1-5 行 import 区,`import type { GenerationConfigSummary, GenerationField, GenerationSummary } from "@/types/api";` 后追加:

```ts
import type { LoraSummary } from "@/types/api";
```

- 在 `const configs = ref<GenerationConfigSummary[]>([]);` 之后追加:

```ts
const loras = ref<LoraSummary[]>([]);
const showAllLoras = ref(false);
```

- 在 `onMounted` 的 `configs.value = (await api.workflows.generationConfigs()).items;` 之前追加(即 `try {` 内首行):

```ts
    try {
      loras.value = (await api.loras.list()).items;
    } catch {
      /* LoRA 列表不可用时不阻塞生成流程 */
    }
```

- 在 `selectWorkflow` 函数定义之后追加两个 helper:

```ts
function isLoraField(f: GenerationField): boolean {
  return f.key === "lora_name";
}

function loraOptions(f: GenerationField): string[] {
  if (!isLoraField(f)) return f.options ?? [];
  const all = f.options ?? [];
  const mainModel = currentConfig.value?.main_model;
  if (!mainModel || showAllLoras.value) return all;
  const filtered = loras.value
    .filter((l) => l.models.includes(mainModel))
    .map((l) => l.name);
  return filtered.length > 0 ? filtered : all;
}
```

- [ ] **Step 2: 修改模板 — select 选项**

模板中 type === 'select' 的渲染块(当前第 389-401 行):

```html
          <el-select
            v-else-if="f.type === 'select'"
            :model-value="values[f.key]"
            @update:model-value="(v: string | number) => values[f.key] = v"
            style="width: 100%"
          >
            <el-option
              v-for="opt in f.options ?? []"
              :key="opt"
              :value="opt"
              :label="opt"
            />
          </el-select>
```

替换为:

```html
          <el-select
            v-else-if="f.type === 'select'"
            :model-value="values[f.key]"
            @update:model-value="(v: string | number) => values[f.key] = v"
            style="width: 100%"
          >
            <el-option
              v-for="opt in loraOptions(f)"
              :key="opt"
              :value="opt"
              :label="opt"
            />
          </el-select>
```

- [ ] **Step 3: 修改模板 — 「全部」切换**

在 select 渲染块之前(第 389 行 `<el-select v-else-if="f.type === 'select'"` 之前)插入:

```html
          <div v-if="isLoraField(f) && currentConfig?.main_model" class="cc-lora-toggle">
            <el-checkbox
              :model-value="showAllLoras"
              @update:model-value="(v: boolean) => showAllLoras = v"
            >显示全部 LoRA</el-checkbox>
          </div>
```

- [ ] **Step 4: 样式**

在 `<style lang="scss" scoped>` 末尾追加:

```scss
.cc-lora-toggle {
  margin-bottom: 0.25rem;
}
```

- [ ] **Step 5: 类型检查 + 构建**

```powershell
cd D:\learnAI\ComfyChat
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Expected: 两个都 PASS。

- [ ] **Step 6: 提交**

```powershell
cd D:\learnAI\ComfyChat
git add frontend/src/features/generations/GenerationCreateModal.vue; if ($?) { git commit -m "feat(frontend): filter lora_name select by workflow main model" }
```

---

## Task 10: 最终验证

**Files:**(只读,验证用)

- `frontend/`
- `backend/`

- [ ] **Step 1: 后端全量测试**

```powershell
cd D:\learnAI\ComfyChat
backend\.venv\Scripts\python -m pytest backend/tests -v
```

Expected: 原有测试 + 新增测试全部通过(1 个已知 Windows 失败可接受)。

- [ ] **Step 2: 前端类型检查 + 构建**

```powershell
cd D:\learnAI\ComfyChat
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Expected: 两个都 PASS。

- [ ] **Step 3: 手动烟测**

启动 dev 服务:

```powershell
cd D:\learnAI\ComfyChat
powershell -ExecutionPolicy Bypass -File scripts\start-dev.ps1
```

浏览器打开 `http://127.0.0.1:5173/loras`,验证:

1. 侧边栏出现「LoRA」导航;进入页面自动同步,展示 20 个 LoRA。
2. `mumu_20.safetensors` 行的主模型列显示 `z_image_turbo_int8_convrot.safetensors`。
3. 「重新扫描」按钮工作正常。
4. 打开 `http://127.0.0.1:5173/generations` →「新建生成」→ 选择 `z-image-turbo` 工作流 → 参数步的 LoRA 下拉默认只显示 Z-Image 系(如 `mumu_20`、`coser-z_*`),勾选「显示全部 LoRA」后显示完整列表。

烟测完成后停止:

```powershell
cd D:\learnAI\ComfyChat
powershell -ExecutionPolicy Bypass -File scripts\stop-dev.ps1
```

- [ ] **Step 4: 检查 git 状态,确认改动范围**

```powershell
cd D:\learnAI\ComfyChat
git status
git diff --stat HEAD~10..HEAD
```

Expected: 改动文件均在本计划 `File Structure` 表中。无意外文件进入。

- [ ] **Step 5: 推送(可选,用户决定)**

```powershell
cd D:\learnAI\ComfyChat
git push origin main
```

只有当用户明确要求时才执行。

---

## Self-Review Checklist

- [x] **Spec 覆盖:**
  - `loras` + `lora_model_links` 表 → Task 1
  - `Settings.comfyui_loras_dir` → Task 1
  - 识别纯函数(工作流追踪 + metadata/tensor)→ Task 2
  - `LoraRepository` → Task 3
  - `LoraService.sync`(object_info 清单 + 工作流 body 提取 + 清理)→ Task 4
  - `GET /lora`、`POST /lora/sync` → Task 5
  - `main_model` 追加到 generation-configs 列表 + 单条 → Task 6
  - 前端类型 + api 客户端 + 路由 + 侧边栏 → Task 7
  - `/loras` 页面 → Task 8
  - 生成界面 lora_name 过滤 + 「全部」切换 → Task 9
  - metadata 读取(`comfyui_loras_dir` → base_family/source_url/trigger_words)→ Task 4(`read_metadata` + `_metadata_for`)
  - ModelScope/HF 联网识别 → 本期不编排进 `sync`(spec 要求"多源+回退",本计划实现工作流源 + metadata 源 + 张量/架构族检测纯函数)。联网识别列为后续迭代;对非 Modelscope 下载的 LoRA 已有工作流/本地 metadata 两来源覆盖。用户已确认"查不到就留空"原则。
- [x] **Placeholder scan:** 无 TBD / TODO / "implement later" / "Similar to Task N"。所有代码块完整。
- [x] **类型一致性:** `LoraOut`/`LoraSummary` 字段名(`name`/`base_family`/`source_url`/`trigger_words`/`models`)前后端一致;`main_model` 在 schema、TS 类型、路由响应中一致;`lora_model_pairs_from_body`/`_template`/`main_model_from_template`/`detect_base_family`/`tensor_family` 命名在 Task 2 定义、Task 4/6 使用一致。
- [x] **风险已记录:** ModelScope/HF 联网识别本期未编排进 `LoraService.sync`(spec 要求"多源",本计划 Task 4 实现工作流源 + metadata 源,联网识别函数后续接入)。`comfyui_loras_dir` 未配置时 metadata 源静默跳过(测试覆盖)。张量判定只能定架构族不能定具体模型文件(已按 spec Open Questions 取舍)。
