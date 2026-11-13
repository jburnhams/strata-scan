import os

import pytest

from stratascan import settings


def test_defaults_and_env_overrides(tmp_path, monkeypatch):
    monkeypatch.delenv("STRATASCAN_DATA", raising=False)
    monkeypatch.delenv("STRATASCAN_HOME", raising=False)
    assert settings.home() == os.path.join(os.path.expanduser("~"), ".stratascan")
    assert (settings.max_dpi(), settings.workers()) == (600, 4)
    assert settings.data_dir() == settings.DEFAULT_DATA_DIR

    custom_home = tmp_path / "custom_home"
    custom_data = tmp_path / "custom_data"
    monkeypatch.setenv("STRATASCAN_HOME", str(custom_home))
    monkeypatch.setenv("STRATASCAN_DATA", str(custom_data))
    monkeypatch.setenv("STRATASCAN_WORKERS", " 2 ")
    monkeypatch.setenv("STRATASCAN_MAX_DPI", "lots")  # refused by its normaliser: the default applies
    assert settings.home() == str(custom_home)
    assert settings.data_dir() == str(custom_data)
    assert custom_data.is_dir()
    assert (settings.workers(), settings.max_dpi()) == (2, 600)
    assert settings.all_settings() == {"data_dir": str(custom_data), "max_dpi": 600, "workers": 2}


def test_save_load_and_reset(tmp_path):
    assert settings.load() == {}
    elsewhere = str(tmp_path / "appdata")  # absolute on every platform
    saved = settings.save({"workers": "8", "data_dir": elsewhere})
    assert saved == {"workers": "8", "data_dir": elsewhere}
    assert settings.load() == saved
    assert settings.workers() == 8

    after = settings.save({"workers": None})
    assert "workers" not in after
    assert settings.workers() == 4
    with pytest.raises(ValueError, match="from 72 to 1200"):
        settings.save({"max_dpi": "5000"})
    with pytest.raises(ValueError, match="whole number"):
        settings.save({"workers": "many"})

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
    assert settings.all_settings()["workers"] == 4
