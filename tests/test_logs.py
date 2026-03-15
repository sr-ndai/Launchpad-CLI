"""Tests for the `launchpad logs` command and log-resolution helpers."""

from __future__ import annotations

from contextlib import asynccontextmanager
import json
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from launchpad_cli.cli import cli
from launchpad_cli.cli import logs as logs_module
from launchpad_cli.core.config import LaunchpadConfig, SSHConfig
from launchpad_cli.core.job_manifest import JobManifest, TaskReference


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
    assert "Job 12345" in result.output
    assert "Task 2" in result.output
    assert "SLURM log" in result.output
    assert "solver line 1" in result.output
    assert "/shared/sergey/tank_v3/logs/slurm_12345_2.out" in result.output


def test_logs_command_resolves_solver_log_with_follow(monkeypatch: pytest.MonkeyPatch) -> None:
    """The logs command should derive the solver log path from the task work directory."""

    emitted: list[str] = []

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
        logs_module.click.echo("F06\n", nl=False)
        return "F06\n"

    monkeypatch.setattr(logs_module, "ssh_session", fake_ssh_session)
    monkeypatch.setattr(logs_module, "_query_job_rows", fake_query_job_rows)
    monkeypatch.setattr(logs_module, "_read_remote_log", fake_read_remote_log)
    monkeypatch.setattr(logs_module.click, "echo", lambda text, nl=False: emitted.append(text))

    result = CliRunner().invoke(cli, ["logs", "12345", "2", "--solver-log", "--follow", "--lines", "100"])

    assert result.exit_code == 0
    assert "Job 12345" in result.output
    assert "solver log" in result.output
    assert "/shared/sergey/nastran-20260312-2148-abcd/results_wing_2/wing.f06" in result.output
    assert emitted == ["F06\n"]


def test_logs_command_resolves_manifest_task_alias_and_log_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Manifest-backed logs should resolve aliases and non-primary solver log kinds."""

    manifest = JobManifest(
        version=1,
        solver="nastran",
        logs={"solver": ".f06", "telemetry": ".f04"},
        tasks=(
            TaskReference(
                task_id="2",
                alias="003",
                input_relative_path="inputs/wing.dat",
                input_filename="wing.dat",
                input_stem="wing",
                display_label="wing",
                result_dir="results_wing_2",
            ),
        ),
    )

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
                remote_job_dir="/shared/sergey/nastran-20260312-2148-abcd",
            ),
        )

    async def fake_load_job_manifest(*args, **kwargs) -> JobManifest:  # type: ignore[no-untyped-def]
        return manifest

    async def fake_read_remote_log(conn, *, remote_path: str, lines: int, follow: bool) -> str:  # type: ignore[no-untyped-def]
        assert remote_path == "/shared/sergey/nastran-20260312-2148-abcd/results_wing_2/wing.f04"
        assert lines == 50
        assert follow is False
        return "telemetry\n"

    monkeypatch.setattr(logs_module, "ssh_session", fake_ssh_session)
    monkeypatch.setattr(logs_module, "_query_job_rows", fake_query_job_rows)
    monkeypatch.setattr(logs_module, "load_job_manifest", fake_load_job_manifest)
    monkeypatch.setattr(logs_module, "_read_remote_log", fake_read_remote_log)

    result = CliRunner().invoke(cli, ["logs", "12345", "003", "--log-kind", "telemetry"])

    assert result.exit_code == 0
    assert "telemetry log" in result.output
    assert "wing.f04" in result.output


def test_logs_command_rejects_ambiguous_manifest_task_selector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Filename or stem selectors should fail clearly when they match multiple tasks."""

    manifest = JobManifest(
        version=1,
        solver="nastran",
        logs={"solver": ".f06"},
        tasks=(
            TaskReference(
                task_id="0",
                alias="001",
                input_relative_path="set-a/wing.dat",
                input_filename="wing.dat",
                input_stem="wing",
                display_label="set-a/wing",
                result_dir="results_wing_0",
            ),
            TaskReference(
                task_id="1",
                alias="002",
                input_relative_path="set-b/wing.dat",
                input_filename="wing.dat",
                input_stem="wing",
                display_label="set-b/wing",
                result_dir="results_wing_1",
            ),
        ),
    )

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
            logs_module.JobLogRow(job_id="12345", task_id="0", run_name="job", state="COMPLETED"),
            logs_module.JobLogRow(job_id="12345", task_id="1", run_name="job", state="COMPLETED"),
        )

    async def fake_load_job_manifest(*args, **kwargs) -> JobManifest:  # type: ignore[no-untyped-def]
        return manifest

    monkeypatch.setattr(logs_module, "ssh_session", fake_ssh_session)
    monkeypatch.setattr(logs_module, "_query_job_rows", fake_query_job_rows)
    monkeypatch.setattr(logs_module, "load_job_manifest", fake_load_job_manifest)

    result = CliRunner().invoke(cli, ["logs", "12345", "wing.dat"])

    assert result.exit_code == 1
    assert "ambiguous" in result.output
    assert "relative path" in result.output


def test_logs_command_uses_interactive_picker_for_human_multitask_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TTY human flows should open the picker instead of failing on multi-task ambiguity."""

    picker_calls: list[tuple[str, str]] = []

    monkeypatch.setattr(logs_module, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(logs_module, "_supports_interactive_picker", lambda: True)
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
                task_id="0",
                run_name="tank_v3",
                state="RUNNING",
                stdout_path="/shared/sergey/tank_v3/logs/slurm_%A_%a.out",
                work_dir="/shared/sergey/tank_v3/results_root_0",
            ),
            logs_module.JobLogRow(
                job_id="12345",
                task_id="1",
                run_name="tank_v3",
                state="RUNNING",
                stdout_path="/shared/sergey/tank_v3/logs/slurm_%A_%a.out",
                work_dir="/shared/sergey/tank_v3/results_wing_1",
            ),
        )

    def fake_pick_task_interactively(**kwargs) -> logs_module.LogSelection:  # type: ignore[no-untyped-def]
        picker_calls.append((kwargs["job_id"], kwargs["log_kind"]))
        return logs_module.LogSelection(row=kwargs["task_rows"][1], task_ref=None)

    async def fake_read_remote_log(conn, *, remote_path: str, lines: int, follow: bool) -> str:  # type: ignore[no-untyped-def]
        assert remote_path == "/shared/sergey/tank_v3/logs/slurm_12345_1.out"
        return "picked\n"

    monkeypatch.setattr(logs_module, "ssh_session", fake_ssh_session)
    monkeypatch.setattr(logs_module, "_query_job_rows", fake_query_job_rows)
    monkeypatch.setattr(logs_module, "_pick_task_interactively", fake_pick_task_interactively)
    monkeypatch.setattr(logs_module, "_read_remote_log", fake_read_remote_log)

    result = CliRunner().invoke(cli, ["logs", "12345"])

    assert result.exit_code == 0
    assert picker_calls == [("12345", "stdout")]
    assert "picked" in result.output


def test_build_log_picker_options_include_manifest_metadata() -> None:
    """Picker rows should surface the final task-reference and log metadata."""

    manifest = JobManifest(
        version=1,
        solver="nastran",
        logs={"solver": ".f06", "telemetry": ".f04"},
        tasks=(
            TaskReference(
                task_id="0",
                alias="001",
                input_relative_path="inputs/root.dat",
                input_filename="root.dat",
                input_stem="root",
                display_label="root",
                result_dir="results_root_0",
            ),
        ),
    )
    rows = (
        logs_module.JobLogRow(
            job_id="12345",
            task_id="0",
            run_name="tank_v3",
            state="COMPLETED",
            remote_job_dir="/shared/sergey/tank_v3",
        ),
    )

    options = logs_module._build_log_picker_options(
        rows,
        manifest=manifest,
        remote_job_dir="/shared/sergey/tank_v3",
        log_kind="telemetry",
        err=False,
    )

    assert options == (
        logs_module.LogPickerOption(
            row=rows[0],
            task_ref=manifest.tasks[0],
            label="root",
            alias="001",
            state="COMPLETED",
            log_kind="telemetry",
            filename="root.f04",
        ),
    )


def test_logs_command_renders_empty_state_for_blank_log_content(monkeypatch: pytest.MonkeyPatch) -> None:
    """Blank log content should use the restrained empty-state warning instead of silent output."""

    monkeypatch.setattr(logs_module, "configure_logging", lambda **kwargs: None)

    async def fake_run_logs(**kwargs) -> logs_module.LogsResult:  # type: ignore[no-untyped-def]
        return logs_module.LogsResult(
            job_id="12345",
            task_id="2",
            run_name="tank_v3",
            state="RUNNING",
            log_kind="stdout",
            remote_path="/shared/sergey/tank_v3/logs/slurm_12345_2.out",
            lines=50,
            content="",
        )

    monkeypatch.setattr(logs_module, "_run_logs", fake_run_logs)

    result = CliRunner().invoke(cli, ["logs", "12345", "2"])

    assert result.exit_code == 0
    assert "No log output yet." in result.output
    assert "slurm_12345_2.out" in result.output


def test_logs_command_emits_json_when_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    """Buffered log reads should emit structured JSON under the root flag."""

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
                state="COMPLETED",
                stdout_path="/shared/sergey/tank_v3/logs/slurm_%A_%a.out",
            ),
        )

    async def fake_read_remote_log(conn, *, remote_path: str, lines: int, follow: bool) -> str:  # type: ignore[no-untyped-def]
        return "line 1\nline 2\n"

    monkeypatch.setattr(logs_module, "ssh_session", fake_ssh_session)
    monkeypatch.setattr(logs_module, "_query_job_rows", fake_query_job_rows)
    monkeypatch.setattr(logs_module, "_read_remote_log", fake_read_remote_log)

    result = CliRunner().invoke(cli, ["--json", "logs", "12345", "2"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["job_id"] == "12345"
    assert payload["task_id"] == "2"
    assert payload["log_kind"] == "stdout"
    assert payload["remote_path"] == "/shared/sergey/tank_v3/logs/slurm_12345_2.out"
    assert payload["content"] == "line 1\nline 2\n"


def test_logs_command_rejects_follow_with_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Streaming follow mode should not claim to support structured JSON."""

    monkeypatch.setattr(logs_module, "configure_logging", lambda **kwargs: None)

    result = CliRunner().invoke(cli, ["--json", "logs", "12345", "--follow"])

    assert result.exit_code == 1
    assert "does not support `--json` output" in result.output


def test_logs_command_rejects_multiple_log_source_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    """The log-source switches should remain mutually exclusive."""

    monkeypatch.setattr(logs_module, "configure_logging", lambda **kwargs: None)

    result = CliRunner().invoke(
        cli,
        ["logs", "12345", "2", "--solver-log", "--log-kind", "telemetry"],
    )

    assert result.exit_code == 1
    assert "only one of" in result.output


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
    assert "Specify a TASK_REF explicitly" in result.output


def test_logs_command_rejects_non_primary_log_kind_for_legacy_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy jobs without a manifest should only support the primary solver log."""

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

    async def fake_load_job_manifest(*args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(logs_module, "ssh_session", fake_ssh_session)
    monkeypatch.setattr(logs_module, "_query_job_rows", fake_query_job_rows)
    monkeypatch.setattr(logs_module, "load_job_manifest", fake_load_job_manifest)

    result = CliRunner().invoke(cli, ["logs", "12345", "2", "--log-kind", "telemetry"])

    assert result.exit_code == 1
    assert "unavailable for legacy jobs" in result.output


def test_build_tail_command_includes_follow_flag() -> None:
    """Tail follow mode should retry by file name for shortly delayed log creation."""

    command = logs_module._build_tail_command(
        remote_path="/shared/sergey/tank_v3/logs/slurm_12345_2.out",
        lines=25,
        follow=True,
    )

    assert (
        command
        == "tail -n 25 --follow=name --retry /shared/sergey/tank_v3/logs/slurm_12345_2.out"
    )


@pytest.mark.asyncio
async def test_read_remote_log_streams_follow_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """Follow mode should stream from a remote process instead of using buffered run()."""

    emitted: list[str] = []

    class FakeStream:
        def __init__(self, chunks: list[str]) -> None:
            self._chunks = chunks

        def __aiter__(self):
            async def iterator():
                for chunk in self._chunks:
                    yield chunk

            return iterator()

        async def read(self) -> str:
            return ""

    class FakeProcess:
        def __init__(self) -> None:
            self.stdout = FakeStream(["line 1\n", "line 2\n"])
            self.stderr = FakeStream([])
            self.exit_status = 0

        def close(self) -> None:
            return None

        async def wait_closed(self) -> None:
            return None

    class FakeConnection:
        def __init__(self) -> None:
            self.create_process_calls: list[str] = []
            self.run_calls: list[str] = []

        async def create_process(self, command: str) -> FakeProcess:
            self.create_process_calls.append(command)
            return FakeProcess()

        async def run(self, command: str, check: bool = False) -> SimpleNamespace:
            self.run_calls.append(command)
            raise AssertionError("follow mode must not use conn.run()")

    monkeypatch.setattr(logs_module.click, "echo", lambda text, nl=False: emitted.append(text))
    connection = FakeConnection()

    output = await logs_module._read_remote_log(
        connection,
        remote_path="/shared/sergey/tank_v3/logs/slurm_12345_2.out",
        lines=25,
        follow=True,
    )

    assert connection.create_process_calls == [
        "tail -n 25 --follow=name --retry /shared/sergey/tank_v3/logs/slurm_12345_2.out"
    ]
    assert connection.run_calls == []
    assert emitted == ["line 1\n", "line 2\n"]
    assert output == "line 1\nline 2\n"
