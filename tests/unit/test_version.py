import importlib
from importlib.metadata import PackageNotFoundError

import app


def test_version_comes_from_the_installed_package_metadata():
    assert app.__version__ == importlib.metadata.version("python-app-template")


def test_version_falls_back_when_the_package_was_never_installed(monkeypatch):
    def missing(_name):
        raise PackageNotFoundError

    monkeypatch.setattr("importlib.metadata.version", missing)
    try:
        assert importlib.reload(app).__version__ == "0+unknown"
    finally:
        monkeypatch.undo()
        importlib.reload(app)
