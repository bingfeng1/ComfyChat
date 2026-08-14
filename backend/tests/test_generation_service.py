import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.integrations.comfyui.client import ComfyUIError
from app.models.generation import Generation
from app.repositories.generation import GenerationRepository, WorkflowGenerationConfigRepository
from app.services.generation import (
    GenerationService,
    _field_meta,
    _object_info_schema,
    append_lora_trigger,
    apply_parameters,
    discover_fields,
    infer_field_type,
    workflow_to_api_template,
)


TEMPLATE = {
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
    "3": {"class_type": "KSampler", "inputs": {"seed": 0}},
}

FIELDS = [
    {"key": "positive_prompt", "label": "正面提示词", "type": "text", "node_id": "6", "input_name": "text", "default": "", "required": True},
    {"key": "seed", "label": "随机数", "type": "seed", "node_id": "3", "input_name": "seed", "default": 0, "required": True},
]


def _config(session, workflow_id):
    WorkflowGenerationConfigRepository(session).upsert(workflow_id, TEMPLATE, FIELDS)


def _settings(tmp_path):
    return Settings(storage_root=tmp_path / "storage", comfyui_base_url="http://example.com:8188/")


def _service(session, settings, comfyui):
    return GenerationService(
        GenerationRepository(session),
        WorkflowGenerationConfigRepository(session),
        comfyui,
        settings,
    )


def test_apply_parameters_fills_template_and_records():
    filled, effective = apply_parameters(
        json.loads(json.dumps(TEMPLATE)), FIELDS,
        {"positive_prompt": "cat", "seed": 42, "seed_random": False},
    )
    assert filled["6"]["inputs"]["text"] == "cat"
    assert filled["3"]["inputs"]["seed"] == 42
    assert effective["positive_prompt"] == "cat"
    assert effective["seed"] == 42


def test_apply_parameters_generates_random_seed():
    filled, effective = apply_parameters(
        json.loads(json.dumps(TEMPLATE)), FIELDS,
        {"positive_prompt": "cat", "seed": 123, "seed_random": True},
    )
    assert filled["3"]["inputs"]["seed"] != 123
    assert 0 <= filled["3"]["inputs"]["seed"] < 2**32
    assert effective["seed"] == filled["3"]["inputs"]["seed"]
    assert effective["seed_random"] is True


def test_apply_parameters_requires_missing_required():
    with pytest.raises(ValueError):
        apply_parameters(json.loads(json.dumps(TEMPLATE)), FIELDS, {})


def test_apply_parameters_rejects_bad_seed_type():
    with pytest.raises(ValueError):
        apply_parameters(
            json.loads(json.dumps(TEMPLATE)), FIELDS,
            {"positive_prompt": "cat", "seed": "abc", "seed_random": False},
        )


class FakeComfy:
    def __init__(self):
        self.submitted = None
        self.history = {}
        self.queue = {"queue_running": [], "queue_pending": []}
        # 模拟 WS 等待:返回当前 history 条目(空 → ComfyUIError 模拟 WS 超时回退到空 history)。
        self.wait_history_should_fail = False

    def submit_prompt(self, prompt):
        self.submitted = prompt
        return "p-1", "client-1"

    def get_history(self, prompt_id):
        return self.history

    def get_queue(self):
        return self.queue

    def wait_for_history(self, prompt_id, *, timeout=1800.0, client_id=None):
        if self.wait_history_should_fail and self.history.get(prompt_id) is None:
            raise ComfyUIError("WS wait failed and /history empty")
        return self.history.get(prompt_id) or {}

    def get_image(self, filename, subfolder="", image_type="output"):
        return b"PNGDATA"


def test_create_success(session, tmp_path):
    settings = _settings(tmp_path)
    _config(session, "wf1")
    svc = _service(session, settings, FakeComfy())
    gen = svc.create("wf1", {"positive_prompt": "cat", "seed": 5, "seed_random": False})
    assert gen.status == "queued"
    assert gen.prompt_id == "p-1"


def test_create_requires_config(session, tmp_path):
    svc = _service(session, _settings(tmp_path), FakeComfy())
    with pytest.raises(ValueError):
        svc.create("wf1", {})


def test_outputs_dir_uses_year_month(session, tmp_path):
    settings = _settings(tmp_path)
    svc = _service(session, settings, FakeComfy())
    gen = Generation(
        workflow_id="wf1", workflow_name="z-image", parameters_json="{}",
        status="queued", prompt_id="p1", created_at="2026-08-09T12:00:00+00:00",
    )
    d = svc.outputs_dir(gen)
    assert d == settings.storage_root / "outputs" / "2026-08"


def test_outputs_dir_falls_back_for_empty_created_at(session, tmp_path):
    settings = _settings(tmp_path)
    svc = _service(session, settings, FakeComfy())
    gen = Generation(
        workflow_id="wf1", workflow_name="z-image", parameters_json="{}",
        status="queued", prompt_id="p1",
    )
    d = svc.outputs_dir(gen)
    assert d == settings.storage_root / "outputs" / "unknown"


def test_watch_downloads_images_and_succeeds(session, tmp_path):
    """WS 完成事件触发 → 下载图片 → 标记 success。"""
    settings = _settings(tmp_path)
    _config(session, "wf1")
    comfy = FakeComfy()
    comfy.history = {
        "p-1": {
            "status": {"status_str": "success"},
            "outputs": {"9": {"images": [{"filename": "out.png", "subfolder": "", "type": "output"}]}},
        }
    }
    svc = _service(session, settings, comfy)
    gen = svc.create("wf1", {"positive_prompt": "cat", "seed": 5, "seed_random": False})

    svc._watch_and_download(gen.id)

    got = GenerationRepository(session).get(gen.id)
    assert got.status == "success"
    assert json.loads(got.outputs_json) == ["out.png"]
    assert (svc.outputs_dir(gen) / "out.png").read_bytes() == b"PNGDATA"


def test_dedup_target_appends_suffix_on_collision(session, tmp_path):
    settings = _settings(tmp_path)
    svc = _service(session, settings, FakeComfy())
    out_dir = settings.storage_root / "outputs" / "2026-08"
    out_dir.mkdir(parents=True)
    (out_dir / "a.png").write_bytes(b"x")
    first = svc._dedup_target(out_dir, "a.png")
    assert first.name == "a_1.png"
    first.write_bytes(b"y")
    second = svc._dedup_target(out_dir, "a.png")
    assert second.name == "a_2.png"


def test_delete_outputs_only_removes_own_files(session, tmp_path):
    """平铺布局下,删除一条生成记录不能误删同月其他 generation 的文件。"""
    settings = _settings(tmp_path)
    svc = _service(session, settings, FakeComfy())
    repo = GenerationRepository(session)
    g1 = repo.create("wf1", "z-image", {}, "success", "p-1")
    g2 = repo.create("wf1", "z-image", {}, "success", "p-2")
    # 两条记录都指向 outputs/{YYYY-MM}/ (同月)
    out_dir = svc.outputs_dir(g1)
    out_dir.mkdir(parents=True)
    (out_dir / "mine.png").write_bytes(b"1")
    (out_dir / "others.png").write_bytes(b"2")
    repo.update_success(g1.id, ["mine.png"])
    repo.update_success(g2.id, ["others.png"])

    svc._delete_outputs(g1)

    assert not (out_dir / "mine.png").exists()
    assert (out_dir / "others.png").exists()


def test_watch_marks_failed_on_error_status(session, tmp_path):
    """WS 完成事件携带 status_str=error → 标记 failed,error 字段含 messages。"""
    settings = _settings(tmp_path)
    _config(session, "wf1")
    comfy = FakeComfy()
    comfy.history = {"p-1": {"status": {"status_str": "error", "messages": [["execution_error", "boom"]]}}}
    svc = _service(session, settings, comfy)
    gen = svc.create("wf1", {"positive_prompt": "cat", "seed": 5, "seed_random": False})

    svc._watch_and_download(gen.id)

    got = GenerationRepository(session).get(gen.id)
    assert got.status == "failed"
    assert got.error


def test_watch_falls_back_to_history_when_ws_fails(session, tmp_path):
    """WS 超时/断连 → 回退到 /history 一次性查询;若已写入则正常完成。"""
    settings = _settings(tmp_path)
    _config(session, "wf1")
    comfy = FakeComfy()
    comfy.wait_history_should_fail = True
    comfy.history = {
        "p-1": {"status": {"status_str": "success"}, "outputs": {}},
    }
    svc = _service(session, settings, comfy)
    gen = svc.create("wf1", {"positive_prompt": "cat", "seed": 5, "seed_random": False})

    svc._watch_and_download(gen.id)

    assert GenerationRepository(session).get(gen.id).status == "success"


def test_watch_marks_failed_when_ws_fails_and_history_empty(session, tmp_path):
    """WS 失败且 /history 仍无 entry(说明 prompt 真丢了)→ 标记 failed。"""
    settings = _settings(tmp_path)
    _config(session, "wf1")
    comfy = FakeComfy()
    comfy.wait_history_should_fail = True
    comfy.history = {}
    svc = _service(session, settings, comfy)
    gen = svc.create("wf1", {"positive_prompt": "cat", "seed": 5, "seed_random": False})

    svc._watch_and_download(gen.id)

    got = GenerationRepository(session).get(gen.id)
    assert got.status == "failed"
    assert got.error


def test_reconcile_finalizes_pending_tasks_via_history_check(session, tmp_path):
    """reconcile:对 queued/running 行做一次性 /history 检查,有 entry 即完成。"""
    settings = _settings(tmp_path)
    _config(session, "wf1")
    comfy = FakeComfy()
    comfy.history = {
        "p-1": {"status": {"status_str": "success"}, "outputs": {}},
        "p-2": {"status": {"status_str": "error", "messages": [["execution_error", "x"]]}},
    }
    svc = _service(session, settings, comfy)
    repo = GenerationRepository(session)
    g1 = repo.create("wf1", "z-image", {}, "running", "p-1")
    g2 = repo.create("wf1", "z-image", {}, "running", "p-2")

    svc.reconcile()

    assert repo.get(g1.id).status == "success"
    assert repo.get(g2.id).status == "failed"


UI_BODY = {
    "nodes": [
        {
            "id": 7,
            "type": "CLIPTextEncode",
            "inputs": [
                {"name": "clip", "localized_name": "clip", "link": 1},
                {"name": "text", "localized_name": "文本", "widget": {"name": "text"}},
            ],
            "widgets_values": ["一只猫"],
        },
        {
            "id": 16,
            "type": "KSampler",
            "inputs": [
                {"name": "model", "localized_name": "模型", "link": 2},
                {"name": "seed", "localized_name": "种子", "widget": {"name": "seed"}},
                {"name": "steps", "localized_name": "步数", "widget": {"name": "steps"}},
            ],
            "widgets_values": [42, 20],
        },
    ],
    "last_node_id": 16,
}


def test_workflow_to_api_template_converts_ui_format():
    api = workflow_to_api_template(UI_BODY)
    assert api["7"] == {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "一只猫"},
    }
    assert api["16"] == {
        "class_type": "KSampler",
        "inputs": {"seed": 42, "steps": 20},
    }


def test_workflow_to_api_template_handles_empty_body():
    assert workflow_to_api_template({}) == {}


def test_infer_field_type_seed_number_text():
    assert infer_field_type("seed", 42) == "seed"
    assert infer_field_type("seed", "42") == "seed"
    assert infer_field_type("steps", 20) == "number"
    assert infer_field_type("cfg", 1.5) == "number"
    assert infer_field_type("text", "a") == "text"
    assert infer_field_type("batch_size", True) == "text"


def test_discover_fields_returns_widget_candidates():
    fields = discover_fields(UI_BODY)
    assert len(fields) == 3
    text = next(f for f in fields if f["key"] == "text")
    assert text["label"] == "文本"
    assert text["node_id"] == "7"
    assert text["input_name"] == "text"
    assert text["default"] == "一只猫"
    assert text["type"] == "text"
    seed = next(f for f in fields if f["key"] == "seed")
    assert seed["label"] == "种子"
    assert seed["type"] == "seed"
    steps = next(f for f in fields if f["key"] == "steps")
    assert steps["type"] == "number"
    assert steps["default"] == 20


def test_discover_fields_skips_link_inputs():
    fields = discover_fields(UI_BODY)
    keys = {f["key"] for f in fields}
    assert "clip" not in keys
    assert "model" not in keys


NUMBER_FIELDS = [
    {"key": "steps", "label": "步数", "type": "number", "node_id": "16", "input_name": "steps", "default": 20, "required": True},
]


def test_apply_parameters_rejects_bad_number_type():
    with pytest.raises(ValueError):
        apply_parameters(
            {"16": {"class_type": "KSampler", "inputs": {"steps": 20}}},
            NUMBER_FIELDS,
            {"steps": "abc"},
        )


def test_apply_parameters_rejects_bool_as_number():
    with pytest.raises(ValueError):
        apply_parameters(
            {"16": {"class_type": "KSampler", "inputs": {"steps": 20}}},
            NUMBER_FIELDS,
            {"steps": True},
        )


def test_apply_parameters_accepts_number():
    filled, effective = apply_parameters(
        {"16": {"class_type": "KSampler", "inputs": {"steps": 20}}},
        NUMBER_FIELDS,
        {"steps": 30},
    )
    assert filled["16"]["inputs"]["steps"] == 30
    assert effective["steps"] == 30

KSAMPLER_UI = {
    "nodes": [
        {
            "id": 16,
            "type": "KSampler",
            "inputs": [
                {"name": "model", "localized_name": "模型", "link": 2},
                {"name": "seed", "localized_name": "种子", "widget": {"name": "seed"}},
                {"name": "steps", "localized_name": "步数", "widget": {"name": "steps"}},
                {"name": "cfg", "localized_name": "cfg", "widget": {"name": "cfg"}},
                {"name": "sampler_name", "localized_name": "采样器", "widget": {"name": "sampler_name"}},
            ],
            "widgets_values": [89240564304993, "fixed", 9, 1, "euler"],
        },
    ]
}

OBJ_INFO = {
    "KSampler": {
        "input": {
            "required": {
                "seed": ["INT", {"default": 0, "min": 0, "max": 18446744073709551615, "control_after_generate": True}],
                "steps": ["INT", {"default": 20, "min": 1, "max": 10000}],
                "cfg": ["FLOAT", {"default": 8.0, "min": 0.0, "max": 100.0, "step": 0.1}],
                "sampler_name": [["euler", "lcm", "ddim"], {"default": "euler"}],
            }
        }
    }
}


def test_workflow_to_api_template_skips_control_after_generate():
    api = workflow_to_api_template(KSAMPLER_UI)
    assert api["16"]["inputs"]["seed"] == 89240564304993
    assert api["16"]["inputs"]["steps"] == 9
    assert api["16"]["inputs"]["cfg"] == 1
    assert api["16"]["inputs"]["sampler_name"] == "euler"
    assert len(api["16"]["inputs"]) == 4


def test_discover_fields_uses_object_info_metadata():
    fields = discover_fields(KSAMPLER_UI, OBJ_INFO)
    steps = next(f for f in fields if f["key"] == "steps")
    assert steps["min"] == 1
    assert steps["max"] == 10000
    assert steps["type"] == "number"
    sampler = next(f for f in fields if f["key"] == "sampler_name")
    assert sampler["type"] == "select"
    assert sampler["options"] == ["euler", "lcm", "ddim"]
    assert sampler["default"] == "euler"
    seed = next(f for f in fields if f["key"] == "seed")
    assert seed["type"] == "seed"


def test_discover_fields_falls_back_without_object_info():
    fields = discover_fields(KSAMPLER_UI)
    steps = next(f for f in fields if f["key"] == "steps")
    assert steps["type"] == "number"
    sampler = next(f for f in fields if f["key"] == "sampler_name")
    assert sampler["type"] == "text"
    assert "options" not in sampler

LOADER_BODY = {
    "nodes": [
        {
            "id": 4,
            "type": "CLIPLoader",
            "inputs": [
                {"name": "clip_name", "localized_name": "CLIP名称", "widget": {"name": "clip_name"}},
                {"name": "type", "localized_name": "类型", "widget": {"name": "type"}},
                {"name": "device", "localized_name": "设备", "widget": {"name": "device"}},
            ],
            "widgets_values": ["qwen_3_4b.safetensors", "lumina2", "default"],
        },
        {
            "id": 6,
            "type": "LoraLoaderModelOnly",
            "inputs": [
                {"name": "model", "localized_name": "模型", "link": 1},
                {"name": "lora_name", "localized_name": "LoRA名称", "widget": {"name": "lora_name"}},
                {"name": "strength_model", "localized_name": "模型强度", "widget": {"name": "strength_model"}},
            ],
            "widgets_values": ["mumu_20.safetensors", 0],
        },
    ]
}


def test_discover_fields_excludes_loader_inputs():
    fields = discover_fields(LOADER_BODY)
    keys = {f["key"] for f in fields}
    assert "clip_name" not in keys
    assert "type" not in keys
    assert "device" not in keys
    assert "strength_model" in keys


def test_discover_fields_keeps_lora_name():
    fields = discover_fields(LOADER_BODY)
    lora = next((f for f in fields if f["key"] == "lora_name"), None)
    assert lora is not None
    assert lora["node_id"] == "6"
    assert lora["default"] == "mumu_20.safetensors"


def test_discover_lora_name_is_select_with_object_info():
    body = {
        "nodes": [
            {
                "id": 6,
                "type": "LoraLoaderModelOnly",
                "inputs": [
                    {"name": "model", "localized_name": "模型", "link": 1},
                    {"name": "lora_name", "localized_name": "LoRA名称", "widget": {"name": "lora_name"}},
                    {"name": "strength_model", "localized_name": "模型强度", "widget": {"name": "strength_model"}},
                ],
                "widgets_values": ["mumu_20.safetensors", 0],
            },
        ]
    }
    obj_info = {
        "LoraLoaderModelOnly": {
            "input": {
                "required": {
                    "lora_name": [["mumu_20.safetensors", "other.safetensors"], {}],
                    "strength_model": ["FLOAT", {"default": 1.0, "min": -100.0, "max": 100.0}],
                }
            }
        }
    }
    fields = discover_fields(body, obj_info)
    lora = next(f for f in fields if f["key"] == "lora_name")
    assert lora["type"] == "select"
    assert lora["options"] == ["mumu_20.safetensors", "other.safetensors"]


SHIFT_BODY = {
    "nodes": [
        {
            "id": 15,
            "type": "ModelSamplingAuraFlow",
            "inputs": [
                {"name": "model", "localized_name": "模型", "link": 1},
                {"name": "shift", "localized_name": "移位", "widget": {"name": "shift"}},
            ],
            "widgets_values": [1.73],
        },
    ]
}


def test_discover_fields_excludes_model_sampling_shift():
    fields = discover_fields(SHIFT_BODY)
    assert fields == []

COND_BODY = {
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
            "id": 8,
            "type": "CLIPTextEncode",
            "inputs": [
                {"name": "clip", "localized_name": "clip", "link": 2},
                {"name": "text", "localized_name": "文本", "widget": {"name": "text"}},
            ],
            "widgets_values": ["blurry"],
        },
        {
            "id": 16,
            "type": "KSampler",
            "inputs": [
                {"name": "positive", "localized_name": "正面", "link": 11},
                {"name": "negative", "localized_name": "负面", "link": 12},
            ],
            "widgets_values": [],
        },
    ],
    "links": [
        [1, 4, 0, 7, 0, "CLIP"],
        [2, 4, 0, 8, 0, "CLIP"],
        [11, 7, 0, 16, 1, "CONDITIONING"],
        [12, 8, 0, 16, 2, "CONDITIONING"],
    ],
}


def test_discover_fields_labels_positive_negative():
    fields = discover_fields(COND_BODY)
    texts = {f["node_id"]: f["label"] for f in fields if f["input_name"] == "text"}
    assert texts["7"] == "正面提示词"
    assert texts["8"] == "负面提示词"

LINKED_BODY = {
    "nodes": [
        {
            "id": 16,
            "type": "KSampler",
            "inputs": [
                {"name": "model", "localized_name": "模型", "link": 10},
                {"name": "positive", "localized_name": "正面", "link": 11},
                {"name": "seed", "localized_name": "种子", "widget": {"name": "seed"}},
            ],
            "widgets_values": [42],
        },
        {
            "id": 19,
            "type": "PreviewImage",
            "inputs": [
                {"name": "images", "localized_name": "图像", "link": 17},
            ],
            "widgets_values": [],
        },
    ],
    "links": [
        [10, 15, 0, 16, 0, "MODEL"],
        [11, 7, 0, 16, 1, "CONDITIONING"],
        [17, 17, 0, 19, 0, "IMAGE"],
    ],
}


def test_workflow_to_api_template_resolves_links():
    api = workflow_to_api_template(LINKED_BODY)
    assert api["16"]["inputs"]["model"] == ["15", 0]
    assert api["16"]["inputs"]["positive"] == ["7", 0]
    assert api["16"]["inputs"]["seed"] == 42
    assert api["19"]["inputs"]["images"] == ["17", 0]


class FakeCancellableComfy(FakeComfy):
    def __init__(self):
        super().__init__()
        self.interrupt_calls = 0
        self.delete_queued_calls = []

    def interrupt(self):
        self.interrupt_calls += 1

    def delete_queued(self, prompt_id):
        self.delete_queued_calls.append(prompt_id)


def test_cancel_queued_calls_delete_queued(session, tmp_path):
    settings = _settings(tmp_path)
    _config(session, "wf1")
    comfy = FakeCancellableComfy()
    svc = _service(session, settings, comfy)
    repo = GenerationRepository(session)
    gen = svc.create("wf1", {"positive_prompt": "cat", "seed": 5, "seed_random": False})

    result = svc.cancel(gen.id)

    assert repo.get(gen.id) is None
    assert comfy.delete_queued_calls == ["p-1"]
    assert comfy.interrupt_calls == 0


def test_cancel_running_calls_interrupt(session, tmp_path):
    settings = _settings(tmp_path)
    _config(session, "wf1")
    comfy = FakeCancellableComfy()
    comfy.history = {}
    svc = _service(session, settings, comfy)
    repo = GenerationRepository(session)
    gen = repo.create("wf1", "z-image", {}, "running", "p-1")

    result = svc.cancel(gen.id)

    assert repo.get(gen.id) is None
    assert comfy.interrupt_calls == 1
    assert comfy.delete_queued_calls == []


def test_cancel_terminal_status_raises(session, tmp_path):
    settings = _settings(tmp_path)
    comfy = FakeCancellableComfy()
    svc = _service(session, settings, comfy)
    repo = GenerationRepository(session)
    gen = repo.create("wf1", "z-image", {}, "success", "p-1")

    with pytest.raises(ValueError, match="already terminal"):
        svc.cancel(gen.id)


def test_cancel_not_found_raises(session, tmp_path):
    settings = _settings(tmp_path)
    svc = _service(session, settings, FakeCancellableComfy())

    with pytest.raises(ValueError, match="not found"):
        svc.cancel("nonexistent")


def test_cancel_swallows_comfyui_error(session, tmp_path):
    settings = _settings(tmp_path)
    _config(session, "wf1")
    comfy = FakeCancellableComfy()
    comfy.history = {}
    svc = _service(session, settings, comfy)
    repo = GenerationRepository(session)
    gen = repo.create("wf1", "z-image", {}, "running", "p-1")

    def boom():
        raise ComfyUIError("comfyui down")

    comfy.interrupt = boom

    result = svc.cancel(gen.id)

    assert repo.get(gen.id) is None


# ---- append_lora_trigger ----------------------------------------------------

TRIGGER_FIELDS = [
    {"key": "text", "label": "正面提示词", "type": "text", "node_id": "7", "input_name": "text", "default": "", "required": False},
    {"key": "text_1", "label": "负面提示词", "type": "text", "node_id": "8", "input_name": "text", "default": "", "required": False},
    {"key": "lora_name", "label": "LoRA", "type": "select", "node_id": "6", "input_name": "lora_name", "default": "", "required": False},
    {"key": "strength_model", "label": "强度", "type": "number", "node_id": "6", "input_name": "strength_model", "default": 1.0, "required": False},
]


def _seed_lora(session, name, trigger):
    from app.models.lora import Lora
    session.add(Lora(name=name, trigger_words=trigger, is_nsfw=False))
    session.commit()


def _filled_with_effective(text="", lora=None, strength=1.0):
    filled = {
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": text}},
        "8": {"class_type": "CLIPTextEncode", "inputs": {"text": "blurry"}},
        "6": {"class_type": "LoraLoaderModelOnly", "inputs": {"lora_name": lora, "strength_model": strength}},
    }
    effective = {"text": text, "lora_name": lora, "strength_model": strength}
    return filled, effective


def test_append_lora_trigger_adds_separate_line(session):
    _seed_lora(session, "mumu_20.safetensors", "mumu")
    filled, effective = _filled_with_effective(text="a girl", lora="mumu_20.safetensors", strength=1.0)
    append_lora_trigger(filled, TRIGGER_FIELDS, effective, session)
    assert filled["7"]["inputs"]["text"] == "a girl\nmumu"


def test_append_lora_trigger_fills_empty_text(session):
    _seed_lora(session, "mumu_20.safetensors", "mumu")
    filled, effective = _filled_with_effective(text="", lora="mumu_20.safetensors", strength=1.0)
    append_lora_trigger(filled, TRIGGER_FIELDS, effective, session)
    assert filled["7"]["inputs"]["text"] == "mumu"


def test_append_lora_trigger_skips_when_strength_zero(session):
    _seed_lora(session, "mumu_20.safetensors", "mumu")
    filled, effective = _filled_with_effective(text="a girl", lora="mumu_20.safetensors", strength=0)
    append_lora_trigger(filled, TRIGGER_FIELDS, effective, session)
    assert filled["7"]["inputs"]["text"] == "a girl"


def test_append_lora_trigger_skips_when_strength_missing(session):
    _seed_lora(session, "mumu_20.safetensors", "mumu")
    filled, effective = _filled_with_effective(text="a girl", lora="mumu_20.safetensors")
    effective.pop("strength_model", None)
    append_lora_trigger(filled, TRIGGER_FIELDS, effective, session)
    assert filled["7"]["inputs"]["text"] == "a girl"


def test_append_lora_trigger_skips_when_no_lora(session):
    filled, effective = _filled_with_effective(text="a girl", lora=None, strength=1.0)
    append_lora_trigger(filled, TRIGGER_FIELDS, effective, session)
    assert filled["7"]["inputs"]["text"] == "a girl"


def test_append_lora_trigger_skips_when_no_trigger_words(session):
    _seed_lora(session, "noloop.safetensors", None)
    filled, effective = _filled_with_effective(text="a girl", lora="noloop.safetensors", strength=1.0)
    append_lora_trigger(filled, TRIGGER_FIELDS, effective, session)
    assert filled["7"]["inputs"]["text"] == "a girl"


def test_append_lora_trigger_dedup_case_insensitive(session):
    _seed_lora(session, "mumu_20.safetensors", "mumu")
    filled, effective = _filled_with_effective(text="a girl, Mumu", lora="mumu_20.safetensors", strength=1.0)
    append_lora_trigger(filled, TRIGGER_FIELDS, effective, session)
    assert filled["7"]["inputs"]["text"] == "a girl, Mumu"


def test_append_lora_trigger_does_not_touch_negative(session):
    _seed_lora(session, "mumu_20.safetensors", "mumu")
    filled, effective = _filled_with_effective(text="a girl", lora="mumu_20.safetensors", strength=1.0)
    append_lora_trigger(filled, TRIGGER_FIELDS, effective, session)
    assert filled["8"]["inputs"]["text"] == "blurry"


def test_create_with_auto_add_trigger_appends_to_filled_not_effective(session, tmp_path):
    settings = _settings(tmp_path)
    api_template = {
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
        "8": {"class_type": "CLIPTextEncode", "inputs": {"text": "blurry"}},
        "6": {"class_type": "LoraLoaderModelOnly", "inputs": {"lora_name": "", "strength_model": 1.0}},
    }
    WorkflowGenerationConfigRepository(session).upsert("wf1", api_template, TRIGGER_FIELDS)
    _seed_lora(session, "mumu_20.safetensors", "mumu")
    comfy = FakeComfy()
    svc = _service(session, settings, comfy)
    gen = svc.create("wf1", {
        "text": "a girl",
        "lora_name": "mumu_20.safetensors",
        "strength_model": 1.0,
        "auto_add_trigger": True,
    })
    assert comfy.submitted["7"]["inputs"]["text"] == "a girl\nmumu"
    params = json.loads(gen.parameters_json)
    assert params["text"] == "a girl"  # 入库不含 trigger
    assert "auto_add_trigger" not in params  # 标志不入库


def test_create_with_auto_add_trigger_false(session, tmp_path):
    settings = _settings(tmp_path)
    api_template = {
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
        "8": {"class_type": "CLIPTextEncode", "inputs": {"text": "blurry"}},
        "6": {"class_type": "LoraLoaderModelOnly", "inputs": {"lora_name": "", "strength_model": 1.0}},
    }
    WorkflowGenerationConfigRepository(session).upsert("wf1", api_template, TRIGGER_FIELDS)
    _seed_lora(session, "mumu_20.safetensors", "mumu")
    comfy = FakeComfy()
    svc = _service(session, settings, comfy)
    gen = svc.create("wf1", {
        "text": "a girl",
        "lora_name": "mumu_20.safetensors",
        "strength_model": 1.0,
        "auto_add_trigger": False,
    })
    assert comfy.submitted["7"]["inputs"]["text"] == "a girl"
    assert json.loads(gen.parameters_json)["text"] == "a girl"


# ---- is_array: per-anchor LoRA chain rebuild ---------------------------------

LORA_API_TEMPLATE = {
    "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "u.safetensors", "weight_dtype": "default"}},
    "23": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["2", 0], "lora_name": "", "strength_model": 1.0}},
    "15": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["23", 0], "shift": 5}},
    "16": {"class_type": "KSampler", "inputs": {"model": ["15", 0], "seed": 0}},
    "7": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
}

LORA_ARRAY_FIELD = {
    "key": "lora_name", "label": "LoRA", "type": "select", "node_id": "23",
    "input_name": "lora_name", "default": "", "required": False, "is_array": True,
}


def test_apply_parameters_lora_array_single_entry():
    """1 entry → 1 new node, model=upstream, downstream 指向新节点。"""
    filled, effective = apply_parameters(
        json.loads(json.dumps(LORA_API_TEMPLATE)),
        [LORA_ARRAY_FIELD],
        {"lora_name": [{"lora_name": "X.safetensors", "strength_model": 0.5}]},
    )
    assert "23" not in filled
    new_ids = [nid for nid in filled if filled[nid]["class_type"] == "LoraLoaderModelOnly"]
    assert len(new_ids) == 1
    new_id = new_ids[0]
    node = filled[new_id]
    assert node["inputs"]["lora_name"] == "X.safetensors"
    assert node["inputs"]["strength_model"] == 0.5
    assert node["inputs"]["model"] == ["2", 0]
    assert filled["15"]["inputs"]["model"] == [new_id, 0]
    assert effective["lora_name"] == [{"lora_name": "X.safetensors", "strength_model": 0.5}]


def test_apply_parameters_lora_array_multiple_entries():
    """3 entries → 3 new nodes chained in place. downstream 指向最后一个。"""
    filled, effective = apply_parameters(
        json.loads(json.dumps(LORA_API_TEMPLATE)),
        [LORA_ARRAY_FIELD],
        {"lora_name": [
            {"lora_name": "A.safetensors", "strength_model": 0.5},
            {"lora_name": "B.safetensors", "strength_model": 0.7},
            {"lora_name": "C.safetensors", "strength_model": 0.9},
        ]},
    )
    assert "23" not in filled
    new_ids = sorted(
        nid for nid in filled
        if filled[nid]["class_type"] == "LoraLoaderModelOnly"
    )
    assert len(new_ids) == 3
    a, b, c = new_ids
    assert filled[a]["inputs"]["model"] == ["2", 0]
    assert filled[a]["inputs"]["lora_name"] == "A.safetensors"
    assert filled[b]["inputs"]["model"] == [a, 0]
    assert filled[b]["inputs"]["lora_name"] == "B.safetensors"
    assert filled[c]["inputs"]["model"] == [b, 0]
    assert filled[c]["inputs"]["lora_name"] == "C.safetensors"
    assert filled["15"]["inputs"]["model"] == [c, 0]


def test_apply_parameters_lora_array_empty():
    """0 entries → anchor 删除,downstream 直接接 upstream。"""
    filled, effective = apply_parameters(
        json.loads(json.dumps(LORA_API_TEMPLATE)),
        [LORA_ARRAY_FIELD],
        {"lora_name": []},
    )
    assert "23" not in filled
    assert filled["15"]["inputs"]["model"] == ["2", 0]
    assert effective["lora_name"] == []


def test_apply_parameters_lora_array_node_ids_dont_clash():
    """新节点 ID 不会与模板中现有数字 ID 冲突,且按顺序递增。"""
    tmpl = json.loads(json.dumps(LORA_API_TEMPLATE))
    # 在模板里塞一个非 LoRA 数字 ID = 999,确认新节点 ID 跳到 1000
    tmpl["999"] = {"class_type": "Note", "inputs": {}}
    filled, _ = apply_parameters(
        tmpl,
        [LORA_ARRAY_FIELD],
        {"lora_name": [{"lora_name": "X.safetensors", "strength_model": 0.5}]},
    )
    new_ids = [nid for nid in filled if filled[nid]["class_type"] == "LoraLoaderModelOnly"]
    assert len(new_ids) == 1
    assert int(new_ids[0]) > 999


def test_apply_parameters_lora_array_two_anchors_independent():
    """两个 LoRA 占位都标 array,apply 顺序执行,后者看到前者的产物。"""
    tmpl = {
        "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "u.safetensors", "weight_dtype": "default"}},
        "23": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["2", 0], "lora_name": "", "strength_model": 1.0}},
        "24": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["23", 0], "lora_name": "", "strength_model": 1.0}},
        "15": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["24", 0], "shift": 5}},
        "16": {"class_type": "KSampler", "inputs": {"model": ["15", 0], "seed": 0}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
    }
    fields = [
        {"key": "lora_name", "label": "L1", "type": "select", "node_id": "23", "input_name": "lora_name", "default": "", "is_array": True},
        {"key": "lora_name_1", "label": "L2", "type": "select", "node_id": "24", "input_name": "lora_name", "default": "", "is_array": True},
    ]
    filled, _ = apply_parameters(
        json.loads(json.dumps(tmpl)),
        fields,
        {
            "lora_name": [
                {"lora_name": "A.safetensors", "strength_model": 0.5},
                {"lora_name": "B.safetensors", "strength_model": 0.6},
            ],
            "lora_name_1": [
                {"lora_name": "X.safetensors", "strength_model": 0.7},
            ],
        },
    )
    a_nodes = sorted(nid for nid in filled if filled[nid]["class_type"] == "LoraLoaderModelOnly")
    # 2 个 (A, B) 替换 23 + 1 个 (X) 替换 24 = 3 个
    assert len(a_nodes) == 3
    # 链顺序: A → B 接 23 上游, X 接 B 后, 15 接 X
    last = a_nodes[-1]
    second_last = a_nodes[-2]
    assert filled[last]["inputs"]["lora_name"] == "X.safetensors"
    assert filled[last]["inputs"]["model"] == [second_last, 0]
    assert filled["15"]["inputs"]["model"] == [last, 0]


def test_apply_parameters_lora_array_mixed_with_scalar_fields():
    """is_array 字段与 scalar 字段共存,各自正常处理。"""
    fields = [
        LORA_ARRAY_FIELD,
        {"key": "text", "label": "提示词", "type": "text", "node_id": "7", "input_name": "text", "default": "", "required": False},
    ]
    filled, effective = apply_parameters(
        json.loads(json.dumps(LORA_API_TEMPLATE)),
        fields,
        {
            "lora_name": [{"lora_name": "X.safetensors", "strength_model": 0.5}],
            "text": "hello",
        },
    )
    assert filled["7"]["inputs"]["text"] == "hello"
    assert effective["text"] == "hello"
    assert effective["lora_name"] == [{"lora_name": "X.safetensors", "strength_model": 0.5}]


def test_apply_parameters_lora_array_rejects_non_list():
    """is_array 但 value 不是 list → ValueError。"""
    with pytest.raises(ValueError):
        apply_parameters(
            json.loads(json.dumps(LORA_API_TEMPLATE)),
            [LORA_ARRAY_FIELD],
            {"lora_name": "X.safetensors"},
        )


def test_apply_parameters_lora_array_rejects_non_dict_entry():
    """is_array list 中非 dict 元素 → ValueError。"""
    with pytest.raises(ValueError):
        apply_parameters(
            json.loads(json.dumps(LORA_API_TEMPLATE)),
            [LORA_ARRAY_FIELD],
            {"lora_name": ["X.safetensors"]},
        )


# ---- append_lora_trigger with array -----------------------------------------

ARRAY_TRIGGER_FIELDS = [
    {"key": "text", "label": "正面提示词", "type": "text", "node_id": "7", "input_name": "text", "default": "", "required": False},
    {"key": "text_1", "label": "负面提示词", "type": "text", "node_id": "8", "input_name": "text", "default": "", "required": False},
    {"key": "lora_name", "label": "LoRA", "type": "select", "node_id": "23", "input_name": "lora_name", "default": "", "is_array": True},
]


def _filled_with_array_effectiv(text="", entries=None):
    filled = {
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": text}},
        "8": {"class_type": "CLIPTextEncode", "inputs": {"text": "blurry"}},
    }
    effective = {"text": text, "lora_name": entries or []}
    return filled, effective


def test_append_lora_trigger_array_multiple_entries(session):
    """多 LoRA trigger 都拼到 text,先后顺序与 entries 一致。"""
    _seed_lora(session, "mumu.safetensors", "mumu")
    _seed_lora(session, "cat.safetensors", "cat")
    filled, effective = _filled_with_array_effectiv(
        text="a girl",
        entries=[
            {"lora_name": "mumu.safetensors", "strength_model": 1.0},
            {"lora_name": "cat.safetensors", "strength_model": 0.5},
        ],
    )
    append_lora_trigger(filled, ARRAY_TRIGGER_FIELDS, effective, session)
    assert filled["7"]["inputs"]["text"] == "a girl\nmumu\ncat"


def test_append_lora_trigger_array_skips_zero_strength_entry(session):
    """单条 strength=0 跳过,其他正常追加。"""
    _seed_lora(session, "mumu.safetensors", "mumu")
    _seed_lora(session, "cat.safetensors", "cat")
    filled, effective = _filled_with_array_effectiv(
        text="a girl",
        entries=[
            {"lora_name": "mumu.safetensors", "strength_model": 0},
            {"lora_name": "cat.safetensors", "strength_model": 0.5},
        ],
    )
    append_lora_trigger(filled, ARRAY_TRIGGER_FIELDS, effective, session)
    assert filled["7"]["inputs"]["text"] == "a girl\ncat"


def test_append_lora_trigger_array_dedup_within_session(session):
    """trigger 已存在则跳过;不重复添加。"""
    _seed_lora(session, "mumu.safetensors", "mumu")
    _seed_lora(session, "cat.safetensors", "cat")
    filled, effective = _filled_with_array_effectiv(
        text="a girl, mumu",
        entries=[
            {"lora_name": "mumu.safetensors", "strength_model": 1.0},
            {"lora_name": "cat.safetensors", "strength_model": 1.0},
        ],
    )
    append_lora_trigger(filled, ARRAY_TRIGGER_FIELDS, effective, session)
    assert filled["7"]["inputs"]["text"] == "a girl, mumu\ncat"


def test_append_lora_trigger_array_empty_list(session):
    """空 list → text 不变。"""
    filled, effective = _filled_with_array_effectiv(text="a girl", entries=[])
    append_lora_trigger(filled, ARRAY_TRIGGER_FIELDS, effective, session)
    assert filled["7"]["inputs"]["text"] == "a girl"


def test_append_lora_trigger_array_does_not_touch_negative(session):
    _seed_lora(session, "mumu.safetensors", "mumu")
    filled, effective = _filled_with_array_effectiv(
        text="a girl",
        entries=[{"lora_name": "mumu.safetensors", "strength_model": 1.0}],
    )
    append_lora_trigger(filled, ARRAY_TRIGGER_FIELDS, effective, session)
    assert filled["8"]["inputs"]["text"] == "blurry"


def test_append_lora_trigger_array_with_create_end_to_end(session, tmp_path):
    """is_array lora 字段 + auto_add_trigger → 实际提交到 ComfyUI 的 prompt 包含所有 trigger。"""
    api_template = {
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
        "8": {"class_type": "CLIPTextEncode", "inputs": {"text": "blurry"}},
        "23": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["2", 0], "lora_name": "", "strength_model": 1.0}},
        "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "u.safetensors", "weight_dtype": "default"}},
        "15": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["23", 0], "shift": 5}},
        "16": {"class_type": "KSampler", "inputs": {"model": ["15", 0], "seed": 0}},
    }
    WorkflowGenerationConfigRepository(session).upsert("wf1", api_template, ARRAY_TRIGGER_FIELDS)
    _seed_lora(session, "mumu.safetensors", "mumu")
    _seed_lora(session, "cat.safetensors", "cat")
    settings = _settings(tmp_path)
    comfy = FakeComfy()
    svc = _service(session, settings, comfy)
    gen = svc.create("wf1", {
        "text": "a girl",
        "lora_name": [
            {"lora_name": "mumu.safetensors", "strength_model": 1.0},
            {"lora_name": "cat.safetensors", "strength_model": 0.8},
        ],
        "auto_add_trigger": True,
    })
    assert comfy.submitted["7"]["inputs"]["text"] == "a girl\nmumu\ncat"
    params = json.loads(gen.parameters_json)
    assert params["text"] == "a girl"
    assert params["lora_name"] == [
        {"lora_name": "mumu.safetensors", "strength_model": 1.0},
        {"lora_name": "cat.safetensors", "strength_model": 0.8},
    ]
    # 提交了两条 LoRA 节点
    lora_ids = [nid for nid in comfy.submitted if comfy.submitted[nid]["class_type"] == "LoraLoaderModelOnly"]
    assert len(lora_ids) == 2
    # 链头接 2,链尾接 15
    assert comfy.submitted["15"]["inputs"]["model"][0] in lora_ids


def test_apply_parameters_lora_array_anchor_missing_in_template():
    """anchor node_id 在 api_template 中不存在 → 静默跳过,fields 走过后 remaining 字段不受影响。"""
    fields = [
        {"key": "lora_name", "label": "L", "type": "select", "node_id": "MISSING", "input_name": "lora_name", "is_array": True},
        {"key": "text", "label": "T", "type": "text", "node_id": "7", "input_name": "text", "default": "", "required": False},
    ]
    filled, effective = apply_parameters(
        json.loads(json.dumps(LORA_API_TEMPLATE)),
        fields,
        {"lora_name": [{"lora_name": "X", "strength_model": 0.5}], "text": "hi"},
    )
    assert filled["7"]["inputs"]["text"] == "hi"
    assert effective["lora_name"] == [{"lora_name": "X", "strength_model": 0.5}]


def test_apply_parameters_lora_array_no_downstream():
    """anchor 没有下游消费者(例如直接接 KSampler 但 model 不是 link)→ 安全跳过 reconnect。"""
    # 构造: 2 → 23 → KSampler(没有中间 modeler)
    tmpl = {
        "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "u", "weight_dtype": "default"}},
        "23": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["2", 0], "lora_name": "", "strength_model": 1.0}},
        "16": {"class_type": "KSampler", "inputs": {"model": ["23", 0], "seed": 0}},
    }
    filled, _ = apply_parameters(
        json.loads(json.dumps(tmpl)),
        [LORA_ARRAY_FIELD],
        {"lora_name": [{"lora_name": "X.safetensors", "strength_model": 0.5}]},
    )
    assert "23" not in filled
    new_ids = [nid for nid in filled if filled[nid]["class_type"] == "LoraLoaderModelOnly"]
    assert len(new_ids) == 1
    # KSampler 的 model 输入被重写为 [new_id, 0]
    assert filled["16"]["inputs"]["model"] == [new_ids[0], 0]


def test_apply_parameters_lora_array_anchor_middle_of_chain():
    """anchor 夹在两个 LoRA 节点之间 → 只替换 anchor,前后节点保留。"""
    tmpl = {
        "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "u", "weight_dtype": "default"}},
        "23": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["2", 0], "lora_name": "", "strength_model": 1.0}},
        "24": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["23", 0], "lora_name": "", "strength_model": 1.0}},
        "15": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["24", 0], "shift": 5}},
    }
    fields = [
        {"key": "lora_name", "label": "L", "type": "select", "node_id": "24", "input_name": "lora_name", "is_array": True},
    ]
    filled, _ = apply_parameters(
        json.loads(json.dumps(tmpl)),
        fields,
        {"lora_name": [
            {"lora_name": "X.safetensors", "strength_model": 0.5},
            {"lora_name": "Y.safetensors", "strength_model": 0.6},
        ]},
    )
    # 23 保留,24 被 X,Y 替换
    assert "23" in filled
    assert "24" not in filled
    new_ids = sorted(nid for nid in filled if filled[nid]["class_type"] == "LoraLoaderModelOnly")
    assert len(new_ids) == 3  # 23, X, Y
    # 23 仍接 2
    assert filled["23"]["inputs"]["model"] == ["2", 0]
    # X 接 23
    x, y = [nid for nid in new_ids if nid != "23"]
    assert filled[x]["inputs"]["model"] == ["23", 0]
    assert filled[y]["inputs"]["model"] == [x, 0]
    # 15 接 Y
    assert filled["15"]["inputs"]["model"] == [y, 0]


def test_append_lora_trigger_array_skips_non_dict_entry(session):
    """list 含非 dict 元素 → 跳过该元素,继续处理后续。"""
    _seed_lora(session, "cat.safetensors", "cat")
    filled, effective = _filled_with_array_effectiv(
        text="a girl",
        entries=[
            "not a dict",
            {"lora_name": "cat.safetensors", "strength_model": 1.0},
        ],
    )
    append_lora_trigger(filled, ARRAY_TRIGGER_FIELDS, effective, session)
    assert filled["7"]["inputs"]["text"] == "a girl\ncat"


def test_append_lora_trigger_array_skips_empty_lora_name(session):
    """entry.lora_name 为空字符串 → 跳过。"""
    _seed_lora(session, "cat.safetensors", "cat")
    filled, effective = _filled_with_array_effectiv(
        text="a girl",
        entries=[
            {"lora_name": "", "strength_model": 1.0},
            {"lora_name": "cat.safetensors", "strength_model": 1.0},
        ],
    )
    append_lora_trigger(filled, ARRAY_TRIGGER_FIELDS, effective, session)
    assert filled["7"]["inputs"]["text"] == "a girl\ncat"


# ---- 动态 COMBO 子输入 schema 解析 ----

DYNAMIC_COMBO_OBJECT_INFO = {
    "ResizeImageMaskNode": {
        "input": {
            "required": {
                "input": ["COMFY_MATCHTYPE_V3", {}],
                "resize_type": [
                    "COMFY_DYNAMICCOMBO_V3",
                    {
                        "options": [
                            {
                                "key": "scale dimensions",
                                "inputs": {
                                    "required": {
                                        "width": ["INT", {"default": 512, "min": 0, "max": 16384, "step": 1}],
                                    }
                                },
                            },
                            {
                                "key": "scale by multiplier",
                                "inputs": {
                                    "required": {
                                        "multiplier": ["FLOAT", {"default": 1.0, "min": 0.01, "max": 8.0, "step": 0.01}],
                                    }
                                },
                            },
                        ]
                    },
                ],
            }
        }
    }
}


def test_object_info_schema_plain_input():
    """普通输入直接命中 object_info 的 required/optional。"""
    schema = _object_info_schema(DYNAMIC_COMBO_OBJECT_INFO, "ResizeImageMaskNode", "resize_type")
    assert schema is not None
    assert isinstance(schema["options"], list)


def test_object_info_schema_dynamic_combo_child():
    """动态 COMBO 子输入(父输入名.子输入名)应从对应 option 的 inputs 中解析。"""
    schema = _object_info_schema(DYNAMIC_COMBO_OBJECT_INFO, "ResizeImageMaskNode", "resize_type.multiplier")
    assert schema is not None
    assert schema["min"] == 0.01
    assert schema["max"] == 8.0
    assert schema["step"] == 0.01


def test_object_info_schema_dynamic_combo_child_multiple_options():
    """同一子输入名出现在多个 option 中时合并所有元数据。"""
    obj = {
        "ResizeImageMaskNode": {
            "input": {
                "required": {
                    "resize_type": [
                        "COMFY_DYNAMICCOMBO_V3",
                        {
                            "options": [
                                {"key": "a", "inputs": {"optional": {"size": ["INT", {"min": 1, "max": 100}]}}},
                                {"key": "b", "inputs": {"optional": {"size": ["INT", {"step": 5}]}}},
                            ]
                        },
                    ],
                }
            }
        }
    }
    schema = _object_info_schema(obj, "ResizeImageMaskNode", "resize_type.size")
    assert schema["min"] == 1
    assert schema["max"] == 100
    assert schema["step"] == 5


def test_object_info_schema_dynamic_combo_child_missing():
    """子输入不在任何 option 中 → None。"""
    assert _object_info_schema(DYNAMIC_COMBO_OBJECT_INFO, "ResizeImageMaskNode", "resize_type.nope") is None


def test_field_meta_dynamic_combo_child():
    """_field_meta 应从动态 COMBO 子输入提取 min/max/step。"""
    meta = _field_meta(DYNAMIC_COMBO_OBJECT_INFO, "ResizeImageMaskNode", "resize_type.multiplier")
    assert meta == {"min": 0.01, "max": 8.0, "step": 0.01}
