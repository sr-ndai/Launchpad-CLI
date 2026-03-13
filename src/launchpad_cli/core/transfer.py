"""Single-stream SFTP upload and download helpers."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Callable

import asyncssh
from loguru import logger

TRANSFER_CHUNK_SIZE = 1024 * 1024
ProgressCallback = Callable[[int], None]


def _emit_progress(progress_callback: ProgressCallback | None, transferred: int) -> None:
    if progress_callback is not None:
        progress_callback(transferred)


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
