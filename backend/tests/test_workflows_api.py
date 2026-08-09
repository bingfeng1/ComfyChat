import io
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.deps import get_services, get_settings
from app.main import create_app


def _client(tmp_path: Path, monkeypatch=None):
    settings = __import__("app.core.config", fromlist=["Settings"]).Settings(
        database_url=f"sqlite:///{tmp_path}/api.db",
        storage_root=tmp_path / "storage",
        comfyui_userdata_dir=tmp_path / "user",
    )
    (settings.comfyui_userdata_dir / "workflows").mkdir(parents=True, exist_ok=True)
    app = create_app(settings)
    return TestClient(app), settings


def test_list_empty(tmp_path):
    client, _ = _client(tmp_path)
    r = client.get("/workflows")
    assert r.status_code == 200
    assert r.json() == {"items": []}


def test_import_and_list(tmp_path):
    client, _ = _client(tmp_path)
    files = {"file": ("a.json", io.BytesIO(b'{"x":1}'), "application/json")}
    r = client.post("/workflows/import", files=files)
    assert r.status_code == 201
    data = r.json()
    assert data["source_key"] == "a.json"
    assert data["name"] == "a"

    r2 = client.get("/workflows")
    assert len(r2.json()["items"]) == 1


def test_import_duplicate_conflict(tmp_path):
    client, _ = _client(tmp_path)
    files = {"file": ("a.json", io.BytesIO(b'{"x":1}'), "application/json")}
    client.post("/workflows/import", files=files)
    r = client.post("/workflows/import", files=files)
    assert r.status_code == 409
    assert r.json()["filename"] == "a.json"
    assert r.json()["existing"]["name"] == "a"


def test_import_overwrite(tmp_path):
    client, _ = _client(tmp_path)
    files = {"file": ("a.json", io.BytesIO(b'{"x":1}'), "application/json")}
    client.post("/workflows/import", files=files)
    r = client.post("/workflows/import", files=files, params={"overwrite": "true"})
    assert r.status_code == 200
    assert r.json()["body"] == '{"x":1}'


def test_import_rename(tmp_path):
    client, _ = _client(tmp_path)
    files = {"file": ("a.json", io.BytesIO(b'{"x":1}'), "application/json")}
    client.post("/workflows/import", files=files)
    r = client.post("/workflows/import", files=files, params={"name": "b"})
    assert r.status_code == 201
    assert r.json()["source_key"] == "b.json"


def test_import_invalid_json(tmp_path):
    client, _ = _client(tmp_path)
    files = {"file": ("bad.json", io.BytesIO(b"not json"), "application/json")}
    r = client.post("/workflows/import", files=files)
    assert r.status_code == 400


def test_get_body_and_export(tmp_path):
    client, _ = _client(tmp_path)
    files = {"file": ("a.json", io.BytesIO(b'{"x":1}'), "application/json")}
    wid = client.post("/workflows/import", files=files).json()["id"]

    rb = client.get(f"/workflows/{wid}/body")
    assert rb.status_code == 200
    assert rb.json() == {"x": 1}

    re = client.get(f"/workflows/{wid}/export")
    assert re.status_code == 200
    assert re.headers["content-disposition"].startswith("attachment")
    assert re.content == b'{"x":1}'


def test_delete(tmp_path):
    client, _ = _client(tmp_path)
    files = {"file": ("a.json", io.BytesIO(b'{"x":1}'), "application/json")}
    wid = client.post("/workflows/import", files=files).json()["id"]
    r = client.delete(f"/workflows/{wid}")
    assert r.status_code == 204
    r2 = client.delete(f"/workflows/{wid}")
    assert r2.status_code == 404


def test_sync(tmp_path, monkeypatch):
    client, settings = _client(tmp_path)
    (settings.comfyui_userdata_dir / "workflows" / "wf.json").write_text('{"n":1}', encoding="utf-8")

    from app.integrations.comfyui.client import ComfyUIClient

    class FakeClient:
        def __init__(self, s): pass
        def ping(self): return "ok"
        def list_browse(self):
            return [{"name": "wf.json", "path": "workflows/wf.json", "type": "file", "size": 6}]
        def read_userdata_json(self, name):
            return '{"n":1}'

    monkeypatch.setattr(ComfyUIClient, "list_browse", FakeClient.list_browse)
    monkeypatch.setattr(ComfyUIClient, "read_userdata_json", FakeClient.read_userdata_json)
    r = client.post("/workflows/sync")
    assert r.status_code == 200
    body = r.json()
    assert body["browse"]["added"] == 1
    assert len(client.get("/workflows").json()["items"]) == 1
