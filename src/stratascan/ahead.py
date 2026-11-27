"""strata-models calls a stage can name before it needs them, queued in one bulk call per role and model (`clients.models.submit_many`), so
the Claude calls of a book's pages go through strata-models' batch API at half the price once there are 20 or more of them. A stage plans
its calls, sends them, then does each page as before: a call it planned is answered from the bulk job (waiting for it), any other is made
then. Nothing changes for the page's code, which still calls its run function with the same role, params and model; `wrap` puts the bulk
answers in front of it.

Bulk calls come back within a day (most within an hour), so a book of 20 or more pages waits for its corrections or layouts as a whole.
The CPU-heavy work stays one page at a time (font-match, `stage_rebuild`): only the calls to the cloud models are queued ahead."""

import json
import logging
import threading
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from strata_python.clients import models as sm

log = logging.getLogger("stratascan")
APP = "strata-scan"
Call = tuple[str, dict[str, Any], "str | None"]  # role, params, model
RunFn = Callable[[str, dict[str, Any], "str | None"], Mapping[str, Any]]


def key(role: str, params: Mapping[str, Any], model: str | None) -> str:
    return json.dumps([role, params, model], sort_keys=True, default=str)


class Ahead:
    """Bulk jobs of planned calls, by what they ask (role, params, model); each answers one call."""

    def __init__(self, app: str = APP) -> None:
        self.app = app
        self._ids: dict[str, list[int]] = {}
        self._done: dict[str, Mapping[str, Any]] = {}  # answers already waited for: a page set twice asks the same once
        self._lock = threading.Lock()

    def send(self, calls: Iterable[Call], batch: bool | None = None) -> int:
        """Queue `calls` in bulk, one call of strata-models per (role, model); returns how many were queued. strata-models down or refusing
        leaves them unplanned: each is then made when the page asks for it, as before. `batch`: strata-models' batch API however few (True),
        never (False), or from 20 calls (None, its default)."""
        groups: dict[tuple[str, str | None], list[dict[str, Any]]] = {}
        for role, params, model in calls:
            groups.setdefault((role, model), []).append(params)
        n = 0
        for (role, model), items in groups.items():
            try:
                ids = sm.submit_many(role, items, self.app, model=model, batch=batch)
            except (sm.Unavailable, sm.JobFailed) as e:
                log.warning("%d %s calls not queued ahead: %s", len(items), role, e)
                continue
            with self._lock:
                for p, i in zip(items, ids, strict=True):
                    self._ids.setdefault(key(role, p, model), []).append(i)
            n += len(ids)
        return n

    def take(self, role: str, params: Mapping[str, Any], model: str | None) -> int | None:
        """The id of a queued job asking this, once (None when none was planned)."""
        with self._lock:
            ids = self._ids.get(key(role, params, model))
            return ids.pop(0) if ids else None

    def wrap(self, run: RunFn, error: Callable[[str, Exception], Exception]) -> RunFn:
        """`run`, answering a planned call from its bulk job; a failed one raises `error(role, e)`, as `run` would."""

        def ahead(role: str, params: dict[str, Any], model: str | None) -> Mapping[str, Any]:
            job = self.take(role, params, model)
            k = key(role, params, model)
            if job is None:
                with self._lock:
                    if k in self._done:
                        return self._done[k]
                return run(role, params, model)
            try:
                got = sm.wait(job)
            except (sm.Unavailable, sm.JobFailed) as e:
                raise error(role, e) from e
            if (
                role == "vision-language"
            ):  # a cloud model's answer, the same asked again; a page-build's drawing is made anew
                with self._lock:
                    self._done[k] = got
            return got

        return ahead
