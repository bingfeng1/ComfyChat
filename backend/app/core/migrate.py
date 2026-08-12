from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


def migrate(engine: Engine) -> None:
    """启动时执行的幂等迁移。

    无 alembic;Base.metadata.create_all 不会给已有表加列,这里用 PRAGMA
    检测缺失列并 ALTER。已存在列时跳过,可重复执行。
    """
    _ensure_column(engine, "loras", "deleted_from_comfyui")
    _ensure_column(engine, "loras", "is_nsfw")
    _ensure_column(
        engine,
        "generations",
        "poll_miss_count",
        col_type="INTEGER",
        default="0",
    )


def _ensure_column(
    engine: Engine,
    table: str,
    column: str,
    *,
    col_type: str = "BOOLEAN",
    default: str = "0",
) -> None:
    with engine.begin() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        names = {row[1] for row in rows}
        if column in names:
            return
        conn.execute(
            text(
                f"ALTER TABLE {table} ADD COLUMN {column} "
                f"{col_type} NOT NULL DEFAULT {default}"
            )
        )