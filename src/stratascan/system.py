"""What the web app's System page reports (GET /api/system): versions, where the data lives, how full its disk is, and whether the
strata-models service is there to read pages (and which model its `ocr` role uses)."""

import contextlib
import os
import platform
import shutil
from typing import Any

import strata_models_client as sm  # pyright: ignore[reportMissingTypeStubs]

from stratascan import __version__, settings


def folder_bytes(path: str) -> int:
    """Total size of the files under `path` (files that vanish or cannot be read mid-walk are skipped)."""
    total = 0
    for root, _dirs, names in os.walk(path):
        for name in names:
            with contextlib.suppress(OSError):
                total += os.path.getsize(os.path.join(root, name))
    return total


def models() -> dict[str, Any]:
    """The strata-models service as this app sees it: its address, whether it answers, and the model behind `ocr`."""
    url = str(sm.url())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    up = bool(sm.available(timeout=1.0))  # pyright: ignore[reportUnknownMemberType]
    model: str | None = None
    if up:
        with contextlib.suppress(Exception):
            m = sm.role_model("ocr")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            model = str(m) if m else None  # pyright: ignore[reportUnknownArgumentType]
    return {"url": url, "available": up, "ocr_model": model}


def status() -> dict[str, Any]:
    """A snapshot for the System page. Sizes are bytes; the web app formats them."""
    d = settings.data_dir()
    du = shutil.disk_usage(d)
    return {
        "version": __version__,
        "python": platform.python_version(),
        "platform": f"{platform.system()} {platform.release()}".strip(),
        "data_dir": d,
        "data_bytes": folder_bytes(d),
        "disk": {"total": du.total, "used": du.used, "free": du.free},
        "models": models(),
    }
