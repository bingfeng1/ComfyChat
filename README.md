# ComfyChat

ComfyUI 工作流管理与生成的桌面端 Web 工具。

## 目录

- `frontend/` Vue 3 + Vite + TypeScript 前端。
- `backend/` FastAPI + SQLAlchemy + SQLite 后端。
- `docs/` 设计、计划与后续文档。
- `storage/` 运行时文件（SQLite、上传、生成结果、缩略图、临时），**不入库**。

## 启动

后端（**国内网络必须先设清华 PyPI 镜像**；`backend/.env.example` 中的 `DATABASE_URL` 指向 `./storage/data/comfychat.db`，目录已就绪）：

```powershell
$env:PIP_INDEX_URL = 'https://pypi.tuna.tsinghua.edu.cn/simple'
python -m venv backend/.venv
backend\.venv\Scripts\python -m pip install --upgrade pip
backend\.venv\Scripts\python -m pip install -e "backend[dev]"
Remove-Item Env:PIP_INDEX_URL
backend\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

前端（`frontend/.npmrc` 已把 registry 指向 `https://registry.npmmirror.com/`，另一终端）：

```powershell
cd frontend
npm install
npm run dev
```

打开 `http://127.0.0.1:5173/`；后端根 `http://127.0.0.1:8000/`，健康检查 `http://127.0.0.1:8000/health`。

## 配置

复制 `.env.example`（与 `backend/.env.example`）为 `.env` 并按需修改 `COMFYUI_BASE_URL`、`DATABASE_URL` 等。`.env` 不入库。

## 镜像

国内网络：
- pip 默认走清华 TUNA（命令中已设置 `PIP_INDEX_URL`）。如果清华源不可用，改用阿里源 `https://mirrors.aliyun.com/pypi/simple/`。
- npm 走 npmmirror（`frontend/.npmrc` 已配置）。

## 文档

设计：`docs/superpowers/specs/2026-08-09-comfychat-skeleton-design.md`
计划：`docs/superpowers/plans/2026-08-09-comfychat-skeleton.md`
