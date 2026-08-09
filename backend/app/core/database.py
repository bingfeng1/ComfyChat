from __future__ import annotations

import contextlib
from typing import Iterator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker[Session]] = None
_current_settings: Optional[Settings] = None


def configure(settings: Settings) -> None:
    global _engine, _SessionLocal, _current_settings
    _current_settings = settings
    _engine = create_engine(
        settings.database_url,
        future=True,
        connect_args={"check_same_thread": False, "timeout": 30}
        if settings.database_url.startswith("sqlite")
        else {},
    )
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)


def reset_for_tests() -> None:
    global _engine, _SessionLocal, _current_settings
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
    _current_settings = None


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("Database engine not configured. Call configure(settings) first.")
    return _engine


@contextlib.contextmanager
def get_session() -> Iterator[Session]:
    if _SessionLocal is None:
        raise RuntimeError("Database engine not configured. Call configure(settings) first.")
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()


def check_database() -> bool:
    try:
        with get_session() as session:
            session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False