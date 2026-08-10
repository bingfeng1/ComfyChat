from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Optional

from app.repositories.lora import LoraRepository

BASE_LOADERS: set[str] = {
    "CheckpointLoaderSimple", "UNETLoader", "DiffusionLoader",
    "CLIPLoader", "DualCLIPLoader", "TripleCLIPLoader", "VAELoader",
}

LOADER_MODEL_FIELDS: dict[str, str] = {
    "CheckpointLoaderSimple": "ckpt_name",
    "UNETLoader": "unet_name",
    "DiffusionLoader": "model_name",
    "CLIPLoader": "clip_name",
    "DualCLIPLoader": "clip_name1",
    "TripleCLIPLoader": "clip_name1",
    "VAELoader": "vae_name",
}

LORA_TYPES: set[str] = {"LoraLoader", "LoraLoaderModelOnly"}


def lora_model_pairs_from_body(body: dict) -> list[tuple[str, str]]:
    """从 UI-format body 提取 (lora_name, model_name) 对。"""
    links = body.get("links", [])
    link_map = {int(l[0]): l for l in links if l}
    nodes: dict[str, dict] = {str(n.get("id")): n for n in body.get("nodes", []) if n.get("id") is not None}
    pairs: list[tuple[str, str]] = []
    for node in nodes.values():
        if node.get("type") not in LORA_TYPES:
            continue
        lora = _node_widget(node, "lora_name")
        if not lora:
            continue
        model_link = None
        for inp in node.get("inputs", []):
            if inp.get("name") == "model" and inp.get("link") is not None:
                model_link = inp["link"]
                break
        if model_link is None:
            continue
        link = link_map.get(int(model_link))
        if link is None:
            continue
        src = nodes.get(str(link[1]))
        if src is None or src.get("type") not in BASE_LOADERS:
            continue
        model = _node_widget(src)
        if model:
            pairs.append((lora, model))
    return pairs


def _node_widget(node: dict, name: str | None = None) -> str | None:
    """读节点第一个 widget 值;name 提供时按 inputs 中带 widget 的输入对齐位置。"""
    widgets = node.get("widgets_values") or []
    if not widgets:
        return None
    if name is None:
        val = widgets[0]
    else:
        idx = None
        widx = 0
        for inp in node.get("inputs", []):
            if "widget" not in inp:
                continue
            if inp.get("name") == name:
                idx = widx
                break
            widx += 1
        if idx is None or idx >= len(widgets):
            return None
        val = widgets[idx]
    return val if isinstance(val, str) and val else None


def lora_model_pairs_from_template(api_template: dict) -> list[tuple[str, str]]:
    """从 API-format 模板提取 (lora_name, model_name) 对。"""
    pairs: list[tuple[str, str]] = []
    for node in api_template.values():
        ct = node.get("class_type")
        if ct not in LORA_TYPES:
            continue
        inputs = node.get("inputs") or {}
        lora = inputs.get("lora_name")
        model_ref = inputs.get("model")
        if not isinstance(lora, str) or not isinstance(model_ref, list) or len(model_ref) != 2:
            continue
        src = api_template.get(str(model_ref[0]))
        if not src:
            continue
        field = LOADER_MODEL_FIELDS.get(src.get("class_type", ""))
        if not field:
            continue
        val = (src.get("inputs") or {}).get(field)
        if isinstance(val, str) and val:
            pairs.append((lora, val))
    return pairs


def main_model_from_template(api_template: dict) -> str | None:
    pairs = lora_model_pairs_from_template(api_template)
    return pairs[0][1] if pairs else None


def tensor_family(keys: list[str]) -> str | None:
    """从张量键名判定架构族。命中顺序即优先级。"""
    s = " ".join(keys).lower()
    if "lora_te_text_model_encoder" in s:
        return "SD1.5"
    if "diffusion_model.transformer_blocks" in s or "transformer_blocks.0.attn" in s:
        return "Qwen-Image"
    if "diffusion_model.blocks." in s and "adaln_proj" in s:
        return "MiniMax-H3"
    if "diffusion_model.layers." in s and "adaLN_modulation" in s:
        return "Z-Image"
    if "context_refiner" in s or "noise_refiner" in s:
        return "Z-Image"
    if "lora_unet_down_blocks" in s and "downsamplers" in s:
        return "SDXL"
    if "lora_te_" in s or ("lora_unet_" in s and "attn1" in s):
        return "SD1.5"
    return None


def detect_base_family(header: dict) -> str | None:
    """从 safetensors header 判定架构族:metadata 优先,张量回退。"""
    meta = header.get("__metadata__") or {}
    for key in ("base_model", "compatible_base"):
        val = meta.get(key)
        if val:
            low = val.lower()
            for family, markers in _FAMILY_MARKERS.items():
                if any(m in low for m in markers):
                    return family
    keys = [k for k in header.keys() if k != "__metadata__"]
    return tensor_family(keys)


_FAMILY_MARKERS: dict[str, list[str]] = {
    "SD1.5": ["sd1.5", "sd15", "stable diffusion 1.5", "runwayml/stable-diffusion-v1"],
    "SDXL": ["sdxl", "sd_xl", "stabilityai/stable-diffusion-xl"],
    "Qwen-Image": ["qwen-image", "qwen_image", "tongyi-mai/qwen-image"],
    "MiniMax-H3": ["minimax-h3", "minimax_h3", "minimax"],
    "Z-Image": ["z-image", "z_image", "zimage", "tongyi-mai/z-image"],
}


class LoraService:
    def __init__(self, repo: LoraRepository, workflow_repo, comfyui, settings) -> None:
        self.repo = repo
        self.workflow_repo = workflow_repo
        self.comfyui = comfyui
        self.settings = settings

    def list_installed(self) -> Optional[list[str]]:
        """从 ComfyUI object_info 拉全部已安装 LoRA 文件名(去重)。

        ComfyUI 不可达(如 get_object_info 抛错)时返回 None,调用方应据此
        判定同步失败并保留本地缓存,而非当作空列表清空 loras 表。
        """
        names: set[str] = set()
        try:
            info = self.comfyui.get_object_info(["LoraLoader", "LoraLoaderModelOnly"])
        except Exception:
            return None
        for node_type in ("LoraLoader", "LoraLoaderModelOnly"):
            node = (info or {}).get(node_type) or {}
            entry = (((node.get("input") or {}).get("required") or {}).get("lora_name") or [])
            if entry and isinstance(entry[0], list):
                names.update(str(x) for x in entry[0])
        return sorted(names)

    def read_metadata(self, path: Path) -> Optional[dict]:
        """读 safetensors 头 JSON(8 字节长度前缀)。失败返回 None。"""
        try:
            with open(path, "rb") as f:
                size_bytes = f.read(8)
                if len(size_bytes) != 8:
                    return None
                (length,) = struct.unpack("<Q", size_bytes)
                if length > 8 * 1024 * 1024:
                    return None
                header = json.loads(f.read(length))
            return header if isinstance(header, dict) else None
        except Exception:
            return None

    def _metadata_for(self, name: str) -> dict:
        """按文件名在 loras 目录里找文件并读 header;找不到返回 {}。"""
        lora_dir = self.settings.comfyui_loras_dir
        if not lora_dir:
            return {}
        root = Path(lora_dir).resolve()
        candidate = (root / name).resolve()
        if candidate.parent != root:
            return {}
        header = self.read_metadata(candidate)
        return header if header is not None else {}

    def sync(self) -> dict:
        installed = self.list_installed()
        if installed is None:
            return {"total": 0, "error": "ComfyUI 不可达"}
        known: set[str] = set()
        collected: dict[str, set[str]] = {}
        if self.workflow_repo is not None:
            for wf in self.workflow_repo.list():
                try:
                    body = json.loads(wf.body)
                except Exception:
                    continue
                for lora, model in lora_model_pairs_from_body(body):
                    collected.setdefault(lora, set()).add(model)
        for name in installed:
            known.add(name)
            header = self._metadata_for(name)
            meta = header.get("__metadata__") or {}
            base_family = detect_base_family(header)
            source_url = meta.get("url")
            trigger = meta.get("repoId")
            self.repo.upsert_lora(
                name,
                base_family=base_family,
                source_url=source_url,
                trigger_words=trigger,
            )
            pairs = collected.get(name)
            if pairs:
                self.repo.replace_links(name, sorted(pairs), "workflow")
        self.repo.clear_stale(known)
        return {"total": len(installed)}
