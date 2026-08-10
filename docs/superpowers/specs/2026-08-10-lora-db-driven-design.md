# LoRA 绑定数据去硬编码 + 删除标记 + 新 LoRA AI 引导

**Date:** 2026-08-10
**Status:** Design — awaiting review
**Scope:** Backend + frontend + docs. Refactor LoRA binding data out of hardcoded seed script into DB-driven sync, add ComfyUI-deletion marking, sort deleted loras last, and guide users to have AI bind newly-seen loras.

## Goal

消除 LoRA 绑定的硬编码(seed 脚本),改为完全由 DB 驱动:sync 从 ComfyUI 发现当前 LoRA,DB 保存绑定关系;ComfyUI 中删除的 LoRA 在 DB 标记而非物理删除,并排到列表最后;首次出现且未绑定的 LoRA 在前端提示,引导用户通过 AI 完成绑定(附文档链接)。

## Background

- 现状:`backend/scripts/seed_lora_bindings.py` 硬编码了本机 20 个 LoRA 的主模型绑定(调研结果)。别人使用此项目时其 ComfyUI 无这些 LoRA,硬编码无意义且有害。
- `sync()` 已从 ComfyUI object_info 拉当前 LoRA 列表,但对不在列表中的用 `clear_stale` 物理删除。
- `loras` / `lora_model_links` 表已存绑定;`replace_links` 已修复为仅覆盖同源链接(manual 保留)。
- 本项目无 alembic;`Base.metadata.create_all` 不会给已有表加列,需 ALTER 迁移。

## Non-Goals

- 不做手动编辑 UI(绑定靠 AI/工作流/调研,页面仍只展示)。
- 不新增复杂权限/多用户。
- 不改生成界面的 LoRA 过滤逻辑。

## 数据模型

### `loras` 表新增列
- `deleted_from_comfyui: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)`(SQLAlchemy 模型)。
- 既有 DB 迁移:SQLite `ALTER TABLE loras ADD COLUMN deleted_from_comfyui BOOLEAN NOT NULL DEFAULT 0`(一次性,写入 AGENTS.md 迁移说明或提供小脚本)。

### `LoraOut` schema 新增
- `deleted_from_comfyui: bool`
- `is_new: bool`(本次 sync 首次出现的 LoRA,且当前无任何绑定)

## sync() 语义(改 `services/lora.py` + `repositories/lora.py`)

1. `list_installed()` 从 ComfyUI 拉当前 LoRA 文件名(已有)。
2. 对每个 installed LoRA:
   - 记录该 LoRA 在 sync 前是否存在于 DB(`pre_existing`)。
   - `upsert_lora`(metadata 来源填 base_family/source_url/trigger_words,已有)。
   - `mark_present(name)`:`deleted_from_comfyui = False`。
   - 工作流链接:`replace_links(name, pairs, "workflow")`(已有,仅覆盖 workflow 源)。
3. 对 DB 中**不在** installed 的 LoRA:`mark_deleted(name)` 置 `deleted_from_comfyui = True`(不删记录、不删绑定)。
4. 移除 `clear_stale` 的物理删除语义(改为 `mark_missing` = 对不在 installed 的行标记 deleted)。
5. `is_new` 判定:sync 开始前该 LoRA 不在 `loras` 表(首次出现)且当前 `lora_model_links` 无该 LoRA 的行。

### `list_all()` 排序
- `ORDER BY deleted_from_comfyui ASC, name ASC` → **已删除排最后**,未删除按名称升序。
- 返回每行含 `deleted_from_comfyui`;`is_new` 由 sync 结果补充。

## 后端 API

- `GET /lora` — sync 后返回 `{items: [{name, base_family, source_url, trigger_words, models, deleted_from_comfyui, is_new}]}`,items 已按 deleted 升序排序。
- `POST /lora/sync` — 同上。
- 无新增端点。

## 前端(`LorasView.vue`)

### 已删除展示
- 行:`deleted_from_comfyui` 为 true 时加 `.cc-deleted` 类(灰显文字/降低不透明度)+ 文件名后「已删除」`el-tag`(type="info")。
- 筛选:绑定状态下拉旁新增「状态」下拉或复用——新增选项 `已删除`(过滤 `deleted_from_comfyui === true`)/ `正常`;clearable 默认全部。
- 排序:依赖后端返回顺序(已删除在最后),前端不重排。

### 新 LoRA AI 引导
- `computed newUnboundLoras = items.filter(i => i.is_new && i.models.length === 0)`。
- `newUnboundLoras.length > 0` 时在工具栏下方显示 `el-alert`(type="info",可关闭):
  - 文案:「检测到 N 个新 LoRA 尚未绑定主模型。可让 AI 帮你查询并绑定。查看说明 →」
  - 含链接 `<a :href="bindingGuideUrl" target="_blank">AI 绑定指南</a>`。
- `bindingGuideUrl`:前端常量指向 docs 文档的相对/绝对路径。因 docs 不在前端静态目录,用项目内相对链接或仓库 URL;取实现最简者(可指向 `/docs/lora-ai-binding-guide.md` 若 vite 代理可达,否则用前端静态资源或直接展示文档路径文本)。**确认点见 Open Questions。**

## 文档

### `docs/lora-ai-binding-guide.md`(新增)
内容:教 AI/开发者如何确定一个 LoRA 的主模型并写入绑定:
- 方法 1:工作流追踪(UI body 连线 / api_template)→ 已自动,无需人工。
- 方法 2:读 safetensors 文件头 metadata(`base_model`/`compatible_base`/`repoId`)。
- 方法 3:查 ModelScope API(`/api/v1/models/{repoId}` 返回 BaseModel/TriggerWords)。
- 方法 4:查 HuggingFace API(`/api/models?search={name}` 返回 base_model tag)。
- 方法 5:张量结构签名判定架构族。
- 写入 DB:直接更新 `loras.base_family` / `lora_model_links`(source=`manual`),或通过项目接口。
- 示例:以 `mumu_20` → `z_image_turbo_*` 为例。

## Edge Cases

- ComfyUI 不可达:sync 返回 error,不动 DB(已有)。
- LoRA 从 ComfyUI 删除后重新出现:`mark_present` 恢复 deleted=false,绑定保留。
- 新 LoRA 已通过工作流自动绑定:`is_new=true` 但 `models.length>0` → 不提示。
- 迁移列已存在:ALTER 幂等(先查 PRAGMA)。

## Verification

1. 后端:`backend\.venv\Scripts\python -m pytest backend/tests -v`(新增 sync 标记/恢复/排序/is_new 测试)。
2. 前端:`npm --prefix frontend run typecheck` + `npm --prefix frontend run build`。
3. 手动烟测:
   - LoRA 页:现有 20 个排序正常,无「已删除」。
   - 临时改名/删除一个 ComfyUI LoRA → 同步后该行灰显 + 「已删除」+ 排最后。
   - 放回 → 恢复。
   - 新增一个 LoRA 文件 → 同步后出现提示条(未绑定新 LoRA)+ 链接。
   - 用工作流绑定后重新扫描 → 提示消失。

## Open Questions

- **docs 链接可达性**:`docs/` 不在 vite 静态服务目录。**已定**:将指南复制一份到 `frontend/public/docs/lora-ai-binding-guide.md`(vite 会自动静态服务 `/docs/lora-ai-binding-guide.md`),前端 `href` 指向该路径;源文档保留在 `docs/` 供仓库阅读。两处内容保持一致(实现时同步)。
- 迁移脚本放哪:`backend/scripts/` 或 AGENTS.md 说明。**已定**:在 AGENTS.md 记录一次性 ALTER 命令,并提供一个幂等迁移函数放 `app/core/migrate.py`(启动时检测列是否存在,不存在则 ALTER,幂等)。
