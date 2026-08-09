import pytest
from pydantic import ValidationError

from app.schemas.generation import (
    GenerationConfigIn,
    GenerationConfigOut,
    GenerationField,
    GenerationOut,
)


def test_generation_field_rejects_unknown_type():
    with pytest.raises(ValidationError):
        GenerationField(
            key="x", label="X", type="checkbox",
            node_id="1", input_name="text", default="", required=True,
        )


def test_generation_config_in_ok():
    cfg = GenerationConfigIn(
        api_template={"3": {"class_type": "KSampler", "inputs": {"seed": 0}}},
        fields=[
            GenerationField(key="seed", label="种子", type="seed", node_id="3", input_name="seed", default=0, required=True),
        ],
    )
    assert cfg.api_template["3"]["inputs"]["seed"] == 0


def test_generation_out_from_model(session):
    from app.repositories.generation import GenerationRepository
    gen = GenerationRepository(session).create(
        "wf1", "z-image", {"positive_prompt": "cat", "seed": 1, "seed_random": False},
        "success", "p1",
    )
    gen.outputs_json = '["a.png"]'
    session.commit()
    out = GenerationOut.from_model(gen)
    assert out.parameters == {"positive_prompt": "cat", "seed": 1, "seed_random": False}
    assert out.outputs == ["a.png"]
    assert out.status == "success"


def test_generation_config_out_from_model(session):
    from app.models.generation import WorkflowGenerationConfig
    cfg = WorkflowGenerationConfig(workflow_id="wf1", api_template="{}", fields_json='[]')
    session.add(cfg)
    session.commit()
    out = GenerationConfigOut.from_model(cfg)
    assert out.api_template == {}
    assert out.fields == []
