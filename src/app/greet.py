"""Hello-world domain logic and persistent message log (`<data_dir>/messages.json`, newest first)."""

import json
import os
from datetime import UTC, datetime
from typing import Any, cast

from strata_python import oslib

from app import settings

# A greeting record as stored in messages.json and returned by the API: id, name, greeting, message, created.
Record = dict[str, Any]


class GreetingError(ValueError):
    """Raised when a greeting request is invalid."""


def format_greeting(name: str = "World", greeting: str | None = None) -> Record:
    """Format a greeting for `name` using `greeting` (or the configured default)."""
    clean_name = (name or "").strip() or "World"
    clean_greeting = (greeting or "").strip() or settings.greeting()
    if len(clean_name) > 120:
        raise GreetingError("name is too long (at most 120 characters)")
    if len(clean_greeting) > 60:
        raise GreetingError("greeting is too long (at most 60 characters)")
    return {"name": clean_name, "greeting": clean_greeting, "message": f"{clean_greeting}, {clean_name}!"}


def _store_path() -> str:
    return os.path.join(settings.data_dir(), "messages.json")


def list_messages() -> list[Record]:
    """Return the recorded greetings from `<data_dir>/messages.json` (newest first)."""
    p = _store_path()
    if not os.path.exists(p):
        return []
    try:
        with open(p, encoding="utf8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    return cast("list[Record]", data) if isinstance(data, list) else []


def add_message(name: str = "World", greeting: str | None = None) -> Record:
    """Create and persist a greeting entry; returns the created record."""
    rec = format_greeting(name, greeting)
    lock_path = _store_path() + ".lock"
    os.makedirs(settings.data_dir(), exist_ok=True)
    with open(lock_path, "a+", encoding="utf8") as lf, oslib.file_lock(lf):
        items = list_messages()
        # Ids are never reused: the count drops when a greeting is removed, and so does the largest id when the newest one goes. The web app hides a removed row by its id
        # until the removal is committed (useUndoable), so a new greeting under a removed id would vanish with it. `messages.seq` remembers the last id handed out.
        entry = dict(
            id=max(_last_id(), max((m.get("id", 0) for m in items), default=0)) + 1,
            **rec,
            created=datetime.now(UTC).isoformat(),
        )
        items.insert(0, entry)
        _write(items)
        with open(_seq_path(), "w", encoding="utf8") as f:
            f.write(str(entry["id"]))
    return entry


def _seq_path() -> str:
    return os.path.join(settings.data_dir(), "messages.seq")


def _last_id() -> int:
    try:
        with open(_seq_path(), encoding="utf8") as f:
            return int(f.read().strip() or 0)
    except (OSError, ValueError):
        return 0


def _write(items: list[Record]) -> None:
    tmp = _store_path() + ".tmp"
    with open(tmp, "w", encoding="utf8") as f:
        json.dump(items, f, indent=1)
    os.replace(tmp, _store_path())


def page_messages(after: int | None = None, limit: int = 20) -> dict[str, Any]:
    """One page of the log, newest first: the greetings after the one with id `after` (the last one the client holds), and whether there are more.

    A cursor, not an offset: greetings removed between pages would make an offset skip the ones that moved up to fill the gap. Ids grow with time, so `after` still works when that greeting has itself been removed."""
    items = list_messages()
    rest = items if after is None else [m for m in items if m.get("id", 0) < after]
    return {"messages": rest[:limit], "has_more": len(rest) > limit}


def remove_message(message_id: int) -> Record | None:
    """Remove one greeting by id; returns it, or None when there is no such greeting."""
    lock_path = _store_path() + ".lock"
    os.makedirs(settings.data_dir(), exist_ok=True)
    with open(lock_path, "a+", encoding="utf8") as lf, oslib.file_lock(lf):
        items = list_messages()
        found = next((m for m in items if m.get("id") == message_id), None)
        if found is not None:
            _write([m for m in items if m is not found])
    return found


def clear_messages() -> dict[str, int]:
    """Remove all recorded greetings; returns `{cleared: count}`."""
    lock_path = _store_path() + ".lock"
    os.makedirs(settings.data_dir(), exist_ok=True)
    with open(lock_path, "a+", encoding="utf8") as lf, oslib.file_lock(lf):
        n = len(list_messages())
        p = _store_path()
        if os.path.exists(p):
            os.remove(p)
    return {"cleared": n}
