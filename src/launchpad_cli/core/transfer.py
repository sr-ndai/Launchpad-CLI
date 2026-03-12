"""SFTP transfer contracts for future upload and download workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import asyncssh


async def upload(
    conn: asyncssh.SSHClientConnection,
    local_path: Path,
    remote_path: str,
    *,
    resume: bool = True,
    progress_callback: Callable[[int], None] | None = None,
) -> None:
    """Upload a file via SFTP.

    The implementation is intentionally deferred to a later task.
    """

    raise NotImplementedError("Upload support is not implemented yet.")


async def download(
    conn: asyncssh.SSHClientConnection,
    remote_path: str,
    local_path: Path,
    *,
    resume: bool = True,
    progress_callback: Callable[[int], None] | None = None,
) -> None:
    """Download a file via SFTP.

    The implementation is intentionally deferred to a later task.
    """

    raise NotImplementedError("Download support is not implemented yet.")

