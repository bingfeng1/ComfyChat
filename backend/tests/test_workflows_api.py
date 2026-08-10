import io
import json
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


def test_import_rename_conflict_409(tmp_path):
    client, _ = _client(tmp_path)
    files_a = {"file": ("a.json", io.BytesIO(b'{"x":1}'), "application/json")}
    files_b = {"file": ("b.json", io.BytesIO(b'{"y":2}'), "application/json")}
    client.post("/workflows/import", files=files_a)
    client.post("/workflows/import", files=files_b)
    r = client.post("/workflows/import", files=files_a, params={"name": "b"})
    assert r.status_code == 409
    data = r.json()
    assert data["filename"] == "b.json"
    assert data["existing"]["name"] == "b"
    items = client.get("/workflows").json()["items"]
    b_item = [it for it in items if it["source_key"] == "b.json"][0]
    assert b_item["size_bytes"] == len('{"y":2}'.encode("utf-8"))


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


def test_versions_endpoints(tmp_path):
    client, _ = _client(tmp_path)
    files = {"file": ("a.json", io.BytesIO(b'{"x":1}'), "application/json")}
    wid = client.post("/workflows/import", files=files).json()["id"]

    r = client.get(f"/workflows/{wid}/versions")
    assert r.status_code == 200
    assert r.json() == {"items": []}

    r2 = client.get(f"/workflows/{wid}/versions/1")
    assert r2.status_code == 404


def test_versions_after_archive(tmp_path, monkeypatch):
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
    client.post("/workflows/sync")

    class FakeClient2:
        def list_browse(self):
            return [{"name": "wf.json", "path": "workflows/wf.json", "type": "file", "size": 99}]
        def read_userdata_json(self, name):
            return '{"n":2}'

    monkeypatch.setattr(ComfyUIClient, "list_browse", FakeClient2.list_browse)
    monkeypatch.setattr(ComfyUIClient, "read_userdata_json", FakeClient2.read_userdata_json)
    client.post("/workflows/sync")

    lst = client.get("/workflows").json()
    assert lst["items"][0]["has_history"] is True
    wid = lst["items"][0]["id"]

    r = client.get(f"/workflows/{wid}/versions")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["version"] == 1
    assert items[0]["size_bytes"] == 6

    rb = client.get(f"/workflows/{wid}/versions/1")
    assert rb.status_code == 200
    assert rb.json() == {"n": 1}

    rd = client.delete(f"/workflows/{wid}/versions/1")
    assert rd.status_code == 204
    rd2 = client.delete(f"/workflows/{wid}/versions/1")
    assert rd2.status_code == 404


def test_versions_404_unknown_workflow(tmp_path):
    client, _ = _client(tmp_path)
    r = client.get("/workflows/nonexistent/versions")
    assert r.status_code == 404


UI_BODY = json.dumps({
    "nodes": [
        {
            "id": 7,
            "type": "CLIPTextEncode",
            "inputs": [
                {"name": "clip", "localized_name": "clip", "link": 1},
                {"name": "text", "localized_name": "文本", "widget": {"name": "text"}},
            ],
            "widgets_values": ["a cat"],
        },
        {
            "id": 16,
            "type": "KSampler",
            "inputs": [
                {"name": "model", "localized_name": "模型", "link": 2},
                {"name": "seed", "localized_name": "种子", "widget": {"name": "seed"}},
            ],
            "widgets_values": [42],
        },
    ]
})


def test_discover_generation_config(tmp_path):
    client, _ = _client(tmp_path)
    files = {"file": ("z.json", io.BytesIO(UI_BODY.encode("utf-8")), "application/json")}
    r = client.post("/workflows/import", files=files)
    wf_id = r.json()["id"]

    d = client.get(f"/workflows/{wf_id}/generation-config/discover")
    assert d.status_code == 200
    data = d.json()
    assert data["api_template"]["7"]["class_type"] == "CLIPTextEncode"
    assert data["api_template"]["7"]["inputs"]["text"] == "a cat"
    keys = {f["key"] for f in data["fields"]}
    assert keys == {"text", "seed"}
    text = next(f for f in data["fields"] if f["key"] == "text")
    assert text["label"] == "文本"
    assert text["type"] == "text"


def test_discover_generation_config_404_missing_workflow(tmp_path):
    client, _ = _client(tmp_path)
    r = client.get("/workflows/nope/generation-config/discover")
    assert r.status_code == 404


def test_discover_dedupes_same_name_keys(tmp_path):
    body = json.dumps({
        "nodes": [
            {
                "id": 7,
                "type": "CLIPTextEncode",
                "inputs": [{"name": "text", "localized_name": "正向", "widget": {"name": "text"}}],
                "widgets_values": ["x"],
            },
            {
                "id": 8,
                "type": "CLIPTextEncode",
                "inputs": [{"name": "text", "localized_name": "负向", "widget": {"name": "text"}}],
                "widgets_values": ["y"],
            },
        ]
    })
    client, _ = _client(tmp_path)
    files = {"file": ("z.json", io.BytesIO(body.encode("utf-8")), "application/json")}
    r = client.post("/workflows/import", files=files)
    wf_id = r.json()["id"]

    d = client.get(f"/workflows/{wf_id}/generation-config/discover")
    keys = [f["key"] for f in d.json()["fields"]]
    assert keys == ["text", "text_1"]
