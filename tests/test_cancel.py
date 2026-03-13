"""Tests for the `launchpad cancel` command."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from launchpad_cli.cli import cli
from launchpad_cli.cli import cancel as cancel_module
from launchpad_cli.core.config import LaunchpadConfig, SSHConfig


def test_cancel_command_cancels_entire_job_with_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    """The cancel command should run without prompting when `--yes` is passed."""

    monkeypatch.setattr(cancel_module, "configure_logging", lambda **kwargs: None)

    async def fake_run_cancel(**kwargs) -> str:  # type: ignore[no-untyped-def]
        assert kwargs["job_id"] == "12345"
        assert kwargs["task_ids"] == ()
        return "Cancelled job 12345."

    monkeypatch.setattr(cancel_module, "_run_cancel", fake_run_cancel)

    result = CliRunner().invoke(cli, ["cancel", "12345", "--yes"])

    assert result.exit_code == 0
    assert "Cancelled job 12345." in result.output


def test_cancel_command_prompts_and_cancels_selected_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    """The cancel command should confirm before cancelling specific array tasks."""

    monkeypatch.setattr(cancel_module, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(cancel_module.click, "confirm", lambda text, default=True: True)

    async def fake_run_cancel(**kwargs) -> str:  # type: ignore[no-untyped-def]
        assert kwargs["job_id"] == "12345"
        assert kwargs["task_ids"] == ("2", "4")
        return "Cancelled job 12345 task(s): 2, 4."

    monkeypatch.setattr(cancel_module, "_run_cancel", fake_run_cancel)

    result = CliRunner().invoke(cli, ["cancel", "12345", "2", "4"])

    assert result.exit_code == 0
    assert "Cancelled job 12345 task(s): 2, 4." in result.output


def test_cancel_command_aborts_when_confirmation_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """The cancel command should stop if the user declines confirmation."""

    monkeypatch.setattr(cancel_module, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(cancel_module.click, "confirm", lambda text, default=True: False)

    result = CliRunner().invoke(cli, ["cancel", "12345"])

    assert result.exit_code == 1
    assert "Cancellation aborted." in result.output


@pytest.mark.asyncio
async def test_run_cancel_invokes_scancel_for_selected_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remote cancel execution should build the expected `scancel` target."""

    monkeypatch.setattr(
        cancel_module,
        "resolve_config",
        lambda **kwargs: SimpleNamespace(
            config=LaunchpadConfig(
                ssh=SSHConfig(host="cluster.example.com", username="sergey")
            )
        ),
    )

    class FakeConnection:
        def __init__(self) -> None:
            self.commands: list[str] = []

        async def run(self, command: str, check: bool = False) -> SimpleNamespace:
            self.commands.append(command)
            return SimpleNamespace(exit_status=0, stdout="", stderr="")

    connection = FakeConnection()

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_ssh_session(config: SSHConfig):  # type: ignore[no-untyped-def]
        yield connection

    monkeypatch.setattr(cancel_module, "ssh_session", fake_ssh_session)

    message = await cancel_module._run_cancel(
        cwd=cancel_module.Path.cwd(),
        env={},
        job_id="12345",
        task_ids=("2", "4"),
    )

    assert connection.commands == ["scancel 12345_2,12345_4"]
    assert message == "Cancelled job 12345 task(s): 2, 4."
