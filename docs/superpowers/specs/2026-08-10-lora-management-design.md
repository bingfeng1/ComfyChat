# LoRA 管理页 + 生成界面按主模型过滤 LoRA

**Date:** 2026-08-10
**Status:** Design — awaiting review
**Scope:** Backend + frontend. New LoRA management page (`/loras`), automatic LoRA↔base-model mapping extraction, and generation-interface LoRA filtering by the workflow's base model.

## Goal

新增 LoRA 管理页,自动识别并维护「哪个 LoRA 用于哪个主模型」的多对多关系(以 LoRA 列表为主);生成界面按当前工作流的主模型过滤 LoRA 下拉,方便手动选择匹配的 LoRA。

## Background / Investigation Findings

映射与来源可自动识别,多来源按优先级回退:

1. **工作流连线追踪**(最强、100% 可靠):`LoraLoader` / `LoraLoaderModelOnly` 节点的 `model` 输入经 `links` 连线指回主模型加载器节点(CheckpointLoaderSimple/UNETLoader/CLIPLoader 等),取其 `ckpt_name`/`unet_name`/`model_name` 即主模型文件名。已有同类解析先例(`workflow_to_api_template`、`_conditioning_labels`)。
2. **safetensors metadata**(可靠):部分 LoRA 头部含 `base_model` / `compatible_base`(如 minimax 明确标 `MiniMax-H3`);Modelscope 下载的含 `repoId` + `url`,可借此调 ModelScope API 拿官方 `BaseModel` + `TriggerWords`(实测 `mumu_20` → Z-Image-Turbo、`coser-z` → Z-Image,都拿到了准确结果)。HuggingFace 模型卡(`huggingface.co/api/models?search={name}`)也是可靠的权威来源——实测 `Smnth_v1_NSFW1` 命中 `Kakelaka/Smnth_v1_NSFW1`,`base_model: Tongyi-MAI/Z-Image-Turbo` + `instance_prompt`。
3. **张量结构签名**(架构族判定):`lora_unet_down_blocks_*_attn1` → SD1.5;`lora_unet_down_blocks_*`(diffusers 风格)→ SDXL;`diffusion_model.transformer_blocks` → Qwen-Image;`diffusion_model.blocks.adaln_proj` → MiniMax-H3;`context_refiner/layers/noise_refiner` → Z-Image 系。

**不采用**文件名/生态知识硬猜(实测 coser-z 文件名像 SD 实为 Z-Image,已踩坑)。

已调研本机 19 个 LoRA:全部可确认主模型——SD1.5 / SDXL / Z-Image / Z-Image-Turbo / MiniMax-H3 / Qwen-Image 六系。`Smnth_v1_NSFW1` 经 HuggingFace 模型卡(`Kakelaka/Smnth_v1_NSFW1`, `base_model: Tongyi-MAI/Z-Image-Turbo`, 触发词 `Smnth_v1`)确认。

## Non-Goals

- 不做 LoRA↔模型的手动编辑入口(本次仅展示;表结构预留 `source` 字段支持未来扩展)。
- 不做触发关键字功能(现代 LoRA 大多无需触发词;ModelScope 返回的 TriggerWords 仅作可选展示,不进主流程)。
- 不改工作流/生成页的既有逻辑(仅生成界面 LoRA 下拉加过滤,并有「全部」退路)。
- 不做 LoRA 文件上传/删除/预览。

## 数据模型

### `loras` 表(新增,模型文件 `backend/app/models/lora.py`)
| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | String(255) PK | LoRA 文件名,如 `mumu_20.safetensors` |
| `base_family` | String | 架构族标签:SD1.5 / SDXL / Z-Image / MiniMax-H3 / Qwen-Image / unknown |
| `source_url` | String nullable | 来源 URL(Modelscope 等,自动填) |
| `trigger_words` | String nullable | 触发词(JSON 数组字符串;ModelScope 返回时记录,仅展示) |
| `updated_at` | String | 同步时间 |

### `lora_model_links` 表(新增)
| 字段 | 类型 | 说明 |
|---|---|---|
| `lora_name` | String(255) FK→loras.name | |
| `model_name` | String(255) | 主模型文件名,如 `z_image_turbo_int8_convrot.safetensors` |
| `source` | String(16) | `workflow` / `metadata`(本次写入;`manual` 预留。张量来源不写此表) |
| `updated_at` | String | |
| 复合主键 | | `(lora_name, model_name)` |

### `Settings` 新增字段
- `comfyui_loras_dir: str = ""`(可选)。配了才读 LoRA 文件 metadata;不配则跳过 metadata/张量来源(工作流追踪仍可用)。

## 识别逻辑(纯函数,`backend/app/services/lora.py`)

同步时对每个 LoRA 文件,按优先级合并来源:

1. **工作流追踪**(对每个 LoRA 扫描全部 workflow body + generation config api_template):找到使用该 lora_name 的 `LoraLoader*` 节点 → 沿 `model` 输入连回主模型加载器 → 记录 `(lora, model)`,source=`workflow`。
2. **metadata 读取**(需 `comfyui_loras_dir`):读文件头 JSON,取 `base_model`/`compatible_base`(定 `base_family`)、`repoId`(若有)→ 调 ModelScope API `https://modelscope.cn/api/v1/models/{repoId}` 拿 `BaseModel`(补映射)+ `TriggerWords` + 来源 URL。source=`metadata`。
3. **张量签名**:读头部 JSON 的 tensor 键前缀,判定架构族,写 `base_family`(不一定能定具体模型文件,所以 `lora_model_links` 主要靠来源 1/2;张量结果只更新 `loras.base_family`)。source=`tensor`。

联网识别细节:ModelScope 按 metadata 里的 `repoId` 精确查询;HuggingFace 按文件名 `search` 且取结果中 `id` 与文件名**完全匹配**(去掉扩展名)的候选,多个命中时取下载量最高者,全部不匹配则跳过。两者都失败时静默跳过,不报错。

合并规则:映射表以「工作流 + metadata」为准;`base_family` 以「metadata > 张量」优先。识别不到的部分留空。联网失败/超时静默跳过(不抛错、不阻塞),已有数据保留。清理失效行(文件不存在 / 主模型不再被引用)。

## 后端 API

- `GET /lora` — 触发同步一次,返回 `{items: [{name, base_family, source_url, trigger_words, models: [model_name]}]}`。
- `POST /lora/sync` — 手动重新扫描,返回同上形状。
- `GET /workflows/generation-configs` — 列表响应每个 config 追加 `main_model: str | null`(该工作流的主模型文件名;无 LoRA 节点或解析失败为 null)。这是 `GenerationCreateModal` 使用的端点(它调 `generationConfigs()` 拿全部 config),过滤逻辑依赖它。
- `GET /workflows/{id}/generation-config` — 单条响应同样追加 `main_model`(保持两处一致)。

## 前端

### `/loras` 页面(新路由 + 侧边栏「LoRA」导航)
- 打开页面自动调 `GET /lora`(同步一次);工具栏「重新扫描」按钮调 `POST /lora/sync`。
- `el-table`:列 = LoRA 文件名、主模型(`el-tag` 多个)、来源 URL(可点击链接)、架构族。
- 仅展示,无增删改按钮。
- 加载/错误/空态与现有页面一致(`v-loading` + `el-alert` + `el-empty`)。

### 生成界面过滤(`GenerationCreateModal.vue`)
- `api.workflows.generationConfigs()` 返回的 configs 现在每个含 `main_model`;`api.loras.list()` 返回全部 LoRA 及其 `models` 列表(复用 LoRA 页数据)。
- 过滤逻辑:当前工作流的 `main_model` → 在 LoRA 数据里找 `models` 含该主模型的 LoRA 文件名集合 → lora_name select 选项 = 该集合;为空则回退显示全部。
- 下拉提供「全部」选项可切回完整列表(默认按主模型过滤)。
- 前端只需新增 `api.workflows.generationConfigs()` 响应类型字段(`main_model`)与 `api.loras.list()` 客户端,无额外查询。

## 边界 / 错误处理

- ComfyUI 不可达:同步失败,页面显示错误并保留 `loras` 表缓存数据(上次同步结果仍在)。
- ModelScope 不可达:静默跳过该来源,靠工作流/本地 metadata。
- 工作流无 LoRA 节点:正常,映射为空。
- 同一 LoRA 在多个工作流配不同主模型:多对多,全部记录。
- `main_model` 无法解析:生成界面 LoRA 下拉显示全部。
- LoRA 文件被删除:同步时清理其链接。

## 测试

后端:
- `services/lora.py` 纯函数单测:构造 UI-format body / api_template / metadata / 张量 header,验证三种来源提取与优先级回退。
- 仓库 upsert / 清理测试。
- 路由测试:`GET /lora`、`POST /lora/sync`、`generation-config` 追加 `main_model`。

前端:`npm run typecheck` + `npm run build` + 手动烟测。

## Verification

1. `npm --prefix frontend run typecheck` + `npm --prefix frontend run build`
2. `backend\.venv\Scripts\python -m pytest backend/tests -v`
3. 手动冒烟:LoRA 页展示 19 个 LoRA 与主模型标签;重新扫描工作;生成界面某 Qwen 工作流 lora 下拉默认只显示 Qwen 系 LoRA,可切「全部」;SD 工作流(若有)显示 SD 系。

## Open Questions

- 张量签名到「具体主模型文件」的映射存在局限:架构族能定(SD1.5/SDXL/DiT),但同一架构族内多个具体模型文件无法区分,故 `lora_model_links` 的 `tensor` 来源本期不写具体模型,只写 `base_family`。确认该取舍。
- ModelScope / HuggingFace 识别依赖 metadata 中 `repoId`(Modelscope)或文件名能被 HF 搜索命中(HuggingFace 按文件名 search);两平台都查不到的 LoRA 只有工作流/张量两来源。联网识别失败一律静默跳过。
