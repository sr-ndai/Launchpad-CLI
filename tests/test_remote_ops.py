"""Tests for remote filesystem helpers."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from launchpad_cli.core.remote_ops import (
    build_remote_job_layout,
    compute_remote_sha256,
    delete_remote_path,
    ensure_remote_directory,
    extract_remote_archive,
    list_remote_directory,
    measure_remote_path,
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


@pytest.mark.asyncio
async def test_measure_remote_path_parses_byte_count() -> None:
    """Remote size helpers should parse `du -sb` output into bytes."""

    connection = FakeConnection()
    connection.run_result = SimpleNamespace(
        exit_status=0,
        stdout="123456\t/shared/sergey/run\n",
        stderr="",
    )

    size_bytes = await measure_remote_path(
        connection,
        "/shared/sergey/run",
        du_binary="/usr/bin/du",
    )

    assert size_bytes == 123456
    assert connection.commands == ["/usr/bin/du -sb -- /shared/sergey/run"]


@pytest.mark.asyncio
async def test_compute_remote_sha256_parses_remote_digest() -> None:
    """Remote checksum helpers should extract the digest from `sha256sum` output."""

    connection = FakeConnection()
    connection.run_result = SimpleNamespace(
        exit_status=0,
        stdout="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /shared/sergey/run/results.tar.zst\n",
        stderr="",
    )

    digest = await compute_remote_sha256(
        connection,
        "/shared/sergey/run/results.tar.zst",
        sha256_binary="/usr/bin/sha256sum",
    )

    assert digest == "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    assert connection.commands == ["/usr/bin/sha256sum -- /shared/sergey/run/results.tar.zst"]


@pytest.mark.asyncio
async def test_list_remote_directory_returns_typed_entries() -> None:
    """Remote listings should parse GNU find output into stable entry metadata."""

    connection = FakeConnection()
    connection.run_result = SimpleNamespace(
        exit_status=0,
        stdout=(
            "d\t4096\t1710249600.0\t/shared/sergey/run/results_0\n"
            "f\t12\t1710249601.5\t/shared/sergey/run/results_0/summary.txt\n"
        ),
        stderr="",
    )

    entries = await list_remote_directory(
        connection,
        "/shared/sergey/run",
        recursive=True,
        find_binary="/usr/bin/find",
    )

    assert [entry.path for entry in entries] == [
        "/shared/sergey/run/results_0",
        "/shared/sergey/run/results_0/summary.txt",
    ]
    assert entries[0].is_dir is True
    assert entries[0].name == "results_0"
    assert entries[1].entry_type == "file"
    assert connection.commands == [
        "/usr/bin/find /shared/sergey/run -mindepth 1 -printf '%y\\t%s\\t%T@\\t%p\\n' | sort"
    ]


@pytest.mark.asyncio
async def test_delete_remote_path_uses_recursive_rm_by_default() -> None:
    """Remote deletion should use guarded recursive removal semantics."""

    connection = FakeConnection()

    deleted = await delete_remote_path(
        connection,
        "/shared/sergey/run",
        rm_binary="/bin/rm",
    )

    assert deleted == "/shared/sergey/run"
    assert connection.commands == ["/bin/rm -rf -- /shared/sergey/run"]


@pytest.mark.asyncio
async def test_ensure_remote_directory_normalizes_paths() -> None:
    """Directory helpers should normalize POSIX paths before creating them."""

    connection = FakeConnection()

    normalized = await ensure_remote_directory(connection, "/shared/sergey/run/../run/results")

    assert normalized == "/shared/sergey/run/../run/results"
    assert connection.directories == ["/shared/sergey/run/../run/results"]
