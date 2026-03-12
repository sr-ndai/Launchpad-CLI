"""Baseline Nastran solver adapter placeholder."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NastranAdapter:
    """Placeholder Nastran adapter used to reserve the solver slot."""

    name: str = "Nastran"
    input_extensions: tuple[str, ...] = (".dat",)

