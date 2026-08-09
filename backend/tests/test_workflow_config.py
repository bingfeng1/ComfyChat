from pathlib import Path

from app.core.config import Settings


def test_settings_comfyui_userdata_dir_defaults_to_none():
    settings = Settings()
    assert settings.comfyui_userdata_dir is None


def test_settings_comfyui_userdata_dir_override():
    settings = Settings(comfyui_userdata_dir="./comfy-user")
    assert settings.comfyui_userdata_dir == Path("./comfy-user")
