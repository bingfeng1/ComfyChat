import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.config import Settings
from app.integrations.comfyui.client import ComfyUIError
from app.models.generation import Generation
from app.repositories.generation import GenerationRepository, WorkflowGenerationConfigRepository
from app.services.generation import (
    GenerationService,
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

    def submit_prompt(self, prompt):
        self.submitted = prompt
        return "p-1"

    def get_history(self, prompt_id):
        return self.history

    def get_queue(self):
        return self.queue

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
    assert d == settings.storage_root / "outputs" / "2026-08" / gen.id


def test_poll_downloads_images_and_succeeds(session, tmp_path):
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

    svc.poll_until_done(gen.id, poll_interval=0.0)

    got = GenerationRepository(session).get(gen.id)
    assert got.status == "success"
    assert json.loads(got.outputs_json) == ["out.png"]
    assert (svc.outputs_dir(gen) / "out.png").read_bytes() == b"PNGDATA"


def test_poll_marks_failed_on_error(session, tmp_path):
    settings = _settings(tmp_path)
    _config(session, "wf1")
    comfy = FakeComfy()
    comfy.history = {"p-1": {"status": {"status_str": "error", "messages": [["execution_error", "boom"]]}}}
    svc = _service(session, settings, comfy)
    gen = svc.create("wf1", {"positive_prompt": "cat", "seed": 5, "seed_random": False})

    svc.poll_until_done(gen.id, poll_interval=0.0)

    got = GenerationRepository(session).get(gen.id)
    assert got.status == "failed"
    assert got.error


def test_poll_retries_until_success(session, tmp_path):
    settings = _settings(tmp_path)
    _config(session, "wf1")
    comfy = FakeComfy()

    def history(prompt_id):
        if not getattr(history, "called", False):
            history.called = True
            return {}
        return {"p-1": {"status": {"status_str": "success"}, "outputs": {}}}

    comfy.get_history = history
    svc = _service(session, settings, comfy)
    gen = svc.create("wf1", {"positive_prompt": "cat", "seed": 5, "seed_random": False})

    svc.poll_until_done(gen.id, poll_interval=0.0)

    assert GenerationRepository(session).get(gen.id).status == "success"


def test_reconcile_finalizes_lost_tasks(session, tmp_path):
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


def test_poll_marks_failed_after_two_running_misses(session, tmp_path):
    settings = _settings(tmp_path)
    comfy = FakeComfy()
    comfy.history = {}
    svc = _service(session, settings, comfy)
    repo = GenerationRepository(session)
    gen = repo.create("wf1", "z-image", {}, "running", "p-1")
    # updated_at 默认是 _utcnow(),需要回拨到宽限期外(>10s) 才能让旧的 miss-counter 行为继续生效。
    backdated = (datetime.now(timezone.utc) - timedelta(seconds=20)).isoformat()
    gen.updated_at = backdated
    session.commit()

    svc.poll_until_done(gen.id, poll_interval=0.0)

    got = repo.get(gen.id)
    assert got.status == "failed"
    assert "生成结果丢失" in (got.error or "")


def test_poll_does_not_count_misses_during_grace_period(session, tmp_path):
    """刚升级到 running 的几秒内,/history 可能还没有 entry,不应计 miss。

    updated_at 默认为 _utcnow() → 处于宽限期内,_poll_once 应直接 return False
    继续等待,而非触发 miss-counter 把任务标记为 failed。

    直接调 _poll_once(poll_until_done 在 poll_interval=0.0 下会跑完 900 次
    max_attempts 后报"轮询超时",不适合验证宽限期内的语义)。
    """
    settings = _settings(tmp_path)
    comfy = FakeComfy()
    comfy.history = {}  # 永远为空
    svc = _service(session, settings, comfy)
    repo = GenerationRepository(session)
    gen = repo.create("wf1", "z-image", {}, "running", "p-1")
    # updated_at 是 now() — 处于宽限期(10s)内

    terminal = svc._poll_once(repo.session, gen)

    got = repo.get(gen.id)
    assert terminal is False
    assert got.status == "running"
    assert got.poll_miss_count == 0


def test_poll_keeps_running_when_prompt_still_in_queue(session, tmp_path):
    """ComfyUI /history 只含已开始/已完成的 prompt;还在 /queue 里等待的 prompt
    (前一个任务没跑完)在 /history 里看不到。此时不能算 miss —— 否则排队中的
    生成会被误标为「生成结果丢失」,而 ComfyUI 其实还在正常生成。

    updated_at 回拨到宽限期外,确保是 /queue 检查(而非宽限期)在兜底。
    """
    settings = _settings(tmp_path)
    comfy = FakeComfy()
    comfy.history = {}
    comfy.queue = {"queue_running": [], "queue_pending": [["p-1", 1, {"x": 1}]]}
    svc = _service(session, settings, comfy)
    repo = GenerationRepository(session)
    gen = repo.create("wf1", "z-image", {}, "running", "p-1")
    backdated = (datetime.now(timezone.utc) - timedelta(seconds=20)).isoformat()
    gen.updated_at = backdated
    session.commit()

    terminal = svc._poll_once(repo.session, gen)

    got = repo.get(gen.id)
    assert terminal is False
    assert got.status == "running"
    assert got.poll_miss_count == 0


def test_poll_keeps_running_when_prompt_is_currently_running_in_queue(session, tmp_path):
    """prompt 正在 ComfyUI 执行中(/history 还没有 entry,但 /queue running 里有)。"""
    settings = _settings(tmp_path)
    comfy = FakeComfy()
    comfy.history = {}
    comfy.queue = {"queue_running": [["p-1", 1, {"x": 1}]], "queue_pending": []}
    svc = _service(session, settings, comfy)
    repo = GenerationRepository(session)
    gen = repo.create("wf1", "z-image", {}, "running", "p-1")
    backdated = (datetime.now(timezone.utc) - timedelta(seconds=20)).isoformat()
    gen.updated_at = backdated
    session.commit()

    terminal = svc._poll_once(repo.session, gen)

    got = repo.get(gen.id)
    assert terminal is False
    assert got.status == "running"
    assert got.poll_miss_count == 0


def test_poll_marks_failed_when_prompt_in_neither_queue_nor_history(session, tmp_path):
    """真正丢失:prompt 既不在 /history 也不在 /queue —— 连续 2 次才标失败。"""
    settings = _settings(tmp_path)
    comfy = FakeComfy()
    comfy.history = {}
    comfy.queue = {"queue_running": [], "queue_pending": []}
    svc = _service(session, settings, comfy)
    repo = GenerationRepository(session)
    gen = repo.create("wf1", "z-image", {}, "running", "p-1")
    backdated = (datetime.now(timezone.utc) - timedelta(seconds=20)).isoformat()
    gen.updated_at = backdated
    session.commit()

    svc.poll_until_done(gen.id, poll_interval=0.0)

    got = repo.get(gen.id)
    assert got.status == "failed"
    assert "生成结果丢失" in (got.error or "")
