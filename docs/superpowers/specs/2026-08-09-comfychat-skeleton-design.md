# ComfyChat 项目骨架设计

日期：2026-08-09
状态：自检通过，待用户复核
适用范围：ComfyChat 项目第一阶段（最小可运行骨架）

## 1. 目标与范围

ComfyChat 是一个用于管理 ComfyUI 工作流、生成任务、生成结果与相关元数据的桌面端 Web 系统，包含一个前端、一个后端和文件存储。本设计仅覆盖**第一阶段：项目骨架与最小可运行版本**，不实现任何业务功能。

第一阶段目标：
- 建立清晰、可扩展的目录结构。
- 搭建一个能启动但无业务功能的前后端最小骨架。
- 初始化 Git 仓库和 `.gitignore`，确保 `storage/` 不入版本控制。
- 为后续多表 CRUD、文件管理、ComfyUI 调用等业务实现预留接口与目录。

明确**不**包含：
- 任何业务实体（模型、工作流、生成任务等）。
- 用户登录、权限、角色管理。
- ComfyUI 工作流执行、文件上传、文件预览、生成结果展示。
- 数据库迁移与种子数据。

## 2. 技术栈

- 前端：Vue 3 + Vite + TypeScript + Vue Router + Pinia。
- 后端：Python 3.11+ + FastAPI + SQLAlchemy 2.x + Alembic + Pydantic v2。
- 数据库：SQLite（存放在 `storage/data/`）。
- ComfyUI 集成：可配置地址（环境变量），后续在 `app/integrations/comfyui/` 中以适配层方式接入。
- 包管理：前端 `npm`；后端 `uv` 或 `pip` + `venv`（在实施计划中确认）。

## 3. 顶层目录结构

```text
ComfyChat/
├─ frontend/        # Vue 前端
├─ backend/         # FastAPI 后端
├─ docs/            # 项目文档（设计、接口、数据库、功能说明）
├─ storage/         # 运行时文件，全部忽略
├─ .gitignore
├─ .env.example
└─ README.md
```

## 4. 后端内部结构

```text
backend/
├─ app/
│  ├─ main.py              # FastAPI 入口
│  ├─ core/                # 配置、数据库连接、依赖注入
│  │  ├─ config.py
│  │  ├─ database.py
│  │  └─ logging.py
│  ├─ api/                 # 路由与路由聚合
│  │  ├─ deps.py
│  │  └─ routes/
│  ├─ models/              # SQLAlchemy 模型
│  ├─ schemas/             # Pydantic 模型
│  ├─ repositories/        # 数据访问层
│  ├─ services/            # 业务逻辑
│  └─ integrations/
│     └─ comfyui/          # ComfyUI 适配层（含 client、ping 占位）
├─ migrations/             # Alembic 迁移
├─ tests/                  # 单元/集成测试
├─ pyproject.toml
└─ .env.example
```

第一阶段只实现 `main.py`、`core/config.py`、`core/database.py`、`integrations/comfyui/client.py`（含 ping 占位）、`api/routes/health.py`。其他目录与文件留空，但创建占位以保持结构。

## 5. 前端内部结构

```text
frontend/
├─ src/
│  ├─ app/                 # 路由、全局状态、根布局
│  │  ├─ router.ts
│  │  ├─ store.ts
│  │  └─ layout/
│  ├─ components/          # 通用组件
│  ├─ features/            # 业务域
│  │  ├─ dashboard/
│  │  ├─ workflows/
│  │  ├─ tasks/
│  │  └─ files/
│  ├─ services/            # API 客户端
│  ├─ types/               # TypeScript 类型
│  ├─ assets/
│  ├─ App.vue
│  └─ main.ts
├─ public/
├─ index.html
├─ package.json
├─ tsconfig.json
└─ vite.config.ts
```

第一阶段只让首页展示“ComfyChat 前端就绪”，并通过 services 调用后端 `/health` 显示状态。`features/*` 仅留占位文件。

## 6. storage 与 .gitignore

```text
storage/
├─ data/        # SQLite 数据库
├─ uploads/     # 用户上传
├─ outputs/     # ComfyUI 生成结果
├─ thumbnails/  # 缩略图
└─ tmp/         # 临时文件
```

`.gitignore` 关键规则：
- `storage/`
- `frontend/node_modules/`、`frontend/dist/`
- `backend/.venv/`、`backend/__pycache__/`
- `.env`、`*.log`、`*.pyc`、`.DS_Store`

`.env.example` 入库，包含 `COMFYUI_BASE_URL`、`COMFYUI_API_KEY`、`DATABASE_URL`、`STORAGE_ROOT` 等占位变量。

## 7. 数据流与接口（仅健康检查）

- `GET /` → `{ "name": "ComfyChat API", "version": "0.1.0" }`
- `GET /health` → `{ "status": "ok", "database": "ok", "comfyui": "unknown" }`
  - `database`：执行 `SELECT 1` 校验 SQLite 连接。
  - `comfyui`：调用 ComfyUI 客户端 ping 模板，未配置时返回 `unknown`，配置时返回 `ok` 或 `error`。
- 第一阶段不暴露任何业务 API。

## 8. 配置与运行

`.env.example`：
```env
COMFYUI_BASE_URL=http://127.0.0.1:8188
COMFYUI_API_KEY=
DATABASE_URL=sqlite:///../storage/data/comfychat.db
STORAGE_ROOT=../storage
```

启动：
- 后端：`uvicorn app.main:app --reload --port 8000`，访问 `http://127.0.0.1:8000/health` 应返回 ok。
- 前端：`npm run dev`，访问 `http://127.0.0.1:5173` 应显示占位页面并展示 `/health` 状态。

## 9. Git 初始化

- `git init` 创建本地仓库。
- 添加 `main` 分支（如使用 `git init -b main`）。
- 首次提交仅包含目录结构、`.gitignore`、`.env.example`、`README.md` 和占位文件。
- `storage/`、依赖、构建产物、`.env` 不入库。
- 后续提交由实施计划决定；不在本次设计内约定提交频率。

## 10. 验收

- `git status` 在首次提交后干净。
- 后端启动后访问 `/` 与 `/health` 返回符合第 7 节。
- 前端 `npm run dev` 启动后浏览器能看到“ComfyChat 前端就绪”并显示后端健康状态。
- `storage/` 目录结构存在但为空；`git check-ignore storage/data/comfychat.db` 返回命中。

## 11. 后续阶段（不在本次设计范围）

- 多表 CRUD：工作流、生成任务、标签、生成结果元数据等。
- 文件上传、下载、预览、缩略图。
- ComfyUI 任务下发、状态轮询、结果回传。
- 数据库迁移与种子数据。
- 简易管理后台页面（列表、详情、编辑、删除）。
