"""SSH connection contracts for future async transport work."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator, cast

import asyncssh

from .config import SSHConfig


@asynccontextmanager
async def ssh_session(config: SSHConfig) -> AsyncIterator[asyncssh.SSHClientConnection]:
    """Open an SSH session using the supplied config.

    The real connection logic is deferred to a later task.
    """

    if False:
        yield cast(asyncssh.SSHClientConnection, config)
    raise NotImplementedError(
        "SSH connectivity is not implemented in the scaffolding task."
    )
