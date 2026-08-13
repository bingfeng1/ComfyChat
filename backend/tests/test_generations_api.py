import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas.generation import GenerationField


FIELDS = [
    GenerationField(key="positive_prompt", label="正面提示词", type="text", node_id="6", input_name="text", default="", required=True),
    GenerationField(key="seed", label="随机数", type="seed", node_id="3", input_name="seed", default=0, required=True),
]
TEMPLATE = {
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
    "3": {"class_type": "KSampler", "inputs": {"seed": 0}},
}


def _client(tmp_path):
    from app.core.config import Settings
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/gen.db",
        storage_root=tmp_path / "storage",
        comfyui_base_url="http://example.com:8188/",
    )
    app = create_app(settings)
    return TestClient(app), settings


def _import_workflow(client, name="z-image"):
    files = {"file": (f"{name}.json", json.dumps(TEMPLATE).encode(), "application/json")}
    return client.post("/workflows/import", files=files).json()["id"]


def _config(client, wid):
    r = client.put(
        f"/workflows/{wid}/generation-config",
        json={"api_template": TEMPLATE, "fields": [f.model_dump() for f in FIELDS]},
    )
    assert r.status_code == 200, r.text
    return r


def test_generation_flow(tmp_path, monkeypatch):
    client, _ = _client(tmp_path)
    wid = _import_workflow(client)
    _config(client, wid)

    from app.integrations.comfyui.client import ComfyUIClient

    class FakeComfy:
        def submit_prompt(self, prompt):
            return "p-1", "c-1"
        def get_history(self, prompt_id):
            return {"p-1": {"status": {"status_str": "success"}, "outputs": {"9": {"images": [{"filename": "out.png", "subfolder": "", "type": "output"}]}}}}
        def get_image(self, filename, subfolder="", image_type="output"):
            return b"PNGDATA"

    for name in ("submit_prompt", "get_history", "get_image"):
        monkeypatch.setattr(ComfyUIClient, name, getattr(FakeComfy, name))

    r = client.post("/generations", json={
        "workflow_id": wid,
        "parameters": {"positive_prompt": "cat", "seed": 42, "seed_random": False},
    })
    assert r.status_code == 201, r.text
    gen = r.json()
    assert gen["status"] in ("queued", "running", "success")
    assert gen["prompt_id"] == "p-1"
    assert gen["parameters"]["positive_prompt"] == "cat"

    lst = client.get("/generations").json()
    assert len(lst["items"]) == 1
    got = client.get(f"/generations/{gen['id']}").json()
    assert got["id"] == gen["id"]

    img = client.get(f"/generations/{gen['id']}/images/out.png")
    assert img.status_code == 200
    assert img.content == b"PNGDATA"

    rdel = client.delete(f"/generations/{gen['id']}")
    assert rdel.status_code == 204
    assert client.get("/generations").json()["items"] == []


def test_create_returns_503_when_comfyui_unavailable(tmp_path, monkeypatch):
    from app.integrations.comfyui.client import ComfyUIError

    client, _ = _client(tmp_path)
    wid = _import_workflow(client)
    _config(client, wid)

    def boom_submit(self, prompt):
        raise ComfyUIError("comfyui down")

    monkeypatch.setattr(
        "app.integrations.comfyui.client.ComfyUIClient.submit_prompt", boom_submit
    )
    r = client.post("/generations", json={
        "workflow_id": wid,
        "parameters": {"positive_prompt": "cat", "seed": 42, "seed_random": False},
    })
    assert r.status_code == 503
    assert "ComfyUI" in r.json()["detail"]
    assert client.get("/generations").json()["items"] == []


def test_create_requires_config(tmp_path):
    client, _ = _client(tmp_path)
    wid = _import_workflow(client)
    r = client.post("/generations", json={
        "workflow_id": wid,
        "parameters": {"positive_prompt": "cat"},
    })
    assert r.status_code in (400, 409)
    assert "not configured" in r.json()["detail"]


def test_create_rejects_missing_required(tmp_path):
    client, _ = _client(tmp_path)
    wid = _import_workflow(client)
    _config(client, wid)
    r = client.post("/generations", json={"workflow_id": wid, "parameters": {}})
    assert r.status_code == 400


def test_image_404_unknown(tmp_path):
    client, _ = _client(tmp_path)
    r = client.get("/generations/nope/images/x.png")
    assert r.status_code == 404


def test_cancel_deletes_record_and_returns_204(tmp_path, monkeypatch):
    client, _ = _client(tmp_path)
    wid = _import_workflow(client)
    _config(client, wid)

    from app.integrations.comfyui.client import ComfyUIClient
    from app.services.generation import GenerationService

    class FakeComfy:
        def submit_prompt(self, prompt):
            return "p-1", "c-1"
        def get_history(self, prompt_id):
            return {}
        def wait_for_history(self, prompt_id, *, timeout=1800.0, client_id=None):
            raise ComfyUIError("stub: WS never resolves in this test")
        def interrupt(self):
            pass
        def delete_queued(self, prompt_id):
            pass

    for name in ("submit_prompt", "get_history", "wait_for_history", "interrupt", "delete_queued"):
        monkeypatch.setattr(ComfyUIClient, name, getattr(FakeComfy, name))
    # Stub _watch_and_download:WS 在测试里没真连,会一直挂;改成 noop 让 cancel 在
    # miss-counter 触发之前先到(否则 cancel 与后台任务 race,状态可能先变 failed)。
    monkeypatch.setattr(GenerationService, "_watch_and_download", lambda self, generation_id: None)

    gen = client.post("/generations", json={
        "workflow_id": wid,
        "parameters": {"positive_prompt": "cat", "seed": 42, "seed_random": False},
    }).json()

    r = client.post(f"/generations/{gen['id']}/cancel")
    assert r.status_code == 204, r.text
    # 中止的生成不留记录
    assert client.get(f"/generations/{gen['id']}").status_code == 404


def test_cancel_returns_404_for_unknown_id(tmp_path):
    client, _ = _client(tmp_path)
    r = client.post("/generations/nonexistent/cancel")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"]


def test_cancel_returns_409_for_terminal(tmp_path, monkeypatch):
    client, _ = _client(tmp_path)
    wid = _import_workflow(client)
    _config(client, wid)

    from app.integrations.comfyui.client import ComfyUIClient

    class FakeComfy:
        def submit_prompt(self, prompt):
            return "p-1", "c-1"
        def get_history(self, prompt_id):
            return {"p-1": {"status": {"status_str": "success"}, "outputs": {}}}
        def get_image(self, filename, subfolder="", image_type="output"):
            return b""
        def interrupt(self):
            pass
        def delete_queued(self, prompt_id):
            pass

    for name in ("submit_prompt", "get_history", "get_image", "interrupt", "delete_queued"):
        monkeypatch.setattr(ComfyUIClient, name, getattr(FakeComfy, name))

    gen = client.post("/generations", json={
        "workflow_id": wid,
        "parameters": {"positive_prompt": "cat", "seed": 42, "seed_random": False},
    }).json()

    import time
    for _ in range(20):
        g = client.get(f"/generations/{gen['id']}").json()
        if g["status"] == "success":
            break
        time.sleep(0.05)
    assert g["status"] == "success"

    r = client.post(f"/generations/{gen['id']}/cancel")
    assert r.status_code == 409
    assert "already terminal" in r.json()["detail"]
