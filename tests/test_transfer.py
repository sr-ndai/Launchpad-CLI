"""Tests for resumable SFTP transfer helpers."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
import shlex

import pytest

from launchpad_cli.core.config import SSHConfig
from launchpad_cli.core import transfer as transfer_module
from launchpad_cli.core.transfer import download, download_many, striped_download, striped_upload, upload, upload_many


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

    async def remove(self, path: str) -> None:
        if path not in self.storage:
            raise FileNotFoundError(path)
        self.storage.pop(path, None)

    async def rename(self, oldpath: str, newpath: str) -> None:
        if oldpath not in self.storage:
            raise FileNotFoundError(oldpath)
        self.storage[newpath] = self.storage.pop(oldpath)


class FakeConnection:
    """SSH connection double exposing the subset of SSH features transfers use."""

    def __init__(self, client: FakeSFTPClient) -> None:
        self.client = client
        self.commands: list[str] = []

    @asynccontextmanager
    async def start_sftp_client(self) -> FakeSFTPClient:
        yield self.client

    async def run(self, command: str, check: bool = False) -> SimpleNamespace:
        self.commands.append(command)
        segments = command.split(" && ")
        if len(segments) == 4 and segments[1].startswith("cat -- "):
            rm_tokens = shlex.split(segments[0])
            cat_tokens = shlex.split(segments[1])
            size_segment = segments[2]
            mv_tokens = shlex.split(segments[3])

            if rm_tokens[:3] != ["rm", "-f", "--"] or mv_tokens[:3] != ["mv", "-f", "--"]:
                return SimpleNamespace(exit_status=1, stdout="", stderr="unsupported command")

            partial_path = rm_tokens[3]
            target_path = mv_tokens[4]
            if mv_tokens[3] != partial_path:
                return SimpleNamespace(exit_status=1, stdout="", stderr="unsupported command")

            try:
                redirect_index = cat_tokens.index(">")
            except ValueError:
                return SimpleNamespace(exit_status=1, stdout="", stderr="unsupported command")
            if cat_tokens[:2] != ["cat", "--"] or cat_tokens[redirect_index + 1] != partial_path:
                return SimpleNamespace(exit_status=1, stdout="", stderr="unsupported command")

            part_paths = cat_tokens[2:redirect_index]
            assembled = b"".join(self.client.storage[path] for path in part_paths)
            self.client.storage.pop(partial_path, None)
            self.client.storage[partial_path] = assembled

            expected_size = int(size_segment.rsplit(" ", maxsplit=2)[1])
            if len(assembled) != expected_size:
                return SimpleNamespace(exit_status=1, stdout="", stderr="size mismatch")

            self.client.storage[target_path] = self.client.storage.pop(partial_path)
            return SimpleNamespace(exit_status=0, stdout="", stderr="")

        parts = shlex.split(command)
        if parts[:3] == ["rm", "-rf", "--"] and len(parts) == 4:
            root = parts[3]
            for path in list(self.client.storage):
                if path == root or path.startswith(f"{root}/"):
                    self.client.storage.pop(path, None)
            return SimpleNamespace(exit_status=0, stdout="", stderr="")
        return SimpleNamespace(exit_status=1, stdout="", stderr="unsupported command")


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


@pytest.mark.asyncio
async def test_striped_upload_assembles_remote_payload_and_cleans_staging(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Striped upload should build the final remote file from temporary parts."""

    source = tmp_path / "payload.bin"
    source.write_bytes(b"abcdefghij")

    storage: dict[str, bytes] = {}
    control_connection = FakeConnection(FakeSFTPClient(storage))

    @asynccontextmanager
    async def fake_ssh_session(_config: SSHConfig):
        yield FakeConnection(FakeSFTPClient(storage))

    monkeypatch.setattr(transfer_module, "ssh_session", fake_ssh_session)

    result = await striped_upload(
        control_connection,
        SSHConfig(host="cluster.example.com", username="sergey"),
        source,
        "/shared/run/payload.bin",
        streams=3,
        chunk_size=4,
        resume=True,
    )

    assert result.effective_streams == 3
    assert storage["/shared/run/payload.bin"] == b"abcdefghij"
    assert any("cat --" in command for command in control_connection.commands)
    assert not any(path.startswith("/shared/run/.launchpad-transfer/") for path in storage)


@pytest.mark.asyncio
async def test_striped_download_resumes_existing_part_and_assembles_locally(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Striped download should reuse completed part files and assemble the final archive."""

    destination = tmp_path / "payload.bin"
    part_dir = tmp_path / "payload.bin.parts"
    part_dir.mkdir(parents=True)
    (part_dir / "part-00000").write_bytes(b"abcd")

    storage = {"/shared/results/payload.bin": b"abcdefghij"}
    control_connection = FakeConnection(FakeSFTPClient(storage))

    @asynccontextmanager
    async def fake_ssh_session(_config: SSHConfig):
        yield FakeConnection(FakeSFTPClient(storage))

    monkeypatch.setattr(transfer_module, "ssh_session", fake_ssh_session)

    result = await striped_download(
        control_connection,
        SSHConfig(host="cluster.example.com", username="sergey"),
        "/shared/results/payload.bin",
        destination,
        streams=3,
        chunk_size=4,
        resume=True,
    )

    assert result.effective_streams == 3
    assert destination.read_bytes() == b"abcdefghij"
    assert not part_dir.exists()


@pytest.mark.asyncio
async def test_upload_many_falls_back_when_additional_sessions_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Worker-pool uploads should reduce effective streams when the server rejects concurrency."""

    first = tmp_path / "one.txt"
    second = tmp_path / "two.txt"
    first.write_text("one", encoding="utf-8")
    second.write_text("two", encoding="utf-8")

    storage: dict[str, bytes] = {}
    open_attempt = {"count": 0}

    @asynccontextmanager
    async def fake_ssh_session(_config: SSHConfig):
        open_attempt["count"] += 1
        if open_attempt["count"] == 2:
            raise OSError("too many sessions")
        yield FakeConnection(FakeSFTPClient(storage))

    monkeypatch.setattr(transfer_module, "ssh_session", fake_ssh_session)

    result = await upload_many(
        SSHConfig(host="cluster.example.com", username="sergey"),
        (
            transfer_module.UploadItem(first, "/shared/run/one.txt"),
            transfer_module.UploadItem(second, "/shared/run/two.txt"),
        ),
        streams=2,
        resume=True,
    )

    assert result.effective_streams == 1
    assert storage["/shared/run/one.txt"] == b"one"
    assert storage["/shared/run/two.txt"] == b"two"


@pytest.mark.asyncio
async def test_download_many_uses_worker_pool_to_copy_multiple_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Worker-pool downloads should preserve file contents across multiple items."""

    storage = {
        "/shared/results/one.txt": b"one",
        "/shared/results/two.txt": b"two",
    }

    @asynccontextmanager
    async def fake_ssh_session(_config: SSHConfig):
        yield FakeConnection(FakeSFTPClient(storage))

    monkeypatch.setattr(transfer_module, "ssh_session", fake_ssh_session)

    result = await download_many(
        SSHConfig(host="cluster.example.com", username="sergey"),
        (
            transfer_module.DownloadItem("/shared/results/one.txt", tmp_path / "one.txt"),
            transfer_module.DownloadItem("/shared/results/two.txt", tmp_path / "two.txt"),
        ),
        streams=2,
        resume=True,
    )

    assert result.effective_streams == 2
    assert (tmp_path / "one.txt").read_text(encoding="utf-8") == "one"
    assert (tmp_path / "two.txt").read_text(encoding="utf-8") == "two"
