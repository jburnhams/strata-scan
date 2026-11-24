"""User settings: one JSON file, `~/.stratascan/settings.json` (the folder can be moved with the STRATASCAN_HOME environment variable).

  data_dir   where the books' pictures live (scans, pages, figures, exports). Default: `data/` in this repository (gitignored) until
             configured. Must be an absolute path. The records are in the shared database (strata_python.db, schema `stratascan`), not here.
  max_dpi    the highest resolution a PDF page is drawn at on import (default 600). A page is drawn at the resolution of the scan inside it
             (Internet Archive books are 360-500 dpi), so this only limits a very large one.
  workers    pages worked on at once (default 4: strata-models runs four CPU jobs beside each other, so a fifth would only queue there).
  correct    the vision-language model that corrects each text page's OCR against the page (default `claude-haiku-5-5-api`), or `off`. On
             strata-models' ocr-hard eval (the 10 worst pages of two 19th-century books) the cleaned page read by Tesseract then this
             correction got 0.27 % of characters wrong (plain Tesseract then Haiku 0.88 %, then the local qwen3.5-9b-vl 3.7 %, Tesseract alone
             23 %), for about $0.0007 a page; the lines and their boxes stay Tesseract's. Ten pages, so the order of the first two is
             not certain.
  layout     the vision-language model that reads each text page's layout (default `claude-opus-5-5-api`), or `off`: page-layout's winner,
             blocks found 96.5 % against Tesseract's 64 %, about 3 cents a page. The Markdown and the rebuilt pages follow it.

The environment variables STRATASCAN_DATA, STRATASCAN_MAX_DPI, STRATASCAN_WORKERS, STRATASCAN_CORRECT and STRATASCAN_LAYOUT override the file. The file handling, precedence and
validation are [strata_python.settings](https://github.com/jburnhams/strata-python); this module only declares the app's settings."""

import os
from collections.abc import Mapping
from typing import Any

from strata_python.settings import Setting, Settings, absolute_path, whole_between


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
        Setting("max_dpi", default="600", normalise=whole_between(72, 1200)),
        Setting("workers", default="4", normalise=whole_between(1, 32)),
        Setting("correct", default="claude-haiku-5-5-api", normalise=model_or_off),
        Setting("layout", default="claude-opus-5-5-api", normalise=model_or_off),
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


def layout_model() -> str | None:
    """The model that reads a page's layout, or None when that is off."""
    v = str(SETTINGS.get("layout"))
    return None if v == "off" else v


def all_settings() -> dict[str, Any]:
    return {"data_dir": data_dir(), "max_dpi": max_dpi(), "workers": workers()}
