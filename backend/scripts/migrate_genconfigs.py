"""一次性迁移脚本: 用修复后的 workflow_to_api_template + discover_fields 重新生成所有
WorkflowGenerationConfig,让旧 api_template 里的 length:73 / width:1344 / height:768
字面量被替换成 link 引用,并补齐缺失字段(如 noise_seed)。

运行方式: 先停止后端 (uvicorn) 以避免 SQLite 文件锁,再:
    cd <repo>
    backend\.venv\Scripts\python backend\scripts\migrate_genconfigs.py

完成后重新启动后端。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# 让脚本能 import app.*(项目根目录加到 sys.path)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core import database  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.models.generation import WorkflowGenerationConfig  # noqa: E402
from app.models.workflow import Workflow  # noqa: E402
from app.services.generation import discover_fields, workflow_to_api_template  # noqa: E402


def _post_process_fields(body: dict, fields: list[dict]) -> list[dict]:
    """镜像 app/api/routes/workflows.py:discover_generation_config 的字段整理:
    - LoRA 节点关联的 strength_model 字段在 is_array 下并入 lora_name,这里删掉
      (前端 modal 仍会按 LoRA 节点单独 toggle is_array;真要保 is_array 需要更复杂
      的合并,本脚本保守起见先把 strength_model 字段丢掉,避免重复暴露)
    - 重复 key 加 _1 / _2 后缀
    """
    lora_node_ids = {
        str(n.get("id"))
        for n in body.get("nodes", [])
        if n.get("type") in ("LoraLoaderModelOnly", "LoraLoader")
    }
    fields = [
        f
        for f in fields
        if not (f.get("input_name") == "strength_model" and str(f.get("node_id")) in lora_node_ids)
    ]
    seen: set[str] = set()
    for f in fields:
        base = f["key"]
        key = base
        n = 1
        while key in seen:
            key = f"{base}_{n}"
            n += 1
        seen.add(key)
        f["key"] = key
    return fields


def main() -> int:
    settings = Settings()
    database.configure(settings)
    SessionLocal = database._SessionLocal
    if SessionLocal is None:
        print("ERROR: SessionLocal not initialized", file=sys.stderr)
        return 1
    session = SessionLocal()
    try:
        cfgs = session.scalars(select(WorkflowGenerationConfig)).all()
        if not cfgs:
            print("No WorkflowGenerationConfig rows found.")
            return 0
        print(f"Found {len(cfgs)} config(s). Re-discovering with current code...")
        for cfg in cfgs:
            wf = session.get(Workflow, cfg.workflow_id)
            if wf is None:
                print(f"  - {cfg.workflow_id}: workflow missing, skipping")
                continue
            try:
                body = json.loads(wf.body)
            except (TypeError, ValueError) as exc:
                print(f"  - {cfg.workflow_id}: bad body JSON ({exc}), skipping")
                continue
            new_template = workflow_to_api_template(body, object_info=None)
            new_fields = discover_fields(body, object_info=None)
            new_fields = _post_process_fields(body, new_fields)
            old_keys = sorted({f.get("key") for f in json.loads(cfg.fields_json or "[]")})
            new_keys = sorted(f["key"] for f in new_fields)
            old_template = json.loads(cfg.api_template)
            node131_old = (old_template.get("131") or {}).get("inputs", {})
            node131_new = new_template.get("131", {}).get("inputs", {})
            length_was = node131_old.get("length", "<absent>")
            length_now = node131_new.get("length", "<absent>")
            cfg.api_template = json.dumps(new_template, ensure_ascii=False)
            cfg.fields_json = json.dumps(new_fields, ensure_ascii=False)
            cfg.updated_at = (
                __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
            )
            added = sorted(set(new_keys) - set(old_keys))
            print(
                f"  - {cfg.workflow_id} ({wf.name[:40]}): "
                f"length {length_was} -> {length_now}; "
                f"fields {len(old_keys)} -> {len(new_keys)} "
                f"(+{','.join(added) if added else 'none'})"
            )
        session.commit()
        print("Done.")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())