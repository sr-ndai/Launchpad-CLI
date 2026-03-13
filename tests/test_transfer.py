"""Tests for resumable SFTP transfer helpers."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from launchpad_cli.core.transfer import download, upload


class FakeSFTPFile:
    """In-memory remote file handle used by transfer tests."""

    def __init__(self, storage: dict[str, bytes], path: str, mode: str) -> None:
        self._storage = storage
        self._path = path
        self._mode = mode
        self._offset = 0

        if "w" in mode:
            self._storage[path] = b""
        elif path not in self._storage:
            self._storage[path] = b""

    async def __aenter__(self) -> FakeSFTPFile:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def seek(self, offset: int, from_what: int = 0) -> int:
        if from_what != 0:
            raise NotImplementedError("Only absolute seeks are needed in tests.")
        self._offset = offset
        return self._offset

    async def read(self, size: int = -1, offset: int | None = None) -> bytes:
        data = self._storage[self._path]
        start = self._offset if offset is None else offset
        if size < 0:
            chunk = data[start:]
            self._offset = len(data)
            return chunk

        chunk = data[start : start + size]
        self._offset = start + len(chunk)
        return chunk

    async def write(self, data: bytes, offset: int | None = None) -> int:
        start = len(self._storage[self._path]) if "a" in self._mode else self._offset
        if offset is not None:
            start = offset

        current = bytearray(self._storage[self._path])
        end = start + len(data)
        if start > len(current):
            current.extend(b"\x00" * (start - len(current)))
        current[start:end] = data
        self._storage[self._path] = bytes(current)
        self._offset = end
        return len(data)


class FakeSFTPClient:
    """Minimal async SFTP client used to validate local transfer semantics."""

    def __init__(self, storage: dict[str, bytes]) -> None:
        self.storage = storage
        self.created_directories: list[str] = []

    async def __aenter__(self) -> FakeSFTPClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def makedirs(self, path: str, exist_ok: bool = False) -> None:
        self.created_directories.append(path)

    async def exists(self, path: str) -> bool:
        return path in self.storage

    async def stat(self, path: str) -> SimpleNamespace:
        if path not in self.storage:
            raise FileNotFoundError(path)
        return SimpleNamespace(size=len(self.storage[path]))

    def open(self, path: str, mode: str) -> FakeSFTPFile:
        return FakeSFTPFile(self.storage, path, mode)


class FakeConnection:
    """SSH connection double exposing only `start_sftp_client()`."""

    def __init__(self, client: FakeSFTPClient) -> None:
        self.client = client

    @asynccontextmanager
    async def start_sftp_client(self) -> FakeSFTPClient:
        yield self.client


@pytest.mark.asyncio
async def test_upload_resumes_existing_remote_file(tmp_path: Path) -> None:
    """Uploads should append from the remote file's current size when resuming."""

    local_path = tmp_path / "payload.bin"
    local_path.write_bytes(b"abcdefghij")

    storage = {"/shared/run/payload.bin": b"abcde"}
    client = FakeSFTPClient(storage)
    connection = FakeConnection(client)
    progress_updates: list[int] = []

    await upload(
        connection,
        local_path,
        "/shared/run/payload.bin",
        progress_callback=progress_updates.append,
    )

    assert storage["/shared/run/payload.bin"] == b"abcdefghij"
    assert progress_updates[0] == 5
    assert progress_updates[-1] == 10
    assert "/shared/run" in client.created_directories


@pytest.mark.asyncio
async def test_upload_restarts_when_remote_file_is_larger(tmp_path: Path) -> None:
    """Resume should restart cleanly if the remote partial is invalid."""

    local_path = tmp_path / "payload.bin"
    local_path.write_bytes(b"12345")

    storage = {"/shared/run/payload.bin": b"123456789"}
    connection = FakeConnection(FakeSFTPClient(storage))

    await upload(connection, local_path, "/shared/run/payload.bin")

    assert storage["/shared/run/payload.bin"] == b"12345"


@pytest.mark.asyncio
async def test_download_resumes_existing_local_file(tmp_path: Path) -> None:
    """Downloads should continue from the existing local byte count."""

    destination = tmp_path / "results" / "payload.bin"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"abc")

    storage = {"/shared/results/payload.bin": b"abcdefghi"}
    connection = FakeConnection(FakeSFTPClient(storage))
    progress_updates: list[int] = []

    await download(
        connection,
        "/shared/results/payload.bin",
        destination,
        progress_callback=progress_updates.append,
    )

    assert destination.read_bytes() == b"abcdefghi"
    assert progress_updates[0] == 3
    assert progress_updates[-1] == 9


@pytest.mark.asyncio
async def test_download_restarts_when_local_file_is_larger(tmp_path: Path) -> None:
    """Resume should restart the download if the local partial is invalid."""

    destination = tmp_path / "payload.bin"
    destination.write_bytes(b"abcdef")

    storage = {"/shared/results/payload.bin": b"abc"}
    connection = FakeConnection(FakeSFTPClient(storage))

    await download(connection, "/shared/results/payload.bin", destination)

    assert destination.read_bytes() == b"abc"
