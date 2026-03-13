"""Local filesystem helpers reserved for later CLI workflows."""

from __future__ import annotations

from pathlib import Path


def ensure_directory(path: Path) -> Path:
    """Create a local directory if it does not already exist."""

    path.mkdir(parents=True, exist_ok=True)
    return path

