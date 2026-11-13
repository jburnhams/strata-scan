import os

import pytest

from app import settings


def test_defaults_and_env_overrides(tmp_path, monkeypatch):
    monkeypatch.delenv("APP_DATA", raising=False)
    monkeypatch.delenv("APP_HOME", raising=False)
    assert settings.home() == os.path.join(os.path.expanduser("~"), ".app")
    assert settings.greeting() == "Hello"
    assert settings.data_dir() == settings.DEFAULT_DATA_DIR

    custom_home = tmp_path / "custom_home"
    custom_data = tmp_path / "custom_data"
    monkeypatch.setenv("APP_HOME", str(custom_home))
    monkeypatch.setenv("APP_DATA", str(custom_data))
    monkeypatch.setenv("APP_GREETING", "  Hi  ")
    assert settings.home() == str(custom_home)
    assert settings.data_dir() == str(custom_data)
    assert custom_data.is_dir()
    assert settings.greeting() == "Hi"


def test_save_load_and_reset(tmp_path):
    assert settings.load() == {}
    elsewhere = str(tmp_path / "appdata")  # absolute on every platform
    saved = settings.save({"greeting": "Welcome", "data_dir": elsewhere})
    assert saved == {"greeting": "Welcome", "data_dir": elsewhere}
    assert settings.load() == saved
    assert settings.greeting() == "Welcome"

    after = settings.save({"greeting": None})
    assert "greeting" not in after
    assert settings.greeting() == "Hello"

    with pytest.raises(KeyError, match="unknown setting"):
        settings.save({"unknown_key": "val"})
    with pytest.raises(ValueError, match="data_dir: must be an absolute path"):
        settings.save({"data_dir": "relative"})


def test_corrupt_or_non_dict_settings_file():
    os.makedirs(settings.home(), exist_ok=True)
    p = os.path.join(settings.home(), "settings.json")
    with open(p, "w", encoding="utf8") as f:
        f.write("{not valid json")
    assert settings.load() == {}
    with open(p, "w", encoding="utf8") as f:
        f.write("[1, 2, 3]")
    assert settings.load() == {}
    assert settings.all_settings()["greeting"] == "Hello"
