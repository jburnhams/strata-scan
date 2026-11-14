"""User settings: one JSON file, `~/.stratascan/settings.json` (the folder can be moved with the STRATASCAN_HOME environment variable).

  data_dir   where the books' pictures live (scans, pages, figures, exports). Default: `data/` in this repository (gitignored) until
             configured. Must be an absolute path. The records are in the shared database (omarchy-db, schema `stratascan`), not here.
  max_dpi    the highest resolution a PDF page is drawn at on import (default 600). A page is drawn at the resolution of the scan inside it
             (Internet Archive books are 360-500 dpi), so this only limits a very large one.
  workers    pages worked on at once (default 4: strata-models runs four CPU jobs beside each other, so a fifth would only queue there).
  correct    the vision-language model that corrects each text page's OCR against the page (default `qwen3.5-9b-vl`), or `off`. On
             strata-models' ocr-pages eval (10 hard pages of two 19th-century books) Tesseract alone got 5.1 % of characters wrong and
             Tesseract then this correction 0.3 %, at about 18 s of GPU time a page; the lines and their boxes stay Tesseract's.

The environment variables STRATASCAN_DATA, STRATASCAN_MAX_DPI, STRATASCAN_WORKERS and STRATASCAN_CORRECT override the file. The file handling, precedence and
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


def model_or_off(v: str) -> str:
    """A strata-models model key, or `off`."""
    t = str(v).strip()
    if not t:
        raise ValueError("must be a model key (such as qwen3.5-9b-vl) or off")
    return "off" if t.lower() == "off" else t


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_DATA_DIR = os.path.join(REPO, "data")

SETTINGS = Settings(
    "stratascan",
    [
        Setting("data_dir", default=DEFAULT_DATA_DIR, normalise=absolute_path, env="STRATASCAN_DATA"),
        Setting("max_dpi", default="600", normalise=whole_number(72, 1200)),
        Setting("workers", default="4", normalise=whole_number(1, 32)),
        Setting("correct", default="qwen3.5-9b-vl", normalise=model_or_off),
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


def correct_model() -> str | None:
    """The model that corrects OCR text, or None when correction is off."""
    v = str(SETTINGS.get("correct"))
    return None if v == "off" else v


def all_settings() -> dict[str, Any]:
    return {"data_dir": data_dir(), "max_dpi": max_dpi(), "workers": workers()}
