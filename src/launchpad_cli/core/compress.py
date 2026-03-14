"""Local and remote `.tar.zst` archive helpers."""

from __future__ import annotations

import hashlib
import shlex
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import asyncssh
import zstandard
from loguru import logger

HASH_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class ArchiveEntry:
    """Typed metadata for a member stored inside an archive."""

    path: str
    size_bytes: int
    is_dir: bool


@dataclass(frozen=True, slots=True)
class ArchiveInspection:
    """Structured view of a local `.tar.zst` archive."""

    archive_path: Path
    entries: tuple[ArchiveEntry, ...]

    @property
    def file_count(self) -> int:
        """Return the number of non-directory members in the archive."""

        return sum(1 for entry in self.entries if not entry.is_dir)

    @property
    def directory_count(self) -> int:
        """Return the number of directory members in the archive."""

        return sum(1 for entry in self.entries if entry.is_dir)


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


def inspect_archive(source: Path) -> ArchiveInspection:
    """Inspect a local `.tar.zst` archive and return its member metadata."""

    archive_path = source.expanduser()
    if not archive_path.is_file():
        raise FileNotFoundError(f"Compressed archive does not exist: {archive_path}")

    entries: list[ArchiveEntry] = []
    decompressor = zstandard.ZstdDecompressor()
    with archive_path.open("rb") as raw_archive:
        with decompressor.stream_reader(raw_archive) as decompressed_stream:
            with tarfile.open(fileobj=decompressed_stream, mode="r|") as archive:
                for member in archive:
                    entries.append(
                        ArchiveEntry(
                            path=member.name,
                            size_bytes=member.size,
                            is_dir=member.isdir(),
                        )
                    )

    return ArchiveInspection(archive_path=archive_path, entries=tuple(entries))


def compute_sha256(source: Path, *, chunk_size: int = HASH_CHUNK_SIZE) -> str:
    """Compute the SHA-256 checksum for a local file."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    file_path = source.expanduser()
    if not file_path.is_file():
        raise FileNotFoundError(f"Checksum source does not exist: {file_path}")

    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def build_remote_archive_command(
    *,
    source_paths: Sequence[str],
    archive_path: str,
    base_dir: str | None = None,
    exclude_patterns: Sequence[str] = (),
    tar_binary: str = "tar",
    zstd_binary: str = "zstd",
    compression_level: int = 3,
    compression_threads: int = 0,
) -> str:
    """Build the remote `tar` command used to create a `.tar.zst` archive."""

    if not source_paths:
        raise ValueError("source_paths must contain at least one entry")
    if not 1 <= compression_level <= 19:
        raise ValueError("compression_level must be between 1 and 19")
    if compression_threads < 0:
        raise ValueError("compression_threads must be non-negative")

    compress_program = " ".join(
        [
            shlex.quote(zstd_binary),
            f"-{compression_level}",
            f"-T{compression_threads}",
        ]
    )
    command = [
        shlex.quote(tar_binary),
        f"--use-compress-program={shlex.quote(compress_program)}",
        "-cf",
        shlex.quote(archive_path),
    ]
    if base_dir is not None:
        command.extend(["-C", shlex.quote(base_dir)])
    for pattern in exclude_patterns:
        command.append(f"--exclude={shlex.quote(pattern)}")
    command.extend(shlex.quote(path) for path in source_paths)
    return " ".join(command)


async def create_remote_archive(
    conn: asyncssh.SSHClientConnection,
    *,
    source_paths: Sequence[str],
    archive_path: str,
    base_dir: str | None = None,
    exclude_patterns: Sequence[str] = (),
    tar_binary: str = "tar",
    zstd_binary: str = "zstd",
    compression_level: int = 3,
    compression_threads: int = 0,
) -> str:
    """Create a remote `.tar.zst` archive from the provided source paths."""

    command = build_remote_archive_command(
        source_paths=source_paths,
        archive_path=archive_path,
        base_dir=base_dir,
        exclude_patterns=exclude_patterns,
        tar_binary=tar_binary,
        zstd_binary=zstd_binary,
        compression_level=compression_level,
        compression_threads=compression_threads,
    )
    result = await conn.run(command, check=False)
    if result.exit_status != 0:
        raise RuntimeError(
            "Remote archive creation failed: "
            f"{result.stderr.strip() or result.stdout.strip() or 'unknown error'}"
        )
    return archive_path
