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
