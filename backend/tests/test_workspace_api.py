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
