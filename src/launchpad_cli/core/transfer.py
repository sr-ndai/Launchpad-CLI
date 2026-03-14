"""Transfer helpers for single-stream, striped, and worker-pool workflows."""

from __future__ import annotations

import asyncio
import shlex
import shutil
from contextlib import AsyncExitStack, suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Callable, Sequence

import asyncssh
from loguru import logger

from .config import SSHConfig
from .ssh import ssh_session

TRANSFER_CHUNK_SIZE = 1024 * 1024
ProgressCallback = Callable[[int], None]


@dataclass(frozen=True, slots=True)
class UploadItem:
    """One local-to-remote file copy operation."""

    local_path: Path
    remote_path: str


@dataclass(frozen=True, slots=True)
class DownloadItem:
    """One remote-to-local file copy operation."""

    remote_path: str
    local_path: Path


@dataclass(frozen=True, slots=True)
class TransferExecution:
    """Effective transfer settings after stream fallback is applied."""

    effective_streams: int


@dataclass(frozen=True, slots=True)
class _LocalPart:
    """One deterministic temporary file used by striped upload/download."""

    index: int
    offset: int
    size_bytes: int
    path: Path


def _emit_progress(progress_callback: ProgressCallback | None, transferred: int) -> None:
    if progress_callback is not None:
        progress_callback(transferred)


def chunk_size_bytes(chunk_size_mb: int) -> int:
    """Convert a configured chunk size in MB into bytes."""

    if chunk_size_mb <= 0:
        raise ValueError("chunk_size_mb must be positive")
    return chunk_size_mb * 1024 * 1024


async def upload(
    conn: asyncssh.SSHClientConnection,
    local_path: Path,
    remote_path: str,
    *,
    resume: bool = True,
    progress_callback: ProgressCallback | None = None,
) -> None:
    """Upload a file via SFTP with resume support and cumulative progress."""

    source = local_path.expanduser()
    if not source.is_file():
        raise FileNotFoundError(f"Local upload source does not exist: {source}")

    total_size = source.stat().st_size
    remote_target = PurePosixPath(remote_path)
    remote_parent = remote_target.parent

    logger.debug(
        "Uploading {} to {} (resume={})",
        source,
        remote_target,
        resume,
    )

    async with conn.start_sftp_client() as sftp:
        if str(remote_parent) not in ("", ".", "/"):
            await sftp.makedirs(str(remote_parent), exist_ok=True)

        remote_size = 0
        remote_exists = await sftp.exists(str(remote_target))
        if remote_exists:
            remote_size = int((await sftp.stat(str(remote_target))).size or 0)

        if not resume:
            remote_size = 0
        elif remote_size > total_size:
            logger.warning(
                "Remote file {} is larger than the local source; restarting upload",
                remote_target,
            )
            remote_size = 0

        _emit_progress(progress_callback, remote_size)

        open_mode = "ab" if remote_size else "wb"
        async with sftp.open(str(remote_target), open_mode) as remote_file:
            with source.open("rb") as local_file:
                local_file.seek(remote_size)
                transferred = remote_size
                while True:
                    chunk = local_file.read(TRANSFER_CHUNK_SIZE)
                    if not chunk:
                        break
                    await remote_file.write(chunk)
                    transferred += len(chunk)
                    _emit_progress(progress_callback, transferred)

        final_size = int((await sftp.stat(str(remote_target))).size or 0)
        if final_size != total_size:
            raise IOError(
                f"Upload size mismatch for {remote_target}: expected {total_size}, got {final_size}"
            )


async def download(
    conn: asyncssh.SSHClientConnection,
    remote_path: str,
    local_path: Path,
    *,
    resume: bool = True,
    progress_callback: ProgressCallback | None = None,
) -> None:
    """Download a file via SFTP with resume support and cumulative progress."""

    destination = local_path.expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    remote_target = PurePosixPath(remote_path)

    logger.debug(
        "Downloading {} to {} (resume={})",
        remote_target,
        destination,
        resume,
    )

    async with conn.start_sftp_client() as sftp:
        remote_size = int((await sftp.stat(str(remote_target))).size or 0)

        local_size = destination.stat().st_size if destination.exists() else 0
        if destination.exists() and not destination.is_file():
            raise IsADirectoryError(f"Download destination is not a file: {destination}")

        if not resume:
            local_size = 0
        elif local_size > remote_size:
            logger.warning(
                "Local file {} is larger than the remote source; restarting download",
                destination,
            )
            local_size = 0

        _emit_progress(progress_callback, local_size)

        write_mode = "ab" if local_size else "wb"
        async with sftp.open(str(remote_target), "rb") as remote_file:
            if local_size:
                await remote_file.seek(local_size)

            with destination.open(write_mode) as local_file:
                transferred = local_size
                while True:
                    chunk = await remote_file.read(TRANSFER_CHUNK_SIZE)
                    if not chunk:
                        break
                    local_file.write(chunk)
                    transferred += len(chunk)
                    _emit_progress(progress_callback, transferred)

        final_size = destination.stat().st_size
        if final_size != remote_size:
            raise IOError(
                f"Download size mismatch for {remote_target}: expected {remote_size}, got {final_size}"
            )


async def upload_many(
    ssh_config: SSHConfig,
    items: Sequence[UploadItem],
    *,
    streams: int,
    resume: bool = True,
) -> TransferExecution:
    """Upload many files concurrently using a bounded worker pool."""

    if not items:
        return TransferExecution(effective_streams=1)

    logger.debug(
        "Starting multi-file upload of {} item(s) with {} requested stream(s)",
        len(items),
        streams,
    )

    async def runner(effective_streams: int) -> None:
        async def worker(conn: asyncssh.SSHClientConnection, item: UploadItem) -> None:
            await upload(conn, item.local_path, item.remote_path, resume=resume)

        await _run_worker_pool(
            ssh_config=ssh_config,
            items=items,
            streams=effective_streams,
            worker=worker,
        )

    effective_streams = await _run_with_stream_fallback(
        requested_streams=streams,
        item_count=len(items),
        operation_name="upload",
        runner=runner,
    )
    return TransferExecution(effective_streams=effective_streams)


async def download_many(
    ssh_config: SSHConfig,
    items: Sequence[DownloadItem],
    *,
    streams: int,
    resume: bool = True,
) -> TransferExecution:
    """Download many files concurrently using a bounded worker pool."""

    if not items:
        return TransferExecution(effective_streams=1)

    logger.debug(
        "Starting multi-file download of {} item(s) with {} requested stream(s)",
        len(items),
        streams,
    )

    async def runner(effective_streams: int) -> None:
        async def worker(conn: asyncssh.SSHClientConnection, item: DownloadItem) -> None:
            await download(conn, item.remote_path, item.local_path, resume=resume)

        await _run_worker_pool(
            ssh_config=ssh_config,
            items=items,
            streams=effective_streams,
            worker=worker,
        )

    effective_streams = await _run_with_stream_fallback(
        requested_streams=streams,
        item_count=len(items),
        operation_name="download",
        runner=runner,
    )
    return TransferExecution(effective_streams=effective_streams)


async def striped_upload(
    conn: asyncssh.SSHClientConnection,
    ssh_config: SSHConfig,
    local_path: Path,
    remote_path: str,
    *,
    streams: int,
    chunk_size: int,
    resume: bool = True,
) -> TransferExecution:
    """Upload one logical payload through deterministic temporary remote parts."""

    source = local_path.expanduser()
    if not source.is_file():
        raise FileNotFoundError(f"Local upload source does not exist: {source}")

    total_size = source.stat().st_size
    remote_target = str(PurePosixPath(remote_path))
    existing_size = await _remote_size(conn, remote_target)
    if resume and existing_size == total_size:
        logger.info("Striped upload already complete for {}; reusing remote payload", remote_target)
        return TransferExecution(effective_streams=1)

    with TemporaryDirectory(prefix=f"{source.stem}-parts-") as temp_dir:
        part_dir = Path(temp_dir)
        parts = _split_local_file(source, part_dir, chunk_size=chunk_size)
        staging_dir = _remote_staging_dir(remote_target)
        remote_items = [
            UploadItem(
                local_path=part.path,
                remote_path=str(PurePosixPath(staging_dir) / f"part-{part.index:05d}"),
            )
            for part in parts
        ]
        logger.debug(
            "Starting striped upload of {} ({} bytes) as {} part(s)",
            source,
            total_size,
            len(remote_items),
        )

        effective = await upload_many(
            ssh_config,
            remote_items,
            streams=min(streams, len(remote_items)),
            resume=resume,
        )

        await _assemble_remote_parts(
            conn,
            remote_parts=[item.remote_path for item in remote_items],
            remote_target=remote_target,
            expected_size=total_size,
        )
        await _remove_remote_tree(conn, staging_dir)
        return effective


async def striped_download(
    conn: asyncssh.SSHClientConnection,
    ssh_config: SSHConfig,
    remote_path: str,
    local_path: Path,
    *,
    streams: int,
    chunk_size: int,
    resume: bool = True,
) -> TransferExecution:
    """Download one logical payload through deterministic local temporary parts."""

    remote_target = str(PurePosixPath(remote_path))
    remote_size = await _require_remote_size(conn, remote_target)
    destination = local_path.expanduser()
    if destination.exists() and not destination.is_file():
        raise IsADirectoryError(f"Download destination is not a file: {destination}")
    if resume and destination.exists() and destination.stat().st_size == remote_size:
        logger.info("Striped download already complete for {}; reusing local payload", destination)
        return TransferExecution(effective_streams=1)

    part_dir = _local_part_dir(destination)
    part_dir.mkdir(parents=True, exist_ok=True)
    parts = _build_local_parts(part_dir, total_size=remote_size, chunk_size=chunk_size)
    logger.debug(
        "Starting striped download of {} ({} bytes) as {} part(s)",
        remote_target,
        remote_size,
        len(parts),
    )

    async def runner(effective_streams: int) -> None:
        async def worker(conn: asyncssh.SSHClientConnection, part: _LocalPart) -> None:
            await _download_remote_part(
                conn,
                remote_path=remote_target,
                part=part,
                resume=resume,
            )

        await _run_worker_pool(
            ssh_config=ssh_config,
            items=parts,
            streams=effective_streams,
            worker=worker,
        )

    effective_streams = await _run_with_stream_fallback(
        requested_streams=streams,
        item_count=len(parts),
        operation_name="striped download",
        runner=runner,
    )

    _assemble_local_parts(parts, destination)
    final_size = destination.stat().st_size
    if final_size != remote_size:
        raise IOError(
            f"Download size mismatch for {remote_target}: expected {remote_size}, got {final_size}"
        )

    shutil.rmtree(part_dir, ignore_errors=True)
    return TransferExecution(effective_streams=effective_streams)


async def _run_worker_pool(
    *,
    ssh_config: SSHConfig,
    items: Sequence[object],
    streams: int,
    worker,
) -> None:
    """Run a bounded async worker pool over SSH connections."""

    queue: asyncio.Queue[object] = asyncio.Queue()
    for item in items:
        queue.put_nowait(item)

    async with AsyncExitStack() as stack:
        connections = [
            await stack.enter_async_context(ssh_session(ssh_config))
            for _ in range(streams)
        ]

        async def run_worker(conn: asyncssh.SSHClientConnection) -> None:
            while True:
                try:
                    item = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    await worker(conn, item)
                finally:
                    queue.task_done()

        await asyncio.gather(*(run_worker(conn) for conn in connections))


async def _run_with_stream_fallback(
    *,
    requested_streams: int,
    item_count: int,
    operation_name: str,
    runner,
) -> int:
    """Retry a parallel transfer with fewer streams when the server rejects concurrency."""

    effective_streams = max(1, min(requested_streams, item_count))
    if effective_streams < requested_streams:
        logger.debug(
            "{} stream budget capped from {} to {} for {} item(s)",
            operation_name.capitalize(),
            requested_streams,
            effective_streams,
            item_count,
        )
    while True:
        try:
            await runner(effective_streams)
            return effective_streams
        except Exception as exc:
            if effective_streams <= 1 or not _is_parallelism_error(exc):
                raise
            logger.warning(
                "{} failed at {} streams ({}); retrying with {}",
                operation_name.capitalize(),
                effective_streams,
                exc,
                effective_streams - 1,
            )
            effective_streams -= 1


def _is_parallelism_error(exc: Exception) -> bool:
    """Return whether the exception looks like a server-side concurrency ceiling."""

    text = str(exc).lower()
    if isinstance(exc, asyncssh.Error):
        return any(
            token in text
            for token in (
                "too many",
                "channel",
                "session",
                "administratively prohibited",
                "open failed",
                "connection",
                "sftp",
            )
        )
    if isinstance(exc, OSError):
        return any(
            token in text
            for token in (
                "too many",
                "connection",
                "session",
                "channel",
                "sftp",
            )
        )
    return False


def _split_local_file(source: Path, destination_dir: Path, *, chunk_size: int) -> list[_LocalPart]:
    """Split a local file into deterministic part files for striped upload."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    parts: list[_LocalPart] = []
    offset = 0
    index = 0
    with source.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk and parts:
                break

            part_path = destination_dir / f"part-{index:05d}"
            part_path.write_bytes(chunk)
            parts.append(
                _LocalPart(
                    index=index,
                    offset=offset,
                    size_bytes=len(chunk),
                    path=part_path,
                )
            )
            if not chunk:
                break
            offset += len(chunk)
            index += 1

    return parts


def _build_local_parts(destination_dir: Path, *, total_size: int, chunk_size: int) -> list[_LocalPart]:
    """Build deterministic local part metadata for striped download."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    if total_size == 0:
        return [
            _LocalPart(
                index=0,
                offset=0,
                size_bytes=0,
                path=destination_dir / "part-00000",
            )
        ]

    parts: list[_LocalPart] = []
    offset = 0
    index = 0
    while offset < total_size:
        size_bytes = min(chunk_size, total_size - offset)
        parts.append(
            _LocalPart(
                index=index,
                offset=offset,
                size_bytes=size_bytes,
                path=destination_dir / f"part-{index:05d}",
            )
        )
        offset += size_bytes
        index += 1

    return parts


async def _download_remote_part(
    conn: asyncssh.SSHClientConnection,
    *,
    remote_path: str,
    part: _LocalPart,
    resume: bool,
) -> None:
    """Download one byte range into its deterministic local part file."""

    part.path.parent.mkdir(parents=True, exist_ok=True)
    local_size = part.path.stat().st_size if part.path.exists() else 0
    if not resume:
        local_size = 0
    elif local_size > part.size_bytes:
        logger.warning(
            "Local part {} is larger than expected; restarting striped download part",
            part.path,
        )
        local_size = 0

    write_mode = "r+b" if local_size else "wb"
    async with conn.start_sftp_client() as sftp:
        async with sftp.open(remote_path, "rb") as remote_file:
            with part.path.open(write_mode) as local_file:
                if local_size:
                    local_file.seek(local_size)

                transferred = local_size
                while transferred < part.size_bytes:
                    chunk = await remote_file.read(
                        min(TRANSFER_CHUNK_SIZE, part.size_bytes - transferred),
                        offset=part.offset + transferred,
                    )
                    if not chunk:
                        break
                    local_file.write(chunk)
                    transferred += len(chunk)

    final_size = part.path.stat().st_size
    if final_size != part.size_bytes:
        raise IOError(
            f"Striped download part mismatch for {remote_path} part {part.index}: "
            f"expected {part.size_bytes}, got {final_size}"
        )


def _assemble_local_parts(parts: Sequence[_LocalPart], destination: Path) -> None:
    """Concatenate local part files into the final destination file."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as final_file:
        for part in parts:
            with part.path.open("rb") as part_file:
                while True:
                    chunk = part_file.read(TRANSFER_CHUNK_SIZE)
                    if not chunk:
                        break
                    final_file.write(chunk)


async def _assemble_remote_parts(
    conn: asyncssh.SSHClientConnection,
    *,
    remote_parts: Sequence[str],
    remote_target: str,
    expected_size: int,
) -> None:
    """Concatenate remote part files into the final remote payload on the host."""

    partial_target = f"{remote_target}.partial"
    part_args = " ".join(shlex.quote(path) for path in remote_parts)
    quoted_partial = shlex.quote(partial_target)
    quoted_target = shlex.quote(remote_target)
    command = " && ".join(
        [
            f"rm -f -- {quoted_partial}",
            f"cat -- {part_args} > {quoted_partial}",
            f'[ "$(wc -c < {quoted_partial})" -eq {expected_size} ]',
            f"mv -f -- {quoted_partial} {quoted_target}",
        ]
    )
    logger.debug("Assembling {} striped part(s) into {}", len(remote_parts), remote_target)
    result = await conn.run(command, check=False)
    if result.exit_status != 0:
        raise RuntimeError(
            f"Remote assembly failed for {remote_target}: {result.stderr.strip() or result.stdout.strip() or 'unknown error'}"
        )


async def _safe_remove_remote_file(sftp, path: str) -> None:
    """Delete a remote file if it exists."""

    with suppress(FileNotFoundError):
        await sftp.remove(path)


def _remote_staging_dir(remote_target: str) -> str:
    """Return the hidden deterministic staging directory for a remote payload."""

    target = PurePosixPath(remote_target)
    return str(target.parent / ".launchpad-transfer" / f"{target.name}.parts")


def _local_part_dir(destination: Path) -> Path:
    """Return the deterministic local part directory for a striped download."""

    return destination.parent / f"{destination.name}.parts"


async def _remote_size(conn: asyncssh.SSHClientConnection, remote_path: str) -> int | None:
    """Return the current remote file size when the path exists."""

    async with conn.start_sftp_client() as sftp:
        if not await sftp.exists(remote_path):
            return None
        return int((await sftp.stat(remote_path)).size or 0)


async def _require_remote_size(conn: asyncssh.SSHClientConnection, remote_path: str) -> int:
    """Return the current remote file size or raise when the path is missing."""

    size = await _remote_size(conn, remote_path)
    if size is None:
        raise FileNotFoundError(f"Remote download source does not exist: {remote_path}")
    return size


async def _remove_remote_tree(conn: asyncssh.SSHClientConnection, remote_path: str) -> None:
    """Delete a remote staging tree after a successful striped transfer."""

    command = f"rm -rf -- {shlex.quote(remote_path)}"
    result = await conn.run(command, check=False)
    if result.exit_status != 0:
        raise RuntimeError(
            f"Remote cleanup failed for {remote_path}: {result.stderr.strip() or result.stdout.strip() or 'unknown error'}"
        )
