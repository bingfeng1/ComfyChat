import json

from fastapi.testclient import TestClient

from app.main import create_app


def _client(tmp_path):
    from app.core.config import Settings
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/lora.db",
        storage_root=tmp_path / "storage",
        comfyui_base_url="http://example.com:8188/",
    )
    return TestClient(create_app(settings))


def _patch_comfy(monkeypatch, loras):
    class FakeComfy:
        def get_object_info(self, node_types=None):
            return {
                "LoraLoader": {"input": {"required": {"lora_name": [loras]}}},
                "LoraLoaderModelOnly": {"input": {"required": {"lora_name": [loras]}}},
            }
    from app.integrations.comfyui.client import ComfyUIClient
    monkeypatch.setattr(ComfyUIClient, "get_object_info", FakeComfy.get_object_info)


def test_get_lora_returns_items(tmp_path, monkeypatch):
    _patch_comfy(monkeypatch, ["a.safetensors"])
    client = _client(tmp_path)
    r = client.get("/lora")
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [i["name"] for i in items] == ["a.safetensors"]
    assert items[0]["models"] == []


def test_sync_endpoint(tmp_path, monkeypatch):
    _patch_comfy(monkeypatch, ["x.safetensors", "y.safetensors"])
    client = _client(tmp_path)
    r = client.post("/lora/sync")
    assert r.status_code == 200, r.text
    names = {i["name"] for i in r.json()["items"]}
    assert names == {"x.safetensors", "y.safetensors"}
