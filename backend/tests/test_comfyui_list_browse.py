from pathlib import Path

import pytest

from app.core.config import Settings
from app.integrations.comfyui.client import ComfyUIClient, ComfyUIError


def test_list_browse_calls_v2_path_param(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url):
            captured["url"] = url
            return FakeResponse()

    class FakeHttpx:
        Client = FakeClient

    monkeypatch.setattr("app.integrations.comfyui.client.httpx", FakeHttpx)
    client = ComfyUIClient(Settings(comfyui_base_url="http://x:8188/"))
    client.list_browse()
    assert captured["url"] == "http://x:8188/v2/userdata?path=workflows"


def test_read_userdata_json_returns_none_when_unconfigured(tmp_path: Path):
    settings = Settings(comfyui_userdata_dir=None)
    client = ComfyUIClient(settings)
    assert client.read_userdata_json("a.json") is None


def test_read_userdata_json_reads_file(tmp_path: Path):
    userdata = tmp_path / "user"
    (userdata / "workflows").mkdir(parents=True)
    (userdata / "workflows" / "a.json").write_text('{"x":1}', encoding="utf-8")
    settings = Settings(comfyui_userdata_dir=userdata)
    client = ComfyUIClient(settings)
    assert client.read_userdata_json("a.json") == '{"x":1}'


def test_read_userdata_json_rejects_path_traversal(tmp_path: Path):
    userdata = tmp_path / "user"
    (userdata / "workflows").mkdir(parents=True)
    settings = Settings(comfyui_userdata_dir=userdata)
    client = ComfyUIClient(settings)
    assert client.read_userdata_json("../secret.json") is None
    assert client.read_userdata_json("sub/../x.json") is None
