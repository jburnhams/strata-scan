"""Shared pytest configuration. Hermetic tests (own home and data folder, no network, no stray override variables) and the `http_server` / `live_app` fixtures come from the strata-python plugin, configured in pyproject.toml. Tests under tests/integration get the `integration` marker automatically."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "utils"))


@pytest.fixture(autouse=True)
def _database(db_env):
    """Every test gets a fresh migrated database (omarchy-db's `db_env`: SQLite by default, a throwaway Postgres with `--pg`), and the app's
    cached engine is dropped so it connects to that one."""
    from stratascan import store

    store.reset()
    yield
    store.reset()


@pytest.fixture
def runner():
    """A pipeline.Runner whose OCR is the real `tesseract` command (tests/utils/books.py), in place of the strata-models service, and with no
    correction pass (a vision-language model; test_pipeline.py tests it with a stand-in)."""
    from books import tesseract_ocr

    from stratascan import pipeline

    return pipeline.Runner(ocr=tesseract_ocr, correct=None)


@pytest.fixture
def make_book(tmp_path):
    """`make_book()` -> the id of a book whose source is a 4-scan PDF made in the test (books.book_pdf), not yet imported."""
    from books import book_pdf

    from stratascan import store
    from stratascan.db.models import Book

    def make(title="Punch and Judy", scans=None):
        src = book_pdf(str(tmp_path / "book.pdf"), scans)
        with store.session() as s:
            b = Book(title=title, source=src)
            s.add(b)
            s.flush()
            return b.id

    return make


@pytest.fixture
def models_service(monkeypatch):
    """A strata-models stand-in on a loopback port whose `ocr` role is the real Tesseract (tests/utils/models_service.py); the client is
    pointed at it with STRATA_MODELS_URL, as the app's own service would be."""
    import threading

    from models_service import ModelsService

    svc = ModelsService()
    t = threading.Thread(target=svc.serve_forever, daemon=True)
    t.start()
    monkeypatch.setenv("STRATA_MODELS_URL", svc.url)
    yield svc
    svc.shutdown()
    svc.server_close()


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
