"""Shared pytest configuration. Hermetic tests (own home and data folder, no network, no stray override variables) and the `http_server` / `live_app` fixtures come from the strata-python plugin, configured in pyproject.toml. Tests under tests/integration get the `integration` marker automatically."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "utils"))


def pytest_collection_modifyitems(items):
    for item in items:
        if os.sep + "integration" + os.sep in str(item.fspath):
            item.add_marker(pytest.mark.integration)


@pytest.fixture
def fake_urlopen(monkeypatch):
    """Script `urllib.request.urlopen`: `fake_urlopen.reply({...}, http_error(429))`, then assert on `fake_urlopen.calls` (url, method, headers, parsed JSON body). Unexpected calls fail."""
    import urllib.request

    from fakes import FakeUrlopen

    f = FakeUrlopen()
    monkeypatch.setattr(urllib.request, "urlopen", f)
    return f


@pytest.fixture
def fake_popen(monkeypatch):
    """Replace `subprocess.Popen` everywhere: nothing starts; `fake_popen.instances` lists the commands (`.cmd`) and kwargs (`.kw`) it was asked to run."""
    import subprocess

    from fakes import FakePopen

    FakePopen.instances = []
    monkeypatch.setattr(subprocess, "Popen", FakePopen)
    return FakePopen


@pytest.fixture
def fake_run(monkeypatch):
    """Replace `subprocess.run` / `check_output`: record the command lines in `.calls`; set `.returns['cmd'] = b'...'` (substring of the command line) for output, `.code = 1` to fail."""
    import subprocess

    from fakes import FakeRun

    f = FakeRun()
    monkeypatch.setattr(subprocess, "run", f)
    monkeypatch.setattr(subprocess, "check_output", f.check_output)
    return f
