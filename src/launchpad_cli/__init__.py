"""Top-level package for the Launchpad CLI."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("launchpad-cli")
except PackageNotFoundError:
    __version__ = "0.1.0"

