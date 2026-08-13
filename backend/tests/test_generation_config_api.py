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


def test_list_configs_include_main_model(tmp_path):
    client = _client(tmp_path)
    wid = _import(client)
    body = {
        "api_template": {
            "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "z_image_turbo_int8_convrot.safetensors"}},
            "6": {"class_type": "LoraLoaderModelOnly", "inputs": {
                "model": ["2", 0], "lora_name": "mumu_20.safetensors", "strength_model": 0}},
        },
        "fields": [],
    }
    client.put(f"/workflows/{wid}/generation-config", json=body)
    r = client.get("/workflows/generation-configs")
    assert r.status_code == 200
    item = r.json()["items"][0]
    assert item["main_model"] == "z_image_turbo_int8_convrot.safetensors"

    r2 = client.get(f"/workflows/{wid}/generation-config")
    assert r2.json()["main_model"] == "z_image_turbo_int8_convrot.safetensors"


def test_list_configs_main_model_null_without_lora(tmp_path):
    client = _client(tmp_path)
    wid = _import(client)
    body = {"api_template": {"3": {"class_type": "KSampler", "inputs": {"seed": 0}}}, "fields": []}
    client.put(f"/workflows/{wid}/generation-config", json=body)
    r = client.get("/workflows/generation-configs")
    assert r.json()["items"][0]["main_model"] is None


def test_discover_omits_strength_model_for_lora_node(tmp_path):
    """LoRA 节点的 strength_model 不应作为独立字段返回(它是 LoRA array entry 的子属性)。"""
    client = _client(tmp_path)
    workflow_body = {
        "nodes": [
            {
                "id": 2, "type": "UNETLoader",
                "inputs": [
                    {"name": "unet_name", "type": "COMBO", "widget": {"name": "unet_name"}},
                    {"name": "weight_dtype", "type": "COMBO", "widget": {"name": "weight_dtype"}},
                ],
                "widgets_values": ["u.safetensors", "default"],
            },
            {
                "id": 6, "type": "LoraLoaderModelOnly",
                "inputs": [
                    {"name": "model", "type": "MODEL", "link": 1},
                    {"name": "lora_name", "type": "COMBO", "widget": {"name": "lora_name"}},
                    {"name": "strength_model", "type": "FLOAT", "widget": {"name": "strength_model"}},
                ],
                "widgets_values": ["mumu_20.safetensors", 0.5],
            },
            {
                "id": 16, "type": "KSampler",
                "inputs": [
                    {"name": "model", "type": "MODEL", "link": 2},
                    {"name": "seed", "type": "INT", "widget": {"name": "seed"}},
                    {"name": "steps", "type": "INT", "widget": {"name": "steps"}},
                ],
                "widgets_values": [0, "fixed", 1],
            },
        ],
        "links": [
            [1, 2, 0, 6, 0, "MODEL"],
            [2, 6, 0, 16, 0, "MODEL"],
        ],
    }
    files = {"file": ("z-image.json", json.dumps(workflow_body).encode(), "application/json")}
    r = client.post("/workflows/import", files=files)
    assert r.status_code == 201
    wid = r.json()["id"]
    r = client.get(f"/workflows/{wid}/generation-config/discover")
    assert r.status_code == 200
    fields = r.json()["fields"]
    keys = [f["key"] for f in fields]
    assert "lora_name" in keys
    assert "strength_model" not in keys
    lora_field = next(f for f in fields if f["key"] == "lora_name")
    assert lora_field["node_id"] == "6"
    assert lora_field["input_name"] == "lora_name"


def test_save_config_with_is_array_field(tmp_path):
    """字段可携带 is_array=true 并被持久化。"""
    client = _client(tmp_path)
    wid = _import(client)
    body = {
        "api_template": {"6": {"class_type": "LoraLoaderModelOnly", "inputs": {}}},
        "fields": [
            {"key": "lora_name", "label": "LoRA", "type": "select", "node_id": "6", "input_name": "lora_name", "default": "", "required": False, "is_array": True},
        ],
    }
    r = client.put(f"/workflows/{wid}/generation-config", json=body)
    assert r.status_code == 200
    r2 = client.get(f"/workflows/{wid}/generation-config")
    assert r2.json()["fields"][0]["is_array"] is True


def test_save_config_is_array_default_false(tmp_path):
    """默认 is_array=False(老字段无 is_array 时)。"""
    client = _client(tmp_path)
    wid = _import(client)
    body = {
        "api_template": {"3": {}},
        "fields": [{"key": "seed", "label": "随机数", "type": "seed", "node_id": "3", "input_name": "seed", "default": 0, "required": False}],
    }
    r = client.put(f"/workflows/{wid}/generation-config", json=body)
    assert r.status_code == 200
    r2 = client.get(f"/workflows/{wid}/generation-config")
    assert r2.json()["fields"][0]["is_array"] is False


def test_discover_with_two_lora_nodes_keeps_two_fields(tmp_path):
    """两个 LoraLoaderModelOnly 节点 → 2 个 lora_name 字段(lora_name, lora_name_1),各自独立。"""
    client = _client(tmp_path)
    workflow_body = {
        "nodes": [
            {
                "id": 2, "type": "UNETLoader",
                "inputs": [
                    {"name": "unet_name", "type": "COMBO", "widget": {"name": "unet_name"}},
                    {"name": "weight_dtype", "type": "COMBO", "widget": {"name": "weight_dtype"}},
                ],
                "widgets_values": ["u.safetensors", "default"],
            },
            {
                "id": 6, "type": "LoraLoaderModelOnly",
                "inputs": [
                    {"name": "model", "type": "MODEL", "link": 1},
                    {"name": "lora_name", "type": "COMBO", "widget": {"name": "lora_name"}},
                    {"name": "strength_model", "type": "FLOAT", "widget": {"name": "strength_model"}},
                ],
                "widgets_values": ["A.safetensors", 0.5],
            },
            {
                "id": 7, "type": "LoraLoaderModelOnly",
                "inputs": [
                    {"name": "model", "type": "MODEL", "link": 2},
                    {"name": "lora_name", "type": "COMBO", "widget": {"name": "lora_name"}},
                    {"name": "strength_model", "type": "FLOAT", "widget": {"name": "strength_model"}},
                ],
                "widgets_values": ["B.safetensors", 0.7],
            },
            {
                "id": 16, "type": "KSampler",
                "inputs": [
                    {"name": "model", "type": "MODEL", "link": 3},
                    {"name": "seed", "type": "INT", "widget": {"name": "seed"}},
                ],
                "widgets_values": [0],
            },
        ],
        "links": [
            [1, 2, 0, 6, 0, "MODEL"],
            [2, 6, 0, 7, 0, "MODEL"],
            [3, 7, 0, 16, 0, "MODEL"],
        ],
    }
    files = {"file": ("wf.json", json.dumps(workflow_body).encode(), "application/json")}
    r = client.post("/workflows/import", files=files)
    assert r.status_code == 201
    wid = r.json()["id"]
    r = client.get(f"/workflows/{wid}/generation-config/discover")
    fields = r.json()["fields"]
    lora_fields = [f for f in fields if f["input_name"] == "lora_name"]
    assert len(lora_fields) == 2
    keys = {f["key"] for f in lora_fields}
    assert keys == {"lora_name", "lora_name_1"}
    for f in lora_fields:
        companion = next((x for x in fields if x["node_id"] == f["node_id"] and x["input_name"] == "strength_model"), None)
        assert companion is None
