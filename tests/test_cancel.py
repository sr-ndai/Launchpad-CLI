"""Tests for the `launchpad cancel` command."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from launchpad_cli.cli import cli
from launchpad_cli.cli import cancel as cancel_module
from launchpad_cli.core.config import LaunchpadConfig, SSHConfig


def test_cancel_command_cancels_entire_job_with_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    """The cancel command should run without prompting when `--yes` is passed."""

    monkeypatch.setattr(cancel_module, "configure_logging", lambda **kwargs: None)

    async def fake_run_cancel(**kwargs) -> cancel_module.CancelResult:  # type: ignore[no-untyped-def]
        assert kwargs["job_id"] == "12345"
        assert kwargs["task_ids"] == ()
        return cancel_module.CancelResult(job_id="12345", task_ids=(), target="12345")

    monkeypatch.setattr(cancel_module, "_run_cancel", fake_run_cancel)

    result = CliRunner().invoke(cli, ["cancel", "12345", "--yes"])

    assert result.exit_code == 0
    assert "Cancellation Requested" in result.output
    assert "Cancelled job 12345." in result.output


def test_cancel_command_prompts_and_cancels_selected_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    """The cancel command should confirm before cancelling specific array tasks."""

    monkeypatch.setattr(cancel_module, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(cancel_module.click, "confirm", lambda *args, **kwargs: True)

    async def fake_run_cancel(**kwargs) -> cancel_module.CancelResult:  # type: ignore[no-untyped-def]
        assert kwargs["job_id"] == "12345"
        assert kwargs["task_ids"] == ("2", "4")
        return cancel_module.CancelResult(job_id="12345", task_ids=("2", "4"), target="12345_2,12345_4")

    monkeypatch.setattr(cancel_module, "_run_cancel", fake_run_cancel)

    result = CliRunner().invoke(cli, ["cancel", "12345", "2", "4"])

    assert result.exit_code == 0
    assert "Cancel Preview" in result.output
    assert "Cancellation Requested" in result.output
    assert "Cancelled job 12345 task(s): 2, 4." in result.output


def test_cancel_command_resolves_manifest_task_refs_before_cancelling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-numeric task refs should resolve before the destructive action runs."""

    monkeypatch.setattr(cancel_module, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(cancel_module.click, "confirm", lambda *args, **kwargs: True)

    async def fake_resolve_cancel_task_ids(**kwargs) -> tuple[str, ...]:  # type: ignore[no-untyped-def]
        assert kwargs["task_refs"] == ("002", "wing.dat")
        return ("2", "4")

    async def fake_run_cancel(**kwargs) -> cancel_module.CancelResult:  # type: ignore[no-untyped-def]
        assert kwargs["job_id"] == "12345"
        assert kwargs["task_ids"] == ("2", "4")
        return cancel_module.CancelResult(job_id="12345", task_ids=("2", "4"), target="12345_2,12345_4")

    monkeypatch.setattr(cancel_module, "_resolve_cancel_task_ids", fake_resolve_cancel_task_ids)
    monkeypatch.setattr(cancel_module, "_run_cancel", fake_run_cancel)

    result = CliRunner().invoke(cli, ["cancel", "12345", "002", "wing.dat"])

    assert result.exit_code == 0
    assert "Cancelled job 12345 task(s): 2, 4." in result.output


def test_cancel_command_emits_json_when_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cancellation should emit a structured payload under the root JSON flag."""

    monkeypatch.setattr(cancel_module, "configure_logging", lambda **kwargs: None)

    async def fake_run_cancel(**kwargs) -> cancel_module.CancelResult:  # type: ignore[no-untyped-def]
        return cancel_module.CancelResult(job_id="12345", task_ids=("2", "4"), target="12345_2,12345_4")

    monkeypatch.setattr(cancel_module, "_run_cancel", fake_run_cancel)

    result = CliRunner().invoke(cli, ["--json", "cancel", "12345", "2", "4", "--yes"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload == {
        "job_id": "12345",
        "task_ids": ["2", "4"],
        "target": "12345_2,12345_4",
        "message": "Cancelled job 12345 task(s): 2, 4.",
    }


def test_cancel_command_aborts_when_confirmation_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """The cancel command should stop if the user declines confirmation."""

    monkeypatch.setattr(cancel_module, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(cancel_module.click, "confirm", lambda *args, **kwargs: False)

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

    result = await cancel_module._run_cancel(
        cwd=cancel_module.Path.cwd(),
        env={},
        job_id="12345",
        task_ids=("2", "4"),
    )

    assert connection.commands == ["scancel 12345_2,12345_4"]
    assert result.message == "Cancelled job 12345 task(s): 2, 4."


@pytest.mark.asyncio
async def test_resolve_cancel_task_ids_rejects_non_numeric_legacy_refs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy jobs without a manifest should reject alias-style task selectors."""

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
        pass

    connection = FakeConnection()

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_ssh_session(config: SSHConfig):  # type: ignore[no-untyped-def]
        yield connection

    async def fake_query_job_rows(*args, **kwargs) -> tuple[cancel_module.CancelJobRow, ...]:  # type: ignore[no-untyped-def]
        return (
            cancel_module.CancelJobRow(
                job_id="12345",
                task_id="0",
                remote_job_dir="/shared/sergey/tank_v3",
            ),
        )

    async def fake_load_job_manifest(*args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(cancel_module, "ssh_session", fake_ssh_session)
    monkeypatch.setattr(cancel_module, "_query_job_rows", fake_query_job_rows)
    monkeypatch.setattr(cancel_module, "load_job_manifest", fake_load_job_manifest)

    with pytest.raises(ValueError, match="Only raw numeric task IDs are supported"):
        await cancel_module._resolve_cancel_task_ids(
            cwd=cancel_module.Path.cwd(),
            env={},
            job_id="12345",
            task_refs=("wing.dat",),
        )
