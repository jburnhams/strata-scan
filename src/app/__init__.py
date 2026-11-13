"""app: full-stack Python + React application template."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("python-app-template")  # pyproject.toml is the one place the version lives
except PackageNotFoundError:
    __version__ = "0+unknown"  # running from a source tree that was never installed
