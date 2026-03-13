"""Tests for the `launchpad logs` command and log-resolution helpers."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from launchpad_cli.cli import cli
from launchpad_cli.cli import logs as logs_module
from launchpad_cli.core.config import LaunchpadConfig, SSHConfig


def test_logs_command_reads_slurm_stdout_for_specific_task(monkeypatch: pytest.MonkeyPatch) -> None:
    """The logs command should resolve and print the selected SLURM stdout log."""

    monkeypatch.setattr(logs_module, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(
        logs_module,
        "resolve_config",
        lambda **kwargs: SimpleNamespace(
            config=LaunchpadConfig(
                ssh=SSHConfig(host="cluster.example.com", username="sergey")
            )
        ),
    )

    @asynccontextmanager
    async def fake_ssh_session(config: SSHConfig):  # type: ignore[no-untyped-def]
        yield object()

    async def fake_query_job_rows(*args, **kwargs) -> tuple[logs_module.JobLogRow, ...]:  # type: ignore[no-untyped-def]
        return (
            logs_module.JobLogRow(
                job_id="12345",
                task_id="2",
                run_name="tank_v3",
                state="RUNNING",
                stdout_path="/shared/sergey/tank_v3/logs/slurm_%A_%a.out",
                stderr_path="/shared/sergey/tank_v3/logs/slurm_%A_%a.err",
                work_dir="/shared/sergey/tank_v3/results_wing_2",
            ),
        )

    async def fake_read_remote_log(conn, *, remote_path: str, lines: int, follow: bool) -> str:  # type: ignore[no-untyped-def]
        assert remote_path == "/shared/sergey/tank_v3/logs/slurm_12345_2.out"
        assert lines == 50
        assert follow is False
        return "solver line 1\nsolver line 2\n"

    monkeypatch.setattr(logs_module, "ssh_session", fake_ssh_session)
    monkeypatch.setattr(logs_module, "_query_job_rows", fake_query_job_rows)
    monkeypatch.setattr(logs_module, "_read_remote_log", fake_read_remote_log)

    result = CliRunner().invoke(cli, ["logs", "12345", "2"])

    assert result.exit_code == 0
    assert "solver line 1" in result.output


def test_logs_command_resolves_solver_log_with_follow(monkeypatch: pytest.MonkeyPatch) -> None:
    """The logs command should derive the solver log path from the task work directory."""

    monkeypatch.setattr(logs_module, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(
        logs_module,
        "resolve_config",
        lambda **kwargs: SimpleNamespace(
            config=LaunchpadConfig(
                ssh=SSHConfig(host="cluster.example.com", username="sergey")
            )
        ),
    )

    @asynccontextmanager
    async def fake_ssh_session(config: SSHConfig):  # type: ignore[no-untyped-def]
        yield object()

    async def fake_query_job_rows(*args, **kwargs) -> tuple[logs_module.JobLogRow, ...]:  # type: ignore[no-untyped-def]
        return (
            logs_module.JobLogRow(
                job_id="12345",
                task_id="2",
                run_name="nastran-20260312-2148-abcd",
                state="COMPLETED",
                work_dir="/shared/sergey/nastran-20260312-2148-abcd/results_wing_2",
            ),
        )

    async def fake_read_remote_log(conn, *, remote_path: str, lines: int, follow: bool) -> str:  # type: ignore[no-untyped-def]
        assert remote_path == "/shared/sergey/nastran-20260312-2148-abcd/results_wing_2/wing.f06"
        assert lines == 100
        assert follow is True
        return "F06\n"

    monkeypatch.setattr(logs_module, "ssh_session", fake_ssh_session)
    monkeypatch.setattr(logs_module, "_query_job_rows", fake_query_job_rows)
    monkeypatch.setattr(logs_module, "_read_remote_log", fake_read_remote_log)

    result = CliRunner().invoke(cli, ["logs", "12345", "2", "--solver-log", "--follow", "--lines", "100"])

    assert result.exit_code == 0
    assert "F06" in result.output


def test_logs_command_requires_task_id_when_multiple_rows_exist(monkeypatch: pytest.MonkeyPatch) -> None:
    """The logs command should fail clearly when a multi-task job is ambiguous."""

    monkeypatch.setattr(logs_module, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(
        logs_module,
        "resolve_config",
        lambda **kwargs: SimpleNamespace(
            config=LaunchpadConfig(
                ssh=SSHConfig(host="cluster.example.com", username="sergey")
            )
        ),
    )

    @asynccontextmanager
    async def fake_ssh_session(config: SSHConfig):  # type: ignore[no-untyped-def]
        yield object()

    async def fake_query_job_rows(*args, **kwargs) -> tuple[logs_module.JobLogRow, ...]:  # type: ignore[no-untyped-def]
        return (
            logs_module.JobLogRow(job_id="12345", task_id="0", run_name="tank_v3", state="RUNNING"),
            logs_module.JobLogRow(job_id="12345", task_id="1", run_name="tank_v3", state="RUNNING"),
        )

    monkeypatch.setattr(logs_module, "ssh_session", fake_ssh_session)
    monkeypatch.setattr(logs_module, "_query_job_rows", fake_query_job_rows)

    result = CliRunner().invoke(cli, ["logs", "12345"])

    assert result.exit_code == 1
    assert "Specify a TASK_ID explicitly" in result.output


def test_build_tail_command_includes_follow_flag() -> None:
    """Tail command construction should be deterministic for follow mode."""

    command = logs_module._build_tail_command(
        remote_path="/shared/sergey/tank_v3/logs/slurm_12345_2.out",
        lines=25,
        follow=True,
    )

    assert command == "tail -n 25 -f /shared/sergey/tank_v3/logs/slurm_12345_2.out"
