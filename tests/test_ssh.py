"""Tests for SSH connection lifecycle helpers."""

from __future__ import annotations

from pathlib import Path

import asyncssh
import pytest

from launchpad_cli.core.config import SSHConfig
from launchpad_cli.core import ssh as ssh_module


class FakeConnection:
    """Minimal AsyncSSH connection test double."""

    def __init__(self) -> None:
        self.closed = False
        self.wait_closed_calls = 0

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        self.wait_closed_calls += 1


@pytest.mark.asyncio
async def test_ssh_session_retries_and_closes_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    """Transient connection failures should retry and still close cleanly."""

    attempts: list[dict[str, object]] = []
    connection = FakeConnection()

    async def fake_connect(**kwargs: object) -> FakeConnection:
        attempts.append(kwargs)
        if len(attempts) == 1:
            raise asyncssh.Error(1, "temporary failure")
        return connection

    async def fake_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(ssh_module, "CONNECT_RETRIES", 2)
    monkeypatch.setattr(ssh_module, "CONNECT_RETRY_DELAY", 0.0)
    monkeypatch.setattr(ssh_module.asyncssh, "connect", fake_connect)
    monkeypatch.setattr(ssh_module.asyncio, "sleep", fake_sleep)

    config = SSHConfig(
        host="cluster.example.com",
        username="sergey",
        key_path="~/.ssh/id_ed25519",
        known_hosts_path="~/.ssh/known_hosts",
    )

    async with ssh_module.ssh_session(config) as active_connection:
        assert active_connection is connection

    assert len(attempts) == 2
    assert attempts[-1]["host"] == "cluster.example.com"
    assert attempts[-1]["username"] == "sergey"
    assert attempts[-1]["client_keys"] == [str(Path("~/.ssh/id_ed25519").expanduser())]
    assert attempts[-1]["known_hosts"] == str(Path("~/.ssh/known_hosts").expanduser())
    assert connection.closed is True
    assert connection.wait_closed_calls == 1


@pytest.mark.asyncio
async def test_ssh_session_requires_host_and_username() -> None:
    """Missing required SSH fields should fail before connecting."""

    with pytest.raises(ValueError):
        async with ssh_module.ssh_session(SSHConfig(username="sergey")):
            pass

    with pytest.raises(ValueError):
        async with ssh_module.ssh_session(SSHConfig(host="cluster.example.com")):
            pass
