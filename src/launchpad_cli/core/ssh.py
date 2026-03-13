"""Async SSH connection lifecycle helpers."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import asyncssh
from loguru import logger

from .config import SSHConfig

CONNECT_RETRIES = 3
CONNECT_RETRY_DELAY = 1.0


def _connection_options(config: SSHConfig) -> dict[str, Any]:
    """Build AsyncSSH connection kwargs from the resolved config."""

    if not config.host:
        raise ValueError("SSH host is required to open a session.")
    if not config.username:
        raise ValueError("SSH username is required to open a session.")

    options: dict[str, Any] = {
        "host": config.host,
        "port": config.port,
        "username": config.username,
    }

    if config.key_path:
        options["client_keys"] = [str(Path(config.key_path).expanduser())]
    if config.known_hosts_path:
        options["known_hosts"] = str(Path(config.known_hosts_path).expanduser())

    return options


@asynccontextmanager
async def ssh_session(config: SSHConfig) -> AsyncIterator[asyncssh.SSHClientConnection]:
    """Open an SSH connection to the configured cluster head node."""

    options = _connection_options(config)
    last_error: Exception | None = None

    for attempt in range(1, CONNECT_RETRIES + 1):
        try:
            logger.debug(
                "Opening SSH session to {}@{}:{} (attempt {}/{})",
                options["username"],
                options["host"],
                options["port"],
                attempt,
                CONNECT_RETRIES,
            )
            connection = await asyncssh.connect(**options)
            break
        except (OSError, asyncssh.Error) as exc:
            last_error = exc
            logger.warning(
                "SSH connection attempt {}/{} failed: {}",
                attempt,
                CONNECT_RETRIES,
                exc,
            )
            if attempt == CONNECT_RETRIES:
                raise
            await asyncio.sleep(CONNECT_RETRY_DELAY)
    else:
        raise RuntimeError("SSH connection retries exhausted unexpectedly.") from last_error

    try:
        yield connection
    finally:
        logger.debug("Closing SSH session to {}@{}", options["username"], options["host"])
        connection.close()
        await connection.wait_closed()
