import json

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


# ---- wait_for_history (WebSocket-driven completion wait) --------------------


class _FakeWS:
    """Minimal stand-in for websockets.sync.client connection."""

    def __init__(self, messages, *, raise_after=None):
        self._messages = list(messages)
        self._raise_after = raise_after
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.closed = True
        return False

    def recv(self, timeout=None):
        if not self._messages:
            if self._raise_after is not None:
                raise self._raise_after
            raise TimeoutError()
        return self._messages.pop(0)


def _patch_ws(monkeypatch, messages, *, raise_after=None):
    def fake_connect(url, open_timeout=None, **kwargs):
        assert url.startswith(("ws://", "wss://"))
        assert "/ws?clientId=" in url
        return _FakeWS(messages, raise_after=raise_after)

    monkeypatch.setattr("app.integrations.comfyui.client._ws_connect", fake_connect)


def test_wait_for_history_returns_entry_already_in_history(monkeypatch):
    """Race-tolerant fast path: prompt completed before we connected → return."""
    history_payload = {
        "p-1": {"status": {"status_str": "success"}, "outputs": {}},
    }

    class FakeHttpx:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, params=None):
            return type("R", (), {"raise_for_status": lambda self: None,
                                   "json": lambda self: history_payload})()

    monkeypatch.setattr("app.integrations.comfyui.client.httpx.Client", FakeHttpx)
    # WS must NOT be touched in the fast path.
    def must_not_connect(*a, **kw):
        raise AssertionError("WS connect should not be called when history already populated")

    monkeypatch.setattr("app.integrations.comfyui.client._ws_connect", must_not_connect)

    client = ComfyUIClient(Settings(comfyui_base_url="http://example.com:8188/"))
    entry = client.wait_for_history("p-1", timeout=10.0)

    assert entry["status"]["status_str"] == "success"


def test_wait_for_history_returns_on_executing_node_null(monkeypatch):
    """WS pushes executing{node:null, prompt_id} → fetch /history → return."""
    final_history = {"p-1": {"status": {"status_str": "success"}, "outputs": {}}}
    history_call_count = {"n": 0}

    class FakeHttpx:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, params=None):
            history_call_count["n"] += 1
            # First call: pre-check returns empty (no entry yet).
            # Second call: post-event returns final entry.
            if history_call_count["n"] == 1:
                return type("R", (), {"raise_for_status": lambda self: None,
                                       "json": lambda self: {}})()
            return type("R", (), {"raise_for_status": lambda self: None,
                                   "json": lambda self: final_history})()

    monkeypatch.setattr("app.integrations.comfyui.client.httpx.Client", FakeHttpx)
    messages = [
        # Unrelated event for another prompt: should be ignored.
        json.dumps({"type": "executing", "data": {"prompt_id": "other", "node": "1"}}),
        # Progress for ours: ignored (no completion).
        json.dumps({"type": "progress", "data": {"prompt_id": "p-1", "value": 1, "max": 9}}),
        # Completion: node=null → fetch history and return.
        json.dumps({"type": "executing", "data": {"prompt_id": "p-1", "node": None}}),
    ]
    _patch_ws(monkeypatch, messages)

    client = ComfyUIClient(Settings(comfyui_base_url="http://example.com:8188/"))
    entry = client.wait_for_history("p-1", timeout=10.0)

    assert entry["status"]["status_str"] == "success"
    assert history_call_count["n"] == 2


def test_wait_for_history_returns_on_execution_error_event(monkeypatch):
    """WS pushes execution_error{prompt_id} → return history entry (caller checks status)."""
    final_history = {
        "p-1": {
            "status": {"status_str": "error", "messages": [{"type": "execution_error"}]},
        },
    }

    class FakeHttpx:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, params=None):
            return type("R", (), {"raise_for_status": lambda self: None,
                                   "json": lambda self: final_history})()

    monkeypatch.setattr("app.integrations.comfyui.client.httpx.Client", FakeHttpx)
    messages = [
        json.dumps({"type": "execution_error", "data": {"prompt_id": "p-1", "exception_message": "boom"}}),
    ]
    _patch_ws(monkeypatch, messages)

    client = ComfyUIClient(Settings(comfyui_base_url="http://example.com:8188/"))
    entry = client.wait_for_history("p-1", timeout=10.0)

    assert entry["status"]["status_str"] == "error"


def test_wait_for_history_raises_on_timeout(monkeypatch):
    """No completion event arrives within timeout → ComfyUIError."""

    class FakeHttpx:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, params=None):
            return type("R", (), {"raise_for_status": lambda self: None,
                                   "json": lambda self: {}})()

    monkeypatch.setattr("app.integrations.comfyui.client.httpx.Client", FakeHttpx)
    # recv always times out (no messages).
    _patch_ws(monkeypatch, messages=[], raise_after=TimeoutError())

    client = ComfyUIClient(Settings(comfyui_base_url="http://example.com:8188/"))
    import pytest
    from app.integrations.comfyui.client import ComfyUIError
    with pytest.raises(ComfyUIError, match="timed out"):
        client.wait_for_history("p-1", timeout=0.5)


def test_wait_for_history_raises_on_ws_disconnect(monkeypatch):
    """WS disconnects mid-wait → ComfyUIError (caller can fall back to /history)."""

    class FakeHttpx:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, params=None):
            return type("R", (), {"raise_for_status": lambda self: None,
                                   "json": lambda self: {}})()

    monkeypatch.setattr("app.integrations.comfyui.client.httpx.Client", FakeHttpx)

    class FakeWSDisconnect(_FakeWS):
        def recv(self, timeout=None):
            raise ConnectionError("server went away")

    def fake_connect(url, open_timeout=None, **kwargs):
        return FakeWSDisconnect([])

    monkeypatch.setattr("app.integrations.comfyui.client._ws_connect", fake_connect)

    client = ComfyUIClient(Settings(comfyui_base_url="http://example.com:8188/"))
    import pytest
    from app.integrations.comfyui.client import ComfyUIError
    with pytest.raises(ComfyUIError, match="WS wait failed"):
        client.wait_for_history("p-1", timeout=10.0)


def test_wait_for_history_uses_https_for_wss(monkeypatch):
    """HTTPS base_url → wss:// WS URL (sanity for TLS deployments)."""
    captured = {}

    history_call_count = {"n": 0}
    final_history = {"p-1": {"status": {"status_str": "success"}}}

    class FakeHttpx:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, params=None):
            history_call_count["n"] += 1
            payload = {} if history_call_count["n"] == 1 else final_history
            return type("R", (), {"raise_for_status": lambda self: None,
                                   "json": lambda self: payload})()

    monkeypatch.setattr("app.integrations.comfyui.client.httpx.Client", FakeHttpx)

    def fake_connect(url, open_timeout=None, **kwargs):
        captured["url"] = url
        return _FakeWS([json.dumps({"type": "executing", "data": {"prompt_id": "p-1", "node": None}})])

    monkeypatch.setattr("app.integrations.comfyui.client._ws_connect", fake_connect)

    client = ComfyUIClient(Settings(comfyui_base_url="https://example.com:8188/"))
    client.wait_for_history("p-1", timeout=10.0)

    assert captured["url"].startswith("wss://")
