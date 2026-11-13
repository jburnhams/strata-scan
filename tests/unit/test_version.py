import importlib
from importlib.metadata import PackageNotFoundError

import stratascan


def test_version_comes_from_the_installed_package_metadata():
    assert stratascan.__version__ == importlib.metadata.version("strata-scan")


def test_version_falls_back_when_the_package_was_never_installed(monkeypatch):
    def missing(_name):
        raise PackageNotFoundError

    monkeypatch.setattr("importlib.metadata.version", missing)
    try:
        assert importlib.reload(stratascan).__version__ == "0+unknown"
    finally:
        monkeypatch.undo()
        importlib.reload(stratascan)
