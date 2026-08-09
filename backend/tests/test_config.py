from pathlib import Path

from app.core.config import Settings


def test_settings_defaults():
    settings = Settings(_env_file=None)
    assert settings.comfyui_base_url is None
    assert settings.comfyui_api_key is None
    assert settings.database_url.startswith("sqlite:///")
    assert isinstance(settings.storage_root, Path)


def test_settings_overrides():
    settings = Settings(
        comfyui_base_url="http://127.0.0.1:8188/",
        comfyui_api_key="abc",
        database_url="sqlite:///./custom.db",
        storage_root="./custom-storage",
    )
    assert settings.comfyui_base_url == "http://127.0.0.1:8188/"
    assert settings.comfyui_api_key == "abc"
    assert settings.database_url == "sqlite:///./custom.db"
    assert settings.storage_root == Path("./custom-storage")
