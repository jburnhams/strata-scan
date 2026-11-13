"""What the web app's System page reports (GET /api/system): versions, where the data lives, and how full its disk is."""

import contextlib
import os
import platform
import shutil
from typing import Any

from app import __version__, greet, settings


def folder_bytes(path: str) -> int:
    """Total size of the files under `path` (files that vanish or cannot be read mid-walk are skipped)."""
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            with contextlib.suppress(OSError):
                total += os.path.getsize(os.path.join(root, name))
    return total


def status() -> dict[str, Any]:
    """A snapshot for the System page. Sizes are bytes; the web app formats them."""
    d = settings.data_dir()
    du = shutil.disk_usage(d)
    return {
        "version": __version__,
        "python": platform.python_version(),
        "platform": f"{platform.system()} {platform.release()}".strip(),
        "data_dir": d,
        "messages": len(greet.list_messages()),
        "data_bytes": folder_bytes(d),
        "disk": {"total": du.total, "used": du.used, "free": du.free},
    }
