"""Local `.tar.zst` archive helpers."""

from __future__ import annotations

import tarfile
from pathlib import Path

import zstandard
from loguru import logger


def compress_path(source: Path, destination: Path, *, level: int = 3) -> Path:
    """Compress a file or directory into a local `.tar.zst` archive."""

    source_path = source.expanduser()
    if not source_path.exists():
        raise FileNotFoundError(f"Compression source does not exist: {source_path}")

    archive_path = destination.expanduser()
    archive_path.parent.mkdir(parents=True, exist_ok=True)

    logger.debug("Compressing {} into {} with zstd level {}", source_path, archive_path, level)

    compressor = zstandard.ZstdCompressor(level=level)
    with archive_path.open("wb") as raw_archive:
        with compressor.stream_writer(raw_archive) as compressed_stream:
            with tarfile.open(fileobj=compressed_stream, mode="w|") as archive:
                archive.add(source_path, arcname=source_path.name, recursive=True)

    logger.debug(
        "Compressed {} bytes into {} bytes",
        source_path.stat().st_size if source_path.is_file() else 0,
        archive_path.stat().st_size,
    )
    return archive_path


def decompress_path(source: Path, destination: Path) -> Path:
    """Decompress a local `.tar.zst` archive into a destination directory."""

    archive_path = source.expanduser()
    if not archive_path.is_file():
        raise FileNotFoundError(f"Compressed archive does not exist: {archive_path}")

    destination_path = destination.expanduser()
    destination_path.mkdir(parents=True, exist_ok=True)

    logger.debug("Decompressing {} into {}", archive_path, destination_path)

    decompressor = zstandard.ZstdDecompressor()
    with archive_path.open("rb") as raw_archive:
        with decompressor.stream_reader(raw_archive) as decompressed_stream:
            with tarfile.open(fileobj=decompressed_stream, mode="r|") as archive:
                archive.extractall(path=destination_path, filter="data")

    return destination_path
