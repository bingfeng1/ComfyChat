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


def _fake_client(monkeypatch, get_handler):
    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

        @property
        def content(self):
            return b"PNGDATA"

    class FakeHttpx:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json):
            get_handler("post", url, json)
            return FakeResponse({"prompt_id": "abc123"})

        def get(self, url, params=None):
            get_handler("get", url, params)
            if "view" in url:
                return FakeResponse({})
            return FakeResponse({"abc123": {"status": {"status_str": "success"}}})

    monkeypatch.setattr("app.integrations.comfyui.client.httpx.Client", FakeHttpx)


def test_submit_prompt(monkeypatch):
    calls = []

    def get_handler(kind, url, payload):
        calls.append((kind, url, payload))

    _fake_client(monkeypatch, get_handler)
    client = ComfyUIClient(Settings(comfyui_base_url="http://example.com:8188/"))

    prompt = {"3": {"class_type": "KSampler", "inputs": {"seed": 1}}}
    result = client.submit_prompt(prompt)

    assert result == "abc123"
    assert calls[0][0] == "post"
    assert calls[0][1].endswith("/prompt")
    assert calls[0][2] == {"prompt": prompt}


def test_submit_prompt_missing_prompt_id_raises(monkeypatch):
    import pytest

    from app.integrations.comfyui.client import ComfyUIError

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"error": "prompt validation failed"}

    class FakeHttpx:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json):
            return FakeResponse()

    monkeypatch.setattr("app.integrations.comfyui.client.httpx.Client", FakeHttpx)
    client = ComfyUIClient(Settings(comfyui_base_url="http://example.com:8188/"))

    with pytest.raises(ComfyUIError):
        client.submit_prompt({"3": {"class_type": "KSampler"}})


def test_get_history(monkeypatch):
    calls = []

    def get_handler(kind, url, payload):
        calls.append((kind, url, payload))

    _fake_client(monkeypatch, get_handler)
    client = ComfyUIClient(Settings(comfyui_base_url="http://example.com:8188/"))

    result = client.get_history("abc123")

    assert calls[0][1].endswith("/history/abc123")
    assert result["abc123"]["status"]["status_str"] == "success"


def test_get_image(monkeypatch):
    calls = []

    def get_handler(kind, url, payload):
        calls.append((kind, url, payload))

    _fake_client(monkeypatch, get_handler)
    client = ComfyUIClient(Settings(comfyui_base_url="http://example.com:8188/"))

    data = client.get_image("x.png", "", "output")

    assert data == b"PNGDATA"
    _, _, params = calls[0]
    assert params == {"filename": "x.png", "subfolder": "", "type": "output"}


def test_get_queue(monkeypatch):
    calls = []

    def get_handler(kind, url, payload):
        calls.append((kind, url, payload))

    _fake_client(monkeypatch, get_handler)
    client = ComfyUIClient(Settings(comfyui_base_url="http://example.com:8188/"))

    result = client.get_queue()

    assert calls[0][1].endswith("/queue")
    assert "abc123" in result


def test_interrupt_posts_interrupt_endpoint(monkeypatch):
    calls = []

    def get_handler(kind, url, payload):
        calls.append((kind, url, payload))

    _fake_client(monkeypatch, get_handler)
    client = ComfyUIClient(Settings(comfyui_base_url="http://example.com:8188/"))

    client.interrupt()

    assert calls == [("post", "http://example.com:8188/interrupt", None)]


def test_delete_queued_posts_queue_with_prompt_id(monkeypatch):
    calls = []

    def get_handler(kind, url, payload):
        calls.append((kind, url, payload))

    _fake_client(monkeypatch, get_handler)
    client = ComfyUIClient(Settings(comfyui_base_url="http://example.com:8188/"))

    client.delete_queued("p-42")

    assert calls == [("post", "http://example.com:8188/queue", {"delete": ["p-42"]})]
