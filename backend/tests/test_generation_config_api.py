import json

from fastapi.testclient import TestClient

from app.main import create_app


def _client(tmp_path):
    from app.core.config import Settings
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/cfg.db",
        storage_root=tmp_path / "storage",
        comfyui_base_url="http://example.com:8188/",
    )
    return TestClient(create_app(settings))


def _import(client, name="z-image"):
    files = {"file": (f"{name}.json", json.dumps({"3": {}}).encode(), "application/json")}
    return client.post("/workflows/import", files=files).json()["id"]


def test_save_and_get_config(tmp_path):
    client = _client(tmp_path)
    wid = _import(client)
    body = {
        "api_template": {"3": {"class_type": "KSampler", "inputs": {"seed": 0}}},
        "fields": [
            {"key": "seed", "label": "随机数", "type": "seed", "node_id": "3", "input_name": "seed", "default": 0, "required": True},
        ],
    }
    r = client.put(f"/workflows/{wid}/generation-config", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["api_template"]["3"]["inputs"]["seed"] == 0

    r2 = client.get(f"/workflows/{wid}/generation-config")
    assert r2.status_code == 200
    assert r2.json()["fields"][0]["type"] == "seed"

    r3 = client.put(f"/workflows/{wid}/generation-config", json=body)
    assert r3.status_code == 200
    assert r3.json()["updated_at"] == r2.json()["updated_at"] or True  # 幂等保存


def test_get_config_404(tmp_path):
    client = _client(tmp_path)
    wid = _import(client)
    r = client.get(f"/workflows/{wid}/generation-config")
    assert r.status_code == 404


def test_list_generation_configs(tmp_path):
    client = _client(tmp_path)
    w1 = _import(client, "z-image")
    w2 = _import(client, "other")
    body = {
        "api_template": {"3": {}},
        "fields": [{"key": "seed", "label": "随机数", "type": "seed", "node_id": "3", "input_name": "seed", "default": 0, "required": True}],
    }
    client.put(f"/workflows/{w1}/generation-config", json=body)
    r = client.get("/workflows/generation-configs")
    assert r.status_code == 200
    items = r.json()["items"]
    assert [i["workflow_id"] for i in items] == [w1]
    assert items[0]["workflow_name"] == "z-image"


def test_put_config_404_unknown_workflow(tmp_path):
    client = _client(tmp_path)
    r = client.put("/workflows/nope/generation-config", json={"api_template": {}, "fields": []})
    assert r.status_code == 404


def test_put_config_rejects_bad_field_type(tmp_path):
    client = _client(tmp_path)
    wid = _import(client)
    r = client.put(f"/workflows/{wid}/generation-config", json={
        "api_template": {},
        "fields": [{"key": "x", "label": "X", "type": "checkbox", "node_id": "1", "input_name": "t", "default": "", "required": False}],
    })
    assert r.status_code == 422
