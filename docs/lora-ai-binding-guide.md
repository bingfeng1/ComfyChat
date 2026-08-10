# LoRA 主模型绑定指南（给 AI / 开发者）

当 LoRA 管理页提示「检测到新 LoRA 尚未绑定主模型」时，可以按本指南让 AI 或开发者确定该 LoRA 适用于哪个主模型，并写入绑定。

## 背景

- LoRA 是应用在主模型（checkpoint / unet / diffusion model）上的微调权重。一个 LoRA 可以适用于多个主模型（多对多）。
- 绑定关系存在数据库 `lora_model_links` 表：`lora_name` + `model_name`（复合主键）+ `source`（`workflow` 自动 / `manual` 手动）。
- `loras` 表存 LoRA 元数据：`base_family`（架构族）、`source_url`、`trigger_words`、`deleted_from_comfyui`。
- `GET /api/lora` 返回每个 LoRA 的 `models` 列表、`deleted_from_comfyui`、`is_new`。

## 确定主模型的方法（按可靠度排序）

### 方法 1：工作流连线追踪（已自动，无需人工）
ComfyUI 工作流里，`LoraLoader*` 节点的 `model` 输入会连到主模型加载器（CheckpointLoaderSimple / UNETLoader / DiffusionLoader 等）。系统已自动从工作流推导，无需手动。

### 方法 2：读 safetensors 文件头 metadata
LoRA 文件前 8 字节是 JSON header 长度（小端），后面是 JSON。检查 `__metadata__`：
- `base_model` / `compatible_base`：直接写主模型名（如 `MiniMax-H3`）。
- `repoId` / `url` / `author`：指向来源（Modelscope 等），可据此查详情页。

### 方法 3：查 ModelScope API
若 metadata 有 `repoId`（如 `jcplus/coser-z`）：
```
GET https://modelscope.cn/api/v1/models/{repoId}
```
响应 `Data.BaseModel` 给出基础模型（如 `["Tongyi-MAI/Z-Image@master"]`），`Data.MuseInfo` 可含 `triggerWords`。

### 方法 4：查 HuggingFace API
按文件名搜索：
```
GET https://huggingface.co/api/models?search={name}
```
取 `id` 与文件名完全匹配（去扩展名）的候选；tags 里的 `base_model:Tongyi-MAI/Z-Image-Turbo` 即主模型；`cardData.instance_prompt` 为触发词。

### 方法 5：张量结构签名判定架构族
读 header 的 tensor 键名，判定架构族（无法区分同族内具体文件）：
- `lora_unet_down_blocks_*_attn1` / `lora_te_text_model_encoder` → SD1.5
- `lora_unet_down_blocks_*`（diffusers 风格）→ SDXL
- `diffusion_model.transformer_blocks` → Qwen-Image
- `diffusion_model.blocks.adaln_proj` → MiniMax-H3
- `context_refiner` / `noise_refiner` → Z-Image
- `diffusion_model.layers.adaLN_modulation` → Z-Image

## 写入绑定

绑定数据由系统 sync 从工作流自动写入（source=`workflow`）。人工/AI 确认后，可：

1. **通过数据库直接写入**（source=`manual`）：
   - `loras` 表 upsert 该 LoRA（填 `base_family` / `source_url` / `trigger_words`）。
   - `lora_model_links` 表插入 `(lora_name, model_name, source='manual')`。同一 `(lora_name, model_name)` 已存在时更新 `source` 即可，不要重复插入（复合主键）。
   - 系统 sync 只覆盖 `workflow` 源链接，`manual` 链接保留，不会被冲掉。

2. **通过后端代码/接口**：若项目提供写入接口，用它；否则用方案 1。

## 示例

`mumu_20.safetensors`：
- metadata 无 `base_model`，但 Modelscope 页面 `duanjie4b/mumu` 的 `BaseModel` 为 `["Tongyi-MAI/Z-Image-Turbo@master"]`，触发词 `mumu`。
- 用户工作流 `z-image-turbo` 已将其连到 `z_image_turbo_int8_convrot.safetensors`（自动 workflow 源）。
- manual 补充可绑 `z_image_turbo_bf16.safetensors`。

## 判定原则

- 能确定具体文件就绑具体文件；只能定架构族时，可绑该族全部主模型（生成界面按主模型过滤更灵活）。
- 查不到就不填，留空等后续。
- 联网查询失败静默跳过，不影响已有绑定。
