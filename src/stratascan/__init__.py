"""strata-scan: turn scanned books into clean pages, text and pictures."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("strata-scan")  # pyproject.toml is the one place the version lives
except PackageNotFoundError:
    __version__ = "0+unknown"  # running from a source tree that was never installed
