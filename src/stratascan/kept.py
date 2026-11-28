"""Cloud models' answers kept with the book, so a page set again asks nothing it has asked before (Jonathan, 2026-11-28: "try to reuse all
model work"). A page set again after a fix asks the same line fix and the same second reading of the same picture; they cost the same each
time and answer much the same. Each answer is a file under the book's `answers/`, named by what was asked (`ahead.key`: role, params,
model), so a call asked differently (another picture, other lines, another model) is asked anew.

Only the cloud models' calls (`vision-language`) are kept: the type fits (font-match) run here on the CPU and change with strata-models' own
fixes, which a kept fit would hide."""

import hashlib
import json
import os
from collections.abc import Iterable, Mapping
from typing import Any, cast

from stratascan import ahead, files

KEPT = frozenset({"vision-language"})


def path(book_id: int, role: str, params: Mapping[str, Any], model: str | None) -> str:
    name = hashlib.sha256(ahead.key(role, params, model).encode()).hexdigest()[:32]
    return files.path(book_id, "answers", f"{name}.json")


def get(book_id: int, role: str, params: Mapping[str, Any], model: str | None) -> Mapping[str, Any] | None:
    """The answer kept for this call, or None."""
    if role not in KEPT:
        return None
    try:
        with open(path(book_id, role, params, model), encoding="utf-8") as f:
            return cast("dict[str, Any]", json.load(f))
    except (OSError, ValueError):
        return None


def put(book_id: int, role: str, params: Mapping[str, Any], model: str | None, answer: Mapping[str, Any]) -> None:
    if role not in KEPT:
        return
    p = path(book_id, role, params, model)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    part = f"{p}.{os.getpid()}.part"
    with open(part, "w", encoding="utf-8") as f:
        json.dump(dict(answer), f)
    os.replace(part, p)


def unasked(book_id: int, calls: Iterable[ahead.Call]) -> list[ahead.Call]:
    """The calls with no answer kept: the only ones to queue."""
    return [c for c in calls if get(book_id, *c) is None]


def wrap(book_id: int, run: ahead.RunFn) -> ahead.RunFn:
    """`run`, answering a call from what is kept and keeping each new answer."""

    def keeping(role: str, params: dict[str, Any], model: str | None) -> Mapping[str, Any]:
        got = get(book_id, role, params, model)
        if got is not None:
            return got
        answer = run(role, params, model)
        put(book_id, role, params, model, answer)
        return answer

    return keeping
