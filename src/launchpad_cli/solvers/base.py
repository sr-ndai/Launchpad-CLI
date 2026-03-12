"""Protocol definitions for solver-specific Launchpad behavior."""

from __future__ import annotations

from typing import Protocol


class SolverAdapter(Protocol):
    """Interface that every solver integration must implement."""

    @property
    def name(self) -> str:
        """Return the human-readable solver name."""

    @property
    def input_extensions(self) -> tuple[str, ...]:
        """Return the input file extensions used for discovery."""

