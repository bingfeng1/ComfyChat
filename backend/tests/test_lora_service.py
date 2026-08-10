from app.services.lora import (
    BASE_LOADERS,
    detect_base_family,
    lora_model_pairs_from_body,
    lora_model_pairs_from_template,
    main_model_from_template,
    tensor_family,
)


def _body_with_lora():
    # UI-format: node 2 UNETLoader, node 6 LoraLoaderModelOnly 经 link 3 相连
    return {
        "nodes": [
            {
                "id": 2, "type": "UNETLoader",
                "inputs": [{"name": "unet_name", "widget": {}, "type": "COMBO"}],
                "widgets_values": ["z_image_turbo_int8_convrot.safetensors", "default"],
            },
            {
                "id": 6, "type": "LoraLoaderModelOnly",
                "inputs": [
                    {"name": "model", "type": "MODEL", "link": 3},
                    {"name": "lora_name", "widget": {}, "type": "COMBO"},
                    {"name": "strength_model", "widget": {}, "type": "FLOAT"},
                ],
                "widgets_values": ["mumu_20.safetensors", 0],
            },
        ],
        "links": [[3, 2, 0, 6, 0, "MODEL"]],
    }


def test_body_extracts_lora_model_pair():
    pairs = lora_model_pairs_from_body(_body_with_lora())
    assert pairs == [("mumu_20.safetensors", "z_image_turbo_int8_convrot.safetensors")]


def test_body_without_lora_returns_empty():
    body = {"nodes": [{"id": 1, "type": "KSampler", "inputs": [], "widgets_values": []}], "links": []}
    assert lora_model_pairs_from_body(body) == []


def test_template_extracts_lora_model_pair():
    template = {
        "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "z_image_turbo_int8_convrot.safetensors"}},
        "6": {"class_type": "LoraLoaderModelOnly", "inputs": {
            "model": ["2", 0], "lora_name": "mumu_20.safetensors", "strength_model": 0}},
    }
    assert lora_model_pairs_from_template(template) == [("mumu_20.safetensors", "z_image_turbo_int8_convrot.safetensors")]
    assert main_model_from_template(template) == "z_image_turbo_int8_convrot.safetensors"


def test_main_model_none_without_lora():
    template = {"3": {"class_type": "KSampler", "inputs": {"seed": 0}}}
    assert main_model_from_template(template) is None


def test_base_loaders_contains_common_loaders():
    assert {"CheckpointLoaderSimple", "UNETLoader", "CLIPLoader"} <= BASE_LOADERS


def test_tensor_family_detects_families():
    assert tensor_family(["lora_te_text_model_encoder_layers_0_mlp_fc1.lora_down.weight"]) == "SD1.5"
    assert tensor_family(["lora_unet_down_blocks_0_downsamplers_0_conv.lora_down.weight"]) == "SDXL"
    assert tensor_family(["diffusion_model.transformer_blocks.0.attn.add_k_proj.lora_A.weight"]) == "Qwen-Image"
    assert tensor_family(["diffusion_model.blocks.0.adaln_proj.linear.lora_A.weight"]) == "MiniMax-H3"
    assert tensor_family(["context_refiner.0.attention.to_k.lora_A.default.weight"]) == "Z-Image"
    assert tensor_family(["unknown_key.weight"]) is None


def test_detect_base_family_uses_metadata_first():
    header = {"__metadata__": {"base_model": "MiniMax-H3"}, "x": {"dtype": "F32"}}
    assert detect_base_family(header) == "MiniMax-H3"
    header2 = {"__metadata__": {"compatible_base": "MiniMax-H3 non-pruned bf16"}, "x": {"dtype": "F32"}}
    assert detect_base_family(header2) == "MiniMax-H3"


def test_detect_base_family_falls_back_to_tensors():
    header = {"a": {"dtype": "F32"}, "b": {"dtype": "F32"}}
    assert detect_base_family(header) is None


import json
import struct

import pytest

from app.models.lora import Lora
from app.repositories.lora import LoraRepository
from app.services.lora import LoraService


class FakeComfy:
    def __init__(self, loras):
        self._loras = loras

    def get_object_info(self, node_types=None):
        return {
            "LoraLoader": {"input": {"required": {"lora_name": [self._loras]}}},
            "LoraLoaderModelOnly": {"input": {"required": {"lora_name": [self._loras]}}},
        }


def _mk_service(session, loras, settings_overrides=None):
    from app.core.config import Settings
    settings = Settings(**(settings_overrides or {}))
    return LoraService(
        LoraRepository(session),
        workflow_repo=None,
        comfyui=FakeComfy(loras),
        settings=settings,
    )


def _write_safetensors(path, header: dict):
    payload = json.dumps(header).encode("utf-8")
    with open(path, "wb") as f:
        f.write(struct.pack("<Q", len(payload)))
        f.write(payload)


def test_list_installed_from_object_info(session):
    service = _mk_service(session, ["a.safetensors", "b.safetensors", "a.safetensors"])
    assert sorted(service.list_installed()) == ["a.safetensors", "b.safetensors"]


def test_sync_populates_and_clears_stale(session):
    from app.repositories.workflow import WorkflowRepository
    service = _mk_service(session, ["mumu_20.safetensors", "gone.safetensors"])
    # 预先留一条陈旧 lora
    service.repo.upsert_lora("stale.safetensors")
    # 插入一个带 LoRA 的工作流 body
    repo = WorkflowRepository(session)
    body = {
        "nodes": [
            {"id": 2, "type": "UNETLoader", "inputs": [{"name": "unet_name", "widget": {}, "type": "COMBO"}],
             "widgets_values": ["z_image_turbo_int8_convrot.safetensors", "default"]},
            {"id": 6, "type": "LoraLoaderModelOnly", "inputs": [
                {"name": "model", "type": "MODEL", "link": 3},
                {"name": "lora_name", "widget": {}, "type": "COMBO"},
                {"name": "strength_model", "widget": {}, "type": "FLOAT"}],
             "widgets_values": ["mumu_20.safetensors", 0]},
        ],
        "links": [[3, 2, 0, 6, 0, "MODEL"]],
    }
    repo.upsert("browse", "z.json", "z", "z.json", json.dumps(body), 10)
    service.workflow_repo = repo

    result = service.sync()
    assert result["total"] == 2
    items = dict(service.repo.list_all())
    assert items["mumu_20.safetensors"] == ["z_image_turbo_int8_convrot.safetensors"]
    assert "stale.safetensors" not in items


def test_sync_reads_metadata_when_loras_dir_configured(session, tmp_path):
    lora_dir = tmp_path / "loras"
    lora_dir.mkdir()
    _write_safetensors(
        lora_dir / "coser-z_20.safetensors",
        {"__metadata__": {"repoId": "jcplus/coser-z", "url": "https://www.modelscope.cn/aigc/home"}},
    )
    _write_safetensors(
        lora_dir / "minimax_h3_turbo_4step_comfyui.safetensors",
        {"__metadata__": {"base_model": "MiniMax-H3", "compatible_base": "MiniMax-H3 non-pruned bf16"}},
    )
    service = _mk_service(
        session,
        ["coser-z_20.safetensors", "minimax_h3_turbo_4step_comfyui.safetensors"],
        {"comfyui_loras_dir": lora_dir},
    )
    service.sync()
    items = dict(service.repo.list_all())
    assert items["minimax_h3_turbo_4step_comfyui.safetensors"] == []
    lora = session.get(Lora, "minimax_h3_turbo_4step_comfyui.safetensors")
    assert lora.base_family == "MiniMax-H3"
    lora2 = session.get(Lora, "coser-z_20.safetensors")
    assert lora2.source_url == "https://www.modelscope.cn/aigc/home"
    assert lora2.trigger_words == "jcplus/coser-z"


def test_sync_read_metadata_missing_file_ok(session, tmp_path):
    lora_dir = tmp_path / "loras"
    lora_dir.mkdir()
    service = _mk_service(session, ["a.safetensors"], {"comfyui_loras_dir": lora_dir})
    service.sync()
    lora = session.get(Lora, "a.safetensors")
    assert lora.base_family is None
