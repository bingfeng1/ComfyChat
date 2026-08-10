import json
from pathlib import Path

import pytest

from app.core.config import Settings
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

    def submit_prompt(self, prompt):
        self.submitted = prompt
        return "p-1"

    def get_history(self, prompt_id):
        return self.history

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
