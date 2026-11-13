"""Integration-suite fixtures: the CLI (in-process and as a real process) and the HTTP API over the real database and files."""

import contextlib
import io
import os
import subprocess
import sys
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


@dataclass
class Result:
    stdout: str
    stderr: str
    code: int

    @property
    def out(self):
        return self.stdout + self.stderr


@pytest.fixture
def cli():
    """`cli('books', '--json')` -> Result(stdout, stderr, code), in this process. Raises AssertionError with the output on a non-zero exit unless `check=False`."""
    from stratascan import cli as C

    def run(*args, check=True):
        out, err = io.StringIO(), io.StringIO()
        code = 0
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = C.main([str(a) for a in args]) or 0
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else (1 if e.code else 0)
                err.write(str(e.code) + "\n" if isinstance(e.code, str) else "")
        r = Result(out.getvalue(), err.getvalue(), code)
        if check and code:
            raise AssertionError(f"app {' '.join(map(str, args))} exited {code}:\n{r.out}")
        return r

    return run


@pytest.fixture
def cli_subprocess(isolated_env):
    """The same through a real `python -m stratascan` process: for the entry-point smoke test and anything that must not share this process's state."""

    def run(*args, check=True):
        env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"), PYTHONWARNINGS="ignore")
        p = subprocess.run(
            [sys.executable, "-m", "stratascan", *map(str, args)], capture_output=True, text=True, env=env, timeout=300
        )
        r = Result(p.stdout, p.stderr, p.returncode)
        if check and p.returncode:
            raise AssertionError(f"exited {p.returncode}:\n{r.out}")
        return r

    return run


@pytest.fixture
def client():
    """The HTTP API in this process (no lifespan, so no pipeline thread): for the calls that do not run a stage."""
    from stratascan.server.app import create_app

    return TestClient(create_app())


@pytest.fixture
def base_url(live_app, models_service):
    """The whole app on a loopback port (its pipeline thread running), reading pages through the strata-models stand-in."""
    from stratascan.server.app import create_app

    with live_app(create_app()) as url:
        yield url.rstrip("/")
