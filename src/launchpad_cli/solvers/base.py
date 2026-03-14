"""Shared solver adapter contracts and discovery helpers."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol, runtime_checkable

from launchpad_cli.core.config import LaunchpadConfig


@dataclass(frozen=True, slots=True)
class DiscoveredInput:
    """Validation-friendly metadata for a discovered solver input file."""

    path: Path
    relative_path: Path
    stem: str
    extension: str
    size_bytes: int

    @property
    def basename(self) -> str:
        """Return the file name with extension."""

        return self.path.name


@dataclass(frozen=True, slots=True)
class SubmitOverrides:
    """Narrow submission overrides consumed by solver command builders."""

    cpus: int | None = None
    memory: str | None = None


@runtime_checkable
class SolverAdapter(Protocol):
    """Interface that each solver must implement."""

    @property
    def name(self) -> str:
        """Solver display name."""

    @property
    def input_extensions(self) -> tuple[str, ...]:
        """File extensions used during input discovery."""

    @property
    def output_extensions(self) -> tuple[str, ...]:
        """Output file extensions relevant to later log/result workflows."""

    @property
    def log_catalog(self) -> Mapping[str, str]:
        """Named solver-log kinds captured in the submitted manifest."""

    def discover_inputs(self, input_dir: Path) -> list[DiscoveredInput]:
        """Discover supported input files beneath the given input directory."""

    def build_run_command(
        self,
        input_file: str,
        config: LaunchpadConfig,
        overrides: SubmitOverrides | None = None,
    ) -> str:
        """Build the shell command used to run a single solver input."""

    def build_scratch_env(self, scratch_dir: str) -> dict[str, str]:
        """Return environment variables needed to prepare the scratch area."""


def discover_inputs_by_extension(
    input_dir: Path,
    *,
    extensions: tuple[str, ...],
) -> list[DiscoveredInput]:
    """Return deterministic input discovery results for the requested extensions."""

    root = input_dir.expanduser()
    if not root.exists():
        raise FileNotFoundError(f"Input directory does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Input path is not a directory: {root}")

    normalized_extensions = {normalize_extension(extension) for extension in extensions}
    discovered: list[DiscoveredInput] = []

    for candidate in sorted(root.iterdir(), key=lambda path: path.name.lower()):
        if not candidate.is_file():
            continue
        extension = candidate.suffix.lower()
        if extension not in normalized_extensions:
            continue
        discovered.append(
            DiscoveredInput(
                path=candidate,
                relative_path=Path(candidate.name),
                stem=candidate.stem,
                extension=extension,
                size_bytes=candidate.stat().st_size,
            )
        )

    return discovered


def normalize_extension(extension: str) -> str:
    """Normalize an input/output extension into dotted lowercase form."""

    if not extension:
        raise ValueError("Solver extensions must not be empty.")
    normalized = extension if extension.startswith(".") else f".{extension}"
    return normalized.lower()


def quote_arg(value: str) -> str:
    """Quote a shell argument for later remote command generation."""

    return shlex.quote(value)
