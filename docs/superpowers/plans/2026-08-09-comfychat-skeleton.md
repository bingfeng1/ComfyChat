# ComfyChat 项目骨架实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在空目录 `D:\learnAI\ComfyChat` 中搭建 ComfyChat 第一阶段最小可运行骨架：Vue 3 + Vite + TS 前端、FastAPI + SQLAlchemy + SQLite 后端、ComfyUI 适配层占位、`storage/` 完全不入库、Git 仓库初始化。

**Architecture:** 单仓库四区（`frontend/`、`backend/`、`docs/`、`storage/`），后端按 `core/api/models/schemas/repositories/services/integrations` 分层，前端按 `app/components/features/services/types` 分层。首阶段仅暴露 `/` 与 `/health`，前端只展示“ComfyChat 前端就绪”与后端健康状态。

**Tech Stack:**
- 前端：Vue 3.4+、Vite 5+、TypeScript 5+、Vue Router 4、Pinia 2。
- 后端：Python 3.11+、FastAPI 0.110+、Uvicorn、SQLAlchemy 2.x、Pydantic v2、httpx（ComfyUI 客户端）、pytest。
- 工具：npm 10+、pip/venv、Git 2.40+。

## Global Constraints

- 工作目录：`D:\learnAI\ComfyChat`（Windows + PowerShell 5.1）。运行命令时使用 `bash` 工具的 `workdir` 参数，不要在命令内 `cd`。
- 所有 PowerShell 命令按规范使用 `cmd1; if ($?) { cmd2 }` 串联，避免 `&&`。
- `storage/` 整目录及其子目录全部不进入版本控制；`storage/data/comfychat.db` 必须被忽略。
- `.env` 不入库；`.env.example` 必须入库。
- 提交粒度：以任务为单位；每个任务一个提交，提交信息使用约定式提交（`chore: ...`、`feat: ...`）。
- 不在第一阶段实现任何业务 API、业务模型、文件上传、ComfyUI 工作流。
- 不引入 Tailwind、Element Plus、Ant Design Vue 等 UI 库，保持骨架纯净。
- 不写 license、CI、Docker、部署脚本。
- ComfyUI 客户端在未配置 `COMFYUI_BASE_URL` 时必须返回 `unknown` 而不是抛错。

## File Structure

```
ComfyChat/
├─ .gitignore
├─ .env.example
├─ README.md
├─ docs/
│  └─ superpowers/
│     ├─ specs/2026-08-09-comfychat-skeleton-design.md   # 已存在
│     └─ plans/2026-08-09-comfychat-skeleton.md          # 本文件
├─ storage/
│  ├─ data/.gitkeep
│  ├─ uploads/.gitkeep
│  ├─ outputs/.gitkeep
│  ├─ thumbnails/.gitkeep
│  └─ tmp/.gitkeep
├─ backend/
│  ├─ pyproject.toml
│  ├─ .env.example
│  ├─ app/
│  │  ├─ __init__.py
│  │  ├─ main.py
│  │  ├─ core/
│  │  │  ├─ __init__.py
│  │  │  ├─ config.py
│  │  │  └─ database.py
│  │  ├─ api/
│  │  │  ├─ __init__.py
│  │  │  ├─ deps.py
│  │  │  └─ routes/
│  │  │     ├─ __init__.py
│  │  │     └─ health.py
│  │  ├─ models/__init__.py
│  │  ├─ schemas/__init__.py
│  │  ├─ repositories/__init__.py
│  │  ├─ services/__init__.py
│  │  └─ integrations/
│  │     ├─ __init__.py
│  │     └─ comfyui/
│  │        ├─ __init__.py
│  │        └─ client.py
│  └─ tests/
│     ├─ __init__.py
│     ├─ test_health.py
│     ├─ test_config.py
│     ├─ test_database.py
│     └─ test_comfyui_client.py
└─ frontend/
   ├─ package.json
   ├─ tsconfig.json
   ├─ tsconfig.node.json
   ├─ vite.config.ts
   ├─ index.html
   ├─ .gitignore
   ├─ public/.gitkeep
   └─ src/
      ├─ main.ts
      ├─ App.vue
      ├─ env.d.ts
      ├─ shims-vue.d.ts
      ├─ app/
      │  ├─ router.ts
      │  └─ layout/.gitkeep
      ├─ components/.gitkeep
      ├─ features/
      │  ├─ dashboard/.gitkeep
      │  ├─ workflows/.gitkeep
      │  ├─ tasks/.gitkeep
      │  └─ files/.gitkeep
      ├─ services/api.ts
      ├─ types/api.ts
      └─ assets/.gitkeep
```

## Task Decomposition

任务编号用于提交与审阅。任务 1 建立仓库与忽略规则，任务 2-3 搭后端核心，任务 4-5 搭后端接口与 ComfyUI 适配，任务 6-7 搭前端骨架，任务 8 串联前后端验证并写 README。

---

### Task 1: 初始化仓库与目录骨架

**Files:**
- Create: `D:\learnAI\ComfyChat\.gitignore`
- Create: `D:\learnAI\ComfyChat\.env.example`
- Create: `D:\learnAI\ComfyChat\storage\data\.gitkeep`
- Create: `D:\learnAI\ComfyChat\storage\uploads\.gitkeep`
- Create: `D:\learnAI\ComfyChat\storage\outputs\.gitkeep`
- Create: `D:\learnAI\ComfyChat\storage\thumbnails\.gitkeep`
- Create: `D:\learnAI\ComfyChat\storage\tmp\.gitkeep`
- Create: `D:\learnAI\ComfyChat\docs\superpowers\plans\2026-08-09-comfychat-skeleton.md`（本文件，从 `docs/superpowers/specs/` 引用设计文档）

**Interfaces:**
- Consumes: 无。
- Produces: 已初始化的 Git 仓库 `main` 分支；`storage/` 全部被忽略；根级 `.env.example`。

- [ ] **Step 1: 创建空目录与占位文件**

在 `D:\learnAI\ComfyChat` 中创建以下目录（如不存在）：

- `docs/superpowers/specs/`（设计文档已存在）
- `docs/superpowers/plans/`
- `storage/data`、`storage/uploads`、`storage/outputs`、`storage/thumbnails`、`storage/tmp`

在每个 `storage/*` 子目录中创建名为 `.gitkeep` 的空文件，用于让空目录进入版本控制；`docs/superpowers/plans/` 中创建本计划文件。

- [ ] **Step 2: 编写根级 `.gitignore`**

写入 `D:\learnAI\ComfyChat\.gitignore`：

```gitignore
# Storage (runtime files; keep directory structure, ignore contents)
storage/**
!storage/**/.gitkeep

# Frontend
frontend/node_modules/
frontend/dist/
frontend/.vite/

# Backend
backend/.venv/
backend/__pycache__/
backend/**/__pycache__/
backend/*.egg-info/

# Env & secrets
.env
.env.local
*.local

# Logs & caches
*.log
*.pyc
*.sqlite
*.sqlite-journal

# OS
.DS_Store
Thumbs.db
```

- [ ] **Step 3: 编写根级 `.env.example`**

写入 `D:\learnAI\ComfyChat\.env.example`：

```env
# ComfyUI
COMFYUI_BASE_URL=
COMFYUI_API_KEY=

# Backend
DATABASE_URL=sqlite:///./storage/data/comfychat.db
STORAGE_ROOT=./storage
```

- [ ] **Step 4: 初始化 Git 仓库并提交**

运行：

```powershell
git init -b main
git add .gitignore .env.example docs/ storage/
git -c user.name="ComfyChat Dev" -c user.email="dev@comfychat.local" commit -m "chore: initialize repository skeleton"
git status
```

预期：`git status` 显示 `working tree clean`。

- [ ] **Step 5: 验证 storage 已被忽略**

运行：

```powershell
echo "select 1;" | Out-File -Encoding utf8 storage/data/comfychat.db.test 2>$null
git check-ignore -v storage/data/comfychat.db
git check-ignore -v storage/uploads/
Remove-Item -LiteralPath storage/data/comfychat.db.test -ErrorAction SilentlyContinue
```

预期：`git check-ignore` 命中 `storage/**` 规则，运行时文件被忽略（已跟踪的 `.gitkeep` 不会出现在 `git check-ignore` 输出中）。删除临时测试文件。

---

### Task 2: 后端依赖与配置基线

**Files:**
- Create: `D:\learnAI\ComfyChat\backend\pyproject.toml`
- Create: `D:\learnAI\ComfyChat\backend\.env.example`
- Create: `D:\learnAI\ComfyChat\backend\app\__init__.py`
- Create: `D:\learnAI\ComfyChat\backend\app\core\__init__.py`
- Create: `D:\learnAI\ComfyChat\backend\app\core\config.py`
- Create: `D:\learnAI\ComfyChat\backend\tests\__init__.py`
- Create: `D:\learnAI\ComfyChat\backend\tests\test_config.py`

**Interfaces:**
- Consumes: 无。
- Produces: `app.core.config.Settings`：字段 `comfyui_base_url: str | None`、`comfyui_api_key: str | None`、`database_url: str`、`storage_root: Path`。

- [ ] **Step 1: 编写失败测试 `test_config.py`**

写入 `D:\learnAI\ComfyChat\backend\tests\test_config.py`：

```python
from pathlib import Path

from app.core.config import Settings


def test_settings_defaults():
    settings = Settings()
    assert settings.comfyui_base_url is None
    assert settings.comfyui_api_key is None
    assert settings.database_url.startswith("sqlite:///")
    assert isinstance(settings.storage_root, Path)


def test_settings_overrides():
    settings = Settings(
        comfyui_base_url="http://127.0.0.1:8188/",
        comfyui_api_key="abc",
        database_url="sqlite:///./custom.db",
        storage_root="./custom-storage",
    )
    assert settings.comfyui_base_url == "http://127.0.0.1:8188/"
    assert settings.comfyui_api_key == "abc"
    assert settings.database_url == "sqlite:///./custom.db"
    assert settings.storage_root == Path("./custom-storage")
```

- [ ] **Step 2: 确认测试失败**

```powershell
python -m pytest backend/tests/test_config.py -v
```

预期：`ModuleNotFoundError: No module named 'app'` 或 `ImportError`。

- [ ] **Step 3: 编写 `pyproject.toml`**

写入 `D:\learnAI\ComfyChat\backend\pyproject.toml`：

```toml
[project]
name = "comfychat-backend"
version = "0.1.0"
description = "ComfyChat backend skeleton"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "sqlalchemy>=2.0",
    "pydantic>=2.5",
    "pydantic-settings>=2.1",
    "httpx>=0.27",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["."]
include = ["app*"]
```

- [ ] **Step 4: 编写后端 `.env.example`**

写入 `D:\learnAI\ComfyChat\backend\.env.example`：

```env
COMFYUI_BASE_URL=
COMFYUI_API_KEY=
DATABASE_URL=sqlite:///./storage/data/comfychat.db
STORAGE_ROOT=./storage
```

- [ ] **Step 5: 创建包文件与 `config.py`**

创建 `app/__init__.py`、`app/core/__init__.py`、`tests/__init__.py`（全部留空）。

写入 `D:\learnAI\ComfyChat\backend\app\core\config.py`：

```python
from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    comfyui_base_url: Optional[str] = Field(default=None)
    comfyui_api_key: Optional[str] = Field(default=None)
    database_url: str = Field(default="sqlite:///./storage/data/comfychat.db")
    storage_root: Path = Field(default=Path("./storage"))
```

- [ ] **Step 6: 安装依赖**

```powershell
python -m venv backend/.venv
backend\.venv\Scripts\python -m pip install --upgrade pip
backend\.venv\Scripts\python -m pip install -e "backend[dev]"
```

预期：pip 报告成功安装。

- [ ] **Step 7: 重新运行测试确认通过**

```powershell
backend\.venv\Scripts\python -m pytest backend/tests/test_config.py -v
```

预期：两个测试全部 PASS。

- [ ] **Step 8: 提交**

```powershell
git add backend/pyproject.toml backend/.env.example backend/app backend/tests
git -c user.name="ComfyChat Dev" -c user.email="dev@comfychat.local" commit -m "feat(backend): add config module and dev tooling"
```

---

### Task 3: 后端数据库连接

**Files:**
- Create: `D:\learnAI\ComfyChat\backend\app\core\database.py`
- Create: `D:\learnAI\ComfyChat\backend\tests\test_database.py`

**Interfaces:**
- Consumes: `Settings` from `app.core.config`。
- Produces:
  - `engine: sqlalchemy.Engine` 模块级单例
  - `get_session()` 上下文管理器 yield `sqlalchemy.Session`
  - `check_database()` -> `bool`

- [ ] **Step 1: 编写失败测试 `test_database.py`**

写入 `D:\learnAI\ComfyChat\backend\tests\test_database.py`：

```python
import os
import tempfile
from pathlib import Path

from sqlalchemy import text

from app.core import database
from app.core.config import Settings


def test_check_database_returns_true_for_writable_sqlite(tmp_path: Path):
    db_path = tmp_path / "test.db"
    settings = Settings(database_url=f"sqlite:///{db_path}")
    database.configure(settings)
    try:
        assert database.check_database() is True
        with database.get_session() as session:
            result = session.execute(text("SELECT 1")).scalar_one()
            assert result == 1
    finally:
        database.reset_for_tests()
        if db_path.exists():
            db_path.unlink()


def test_check_database_returns_false_when_path_unwritable(tmp_path: Path):
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    os.chmod(blocked, 0o500)
    settings = Settings(database_url=f"sqlite:///{blocked}/x.db")
    database.configure(settings)
    try:
        assert database.check_database() is False
    finally:
        database.reset_for_tests()
        os.chmod(blocked, 0o700)
```

- [ ] **Step 2: 确认测试失败**

```powershell
backend\.venv\Scripts\python -m pytest backend/tests/test_database.py -v
```

预期：`ImportError: cannot import name 'configure' from 'app.core.database'`。

- [ ] **Step 3: 实现 `database.py`**

写入 `D:\learnAI\ComfyChat\backend\app\core\database.py`：

```python
from __future__ import annotations

import contextlib
from typing import Iterator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker[Session]] = None
_current_settings: Optional[Settings] = None


def configure(settings: Settings) -> None:
    global _engine, _SessionLocal, _current_settings
    _current_settings = settings
    _engine = create_engine(
        settings.database_url,
        future=True,
        connect_args={"check_same_thread": False}
        if settings.database_url.startswith("sqlite")
        else {},
    )
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)


def reset_for_tests() -> None:
    global _engine, _SessionLocal, _current_settings
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
    _current_settings = None


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("Database engine not configured. Call configure(settings) first.")
    return _engine


@contextlib.contextmanager
def get_session() -> Iterator[Session]:
    if _SessionLocal is None:
        raise RuntimeError("Database engine not configured. Call configure(settings) first.")
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()


def check_database() -> bool:
    try:
        with get_session() as session:
            session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
```

- [ ] **Step 4: 重新运行测试确认通过**

```powershell
backend\.venv\Scripts\python -m pytest backend/tests/test_database.py -v
```

预期：两个测试全部 PASS。

- [ ] **Step 5: 提交**

```powershell
git add backend/app/core/database.py backend/tests/test_database.py
git -c user.name="ComfyChat Dev" -c user.email="dev@comfychat.local" commit -m "feat(backend): add sqlite connection layer with health check"
```

---

### Task 4: ComfyUI 客户端占位

**Files:**
- Create: `D:\learnAI\ComfyChat\backend\app\integrations\__init__.py`
- Create: `D:\learnAI\ComfyChat\backend\app\integrations\comfyui\__init__.py`
- Create: `D:\learnAI\ComfyChat\backend\app\integrations\comfyui\client.py`
- Create: `D:\learnAI\ComfyChat\backend\tests\test_comfyui_client.py`

**Interfaces:**
- Consumes: `Settings.comfyui_base_url`、`Settings.comfyui_api_key`。
- Produces:
  - `ComfyUIClient.ping() -> str`，返回 `"ok" | "error" | "unknown"`。

- [ ] **Step 1: 编写失败测试 `test_comfyui_client.py`**

写入 `D:\learnAI\ComfyChat\backend\tests\test_comfyui_client.py`：

```python
from app.core.config import Settings
from app.integrations.comfyui.client import ComfyUIClient


def test_ping_returns_unknown_when_not_configured():
    client = ComfyUIClient(Settings(comfyui_base_url=None))
    assert client.ping() == "unknown"


def test_ping_returns_ok_on_2xx(monkeypatch):
    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url: str):
            assert url.endswith("/system_stats")
            return FakeResponse()

    monkeypatch.setattr("app.integrations.comfyui.client.httpx.Client", FakeClient)
    client = ComfyUIClient(Settings(comfyui_base_url="http://example.com:8188/"))
    assert client.ping() == "ok"


def test_ping_returns_error_on_failure(monkeypatch):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url: str):
            raise RuntimeError("boom")

    monkeypatch.setattr("app.integrations.comfyui.client.httpx.Client", FakeClient)
    client = ComfyUIClient(Settings(comfyui_base_url="http://example.com:8188/"))
    assert client.ping() == "error"
```

- [ ] **Step 2: 确认测试失败**

```powershell
backend\.venv\Scripts\python -m pytest backend/tests/test_comfyui_client.py -v
```

预期：`ModuleNotFoundError: No module named 'app.integrations.comfyui'`。

- [ ] **Step 3: 创建包文件**

创建 `app/integrations/__init__.py` 和 `app/integrations/comfyui/__init__.py`（均留空）。

- [ ] **Step 4: 实现 `client.py`**

写入 `D:\learnAI\ComfyChat\backend\app\integrations\comfyui\client.py`：

```python
from __future__ import annotations

from typing import Optional

import httpx

from app.core.config import Settings


class ComfyUIClient:
    def __init__(self, settings: Settings, timeout: float = 2.0) -> None:
        self._base_url: Optional[str] = settings.comfyui_base_url.rstrip("/") if settings.comfyui_base_url else None
        self._api_key: Optional[str] = settings.comfyui_api_key
        self._timeout = timeout

    def ping(self) -> str:
        if not self._base_url:
            return "unknown"
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else None
        try:
            with httpx.Client(timeout=self._timeout, headers=headers) as client:
                response = client.get(f"{self._base_url}/system_stats")
                response.raise_for_status()
                return "ok"
        except Exception:
            return "error"
```

- [ ] **Step 5: 重新运行测试确认通过**

```powershell
backend\.venv\Scripts\python -m pytest backend/tests/test_comfyui_client.py -v
```

预期：三个测试全部 PASS。

- [ ] **Step 6: 提交**

```powershell
git add backend/app/integrations backend/tests/test_comfyui_client.py
git -c user.name="ComfyChat Dev" -c user.email="dev@comfychat.local" commit -m "feat(backend): add comfyui client with health probe"
```

---

### Task 5: FastAPI 入口与健康检查接口

**Files:**
- Create: `D:\learnAI\ComfyChat\backend\app\api\__init__.py`
- Create: `D:\learnAI\ComfyChat\backend\app\api\routes\__init__.py`
- Create: `D:\learnAI\ComfyChat\backend\app\api\routes\health.py`
- Create: `D:\learnAI\ComfyChat\backend\app\api\deps.py`
- Create: `D:\learnAI\ComfyChat\backend\app\main.py`
- Create: `D:\learnAI\ComfyChat\backend\tests\test_health.py`

**Interfaces:**
- Consumes: `Settings`、`database.check_database()`、`ComfyUIClient.ping()`。
- Produces:
  - `GET /` → `{ "name": "ComfyChat API", "version": "0.1.0" }`
  - `GET /health` → `{ "status": "ok", "database": "ok" | "error", "comfyui": "ok" | "error" | "unknown" }`

- [ ] **Step 1: 编写失败测试 `test_health.py`**

写入 `D:\learnAI\ComfyChat\backend\tests\test_health.py`：

```python
from fastapi.testclient import TestClient

from app.core import database
from app.core.config import Settings
from app.integrations.comfyui.client import ComfyUIClient
from app.main import create_app


def _settings(tmp_path) -> Settings:
    db_path = tmp_path / "health.db"
    return Settings(
        database_url=f"sqlite:///{db_path}",
        storage_root=tmp_path / "storage",
    )


def test_root_endpoint(tmp_path):
    settings = _settings(tmp_path)
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"name": "ComfyChat API", "version": "0.1.0"}


def test_health_endpoint_reports_database_and_comfyui(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    database.reset_for_tests()

    def fake_ping(self):
        return "ok"

    monkeypatch.setattr(ComfyUIClient, "ping", fake_ping)
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["comfyui"] == "ok"


def test_health_endpoint_reports_unknown_comfyui(tmp_path, monkeypatch):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/health.db",
        storage_root=tmp_path,
    )
    database.reset_for_tests()
    monkeypatch.setattr(ComfyUIClient, "ping", lambda self: "unknown")
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["comfyui"] == "unknown"
```

- [ ] **Step 2: 确认测试失败**

```powershell
backend\.venv\Scripts\python -m pytest backend/tests/test_health.py -v
```

预期：`ImportError: cannot import name 'create_app' from 'app.main'`。

- [ ] **Step 3: 创建包文件与路由模块**

创建 `app/api/__init__.py`、`app/api/routes/__init__.py`（留空）。

写入 `D:\learnAI\ComfyChat\backend\app\api\routes\health.py`：

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

router = APIRouter()


@router.get("/")
def read_root() -> dict:
    return {"name": "ComfyChat API", "version": "0.1.0"}


@router.get("/health")
def health(request: Request) -> dict:
    services = request.app.state.services
    database_status = "ok" if services["database"].check_database() else "error"
    comfyui_status = services["comfyui"].ping()
    overall = "ok" if database_status == "ok" and comfyui_status in {"ok", "unknown"} else "error"
    return {
        "status": overall,
        "database": database_status,
        "comfyui": comfyui_status,
    }
```

写入 `D:\learnAI\ComfyChat\backend\app\api\deps.py`：

```python
from __future__ import annotations

from fastapi import Request


def get_settings(request: Request):
    return request.app.state.settings


def get_services(request: Request):
    return request.app.state.services
```

- [ ] **Step 4: 实现 `main.py`**

写入 `D:\learnAI\ComfyChat\backend\app\main.py`：

```python
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI

from app.api.routes import health
from app.core import database
from app.core.config import Settings
from app.integrations.comfyui.client import ComfyUIClient


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or Settings()
    database.configure(settings)

    app = FastAPI(title="ComfyChat API", version="0.1.0")
    app.state.settings = settings
    app.state.services = {
        "database": database,
        "comfyui": ComfyUIClient(settings),
    }

    app.include_router(health.router)
    return app


app = create_app()
```

- [ ] **Step 5: 重新运行测试确认通过**

```powershell
backend\.venv\Scripts\python -m pytest backend/tests -v
```

预期：所有测试（`test_config`、`test_database`、`test_comfyui_client`、`test_health`）PASS。

- [ ] **Step 6: 启动服务做端到端冒烟**

```powershell
backend\.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

在另一终端执行：

```powershell
curl http://127.0.0.1:8000/
curl http://127.0.0.1:8000/health
```

预期：根路径返回 `{"name":"ComfyChat API","version":"0.1.0"}`；`/health` 返回 `{"status":"ok","database":"ok","comfyui":"unknown"}`。完成后停止 uvicorn（Ctrl+C）。

- [ ] **Step 7: 提交**

```powershell
git add backend/app/api backend/app/main.py backend/tests/test_health.py
git -c user.name="ComfyChat Dev" -c user.email="dev@comfychat.local" commit -m "feat(backend): expose / and /health endpoints"
```

---

### Task 6: 前端项目骨架

**Files:**
- Create: `D:\learnAI\ComfyChat\frontend\package.json`
- Create: `D:\learnAI\ComfyChat\frontend\tsconfig.json`
- Create: `D:\learnAI\ComfyChat\frontend\tsconfig.node.json`
- Create: `D:\learnAI\ComfyChat\frontend\vite.config.ts`
- Create: `D:\learnAI\ComfyChat\frontend\index.html`
- Create: `D:\learnAI\ComfyChat\frontend\.gitignore`
- Create: `D:\learnAI\ComfyChat\frontend\public\.gitkeep`
- Create: `D:\learnAI\ComfyChat\frontend\src\main.ts`
- Create: `D:\learnAI\ComfyChat\frontend\src\App.vue`
- Create: `D:\learnAI\ComfyChat\frontend\src\env.d.ts`
- Create: `D:\learnAI\ComfyChat\frontend\src\shims-vue.d.ts`
- Create: `D:\learnAI\ComfyChat\frontend\src\app\router.ts`
- Create: `D:\learnAI\ComfyChat\frontend\src\app\layout\.gitkeep`
- Create: `D:\learnAI\ComfyChat\frontend\src\components\.gitkeep`
- Create: `D:\learnAI\ComfyChat\frontend\src\features\dashboard\.gitkeep`
- Create: `D:\learnAI\ComfyChat\frontend\src\features\workflows\.gitkeep`
- Create: `D:\learnAI\ComfyChat\frontend\src\features\tasks\.gitkeep`
- Create: `D:\learnAI\ComfyChat\frontend\src\features\files\.gitkeep`
- Create: `D:\learnAI\ComfyChat\frontend\src\services\api.ts`
- Create: `D:\learnAI\ComfyChat\frontend\src\types\api.ts`
- Create: `D:\learnAI\ComfyChat\frontend\src\assets\.gitkeep`

**Interfaces:**
- Consumes: 后端 `GET /`、`GET /health`。
- Produces: Vite 开发服务器在 `http://127.0.0.1:5173` 提供首页；首页显示标题与后端 `/health` 状态。

- [ ] **Step 1: 编写 `package.json`**

写入 `D:\learnAI\ComfyChat\frontend\package.json`：

```json
{
  "name": "comfychat-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc --noEmit && vite build",
    "preview": "vite preview",
    "typecheck": "vue-tsc --noEmit"
  },
  "dependencies": {
    "pinia": "^2.1.7",
    "vue": "^3.4.0",
    "vue-router": "^4.2.5"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.0.0",
    "typescript": "^5.3.0",
    "vite": "^5.2.0",
    "vue-tsc": "^2.0.0"
  }
}
```

- [ ] **Step 2: 编写 `tsconfig.json` 与 `tsconfig.node.json`**

写入 `D:\learnAI\ComfyChat\frontend\tsconfig.json`：

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "jsx": "preserve",
    "sourceMap": true,
    "resolveJsonModule": true,
    "esModuleInterop": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "skipLibCheck": true,
    "noEmit": true,
    "isolatedModules": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"]
    }
  },
  "include": ["src/**/*", "src/**/*.vue"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

写入 `D:\learnAI\ComfyChat\frontend\tsconfig.node.json`：

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 3: 编写 `vite.config.ts` 与 `index.html`**

写入 `D:\learnAI\ComfyChat\frontend\vite.config.ts`：

```ts
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import path from "node:path";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
});
```

写入 `D:\learnAI\ComfyChat\frontend\index.html`：

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>ComfyChat</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

- [ ] **Step 4: 编写前端 `.gitignore`**

写入 `D:\learnAI\ComfyChat\frontend\.gitignore`：

```gitignore
node_modules/
dist/
.vite/
*.local
```

- [ ] **Step 5: 创建占位目录与 shims**

创建 `public/.gitkeep`、`src/app/layout/.gitkeep`、`src/components/.gitkeep`、`src/features/dashboard/.gitkeep`、`src/features/workflows/.gitkeep`、`src/features/tasks/.gitkeep`、`src/features/files/.gitkeep`、`src/assets/.gitkeep`（全部空文件）。

写入 `D:\learnAI\ComfyChat\frontend\src\env.d.ts`：

```ts
/// <reference types="vite/client" />
```

写入 `D:\learnAI\ComfyChat\frontend\src\shims-vue.d.ts`：

```ts
declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<{}, {}, any>;
  export default component;
}
```

- [ ] **Step 6: 编写类型与 API 客户端**

写入 `D:\learnAI\ComfyChat\frontend\src\types\api.ts`：

```ts
export interface ApiInfo {
  name: string;
  version: string;
}

export interface HealthStatus {
  status: "ok" | "error";
  database: "ok" | "error";
  comfyui: "ok" | "error" | "unknown";
}
```

写入 `D:\learnAI\ComfyChat\frontend\src\services\api.ts`：

```ts
import type { ApiInfo, HealthStatus } from "@/types/api";

const API_BASE = "/api";

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export const api = {
  root: () => get<ApiInfo>("/"),
  health: () => get<HealthStatus>("/health"),
};
```

- [ ] **Step 7: 编写路由、根组件、入口**

写入 `D:\learnAI\ComfyChat\frontend\src\app\router.ts`：

```ts
import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";

const routes: RouteRecordRaw[] = [
  {
    path: "/",
    name: "home",
    component: () => import("@/App.vue"),
  },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
});
```

写入 `D:\learnAI\ComfyChat\frontend\src\App.vue`：

```vue
<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api } from "@/services/api";
import type { HealthStatus } from "@/types/api";

const health = ref<HealthStatus | null>(null);
const error = ref<string | null>(null);

onMounted(async () => {
  try {
    health.value = await api.health();
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
});
</script>

<template>
  <main>
    <h1>ComfyChat 前端就绪</h1>
    <section>
      <h2>后端健康</h2>
      <p v-if="error">错误：{{ error }}</p>
      <pre v-else-if="health">{{ health }}</pre>
      <p v-else>正在加载…</p>
    </section>
  </main>
</template>

<style scoped>
main {
  font-family: system-ui, sans-serif;
  margin: 2rem auto;
  max-width: 640px;
  padding: 0 1rem;
}
pre {
  background: #f4f4f5;
  padding: 0.75rem;
  border-radius: 4px;
}
</style>
```

写入 `D:\learnAI\ComfyChat\frontend\src\main.ts`：

```ts
import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import { router } from "@/app/router";

const app = createApp(App);
app.use(createPinia());
app.use(router);
app.mount("#app");
```

- [ ] **Step 8: 安装依赖**

```powershell
npm install --no-audit --no-fund
```

预期：在 `frontend/node_modules` 完成安装并生成 `package-lock.json`。

- [ ] **Step 9: 类型检查**

```powershell
npm run typecheck
```

预期：无错误。

- [ ] **Step 10: 启动 dev server 并冒烟**

```powershell
npm run dev
```

预期：Vite 输出 `Local: http://127.0.0.1:5173/`。手动在浏览器访问该地址并确认页面显示“ComfyChat 前端就绪”与 `/health` 返回内容（`comfyui` 应为 `unknown`）。完成后停止 dev server（Ctrl+C）。

- [ ] **Step 11: 提交**

```powershell
git add frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/tsconfig.node.json frontend/vite.config.ts frontend/index.html frontend/.gitignore frontend/public frontend/src
git -c user.name="ComfyChat Dev" -c user.email="dev@comfychat.local" commit -m "feat(frontend): scaffold vue + vite + ts with health probe"
```

注意：`frontend/.gitignore` 提交，根级 `.gitignore` 已忽略 `frontend/node_modules/`，此处的前端 `.gitignore` 不会造成冲突。

---

### Task 7: 根级 README 与设计文档引用

**Files:**
- Create: `D:\learnAI\ComfyChat\README.md`
- Modify: `D:\learnAI\ComfyChat\docs\superpowers\plans\2026-08-09-comfychat-skeleton.md`（本文件由 Task 1 引用，无需修改）

**Interfaces:**
- Consumes: 设计文档路径。
- Produces: 仓库根的 `README.md` 描述启动方式与目录说明。

- [ ] **Step 1: 编写 README**

写入 `D:\learnAI\ComfyChat\README.md`：

```markdown
# ComfyChat

ComfyUI 工作流管理与生成的桌面端 Web 工具。

## 目录

- `frontend/` Vue 3 + Vite + TypeScript 前端。
- `backend/` FastAPI + SQLAlchemy + SQLite 后端。
- `docs/` 设计、计划与后续文档。
- `storage/` 运行时文件（SQLite、上传、生成结果、缩略图、临时），**不入库**。

## 启动

后端：

```powershell
python -m venv backend/.venv
backend\.venv\Scripts\python -m pip install -e "backend[dev]"
backend\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

前端（另一终端）：

```powershell
cd frontend
npm install
npm run dev
```

打开 `http://127.0.0.1:5173/`；后端根 `http://127.0.0.1:8000/`，健康检查 `http://127.0.0.1:8000/health`。

## 配置

复制 `.env.example`（与 `backend/.env.example`）为 `.env` 并按需修改 `COMFYUI_BASE_URL`、`DATABASE_URL` 等。`.env` 不入库。

## 文档

设计：`docs/superpowers/specs/2026-08-09-comfychat-skeleton-design.md`
计划：`docs/superpowers/plans/2026-08-09-comfychat-skeleton.md`
```

- [ ] **Step 2: 提交**

```powershell
git add README.md
git -c user.name="ComfyChat Dev" -c user.email="dev@comfychat.local" commit -m "docs: add project readme"
```

---

### Task 8: 整体端到端验证

**Files:**
- Modify: 无（仅运行验证命令）。

**Interfaces:**
- Consumes: 已完成的任务 1-7。
- Produces: 验收证据。

- [ ] **Step 1: 启动后端并冒烟**

```powershell
backend\.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

在另一终端：

```powershell
curl http://127.0.0.1:8000/
curl http://127.0.0.1:8000/health
git check-ignore -v storage/data/comfychat.db
```

预期：根路径返回 `{name, version}`；`/health` 返回 `ok/ok/unknown`；`git check-ignore` 命中 `storage/`。完成后停止 uvicorn。

- [ ] **Step 2: 启动前端并冒烟**

```powershell
cd frontend
npm run dev
```

在浏览器访问 `http://127.0.0.1:5173/`，确认显示“ComfyChat 前端就绪”与后端健康 JSON。完成后停止 dev server。

- [ ] **Step 3: 全量测试**

```powershell
backend\.venv\Scripts\python -m pytest backend/tests -v
npm --prefix frontend run typecheck
```

预期：后端测试全部 PASS，前端 typecheck 无错误。

- [ ] **Step 4: 最终提交状态**

```powershell
git status
git log --oneline
```

预期：`git status` 干净；`git log` 至少包含任务 1-7 的提交。

---

## Self-Review

- **Spec coverage:**
  - 顶层四区结构（设计 §3）→ Task 1。
  - 后端分层（设计 §4）→ Task 2-5。
  - 前端分层（设计 §5）→ Task 6。
  - `storage/` 与 `.gitignore`（设计 §6）→ Task 1, 6。
  - `/` 与 `/health`（设计 §7）→ Task 5。
  - 配置与运行（设计 §8）→ Task 2, 6, 7。
  - Git 初始化（设计 §9）→ Task 1, 2-7 的 commit 步骤。
  - 验收（设计 §10）→ Task 8。
- **Placeholder scan:** 全文无 TBD / TODO / “类似 Task N” 引用；每个代码块都给出可粘贴内容。
- **Type consistency:** 全文使用 `Settings.comfyui_base_url / comfyui_api_key / database_url / storage_root`、`ComfyUIClient.ping()` 返回 `"ok" | "error" | "unknown"`、`HealthStatus` 字段与前端 `types/api.ts` 一致。
- **No scope creep:** 没有引入 UI 库、CI、Docker、license、数据库迁移；所有超出第一阶段的内容只在 README 与设计文档中提及。
