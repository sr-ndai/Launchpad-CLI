"""Tests for SSH connection lifecycle helpers."""

from __future__ import annotations

from pathlib import Path

import asyncssh
import click
import pytest

from launchpad_cli.core.config import SSHConfig
from launchpad_cli.cli import ssh_cmd as ssh_cmd_module
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


@pytest.mark.asyncio
async def test_open_interactive_shell_uses_local_windows_ssh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows interactive SSH should shell out through the local OpenSSH client."""

    recorded: dict[str, object] = {}

    monkeypatch.setattr(ssh_cmd_module.sys, "platform", "win32")
    monkeypatch.setattr(
        ssh_cmd_module.sys,
        "stdin",
        type("FakeIn", (), {"isatty": staticmethod(lambda: True)})(),
    )
    monkeypatch.setattr(
        ssh_cmd_module.sys,
        "stdout",
        type("FakeOut", (), {"isatty": staticmethod(lambda: True)})(),
    )
    monkeypatch.setattr(ssh_cmd_module.shutil, "which", lambda name: "C:/Windows/System32/OpenSSH/ssh.exe")

    def fake_run_local_ssh_subprocess(command: list[str]) -> int:
        recorded["command"] = command
        return 0

    monkeypatch.setattr(
        ssh_cmd_module,
        "_run_local_ssh_subprocess",
        fake_run_local_ssh_subprocess,
    )

    exit_code = await ssh_cmd_module._open_interactive_shell(
        SSHConfig(
            host="cluster.example.com",
            port=2222,
            username="sergey",
            key_path="~/.ssh/id_ed25519",
            known_hosts_path="~/.ssh/known_hosts",
        )
    )

    assert exit_code == 0
    assert recorded["command"] == [
        "C:/Windows/System32/OpenSSH/ssh.exe",
        "-p",
        "2222",
        "-i",
        str(Path("~/.ssh/id_ed25519").expanduser()),
        "-o",
        f"UserKnownHostsFile={Path('~/.ssh/known_hosts').expanduser()}",
        "sergey@cluster.example.com",
    ]


@pytest.mark.asyncio
async def test_open_interactive_shell_fails_when_windows_ssh_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows interactive SSH should fail clearly when the local client is absent."""

    monkeypatch.setattr(ssh_cmd_module.sys, "platform", "win32")
    monkeypatch.setattr(
        ssh_cmd_module.sys,
        "stdin",
        type("FakeIn", (), {"isatty": staticmethod(lambda: True)})(),
    )
    monkeypatch.setattr(
        ssh_cmd_module.sys,
        "stdout",
        type("FakeOut", (), {"isatty": staticmethod(lambda: True)})(),
    )
    monkeypatch.setattr(ssh_cmd_module.shutil, "which", lambda name: None)

    with pytest.raises(click.ClickException, match="Local OpenSSH client not found"):
        await ssh_cmd_module._open_interactive_shell(
            SSHConfig(host="cluster.example.com", username="sergey")
        )
