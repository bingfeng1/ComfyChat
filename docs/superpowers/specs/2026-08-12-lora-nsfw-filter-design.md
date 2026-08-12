# LoRA NSFW 过滤功能设计

## 概述

为 LoRA 管理页面添加 NSFW（Not Safe For Work）内容过滤功能，支持全局开关和标记管理。

## 需求

- 用户可标记 LoRA 为 NSFW
- 全局开关控制是否显示 NSFW LoRA
- 开关状态持久化到 localStorage
- 过滤全局生效（LoRA 列表、生成配置选择器等）

## 技术方案

### 后端改动

1. **数据库迁移**
   - 在 `loras` 表新增 `is_nsfw` 字段（Boolean，默认 False）
   - 在 `app/core/migrate.py` 中添加 `_ensure_column` 调用

2. **API 扩展**
   - `LoraOut` schema 新增 `is_nsfw` 字段（返回给前端）

3. **Repository 层**
   - 新增 `LoraRepository.update_nsfw(name, is_nsfw)` 方法

### 前端改动

1. **类型定义**
   - `LoraSummary` 接口新增 `is_nsfw: boolean` 字段

2. **全局状态管理**
   - 使用 Vue `provide/inject` 或组合式函数管理 NSFW 开关状态
   - 状态持久化到 `localStorage`（key: `cc_nsfw_enabled`）
   - 默认值：`true`（显示 NSFW）

3. **LoRA 列表页面**
   - 右上角添加 Toggle Switch 控件（"显示 NSFW"）
   - 表格新增"NSFW"列，显示标签
   - 表格新增"NSFW"筛选选项（全部/是/否）
   - 点击 Toggle 时，前端根据开关状态自行过滤列表显示

4. **全局过滤**
   - 创建 `useNsfwFilter` composable 函数
   - 所有使用 LoRA 选择的组件注入此状态
   - 过滤逻辑在前端完成（基于 `is_nsfw` 字段和开关状态）

### 文件变更清单

| 文件 | 改动 |
|------|------|
| `backend/app/core/migrate.py` | 添加 `is_nsfw` 列迁移 |
| `backend/app/schemas/lora.py` | `LoraOut` 新增 `is_nsfw` 字段 |
| `backend/app/repositories/lora.py` | 新增 `update_nsfw()` 方法 |
| `backend/app/api/routes/lora.py` | 无需改动（`LoraOut` 已返回完整数据） |
| `frontend/src/types/api.ts` | `LoraSummary` 新增 `is_nsfw` 字段 |
| `frontend/src/composables/useNsfwFilter.ts` | 新增：NSFW 状态管理 composable |
| `frontend/src/features/loras/LorasView.vue` | 添加 Toggle、NSFW 列、NSFW 筛选 |
| `frontend/src/services/api.ts` | 无需改动（返回完整列表，前端过滤） |

### 数据流

```
用户点击 Toggle
    ↓
updateNsfwEnabled(false)  // localStorage 更新
    ↓
useNsfwFilter 状态变化
    ↓
LorasView / 其他组件监听状态
    ↓
前端根据 is_nsfw 字段自行过滤显示
```

### 迁移策略

1. 运行 `Base.metadata.create_all()` 不会添加新列（已存在表）
2. 使用 `migrate.py` 中的 `_ensure_column` 方法：
   - 检查 `PRAGMA table_info(loras)` 是否已有 `is_nsfw` 列
   - 不存在则执行 `ALTER TABLE loras ADD COLUMN is_nsfw BOOLEAN NOT NULL DEFAULT 0`
3. 幂等设计：重复执行不会出错

### 边界情况

- **ComfyUI 同步**：`sync()` 不修改 `is_nsfw`，保留用户标记
- **删除的 LoRA**：`is_nsfw` 标记跟随 LoRA 记录
- **空值处理**：默认 `False`，旧数据不受影响
