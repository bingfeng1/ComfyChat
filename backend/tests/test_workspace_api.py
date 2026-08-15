from fastapi.testclient import TestClient

from app.main import create_app


def _client(tmp_path):
    from app.core.config import Settings
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/ws.db",
        storage_root=tmp_path / "storage",
        comfyui_base_url="http://example.com:8188/",
    )
    return TestClient(create_app(settings))


def test_list_empty(tmp_path):
    client = _client(tmp_path)
    r = client.get("/workspaces")
    assert r.status_code == 200
    assert r.json() == {"items": []}


def test_create_and_get(tmp_path):
    client = _client(tmp_path)
    r = client.post("/workspaces", json={"name": "Alpha"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Alpha"
    assert body["id"]

    r = client.get("/workspaces")
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == body["id"]


def test_create_duplicate_returns_409(tmp_path):
    client = _client(tmp_path)
    client.post("/workspaces", json={"name": "Dup"})
    r = client.post("/workspaces", json={"name": "Dup"})
    assert r.status_code == 409, r.text
    assert "already exists" in r.json()["detail"]


def test_create_empty_name_rejected(tmp_path):
    client = _client(tmp_path)
    r = client.post("/workspaces", json={"name": ""})
    assert r.status_code == 422


def test_rename(tmp_path):
    client = _client(tmp_path)
    r = client.post("/workspaces", json={"name": "Old"})
    wid = r.json()["id"]
    r = client.patch(f"/workspaces/{wid}", json={"name": "New"})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "New"


def test_rename_to_existing_returns_409(tmp_path):
    client = _client(tmp_path)
    a = client.post("/workspaces", json={"name": "A"}).json()
    client.post("/workspaces", json={"name": "B"})
    r = client.patch(f"/workspaces/{a['id']}", json={"name": "B"})
    assert r.status_code == 409


def test_rename_missing_returns_404(tmp_path):
    client = _client(tmp_path)
    r = client.patch("/workspaces/missing-id", json={"name": "X"})
    assert r.status_code == 404


def test_delete_missing_returns_404(tmp_path):
    client = _client(tmp_path)
    r = client.delete("/workspaces/missing-id")
    assert r.status_code == 404


def test_generation_count_helper(tmp_path):
    client = _client(tmp_path)
    wid = client.post("/workspaces", json={"name": "Empty"}).json()["id"]
    r = client.get(f"/workspaces/{wid}/generation-count")
    assert r.status_code == 200
    assert r.json() == {"count": 0}


def test_generation_count_missing_404(tmp_path):
    client = _client(tmp_path)
    r = client.get("/workspaces/missing/generation-count")
    assert r.status_code == 404


def test_list_includes_count_and_preview(tmp_path, monkeypatch):
    """新建一个工作区并加入 generation,验证 list 返回 count + preview。"""
    from app.core.config import Settings
    from app.integrations.comfyui.client import ComfyUIClient
    from app.main import create_app
    from app.services.generation import GenerationService
    from fastapi.testclient import TestClient

    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/ws.db",
        storage_root=tmp_path / "storage",
        comfyui_base_url="http://example.com:8188/",
    )
    app = create_app(settings)
    client = TestClient(app)

    # Stub ComfyUI for generation creation
    class FakeComfy:
        def submit_prompt(self, prompt):
            return "p-1", "c-1"
        def get_history(self, prompt_id):
            return {}
        def wait_for_history(self, prompt_id, *, timeout=1800.0, client_id=None):
            raise Exception("no")
        def get_image(self, *a, **kw):
            return b"PNG"
    for name in ("submit_prompt", "get_history", "wait_for_history", "get_image"):
        monkeypatch.setattr(ComfyUIClient, name, getattr(FakeComfy, name))
    monkeypatch.setattr(GenerationService, "_watch_and_download", lambda self, gid: None)

    # 准备: import workflow + config
    import json as _json
    from app.schemas.generation import GenerationField
    files = {"file": ("w.json", _json.dumps({}).encode(), "application/json")}
    wid = client.post("/workflows/import", files=files).json()["id"]
    fields = [
        GenerationField(key="text", label="t", type="text", node_id="1", input_name="text", default="", required=True),
    ]
    r = client.put(
        f"/workflows/{wid}/generation-config",
        json={"api_template": {"1": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}}}, "fields": [f.model_dump() for f in fields]},
    )
    assert r.status_code == 200, r.text

    # 创建工作区
    r = client.post("/workspaces", json={"name": "Bin"})
    assert r.status_code == 201, r.text
    ws = r.json()
    assert ws["generation_count"] == 0
    assert ws["preview"] == []

    # 创建 generation + 手动写 outputs_json,再加入工作区
    r = client.post("/generations", json={
        "workflow_id": wid,
        "parameters": {"text": "hi"},
        "workspace_ids": [ws["id"]],
    })
    assert r.status_code == 201, r.text
    gen = r.json()
    # 直接写库,模拟"已下载图片"
    from app.core.database import get_engine
    from sqlalchemy.orm import sessionmaker
    from app.repositories.generation import GenerationRepository
    eng = get_engine()
    with sessionmaker(bind=eng)() as s:
        repo = GenerationRepository(s)
        g = repo.get(gen["id"])
        repo.update_success(gen["id"], ["out.png"])

    # list 现在应返回 count=1 + preview=[out.png]
    r = client.get("/workspaces")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == ws["id"]
    assert items[0]["generation_count"] == 1
    assert len(items[0]["preview"]) == 1
    assert items[0]["preview"][0]["filename"] == "out.png"
    assert items[0]["preview"][0]["media_type"] == "image"
    assert items[0]["preview"][0]["generation_id"] == gen["id"]


def test_get_single_workspace_with_preview(tmp_path):
    client = _client(tmp_path)
    r = client.post("/workspaces", json={"name": "Detail"})
    wid = r.json()["id"]
    r = client.get(f"/workspaces/{wid}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == wid
    assert body["name"] == "Detail"
    assert body["generation_count"] == 0
    assert body["preview"] == []


def test_get_single_workspace_missing_404(tmp_path):
    client = _client(tmp_path)
    r = client.get("/workspaces/missing-id")
    assert r.status_code == 404


def test_create_workspace_response_includes_count_and_preview(tmp_path):
    client = _client(tmp_path)
    r = client.post("/workspaces", json={"name": "Fresh"})
    assert r.status_code == 201
    body = r.json()
    assert body["generation_count"] == 0
    assert body["preview"] == []


def test_rename_response_includes_count_and_preview(tmp_path):
    client = _client(tmp_path)
    wid = client.post("/workspaces", json={"name": "Old"}).json()["id"]
    r = client.patch(f"/workspaces/{wid}", json={"name": "New"})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "New"
    assert "generation_count" in body
    assert "preview" in body
