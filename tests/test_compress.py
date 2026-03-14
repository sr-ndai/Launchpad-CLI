"""Tests for local and remote archive helpers."""

from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

import pytest

from launchpad_cli.core.compress import (
    build_remote_archive_command,
    compress_path,
    compute_sha256,
    create_remote_archive,
    decompress_path,
    inspect_archive,
)


class FakeConnection:
    """SSH connection double exposing only the methods compression helpers use."""

    def __init__(self) -> None:
        self.commands: list[str] = []
        self.run_result = SimpleNamespace(exit_status=0, stdout="", stderr="")

    async def run(self, command: str, check: bool = False) -> SimpleNamespace:
        self.commands.append(command)
        return self.run_result


def test_compress_and_decompress_directory_round_trip(tmp_path: Path) -> None:
    """Directories should round-trip through a `.tar.zst` archive."""

    source = tmp_path / "model"
    nested = source / "nested"
    nested.mkdir(parents=True)
    (source / "input.dat").write_text("GRID,1\n", encoding="utf-8")
    (nested / "material.inc").write_text("MAT1,1\n", encoding="utf-8")

    archive = tmp_path / "artifacts" / "model.tar.zst"
    extracted = tmp_path / "restored"

    result_archive = compress_path(source, archive, level=5)
    result_directory = decompress_path(result_archive, extracted)

    assert result_archive == archive
    assert result_archive.exists()
    assert result_directory == extracted
    assert (extracted / "model" / "input.dat").read_text(encoding="utf-8") == "GRID,1\n"
    assert (
        extracted / "model" / "nested" / "material.inc"
    ).read_text(encoding="utf-8") == "MAT1,1\n"


def test_inspect_archive_reports_members_and_counts(tmp_path: Path) -> None:
    """Archive inspection should expose stable metadata for later verification."""

    source = tmp_path / "results"
    source.mkdir()
    (source / "summary.txt").write_text("done\n", encoding="utf-8")
    archive = compress_path(source, tmp_path / "results.tar.zst")

    inspection = inspect_archive(archive)

    assert inspection.file_count == 1
    assert inspection.directory_count >= 1
    assert inspection.entries[0].path == "results"
    assert any(entry.path == "results/summary.txt" for entry in inspection.entries)


def test_compute_sha256_returns_digest_for_local_file(tmp_path: Path) -> None:
    """Checksum helpers should stream local files into a SHA-256 digest."""

    payload = tmp_path / "payload.bin"
    payload.write_bytes(b"launchpad")

    assert compute_sha256(payload) == "7b3937a5f4397ec652546ef2e72a9e9a35d5ac5241461b09cd1ad524b25ac5b1"


def test_build_remote_archive_command_supports_excludes() -> None:
    """Remote archive commands should wire tar, zstd, and exclude patterns consistently."""

    command = build_remote_archive_command(
        source_paths=("results_a", "results_b"),
        archive_path="/shared/run/results.tar.zst",
        base_dir="/shared/run",
        exclude_patterns=("*.tmp", "scratch/*"),
        tar_binary="/usr/bin/tar",
        zstd_binary="/usr/bin/zstd",
        compression_level=5,
    )

    assert command == (
        "/usr/bin/tar --use-compress-program='/usr/bin/zstd -5 -T0' "
        "-cf /shared/run/results.tar.zst -C /shared/run "
        "--exclude='*.tmp' --exclude='scratch/*' results_a results_b"
    )


@pytest.mark.asyncio
async def test_create_remote_archive_runs_expected_command() -> None:
    """Remote archive creation should execute the tar command built from inputs."""

    connection = FakeConnection()

    archive_path = await create_remote_archive(
        connection,
        source_paths=("results_0", "results_1"),
        archive_path="/shared/run/results.tar.zst",
        base_dir="/shared/run",
        tar_binary="/usr/bin/tar",
        zstd_binary="/usr/bin/zstd",
        compression_level=7,
        compression_threads=4,
    )

    assert archive_path == "/shared/run/results.tar.zst"
    assert connection.commands == [
        "/usr/bin/tar --use-compress-program='/usr/bin/zstd -7 -T4' "
        "-cf /shared/run/results.tar.zst -C /shared/run results_0 results_1"
    ]


@pytest.mark.asyncio
async def test_create_remote_archive_raises_on_remote_failure() -> None:
    """Remote archive creation failures should surface the remote error payload."""

    connection = FakeConnection()
    connection.run_result = SimpleNamespace(exit_status=1, stdout="", stderr="tar failed")

    with pytest.raises(RuntimeError, match="tar failed"):
        await create_remote_archive(
            connection,
            source_paths=("results_0",),
            archive_path="/shared/run/results.tar.zst",
        )


def test_compress_path_requires_existing_source(tmp_path: Path) -> None:
    """Compression should fail fast for missing sources."""

    with pytest.raises(FileNotFoundError):
        compress_path(tmp_path / "missing", tmp_path / "missing.tar.zst")


def test_decompress_path_requires_existing_archive(tmp_path: Path) -> None:
    """Decompression should fail fast for missing archives."""

    with pytest.raises(FileNotFoundError):
        decompress_path(tmp_path / "missing.tar.zst", tmp_path / "output")
