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
from app.integrations.comfyui.client import ComfyUIClient
from app.models.generation import Generation
from app.repositories.generation import GenerationRepository, WorkflowGenerationConfigRepository
from app.repositories.workflow import WorkflowRepository


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def workflow_to_api_template(body_json: dict) -> dict:
    """把 ComfyUI UI 格式工作流 body 转成 API 格式 dict(/prompt 用)。"""
    result: dict = {}
    for node in body_json.get("nodes", []):
        node_id = str(node["id"])
        inputs: dict = {}
        widget_names = [i["name"] for i in node.get("inputs", []) if i.get("widget")]
        widget_values = node.get("widgets_values") or []
        for idx, name in enumerate(widget_names):
            value = widget_values[idx] if idx < len(widget_values) else None
            inputs[name] = value
        result[node_id] = {"class_type": node["type"], "inputs": inputs}
    return result


def infer_field_type(widget_name: str, value) -> str:
    """启发式推断字段类型: seed→'seed'; 数值→'number'; 否则 'text'。"""
    if widget_name.lower() == "seed":
        return "seed"
    if isinstance(value, bool):
        return "text"
    if isinstance(value, (int, float)):
        return "number"
    return "text"


def discover_fields(body_json: dict) -> list[dict]:
    """从 UI 格式 body 返回候选字段(形状与 GenerationField 一致)。

    只为值类型是标量(str/int/float/bool/None)的 widget 输入生成候选。
    连线输入(带 'link')跳过。
    """
    candidates: list[dict] = []
    for node in body_json.get("nodes", []):
        node_id = str(node["id"])
        node_type = node.get("type", "")
        widget_names = [i["name"] for i in node.get("inputs", []) if i.get("widget")]
        widget_values = node.get("widgets_values") or []
        for idx, name in enumerate(widget_names):
            value = widget_values[idx] if idx < len(widget_values) else None
            if not isinstance(value, (str, int, float, bool)) and value is not None:
                continue
            label = f"[{node_type}] {name}"
            for i in node.get("inputs", []):
                if i.get("name") == name and i.get("localized_name"):
                    label = i["localized_name"]
                    break
            candidates.append({
                "key": name,
                "label": label,
                "type": infer_field_type(name, value),
                "node_id": node_id,
                "input_name": name,
                "default": value,
                "required": False,
            })
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
        """查询一次 ComfyUI，返回 True 表示已到达终态。"""
        repo = GenerationRepository(session)
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
