"""Compression helpers reserved for zstd archive workflows."""

from __future__ import annotations

from pathlib import Path


def compress_path(source: Path, destination: Path, *, level: int = 3) -> Path:
    """Compress a local path into an archive.

    The implementation is intentionally deferred to a later task.
    """

    raise NotImplementedError("Local compression is not implemented yet.")


def decompress_path(source: Path, destination: Path) -> Path:
    """Decompress a local archive into a destination directory.

    The implementation is intentionally deferred to a later task.
    """

    raise NotImplementedError("Local decompression is not implemented yet.")

