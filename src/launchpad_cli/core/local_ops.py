"""Local filesystem helpers used by download-oriented workflows."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DiskSpaceReport:
    """Structured disk-space summary for a target local path."""

    target_path: Path
    probe_path: Path
    bytes_required: int
    bytes_free: int
    bytes_total: int
    reserve_bytes: int = 0

    @property
    def bytes_available(self) -> int:
        """Return the bytes available after applying the reserve threshold."""

        return max(self.bytes_free - self.reserve_bytes, 0)

    @property
    def sufficient(self) -> bool:
        """Return whether the target path has enough free space."""

        return self.bytes_available >= self.bytes_required

    @property
    def bytes_missing(self) -> int:
        """Return how many bytes are still needed to satisfy the request."""

        return max(self.bytes_required - self.bytes_available, 0)


def ensure_directory(path: Path) -> Path:
    """Create a local directory if it does not already exist."""

    directory = path.expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def default_download_destination(run_name: str, *, cwd: Path | None = None) -> Path:
    """Return the default local results directory for a downloaded run."""

    base_dir = cwd.expanduser() if cwd is not None else Path.cwd()
    return base_dir / f"results_{run_name}"


def resolve_download_destination(
    destination: Path | None,
    *,
    run_name: str,
    cwd: Path | None = None,
) -> Path:
    """Resolve the local destination directory used by download workflows."""

    if destination is None:
        resolved = default_download_destination(run_name, cwd=cwd)
    elif destination.is_absolute():
        resolved = destination.expanduser()
    else:
        base_dir = cwd.expanduser() if cwd is not None else Path.cwd()
        resolved = (base_dir / destination).expanduser()

    if resolved.exists() and not resolved.is_dir():
        raise NotADirectoryError(f"Download destination is not a directory: {resolved}")

    return resolved


def inspect_disk_space(
    target_path: Path,
    *,
    required_bytes: int,
    reserve_bytes: int = 0,
) -> DiskSpaceReport:
    """Measure disk space for a target path using the nearest existing parent."""

    if required_bytes < 0:
        raise ValueError("required_bytes must be non-negative")
    if reserve_bytes < 0:
        raise ValueError("reserve_bytes must be non-negative")

    resolved_target = target_path.expanduser()
    probe_path = _nearest_existing_directory(resolved_target)
    usage = shutil.disk_usage(probe_path)
    return DiskSpaceReport(
        target_path=resolved_target,
        probe_path=probe_path,
        bytes_required=required_bytes,
        bytes_free=usage.free,
        bytes_total=usage.total,
        reserve_bytes=reserve_bytes,
    )


def _nearest_existing_directory(path: Path) -> Path:
    """Return the closest existing directory for a possibly-missing target path."""

    candidate = path
    if candidate.exists() and not candidate.is_dir():
        candidate = candidate.parent
    while not candidate.exists():
        parent = candidate.parent
        if parent == candidate:
            raise FileNotFoundError(f"No existing parent directory found for {path}")
        candidate = parent

    return candidate if candidate.is_dir() else candidate.parent
