import os
import tempfile
from pathlib import Path

from sqlalchemy import text

from app.core import database
from app.core.config import Settings


def test_check_database_returns_true_for_writable_sqlite(tmp_path: Path):
    db_path = tmp_path / "test.db"
    settings = Settings(database_url=f"sqlite:///{db_path}")
    database.configure(settings)
    try:
        assert database.check_database() is True
        with database.get_session() as session:
            result = session.execute(text("SELECT 1")).scalar_one()
            assert result == 1
    finally:
        database.reset_for_tests()
        if db_path.exists():
            db_path.unlink()


def test_check_database_returns_false_when_path_unwritable(tmp_path: Path):
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    os.chmod(blocked, 0o500)
    settings = Settings(database_url=f"sqlite:///{blocked}/x.db")
    database.configure(settings)
    try:
        assert database.check_database() is False
    finally:
        database.reset_for_tests()
        os.chmod(blocked, 0o700)