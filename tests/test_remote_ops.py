"""Tests for remote submit filesystem helpers."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from launchpad_cli.core.remote_ops import (
    build_remote_job_layout,
    ensure_remote_directory,
    extract_remote_archive,
    prepare_remote_job_directory,
    write_remote_text,
)


class FakeRemoteFile:
    """Minimal remote file writer for SFTP-based tests."""

    def __init__(self, storage: dict[str, bytes], path: str) -> None:
        self.storage = storage
        self.path = path

    async def __aenter__(self) -> FakeRemoteFile:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def write(self, data: bytes) -> int:
        self.storage[self.path] = data
        return len(data)


class FakeSFTPClient:
    """Minimal async SFTP client used by remote helper tests."""

    def __init__(self, storage: dict[str, bytes], directories: list[str]) -> None:
        self.storage = storage
        self.directories = directories

    async def __aenter__(self) -> FakeSFTPClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def makedirs(self, path: str, exist_ok: bool = False) -> None:
        self.directories.append(path)

    def open(self, path: str, mode: str) -> FakeRemoteFile:
        return FakeRemoteFile(self.storage, path)


class FakeConnection:
    """SSH connection double exposing only the methods remote_ops uses."""

    def __init__(self) -> None:
        self.storage: dict[str, bytes] = {}
        self.directories: list[str] = []
        self.commands: list[str] = []
        self.run_result = SimpleNamespace(exit_status=0, stdout="", stderr="")

    @asynccontextmanager
    async def start_sftp_client(self) -> FakeSFTPClient:
        yield FakeSFTPClient(self.storage, self.directories)

    async def run(self, command: str, check: bool = False) -> SimpleNamespace:
        self.commands.append(command)
        return self.run_result


@pytest.mark.asyncio
async def test_prepare_remote_job_directory_creates_expected_paths() -> None:
    """Remote job setup should create the job root, logs dir, and scratch root."""

    connection = FakeConnection()
    layout = build_remote_job_layout(
        remote_job_dir="/shared/sergey/nastran-20260312-1947-abcd",
    )

    prepared = await prepare_remote_job_directory(connection, layout)

    assert prepared == layout
    assert connection.directories == [
        "/shared/sergey/nastran-20260312-1947-abcd",
        "/shared/sergey/nastran-20260312-1947-abcd/logs",
        "/shared/sergey/nastran-20260312-1947-abcd/scratch",
    ]


@pytest.mark.asyncio
async def test_write_remote_text_creates_parent_directories_and_writes_bytes() -> None:
    """Writing remote text should ensure the parent dir exists and persist UTF-8 bytes."""

    connection = FakeConnection()

    remote_path = await write_remote_text(
        connection,
        "/shared/sergey/run/submit.sbatch",
        "#!/usr/bin/env bash\n",
    )

    assert remote_path == "/shared/sergey/run/submit.sbatch"
    assert "/shared/sergey/run" in connection.directories
    assert connection.storage[remote_path] == b"#!/usr/bin/env bash\n"


@pytest.mark.asyncio
async def test_extract_remote_archive_uses_configured_tar_and_zstd_binaries() -> None:
    """Archive extraction should run the expected remote command."""

    connection = FakeConnection()

    await extract_remote_archive(
        connection,
        archive_path="/shared/sergey/run/inputs.tar.zst",
        destination_dir="/shared/sergey/run",
        tar_binary="/usr/bin/tar",
        zstd_binary="/usr/bin/zstd",
    )

    assert connection.commands == [
        "/usr/bin/tar --use-compress-program=/usr/bin/zstd -xf /shared/sergey/run/inputs.tar.zst -C /shared/sergey/run"
    ]


@pytest.mark.asyncio
async def test_extract_remote_archive_raises_on_remote_failure() -> None:
    """Archive extraction failures should surface the remote stderr payload."""

    connection = FakeConnection()
    connection.run_result = SimpleNamespace(exit_status=1, stdout="", stderr="tar failed")

    with pytest.raises(RuntimeError, match="tar failed"):
        await extract_remote_archive(
            connection,
            archive_path="/shared/sergey/run/inputs.tar.zst",
            destination_dir="/shared/sergey/run",
        )
