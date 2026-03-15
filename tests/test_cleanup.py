"""Tests for the `launchpad cleanup` command."""

from __future__ import annotations

from contextlib import asynccontextmanager
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from launchpad_cli.cli import cli
from launchpad_cli.cli import cleanup as cleanup_module
from launchpad_cli.core.config import LaunchpadConfig, ResolvedConfig, SSHConfig
from launchpad_cli.core.remote_ops import RemotePathEntry


def test_cleanup_command_deletes_explicit_job_ids_with_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit job cleanup should skip prompts when `--yes` is passed."""

    monkeypatch.setattr(cleanup_module, "configure_logging", lambda **kwargs: None)

    async def fake_run_cleanup(**kwargs) -> cleanup_module.CleanupResult:  # type: ignore[no-untyped-def]
        assert kwargs["job_ids"] == ("12345", "23456")
        assert kwargs["older_than"] is None
        assert kwargs["yes"] is True
        assert kwargs["json_output"] is False
        return cleanup_module.CleanupResult(
            requested_job_ids=("12345", "23456"),
            older_than=None,
            selected_targets=(
                cleanup_module.CleanupTarget(
                    label="12345",
                    path="/shared/sergey/tank_v3",
                    size_bytes=0,
                    modified_epoch=None,
                    source="job-id",
                ),
                cleanup_module.CleanupTarget(
                    label="23456",
                    path="/shared/sergey/beam_v7",
                    size_bytes=0,
                    modified_epoch=None,
                    source="job-id",
                ),
            ),
            deleted_paths=("/shared/sergey/tank_v3", "/shared/sergey/beam_v7"),
        )

    monkeypatch.setattr(cleanup_module, "_run_cleanup", fake_run_cleanup)

    result = CliRunner().invoke(cli, ["cleanup", "12345", "23456", "--yes"])

    assert result.exit_code == 0
    assert "Deleted 2 remote directories." in result.output
    assert "12345, 23456" in result.output


def test_cleanup_command_emits_json_when_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cleanup should emit a structured response for scripting."""

    monkeypatch.setattr(cleanup_module, "configure_logging", lambda **kwargs: None)

    async def fake_run_cleanup(**kwargs) -> cleanup_module.CleanupResult:  # type: ignore[no-untyped-def]
        assert kwargs["json_output"] is True
        return cleanup_module.CleanupResult(
            requested_job_ids=("12345",),
            older_than=None,
            selected_targets=(
                cleanup_module.CleanupTarget(
                    label="12345",
                    path="/shared/sergey/tank_v3",
                    size_bytes=4096,
                    modified_epoch=1710451200.0,
                    source="job-id",
                ),
            ),
            deleted_paths=("/shared/sergey/tank_v3",),
        )

    monkeypatch.setattr(cleanup_module, "_run_cleanup", fake_run_cleanup)

    result = CliRunner().invoke(cli, ["--json", "cleanup", "12345", "--yes"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["requested_job_ids"] == ["12345"]
    assert payload["deleted_paths"] == ["/shared/sergey/tank_v3"]
    assert payload["deleted_count"] == 1


def test_cleanup_command_renders_empty_state_when_nothing_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Human-readable cleanup should not silently exit when no directories match."""

    monkeypatch.setattr(cleanup_module, "configure_logging", lambda **kwargs: None)

    async def fake_run_cleanup(**kwargs) -> cleanup_module.CleanupResult:  # type: ignore[no-untyped-def]
        return cleanup_module.CleanupResult(
            requested_job_ids=(),
            older_than="30d",
            selected_targets=(),
            deleted_paths=(),
        )

    monkeypatch.setattr(cleanup_module, "_run_cleanup", fake_run_cleanup)

    result = CliRunner().invoke(cli, ["cleanup", "--older-than", "30d", "--yes"])

    assert result.exit_code == 0
    assert "No matching remote job directories found." in result.output


@pytest.mark.asyncio
async def test_run_cleanup_deletes_terminal_job_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Cleanup should resolve job IDs to remote directories and delete them when terminal."""

    resolved = ResolvedConfig(
        config=LaunchpadConfig(
            ssh=SSHConfig(host="cluster.example.com", username="sergey"),
        ),
        layers=(),
    )
    connection = object()
    deleted: list[str] = []

    monkeypatch.setattr(cleanup_module, "resolve_config", lambda **kwargs: resolved)

    @asynccontextmanager
    async def fake_ssh_session(_config: SSHConfig):  # type: ignore[no-untyped-def]
        yield connection

    async def fake_query_job_rows(*args, **kwargs) -> tuple[cleanup_module.CleanupJobRow, ...]:  # type: ignore[no-untyped-def]
        return (
            cleanup_module.CleanupJobRow(
                job_id="12345",
                task_id="0",
                state="COMPLETED",
                remote_job_dir="/shared/sergey/tank_v3",
            ),
        )

    async def fake_load_cleanup_target(conn, remote_path: str, *, label: str, source: str):  # type: ignore[no-untyped-def]
        return cleanup_module.CleanupTarget(
            label=label,
            path=remote_path,
            size_bytes=4096,
            modified_epoch=1710451200.0,
            source=source,
        )

    async def fake_delete_remote_path(conn, path: str, **kwargs) -> str:  # type: ignore[no-untyped-def]
        deleted.append(path)
        return path

    monkeypatch.setattr(cleanup_module, "ssh_session", fake_ssh_session)
    monkeypatch.setattr(cleanup_module, "_query_job_rows", fake_query_job_rows)
    monkeypatch.setattr(cleanup_module, "_load_cleanup_target", fake_load_cleanup_target)
    monkeypatch.setattr(cleanup_module, "delete_remote_path", fake_delete_remote_path)

    result = await cleanup_module._run_cleanup(
        cwd=tmp_path,
        env={},
        console=cleanup_module.build_console(no_color=True),
        job_ids=("12345",),
        older_than=None,
        yes=True,
        json_output=False,
    )

    assert deleted == ["/shared/sergey/tank_v3"]
    assert result.message == "Deleted 1 remote directory: /shared/sergey/tank_v3"


@pytest.mark.asyncio
async def test_run_cleanup_discovers_root_directories_with_age_filter_and_prompt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Cleanup without job IDs should filter root directories and prompt for a numbered selection."""

    resolved = ResolvedConfig(
        config=LaunchpadConfig(
            ssh=SSHConfig(host="cluster.example.com", username="sergey"),
        ),
        layers=(),
    )
    deleted: list[str] = []

    monkeypatch.setattr(cleanup_module, "resolve_config", lambda **kwargs: resolved)
    monkeypatch.setattr(cleanup_module.time, "time", lambda: 1_800_000_000.0)
    monkeypatch.setattr(cleanup_module.click, "prompt", lambda *args, **kwargs: "1")
    monkeypatch.setattr(cleanup_module.click, "confirm", lambda *args, **kwargs: True)

    @asynccontextmanager
    async def fake_ssh_session(_config: SSHConfig):  # type: ignore[no-untyped-def]
        yield object()

    async def fake_list_remote_directory(conn, path: str, *, recursive: bool, **kwargs):  # type: ignore[no-untyped-def]
        return (
            RemotePathEntry(
                path="/shared/sergey/old_run",
                size_bytes=0,
                entry_type="directory",
                modified_epoch=1_790_000_000.0,
            ),
            RemotePathEntry(
                path="/shared/sergey/new_run",
                size_bytes=0,
                entry_type="directory",
                modified_epoch=1_799_999_900.0,
            ),
        )

    async def fake_measure_remote_path(conn, path: str, **kwargs) -> int:  # type: ignore[no-untyped-def]
        return 1024

    async def fake_delete_remote_path(conn, path: str, **kwargs) -> str:  # type: ignore[no-untyped-def]
        deleted.append(path)
        return path

    monkeypatch.setattr(cleanup_module, "ssh_session", fake_ssh_session)
    monkeypatch.setattr(cleanup_module, "list_remote_directory", fake_list_remote_directory)
    monkeypatch.setattr(cleanup_module, "measure_remote_path", fake_measure_remote_path)
    monkeypatch.setattr(cleanup_module, "delete_remote_path", fake_delete_remote_path)

    result = await cleanup_module._run_cleanup(
        cwd=tmp_path,
        env={},
        console=cleanup_module.build_console(no_color=True),
        job_ids=(),
        older_than="30d",
        yes=False,
        json_output=False,
    )

    assert deleted == ["/shared/sergey/old_run"]
    assert result.message == "Deleted 1 remote directory: /shared/sergey/old_run"


@pytest.mark.asyncio
async def test_run_cleanup_rejects_non_terminal_jobs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Cleanup should refuse job-ID deletion when the job is still active."""

    resolved = ResolvedConfig(
        config=LaunchpadConfig(
            ssh=SSHConfig(host="cluster.example.com", username="sergey"),
        ),
        layers=(),
    )

    monkeypatch.setattr(cleanup_module, "resolve_config", lambda **kwargs: resolved)

    @asynccontextmanager
    async def fake_ssh_session(_config: SSHConfig):  # type: ignore[no-untyped-def]
        yield object()

    async def fake_query_job_rows(*args, **kwargs) -> tuple[cleanup_module.CleanupJobRow, ...]:  # type: ignore[no-untyped-def]
        return (
            cleanup_module.CleanupJobRow(
                job_id="12345",
                task_id="0",
                state="RUNNING",
                remote_job_dir="/shared/sergey/tank_v3",
            ),
        )

    monkeypatch.setattr(cleanup_module, "ssh_session", fake_ssh_session)
    monkeypatch.setattr(cleanup_module, "_query_job_rows", fake_query_job_rows)

    with pytest.raises(cleanup_module.click.ClickException, match="terminal jobs"):
        await cleanup_module._run_cleanup(
            cwd=tmp_path,
            env={},
            console=cleanup_module.build_console(no_color=True),
            job_ids=("12345",),
            older_than=None,
            yes=True,
            json_output=False,
        )


@pytest.mark.asyncio
async def test_run_cleanup_discovers_configured_workspace_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Cleanup discovery should scan the configured workspace root when present."""

    resolved = ResolvedConfig(
        config=LaunchpadConfig(
            cluster={"workspace_root": "/shared/launchpad"},
            ssh=SSHConfig(host="cluster.example.com", username="sergey"),
        ),
        layers=(),
    )
    recorded: dict[str, object] = {}

    monkeypatch.setattr(cleanup_module, "resolve_config", lambda **kwargs: resolved)
    monkeypatch.setattr(cleanup_module.click, "prompt", lambda *args, **kwargs: "none")

    @asynccontextmanager
    async def fake_ssh_session(_config: SSHConfig):  # type: ignore[no-untyped-def]
        yield object()

    async def fake_list_remote_directory(conn, path: str, *, recursive: bool, **kwargs):  # type: ignore[no-untyped-def]
        recorded["path"] = path
        recorded["recursive"] = recursive
        return ()

    monkeypatch.setattr(cleanup_module, "ssh_session", fake_ssh_session)
    monkeypatch.setattr(cleanup_module, "list_remote_directory", fake_list_remote_directory)

    result = await cleanup_module._run_cleanup(
        cwd=tmp_path,
        env={},
        console=cleanup_module.build_console(no_color=True),
        job_ids=(),
        older_than=None,
        yes=True,
        json_output=False,
    )

    assert recorded == {"path": "/shared/launchpad", "recursive": False}
    assert result.deleted_paths == ()
