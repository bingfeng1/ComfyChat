from fastapi.testclient import TestClient

from app.core import database
from app.core.config import Settings
from app.integrations.comfyui.client import ComfyUIClient
from app.main import create_app


def _settings(tmp_path) -> Settings:
    db_path = tmp_path / "health.db"
    return Settings(
        database_url=f"sqlite:///{db_path}",
        storage_root=tmp_path / "storage",
    )


def test_root_endpoint(tmp_path):
    settings = _settings(tmp_path)
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"name": "ComfyChat API", "version": "0.1.0"}


def test_health_endpoint_reports_database_and_comfyui(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    database.reset_for_tests()

    def fake_ping(self):
        return "ok"

    monkeypatch.setattr(ComfyUIClient, "ping", fake_ping)
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["comfyui"] == "ok"


def test_health_endpoint_reports_unknown_comfyui(tmp_path, monkeypatch):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/health.db",
        storage_root=tmp_path,
    )
    database.reset_for_tests()
    monkeypatch.setattr(ComfyUIClient, "ping", lambda self: "unknown")
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["comfyui"] == "unknown"