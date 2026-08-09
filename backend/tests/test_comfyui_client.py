from app.core.config import Settings
from app.integrations.comfyui.client import ComfyUIClient


def test_ping_returns_unknown_when_not_configured():
    client = ComfyUIClient(Settings(comfyui_base_url=None))
    assert client.ping() == "unknown"


def test_ping_returns_ok_on_2xx(monkeypatch):
    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url: str):
            assert url.endswith("/system_stats")
            return FakeResponse()

    monkeypatch.setattr("app.integrations.comfyui.client.httpx.Client", FakeClient)
    client = ComfyUIClient(Settings(comfyui_base_url="http://example.com:8188/"))
    assert client.ping() == "ok"


def test_ping_returns_error_on_failure(monkeypatch):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url: str):
            raise RuntimeError("boom")

    monkeypatch.setattr("app.integrations.comfyui.client.httpx.Client", FakeClient)
    client = ComfyUIClient(Settings(comfyui_base_url="http://example.com:8188/"))
    assert client.ping() == "error"
