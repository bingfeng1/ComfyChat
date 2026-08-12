from __future__ import annotations

import contextlib
import json
import random
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, Optional

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.comfyui.client import ComfyUIClient, ComfyUIError
from app.models.generation import Generation
from app.repositories.generation import GenerationRepository, WorkflowGenerationConfigRepository
from app.repositories.workflow import WorkflowRepository


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# _poll_once 在 status == "running" 但 /history 为空时计入 miss。
# 刚从 queued 升级到 running 的几秒内,ComfyUI pipeline 还没把 entry 写进 /history,
# 这种空响应属于正常启动延迟,不应视为 miss。在宽限期内直接 return False 继续等待。
RUNNING_HISTORY_GRACE_SECONDS = 10.0


_CONTROL_TOKENS = {"fixed", "randomize", "increment", "decrement"}

# 模型加载器字段黑名单: 这些是 ComfyUI 底层加载配置,生成时不应让用户填写。
# 按 (节点类型, 输入名) 精确匹配,避免误伤内容字段。
# 排除: 模型文件选择(clip_name/unet_name/vae_name/lora_name)与加载配置(type/device/weight_dtype)。
# 保留: strength_model 等"强度/数值"可调参数。
_LOADER_INPUTS: dict[str, set[str]] = {
    "CLIPLoader": {"clip_name", "type", "device"},
    "DualCLIPLoader": {"clip_name1", "clip_name2", "type", "device"},
    "TripleCLIPLoader": {"clip_name1", "clip_name2", "clip_name3", "type", "device"},
    "UNETLoader": {"unet_name", "weight_dtype"},
    "DiffusionLoader": {"model_name", "weight_dtype"},
    "VAELoader": {"vae_name"},
    "CheckpointLoaderSimple": {"ckpt_name"},
    "LoraLoader": {"model", "clip"},
    "LoraLoaderModelOnly": {"model"},
    "ModelSamplingAuraFlow": {"shift"},
    "ModelSamplingContinuousEDM": {"shift"},
    "ModelSamplingSD3": {"shift"},
    "ModelSamplingDiscrete": {"sampling"},
    "ModelSamplingStableCascade": {"shift"},
    "ModelSamplingAdvanced": {"sampling", "zsnr"},
}


def _is_loader_field(node_type: str, input_name: str) -> bool:
    return input_name in _LOADER_INPUTS.get(node_type, set())


def _object_info_schema(object_info: dict | None, node_type: str, input_name: str) -> dict | None:
    """从 ComfyUI /object_info 提取单个 input 的 schema 元数据(无则 None)。

    返回 dict 含可选的 min/max/step/options/control_after_generate。
    COMBO 类型的 options 来自 entry[0](列表),会并入返回的 dict。
    """
    if not object_info:
        return None
    node = object_info.get(node_type)
    if not node:
        return None
    inp = node.get("input") or {}
    for bucket in ("required", "optional"):
        entry = (inp.get(bucket) or {}).get(input_name)
        if entry is None:
            continue
        meta: dict = {}
        if isinstance(entry[0], list):
            meta["options"] = entry[0]
        if len(entry) > 1 and isinstance(entry[1], dict):
            meta.update(entry[1])
        return meta
    return None


def _align_widgets(
    widget_names: list[str],
    widget_values: list,
    object_info: dict | None,
    node_type: str,
) -> list[tuple[str, object]]:
    """把 widget 输入名与 widgets_values 对齐,处理 control_after_generate 占位。

    ComfyUI 里带 control_after_generate 的输入(如 seed)在 widgets_values 中
    会多占一位('fixed'/'randomize')。有 schema 时用 control_after_generate 标志,
    无 schema 时用值启发式跳过 control token。
    """
    pairs: list[tuple[str, object]] = []
    vi = 0
    for name in widget_names:
        if vi >= len(widget_values):
            pairs.append((name, None))
            continue
        value = widget_values[vi]
        schema = _object_info_schema(object_info, node_type, name)
        has_control = bool(schema and schema.get("control_after_generate"))
        vi += 1
        if has_control and vi < len(widget_values):
            token = widget_values[vi]
            if isinstance(token, str) and token.lower() in _CONTROL_TOKENS:
                vi += 1
        elif (
            name.lower() == "seed"
            and vi < len(widget_values)
            and isinstance(widget_values[vi], str)
            and widget_values[vi].lower() in _CONTROL_TOKENS
        ):
            vi += 1
        pairs.append((name, value))
    return pairs


def workflow_to_api_template(body_json: dict, object_info: dict | None = None) -> dict:
    """把 ComfyUI UI 格式工作流 body 转成 API 格式 dict(/prompt 用)。

    - widget 输入: 从 widgets_values 取值
    - 连线输入: 解析 links 数组为 [from_node_id, from_slot] 引用
    links 结构: [id, from_node, from_slot, to_node, to_slot, type]
    """
    links = body_json.get("links", [])
    link_map: dict[tuple[str, int], tuple[str, int]] = {}
    for link in links:
        from_node, from_slot, to_node, to_slot = link[1], link[2], link[3], link[4]
        link_map[(str(to_node), to_slot)] = (str(from_node), from_slot)

    result: dict = {}
    for node in body_json.get("nodes", []):
        node_id = str(node["id"])
        node_type = node.get("type", "")
        inputs: dict = {}
        # 连线输入
        for idx, inp in enumerate(node.get("inputs", [])):
            if inp.get("link") is None:
                continue
            src = link_map.get((node_id, idx))
            if src:
                inputs[inp["name"]] = [src[0], src[1]]
        # widget 输入
        widget_names = [i["name"] for i in node.get("inputs", []) if i.get("widget")]
        widget_values = node.get("widgets_values") or []
        for name, value in _align_widgets(widget_names, widget_values, object_info, node_type):
            inputs[name] = value
        result[node_id] = {"class_type": node_type, "inputs": inputs}
    return result


def infer_field_type(
    widget_name: str, value, object_info: dict | None = None, node_type: str = ""
) -> str:
    """推断字段类型: schema 优先; 否则 seed→'seed'; 数值→'number'; COMBO→'select'。

    返回 'text' | 'seed' | 'number' | 'select'。
    """
    schema = _object_info_schema(object_info, node_type, widget_name)
    if schema:
        if schema.get("control_after_generate"):
            return "seed"
        if "options" in schema:
            return "select"
        if widget_name.lower() == "seed":
            return "seed"
        # INT/FLOAT 类型名在 entry[0],不在 schema dict;用值启发式兜底
    if widget_name.lower() == "seed":
        return "seed"
    if isinstance(value, bool):
        return "text"
    if isinstance(value, (int, float)):
        return "number"
    return "text"


def _field_meta(object_info: dict | None, node_type: str, input_name: str) -> dict:
    """从 object_info 提取 min/max/step/options 等元数据,无则空 dict。

    注意: 不返回 default — default 由 discover_fields 从工作流 widgets_values
    决定,object_info 的 default 是节点类型默认,会覆盖工作流实际值。
    """
    schema = _object_info_schema(object_info, node_type, input_name)
    if not schema:
        return {}
    meta: dict = {}
    for key in ("min", "max", "step"):
        if key in schema and isinstance(schema[key], (int, float)):
            meta[key] = schema[key]
    if "options" in schema:
        options = schema["options"]
        if isinstance(options, list) and all(isinstance(o, str) for o in options):
            meta["options"] = options
    return meta


def _conditioning_labels(body_json: dict) -> dict[str, str]:
    """解析连线,返回 {CLIPTextEncode 节点 id: "正面提示词"|"负面提示词"}。

    判定方式: 找 KSampler 的 positive/negative 输入各连到哪个源节点。
    用 input 的 link id 反查 links 数组的 [id, from_node, ...]。
    """
    labels: dict[str, str] = {}
    links = body_json.get("links", [])
    links_by_id = {l[0]: l for l in links}
    for node in body_json.get("nodes", []):
        if node.get("type") != "KSampler":
            continue
        for inp in node.get("inputs", []):
            role = inp.get("name")
            if role not in ("positive", "negative"):
                continue
            link = links_by_id.get(inp.get("link"))
            if link is None:
                continue
            from_node = str(link[1])
            labels[from_node] = "正面提示词" if role == "positive" else "负面提示词"
    return labels


def discover_fields(body_json: dict, object_info: dict | None = None) -> list[dict]:
    """从 UI 格式 body 返回候选字段(形状与 GenerationField 一致)。

    只为值类型是标量(str/int/float/bool/None)的 widget 输入生成候选。
    连线输入(带 'link')跳过。带 object_info 时补 min/max/step/options 与类型。
    """
    cond_labels = _conditioning_labels(body_json)
    candidates: list[dict] = []
    for node in body_json.get("nodes", []):
        node_id = str(node["id"])
        node_type = node.get("type", "")
        widget_names = [i["name"] for i in node.get("inputs", []) if i.get("widget")]
        widget_values = node.get("widgets_values") or []
        for name, value in _align_widgets(widget_names, widget_values, object_info, node_type):
            if _is_loader_field(node_type, name):
                continue
            if not isinstance(value, (str, int, float, bool)) and value is not None:
                continue
            label = f"[{node_type}] {name}"
            if node_type == "CLIPTextEncode" and node_id in cond_labels:
                label = cond_labels[node_id]
            else:
                for i in node.get("inputs", []):
                    if i.get("name") == name and i.get("localized_name"):
                        label = i["localized_name"]
                        break
            candidate: dict = {
                "key": name,
                "label": label,
                "type": infer_field_type(name, value, object_info, node_type),
                "node_id": node_id,
                "input_name": name,
                "default": value,
                "required": False,
            }
            candidate.update(_field_meta(object_info, node_type, name))
            candidates.append(candidate)
    return candidates


def apply_parameters(
    api_template: dict,
    fields: list[dict],
    parameters: dict,
) -> tuple[dict, dict]:
    """把用户参数填入 API 模板，返回 (filled_template, effective_parameters)。

    effective_parameters 含所有字段的实际值（随机种子为生成后的值）。
    """
    filled = json.loads(json.dumps(api_template))
    effective: dict = {}
    for field in fields:
        key = field["key"]
        value = parameters.get(key)
        if field["type"] == "seed":
            is_random = bool(parameters.get(f"{key}_random"))
            if is_random:
                value = random.randint(0, 2**32 - 1)
                effective[f"{key}_random"] = True
            elif not isinstance(value, int):
                raise ValueError(f"字段 {field['label']} 必须是整数")
        elif field["type"] == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"字段 {field['label']} 必须是数字")
        elif field["required"] and (value is None or value == ""):
            raise ValueError(f"字段 {field['label']} 为必填")
        effective[key] = value
        node_id = field["node_id"]
        filled[node_id]["inputs"][field["input_name"]] = value
    return filled, effective


def collect_images(history_entry: dict) -> list[dict]:
    images = []
    for node_output in (history_entry.get("outputs") or {}).values():
        images.extend(node_output.get("images") or [])
    return images


class GenerationService:
    def __init__(
        self,
        gen_repo: GenerationRepository,
        config_repo: WorkflowGenerationConfigRepository,
        comfyui: ComfyUIClient,
        settings: Settings,
        db: Optional[Callable[[], object]] = None,
    ) -> None:
        self.gen_repo = gen_repo
        self.config_repo = config_repo
        self.comfyui = comfyui
        self.settings = settings
        self.db = db

    def create(self, workflow_id: str, parameters: dict) -> Generation:
        cfg = self.config_repo.get_by_workflow(workflow_id)
        if cfg is None:
            raise ValueError("workflow not configured")
        filled, effective = apply_parameters(
            json.loads(cfg.api_template),
            json.loads(cfg.fields_json),
            parameters,
        )
        prompt_id = self.comfyui.submit_prompt(filled)
        wf = WorkflowRepository(self.gen_repo.session).get(workflow_id)
        wf_name = wf.name if wf else workflow_id
        return self.gen_repo.create(
            workflow_id=workflow_id,
            workflow_name=wf_name,
            parameters=effective,
            status="queued",
            prompt_id=prompt_id,
        )

    def cancel(self, generation_id: str) -> Generation:
        """按 generation 当前状态选对应 ComfyUI 端点,把 row 标 failed=用户中止。"""
        with self._session_scope() as session:
            repo = GenerationRepository(session)
            gen = repo.get(generation_id)
            if gen is None:
                raise ValueError("generation not found")
            if gen.status in ("success", "failed"):
                raise ValueError(f"already terminal: {gen.status}")
            try:
                if gen.status == "queued":
                    self.comfyui.delete_queued(gen.prompt_id)
                else:  # running
                    self.comfyui.interrupt()
            except ComfyUIError:
                pass
            repo.mark_failed(generation_id, "用户中止")
            session.refresh(gen)
            return gen

    def outputs_dir(self, gen: Generation) -> Path:
        if gen.id is None:
            gen.id = uuid.uuid4().hex
        ym = gen.created_at[:7]
        return self.settings.storage_root / "outputs" / ym / gen.id

    @contextlib.contextmanager
    def _session_scope(self) -> Iterator[Session]:
        """每次轮询用新 session（有 db 时）；测试/请求场景退化为请求 session。"""
        if self.db is not None:
            with self.db.get_session() as session:
                yield session
        else:
            yield self.gen_repo.session

    def _poll_once(self, session: Session, gen: Generation) -> bool:
        """查询一次 ComfyUI,返回 True 表示已到达终态。

        用户中止 + ComfyUI 清掉 history 的边缘场景:`gen.status == "running"`
        但 `get_history` 返回空;连续 2 次空就 mark_failed 退出,避免轮询死循环。
        """
        repo = GenerationRepository(session)
        if gen.status == "running":
            # 宽限期:刚升级到 running 的几秒内,/history 还没 entry 是正常的。
            # 此时空响应不计入 miss,但 /history 的 entry 仍正常检测 —— 不阻塞快速成功的
            # 生成任务。只在尚未计过 miss 时检查宽限期——一旦开始计数,update_poll_miss_count
            # 会刷新 updated_at,这时不再重新进入宽限期,以免死循环。
            in_grace = False
            if (gen.poll_miss_count or 0) == 0:
                try:
                    running_since = datetime.fromisoformat(gen.updated_at)
                except (TypeError, ValueError):
                    running_since = None
                if running_since is not None:
                    elapsed = (datetime.now(timezone.utc) - running_since).total_seconds()
                    if elapsed < RUNNING_HISTORY_GRACE_SECONDS:
                        in_grace = True
            history = self.comfyui.get_history(gen.prompt_id)
            if not history:
                if in_grace:
                    return False
                miss = (gen.poll_miss_count or 0) + 1
                if miss >= 2:
                    repo.mark_failed(gen.id, "生成结果丢失")
                    return True
                repo.update_poll_miss_count(gen.id, miss)
                return False
            if (gen.poll_miss_count or 0) > 0:
                repo.update_poll_miss_count(gen.id, 0)
            entry = history.get(gen.prompt_id)
        else:
            try:
                history = self.comfyui.get_history(gen.prompt_id)
            except Exception:
                return False
            entry = history.get(gen.prompt_id)
        if entry is None:
            if gen.status == "queued":
                repo.update_status(gen.id, "running")
            return False
        status_str = (entry.get("status") or {}).get("status_str")
        if status_str == "error":
            messages = (entry.get("status") or {}).get("messages") or []
            repo.mark_failed(gen.id, json.dumps(messages, ensure_ascii=False))
            return True
        images = collect_images(entry)
        saved = []
        if images:
            out_dir = self.outputs_dir(gen)
            out_dir.mkdir(parents=True, exist_ok=True)
            for img in images:
                filename = Path(img["filename"]).name
                if not filename:
                    continue
                try:
                    data = self.comfyui.get_image(
                        img["filename"], img.get("subfolder", ""), img.get("type", "output")
                    )
                except Exception as exc:
                    repo.mark_failed(gen.id, f"下载图片失败: {filename}: {exc}")
                    return True
                (out_dir / filename).write_bytes(data)
                saved.append(filename)
        repo.update_success(gen.id, saved)
        return True

    def poll_until_done(
        self,
        generation_id: str,
        poll_interval: float = 2.0,
        max_attempts: int = 900,
    ) -> None:
        """后台轮询：每次用新 session，直到终态或超时。"""
        for _ in range(max_attempts):
            with self._session_scope() as session:
                repo = GenerationRepository(session)
                gen = repo.get(generation_id)
                if gen is None:
                    return
                if self._poll_once(session, gen):
                    return
            if poll_interval > 0:
                time.sleep(poll_interval)
        with self._session_scope() as session:
            GenerationRepository(session).mark_failed(generation_id, "轮询超时")

    def reconcile(self) -> None:
        """对仍在 queued/running 的记录做一次兜底查询，用请求 session。"""
        for gen in self.gen_repo.list_pending():
            self._poll_once(self.gen_repo.session, gen)
