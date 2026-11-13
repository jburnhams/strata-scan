"""User settings: one JSON file, `~/.stratascan/settings.json` (the folder can be moved with the STRATASCAN_HOME environment variable).

  data_dir   where the books' pictures live (scans, pages, figures, exports). Default: `data/` in this repository (gitignored) until
             configured. Must be an absolute path. The records are in the shared database (omarchy-db, schema `stratascan`), not here.
  max_dpi    the highest resolution a PDF page is drawn at on import (default 600). A page is drawn at the resolution of the scan inside it
             (Internet Archive books are 360-500 dpi), so this only limits a very large one.
  workers    pages worked on at once (default 4: strata-models runs four CPU jobs beside each other, so a fifth would only queue there).

The environment variables STRATASCAN_DATA, STRATASCAN_MAX_DPI and STRATASCAN_WORKERS override the file. The file handling, precedence and
validation are [strata_python.settings](https://github.com/jburnhams/strata-python); this module only declares the app's settings."""

import os
from collections.abc import Callable, Mapping
from typing import Any

from strata_python.settings import Setting, Settings, absolute_path


def whole_number(lo: int, hi: int) -> Callable[[str], str]:
    """A normaliser for a whole number from lo to hi (settings are stored as text)."""

    def norm(v: str) -> str:
        try:
            n = int(str(v).strip())
        except ValueError as e:
            raise ValueError(f"must be a whole number from {lo} to {hi}") from e
        if not lo <= n <= hi:
            raise ValueError(f"must be from {lo} to {hi}")
        return str(n)

    return norm


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_DATA_DIR = os.path.join(REPO, "data")

SETTINGS = Settings(
    "stratascan",
    [
        Setting("data_dir", default=DEFAULT_DATA_DIR, normalise=absolute_path, env="STRATASCAN_DATA"),
        Setting("max_dpi", default="600", normalise=whole_number(72, 1200)),
        Setting("workers", default="4", normalise=whole_number(1, 32)),
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
    """The folder that holds the books' pictures (created when asked for)."""
    return SETTINGS.folder("data_dir")


def max_dpi() -> int:
    return int(SETTINGS.get("max_dpi"))


def workers() -> int:
    return int(SETTINGS.get("workers"))


def all_settings() -> dict[str, Any]:
    return {"data_dir": data_dir(), "max_dpi": max_dpi(), "workers": workers()}
