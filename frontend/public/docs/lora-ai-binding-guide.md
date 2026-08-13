# LoRA 元数据补全指南（给 AI / 开发者）

本指南描述如何把 LoRA 元数据（主模型绑定、触发词、架构族、NSFW）从零补齐到 `loras` 表 + `lora_model_links` 表。前台 `/loras` 页面只读这两个表，不补的话 LoRA 在生成界面里就选不到。

## 背景

- LoRA 是应用在主模型（checkpoint / unet / diffusion model）上的微调权重。一个 LoRA 可适用于多个主模型（多对多）。
- 绑定关系：`lora_model_links` 表 `(lora_name, model_name, source)` 复合主键；`source` ∈ `{workflow, manual}`。系统 sync 只覆盖 `workflow`，`manual` 不会被冲掉。
- `loras` 表存：`base_family`（架构族）、`source_url`、`trigger_words`、`is_nsfw`、`deleted_from_comfyui`、`is_new`。
- LoRA 文件默认在 `${COMFYUI_USERDATA_DIR}` 之上 4 层找 `ComfyUI/models/loras/`；具体路径由 `.env` 的 `comfyui_loras_dir` 覆盖。Windows 上本机常见路径示例：
  ```
  D:\ComfyUI\ComfyUI_windows_portable\ComfyUI\models\loras\
  ```
- 关键 API：
  - `GET    /api/lora` — 列出全部（返回 `name`、`base_family`、`source_url`、`trigger_words`、`models[]`、`is_nsfw`、`is_new`、`deleted_from_comfyui`）。
  - `POST   /api/lora/{name}/nsfw`  body `{"is_nsfw": bool}` — 改 NSFW 标记。
  - `POST   /api/lora/{name}/trigger` body `{"trigger_words": str|null}` — 改触发词。空串 / 全空白会被存 NULL。

## 完整流程（按顺序执行）

### 步骤 1：读 safetensors header

LoRA 文件前 8 字节是小端 `uint64` JSON header 长度，接着是 JSON。`__metadata__` 子键是 metadata。**注意**：`ss_tag_frequency` 在文件里是 **JSON 编码字符串**，不是 dict，必须二次 `json.loads`。伪代码：

```python
import struct, json
from pathlib import Path

def read_header(p: Path) -> dict | None:
    try:
        with open(p, "rb") as f:
            (length,) = struct.unpack("<Q", f.read(8))
            if length > 8 * 1024 * 1024:
                return None
            return json.loads(f.read(length))
    except Exception:
        return None

def coerce_dict(v):
    if isinstance(v, dict): return v
    if isinstance(v, str) and v.strip().startswith("{"):
        try: return json.loads(v) if isinstance((d := json.loads(v)), dict) else None
        except Exception: return None
    return None
```

### 步骤 2：判 `base_family`（架构族）

优先级从高到低：

1. **`__metadata__.ss_base_model_version`** 直接判定：
   - `"zimage"` / 含 `z-image` / `z_image` → `"Z-Image"`
   - 含 `sdxl` → `"SDXL"`
   - 含 `sd1.5` / `sd15` → `"SD1.5"`
2. **`__metadata__.base_model` / `compatible_base`** 走 `_FAMILY_MARKERS` 字典（在 `backend/app/services/lora.py`）：
   - `MiniMax-H3` / `minimax_h3` / `minimax` → `"MiniMax-H3"`
   - `Z-Image` / `z-image` / `zimage` / `tongyi-mai/z-image` → `"Z-Image"`
   - `Qwen-Image` / `qwen-image` / `tongyi-mai/qwen-image` → `"Qwen-Image"`
   - `SDXL` / `sdxl` / `sd_xl` → `"SDXL"`
   - `SD1.5` / `sd1.5` / `sd15` → `"SD1.5"`
3. **tensor key 签名回退**（`tensor_family` 函数）：
   - `lora_te_text_model_encoder` → `SD1.5`
   - `diffusion_model.transformer_blocks` 或 `transformer_blocks.0.attn` → `Qwen-Image`
   - `diffusion_model.blocks.*adaln_proj` → `MiniMax-H3`
   - `diffusion_model.layers.*adaln_modulation` → `Z-Image`
   - `context_refiner` / `noise_refiner` → `Z-Image`
   - `lora_unet_down_blocks*downsamplers` → `SDXL`
   - `lora_te_*` 或 `lora_unet_*attn1` → `SD1.5`

**已知盲点**：`tensor_family` 把 `transformer.transformer_blocks.*attn*`（无 `diffusion_model.` 前缀，Krea2 / Flux 系）误判为 Qwen-Image。如果遇到 tensor key 是 `transformer.final_layer.linear`、`transformer.img_in`、`transformer.transformer_blocks` 的 LoRA，**保持 `base_family = NULL`**（或新建家族标记如 `Krea` / `Flux`），不要写 Qwen-Image。

### 步骤 3：判主模型绑定（`lora_model_links` 行）

优先级：

1. **方法 1（自动，无需人工）**：`workflow` 源。系统 sync 已经从工作流里追踪 `LoraLoader*` → 主模型加载器链路，无需介入。
2. **方法 2（自动）**：`base_family` 已知时，**绑到本机该族所有主模型文件**。本项目主模型在 `ComfyUI/models/{checkpoints,unet,diffusion_models}/` 下。
   - `SD1.5` → 该族所有 `*.safetensors` / `*.ckpt`
   - `SDXL` → 同上
   - `Z-Image` → `z_image_turbo_bf16.safetensors` + `z_image_turbo_int8_convrot.safetensors`
   - `MiniMax-H3` → `minimax_h3_fl2va_pruned_int8_convrot.safetensors` + `minimax_h3_ref2va_pruned_int8_convrot.safetensors`
   - `Qwen-Image` → `qwen_image_2512_fp8_e4m3fn.safetensors`
   - `Krea` / `Flux` 系 → 看本机有什么，唯一就绑唯一
3. **方法 3（人工 / AI）**：metadata 有具体模型名（`base_model` 写成完整文件名）→ 绑该具体文件。
4. **方法 4（联网，仅 `source_url` 已设时）**：Modelscope `Data.BaseModel` 给的是 `["Tongyi-MAI/Z-Image-Turbo@master"]` 这种 repo 引用，**不是本地文件名**，需把 `@master` 去掉后用本机已有的 Z-Image 模型对应。

### 步骤 4：找 `trigger_words`（触发词）

按下面顺序尝试，**找到就用，不再降级**。

#### 4.1. safetensors metadata（最可靠，零成本）

优先级：

1. `instance_prompt` / `trigger_word` / `trigger_words` / `trigger`（HF 惯例）— 字符串原样取。
2. `ss_tag_frequency` 第一键，去掉前缀 `^\d+_?`。ai-toolkit / StableSwarmUI 训练时把唯一 class token 写在这里（count=1）。
3. `name` / `ss_output_name` — 训练输出名。

#### 4.2. 过滤自动生成的伪 trigger

下列规则命中就**当作没有 trigger**：

```python
_RE_TRAINING_ID = re.compile(
    r"^training[-_]?\d+|"
    r".*_copy(?:_copy)+$|"
    r"^my_first_lora(?:_v\d+)?(?:_copy)*$|"
    r"_zib_lokr\d+_\d+_.*|_zib_.*_1e-\d+_.*",
    re.I,
)
```

并屏蔽集合：`{"put_loras_here", "loras", "lora", "untitled"}`。

**典型伪 trigger 例子**：`training_2867257-20260119224021235`、`my_first_lora_v1_copy_copy_copy_copy_copy`、`PornMaster_bukkake_zimage_v2`（虽然是输出名但其实是 class token — 这条**不算**伪）、`Z Image Turbo - Tiny Panties`（带版本后缀，伪）、`spread legs v1-1`（带版本后缀，伪）。

#### 4.3. 联网补全（仅 `source_url` 已有且 metadata 没拿到）

**HuggingFace**：
```
GET https://huggingface.co/api/models/{owner}/{name}
```
- `cardData.instance_prompt` — 首选
- `cardData.trigger_word` / `trigger_words` — 备选
- `tags[]` 中 `triggers:<token>` 形式的条目

**Modelscope**：
```
GET https://modelscope.cn/api/v1/models/{owner}/{name}
```
- **`Data.TriggerWords` 是 list**（不是字符串！），取第一个非空元素
- `Data.MuseInfo.triggerWords` / `trigger_word` / `trigger` — 备选
- `Data.ReadMeContent` 正则：`trigger[_ ]?words?\s*[:：]\s*[\`"]?([^\`"\n]+)`

**HF search 找源**（已知 LoRA 没 source_url 时）：
```
GET https://huggingface.co/api/models?search={name}&limit=10
```
按下载量或 repo 名匹配后取第一个候选。

#### 4.4. 已知"无 trigger"清单（不要瞎联网）

下列 LoRA 是加速 / turbo / 控制类，**本来就没有触发词**，跳过联网：

- `LCM_LoRA_SDXL` / `LCM_LoRA_SDv15` (`latent-consistency/lcm-lora-*`)
- `sdxl_lightning_{2,4,8}step_lora` (`ByteDance/SDXL-Lightning`)
- `Wuli-Qwen-Image-2512-Turbo-LoRA-2steps-*` (`Wuli-art/Qwen-Image-2512-Turbo-LoRA-2-Steps`)
- `krea2_darkbrush` (`krea/Krea-2-LoRA-darkbrush`)
- 全部 `ip-adapter-*`
- 全部 `minimax_h3_*turbo*` (T2V 类加速 LoRA)
- `v3_sd15_adapter.ckpt` (T2I-Adapter)

### 步骤 5：判 `is_nsfw`

文件名匹配（**连字符归一为下划线**后比对）+ metadata 文本匹配。关键词列表（节选）：

```
nsfw, porn, cum, anal, blowjob, blow_job,
pussy, penis, dick, facial, fisting, bukkake,
sex, fuck, oiled, nipple_clamp, lingerie, panty,
tentacle, tentacled, doggy, lick_ass, pov, lezdom,
cunnilingus, orgasm, hentai,
```

metadata 额外关键词：`cum on body, vaginal, anatomy, anus, asshole, penetration, blow_job, masturbate, clitoris, labia, semen, substance, pornmaster, double_bj, foot_lick, foot-lick, kneeling, sex_machine, spread legs, tiny panties`。

判定为真：`is_nsfw = 1`。前台 `/loras` 页面"显示 NSFW"开关打开后才显示该列。

### 步骤 6：写库

#### 直接 sqlite3（推荐 — 一次性处理批量 LoRA）

`storage/data/comfychat.db` 在 uvicorn 运行时仍可写（共享锁 + `PRAGMA busy_timeout = 30000`）。模板：

```python
import sqlite3
con = sqlite3.connect("storage/data/comfychat.db", timeout=30)
con.execute("PRAGMA busy_timeout = 30000")
cur = con.cursor()

# 主模型绑定（INSERT OR IGNORE 跳过已存在的复合主键）
cur.execute(
    """INSERT OR IGNORE INTO lora_model_links
       (lora_name, model_name, source, updated_at)
       VALUES (?, ?, 'manual', strftime('%Y-%m-%dT%H:%M:%fZ','now'))""",
    (lora_name, model_name),
)
con.commit()

# 更新 base_family / source_url / trigger_words / is_nsfw
cur.execute(
    "UPDATE loras SET base_family=?, source_url=?, trigger_words=?, is_nsfw=?, "
    "updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE name=?",
    (family, url, trig, 1 if nsfw else 0, lora_name),
)
con.commit()
```

#### 通过 API（前台 UI 已经实现了 `触发词` 单元格双击保存）

```bash
curl -X POST http://127.0.0.1:8000/lora/<name>/trigger \
  -H 'Content-Type: application/json' \
  -d '{"trigger_words":"<trigger>"}'

curl -X POST http://127.0.0.1:8000/lora/<name>/nsfw \
  -H 'Content-Type: application/json' \
  -d '{"is_nsfw":true}'
```

注意 URL 编码：带反斜杠的子目录 LoRA 名（如 `ip-adapter\ip-adapter-faceid_sd15_lora.safetensors`）要 `encodeURIComponent`（`%5C`）。

## 已知坑

1. **`ss_tag_frequency` 是字符串**，不是 dict — 必须 `json.loads` 二次解析。
2. **Modelscope `TriggerWords` 是 list**，不是 str — 取首个非空。
3. **`lora_model_links` 复合主键** `(lora_name, model_name)` — 用 `INSERT OR IGNORE`，不要先删后插，否则会冲掉 `workflow` source 的链接。
4. **`workflow` source 链接不要碰** — 只插 `source='manual'`。
5. **`is_nsfw` 默认 `False`** — 前台"显示 NSFW"开关关闭时整列隐藏。
6. **uvicorn 运行时 SQLite 可写**，但写后前端缓存不会自动失效（下次刷新页面才能看到）。无需重启后端。
7. **`tensor_family` 把 Krea2 误判为 Qwen-Image** — 检查时若发现新 LoRA tensor key 是 `transformer.final_layer.linear` + `transformer.img_in` 这种 Flux 风格，**保留 base_family 为 NULL**，不要写 Qwen-Image。
8. **`is_nsfw` / `trigger_words` 的前端单元格** — 双击进入编辑，blur 或 Enter 保存，Esc 取消；空串保存自动 NULL。

## 判定原则

- 能确定具体主模型就绑具体模型；只能定架构族时绑该族全部（生成界面按主模型过滤更灵活）。
- 触发词拿不到就留空（不要瞎填）。
- NSFW 拿不准就留 `False`，宁可漏报不要误报。
- 联网查询失败静默跳过，不影响已有数据。
- 永远不要 `Out-File` 写 SQLite 文件（会被 uvicorn 锁住 IOException），用 `sqlite3` 模块直接 UPDATE。

## 示例：mumu_20.safetensors

1. safetensors metadata：无 `__metadata__`（文件没有）。
2. `source_url = https://www.modelscope.cn/models/duanjie4b/mumu`（之前 sync 时从某工作流推断或人工填）。
3. GET `https://modelscope.cn/api/v1/models/duanjie4b/mumu`：
   - `Data.TriggerWords = ["mumu"]` → `trigger_words = "mumu"`
   - `Data.SubVisionFoundation = "Z_IMAGE_TURBO"` → 绑 `z_image_turbo_int8_convrot.safetensors` 和 `z_image_turbo_bf16.safetensors`
   - `Data.AigcAttributes` → `OfficialTags = ["cg-fantasy", "character-strong", "clothing"]`（只是标签，不是 trigger，跳过）
4. `base_family = "Z-Image"`。
5. `is_nsfw = 0`（文件名无 NSFW 关键词）。
