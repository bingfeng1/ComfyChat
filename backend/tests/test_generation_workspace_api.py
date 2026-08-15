import json

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
        database_url=f"sqlite:///{tmp_path}/genws.db",
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


def _patch_comfy(monkeypatch):
    from app.integrations.comfyui.client import ComfyUIClient
    from app.services.generation import GenerationService

    class FakeComfy:
        def submit_prompt(self, prompt):
            return "p-1", "c-1"
        def get_history(self, prompt_id):
            return {}
        def wait_for_history(self, prompt_id, *, timeout=1800.0, client_id=None):
            raise Exception("WS not used in this test")
        def get_image(self, filename, subfolder="", image_type="output"):
            return b"PNG"
    for name in ("submit_prompt", "get_history", "wait_for_history", "get_image"):
        monkeypatch.setattr(ComfyUIClient, name, getattr(FakeComfy, name))
    # 关闭后台 WS 等待,避免测试 hang
    monkeypatch.setattr(GenerationService, "_watch_and_download", lambda self, gid: None)


def _create_ws(client, name):
    r = client.post("/workspaces", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_gen(client, wid, **extra):
    payload = {
        "workflow_id": wid,
        "parameters": {"positive_prompt": "cat", "seed": 42, "seed_random": False},
    }
    payload.update(extra)
    return client.post("/generations", json=payload).json()


def test_create_gen_with_workspace_ids(tmp_path, monkeypatch):
    client, _ = _client(tmp_path)
    wid = _import_workflow(client)
    _config(client, wid)
    _patch_comfy(monkeypatch)

    w1 = _create_ws(client, "W1")
    w2 = _create_ws(client, "W2")

    r = client.post("/generations", json={
        "workflow_id": wid,
        "parameters": {"positive_prompt": "cat", "seed": 42, "seed_random": False},
        "workspace_ids": [w1, w2],
    })
    assert r.status_code == 201, r.text
    gen = r.json()
    assert sorted(gen["workspace_ids"]) == sorted([w1, w2])

    # GET 单条也带 workspace_ids
    r = client.get(f"/generations/{gen['id']}")
    assert sorted(r.json()["workspace_ids"]) == sorted([w1, w2])

    # 列表带 workspace_ids
    r = client.get("/generations")
    assert sorted(r.json()["items"][0]["workspace_ids"]) == sorted([w1, w2])


def test_create_gen_no_workspace(tmp_path, monkeypatch):
    client, _ = _client(tmp_path)
    wid = _import_workflow(client)
    _config(client, wid)
    _patch_comfy(monkeypatch)

    r = client.post("/generations", json={
        "workflow_id": wid,
        "parameters": {"positive_prompt": "x", "seed": 1, "seed_random": False},
    })
    assert r.status_code == 201, r.text
    assert r.json()["workspace_ids"] == []


def test_create_gen_skips_missing_workspace_ids(tmp_path, monkeypatch):
    """不存在的 workspace_id 静默跳过(不报错)"""
    client, _ = _client(tmp_path)
    wid = _import_workflow(client)
    _config(client, wid)
    _patch_comfy(monkeypatch)
    w1 = _create_ws(client, "Real")

    r = client.post("/generations", json={
        "workflow_id": wid,
        "parameters": {"positive_prompt": "x", "seed": 1, "seed_random": False},
        "workspace_ids": [w1, "does-not-exist"],
    })
    assert r.status_code == 201, r.text
    assert r.json()["workspace_ids"] == [w1]


def test_list_filter_by_workspace(tmp_path, monkeypatch):
    client, _ = _client(tmp_path)
    wid = _import_workflow(client)
    _config(client, wid)
    _patch_comfy(monkeypatch)

    w1 = _create_ws(client, "W1")
    w2 = _create_ws(client, "W2")

    g1 = client.post("/generations", json={
        "workflow_id": wid,
        "parameters": {"positive_prompt": "a", "seed": 1, "seed_random": False},
        "workspace_ids": [w1],
    }).json()
    g2 = client.post("/generations", json={
        "workflow_id": wid,
        "parameters": {"positive_prompt": "b", "seed": 2, "seed_random": False},
        "workspace_ids": [w2],
    }).json()
    client.post("/generations", json={
        "workflow_id": wid,
        "parameters": {"positive_prompt": "c", "seed": 3, "seed_random": False},
    })  # no workspace

    r = client.get(f"/generations?workspace_id={w1}").json()
    assert [g["id"] for g in r["items"]] == [g1["id"]]
    assert r["total"] == 1

    r = client.get(f"/generations?workspace_id={w2}").json()
    assert [g["id"] for g in r["items"]] == [g2["id"]]
    assert r["total"] == 1


def test_set_workspaces_full_replace(tmp_path, monkeypatch):
    client, _ = _client(tmp_path)
    wid = _import_workflow(client)
    _config(client, wid)
    _patch_comfy(monkeypatch)

    w1 = _create_ws(client, "W1")
    w2 = _create_ws(client, "W2")
    w3 = _create_ws(client, "W3")

    gen = client.post("/generations", json={
        "workflow_id": wid,
        "parameters": {"positive_prompt": "x", "seed": 1, "seed_random": False},
        "workspace_ids": [w1, w2],
    }).json()
    assert sorted(gen["workspace_ids"]) == sorted([w1, w2])

    # 替换为 [w2, w3]
    r = client.post(f"/generations/{gen['id']}/workspaces", json={"workspace_ids": [w2, w3]})
    assert r.status_code == 204
    got = client.get(f"/generations/{gen['id']}").json()
    assert sorted(got["workspace_ids"]) == sorted([w2, w3])

    # 清空
    r = client.post(f"/generations/{gen['id']}/workspaces", json={"workspace_ids": []})
    assert r.status_code == 204
    got = client.get(f"/generations/{gen['id']}").json()
    assert got["workspace_ids"] == []


def test_remove_single_workspace(tmp_path, monkeypatch):
    client, _ = _client(tmp_path)
    wid = _import_workflow(client)
    _config(client, wid)
    _patch_comfy(monkeypatch)

    w1 = _create_ws(client, "W1")
    w2 = _create_ws(client, "W2")

    gen = client.post("/generations", json={
        "workflow_id": wid,
        "parameters": {"positive_prompt": "x", "seed": 1, "seed_random": False},
        "workspace_ids": [w1, w2],
    }).json()

    r = client.delete(f"/generations/{gen['id']}/workspaces/{w1}")
    assert r.status_code == 204
    got = client.get(f"/generations/{gen['id']}").json()
    assert got["workspace_ids"] == [w2]


def test_set_workspaces_on_missing_gen_returns_404(tmp_path):
    client, _ = _client(tmp_path)
    w1 = _create_ws(client, "W1")
    r = client.post("/generations/missing/workspaces", json={"workspace_ids": [w1]})
    assert r.status_code == 404


def test_delete_workspace_does_not_delete_generation(tmp_path, monkeypatch):
    """关键语义:删 workspace 不删 generation"""
    client, _ = _client(tmp_path)
    wid = _import_workflow(client)
    _config(client, wid)
    _patch_comfy(monkeypatch)

    ws = _create_ws(client, "Favorites")
    gen = client.post("/generations", json={
        "workflow_id": wid,
        "parameters": {"positive_prompt": "x", "seed": 1, "seed_random": False},
        "workspace_ids": [ws],
    }).json()
    assert gen["workspace_ids"] == [ws]

    # 删 workspace
    r = client.delete(f"/workspaces/{ws}")
    assert r.status_code == 204

    # generation 仍在,workspace_ids 已被清空
    r = client.get(f"/generations/{gen['id']}")
    assert r.status_code == 200
    assert r.json()["workspace_ids"] == []

    # generation-count 显示 0
    # (workspace 已删,无法再查 generation-count — 但 list 该 gen 仍然可访问)


def test_bulk_assign_via_api(tmp_path, monkeypatch):
    """单条 assign 接口: 把已存在的 gen 加入 ws(幂等)"""
    client, _ = _client(tmp_path)
    wid = _import_workflow(client)
    _config(client, wid)
    _patch_comfy(monkeypatch)

    ws = _create_ws(client, "Bin")
    gen = client.post("/generations", json={
        "workflow_id": wid,
        "parameters": {"positive_prompt": "x", "seed": 1, "seed_random": False},
    }).json()
    assert gen["workspace_ids"] == []

    r = client.post(f"/workspaces/{ws}/assign/{gen['id']}")
    assert r.status_code == 204

    got = client.get(f"/generations/{gen['id']}").json()
    assert got["workspace_ids"] == [ws]

    # 幂等: 再 assign 不报错
    r = client.post(f"/workspaces/{ws}/assign/{gen['id']}")
    assert r.status_code == 204
    got = client.get(f"/generations/{gen['id']}").json()
    assert got["workspace_ids"] == [ws]


def test_assign_on_missing_returns_404(tmp_path):
    client, _ = _client(tmp_path)
    ws = _create_ws(client, "Bin")
    r = client.post(f"/workspaces/{ws}/assign/missing-gen")
    assert r.status_code == 404
    r = client.post("/workspaces/missing-ws/assign/whatever")
    assert r.status_code == 404
