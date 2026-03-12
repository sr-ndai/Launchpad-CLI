"""Shared Rich display helpers for CLI-facing output."""

from __future__ import annotations

from rich.console import Console


def build_console(*, stderr: bool = False, no_color: bool = False) -> Console:
    """Create a Rich console with the repository's baseline output defaults."""

    return Console(stderr=stderr, no_color=no_color)

