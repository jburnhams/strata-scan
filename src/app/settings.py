"""User settings: one JSON file, `~/.app/settings.json` (the folder can be moved with the APP_HOME environment variable).

  data_dir   where application data files live. Default: `data/` in this repository (gitignored) until configured. Must be an absolute path.
  greeting   default greeting word used by `greet.py` (default: 'Hello').

The environment variables APP_DATA and APP_GREETING override the file (handy for tests and one-off runs). The file handling, precedence and validation are
[strata_python.settings](https://github.com/jburnhams/strata-python); this module only declares the app's settings."""

import os
from collections.abc import Mapping
from typing import Any

from strata_python.settings import Setting, Settings, absolute_path, non_empty

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_DATA_DIR = os.path.join(REPO, "data")
DEFAULT_GREETING = "Hello"

SETTINGS = Settings(
    "app",
    [
        Setting("data_dir", default=DEFAULT_DATA_DIR, normalise=absolute_path, env="APP_DATA"),
        Setting("greeting", default=DEFAULT_GREETING, normalise=non_empty),
    ],
)
KNOWN = SETTINGS.keys


def home() -> str:
    return SETTINGS.home()


def load() -> dict[str, Any]:
    return SETTINGS.load()


def save(changes: Mapping[str, object]) -> dict[str, Any]:
    """Merge `changes` (known keys only) into the settings file; None resets a setting to its default. A bad value raises ValueError, an unknown key KeyError."""
    return SETTINGS.save(changes)


def data_dir() -> str:
    """The folder that holds application data (created when asked for)."""
    return SETTINGS.folder("data_dir")


def greeting() -> str:
    """The configured greeting word (e.g. 'Hello')."""
    return SETTINGS.get("greeting")


def all_settings() -> dict[str, str]:
    return {"data_dir": data_dir(), "greeting": greeting()}
