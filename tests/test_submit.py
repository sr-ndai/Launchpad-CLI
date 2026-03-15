"""Tests for submit command wiring and dry-run behavior."""

from __future__ import annotations

import json
from pathlib import Path

import asyncssh
import pytest

from click.testing import CliRunner

from launchpad_cli.cli import cli
from launchpad_cli.cli import submit as submit_module
from launchpad_cli.core.config import LaunchpadConfig, ResolvedConfig, SSHConfig
from launchpad_cli.core.job_manifest import build_task_references
from launchpad_cli.core.slurm import SubmittedJob
from launchpad_cli.solvers import DiscoveredInput


def test_submit_dry_run_previews_detected_inputs(monkeypatch, tmp_path: Path) -> None:
    """Dry-run should render the manifest preview without remote side effects."""

    (tmp_path / "wing.dat").write_text("SOL 101\n", encoding="utf-8")
    (tmp_path / "fuselage.dat").write_text("SOL 101\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("keep me\n", encoding="utf-8")

    config = LaunchpadConfig(
        ssh=SSHConfig(host="cluster.example.com", username="sergey"),
    )
    resolved = ResolvedConfig(config=config, layers=())

    monkeypatch.setattr(
        submit_module,
        "configure_logging",
        lambda **kwargs: tmp_path / "launchpad.log",
    )
    monkeypatch.setattr(
        submit_module,
        "resolve_config",
        lambda **kwargs: resolved,
    )

    result = CliRunner().invoke(cli, ["submit", str(tmp_path), "--dry-run"])

    assert result.exit_code == 0
    assert "Submit Preview" in result.output
    assert "wing.dat" in result.output
    assert "fuselage.dat" in result.output
    assert "/shared/sergey/" in result.output
    assert "single-file" in result.output
    assert "001" in result.output
    assert "002" in result.output
    assert "fuselage" in result.output
    assert "wing" in result.output
    assert "Tasks" in result.output
    assert "Transfer" in result.output
    assert "Generated Script" in result.output
    assert "Next" in result.output


def test_submit_executes_remote_flow_and_shows_confirmation(monkeypatch, tmp_path: Path) -> None:
    """Submit should wire the resolved plan into the async execution helper."""

    (tmp_path / "wing.dat").write_text("SOL 101\n", encoding="utf-8")
    (tmp_path / "fuselage.dat").write_text("SOL 101\n", encoding="utf-8")
    config = LaunchpadConfig(
        ssh=SSHConfig(host="cluster.example.com", username="sergey"),
    )
    resolved = ResolvedConfig(config=config, layers=())
    captured_plan: dict[str, submit_module.SubmitPlan] = {}

    monkeypatch.setattr(
        submit_module,
        "configure_logging",
        lambda **kwargs: tmp_path / "launchpad.log",
    )
    monkeypatch.setattr(
        submit_module,
        "resolve_config",
        lambda **kwargs: resolved,
    )

    async def fake_execute_submit(plan: submit_module.SubmitPlan) -> submit_module.SubmitExecution:
        captured_plan["plan"] = plan
        return submit_module.SubmitExecution(
            submitted_job=SubmittedJob(
                job_id="12345",
                script_path=plan.submit_request.script_path,
                remote_job_dir=plan.remote_layout.job_dir,
                stdout="12345\n",
                stderr="",
            ),
            effective_streams=4,
        )

    monkeypatch.setattr(submit_module, "_execute_submit", fake_execute_submit)

    result = CliRunner().invoke(cli, ["submit", str(tmp_path), "--name", "tank_v3"])

    assert result.exit_code == 0
    assert captured_plan["plan"].run_name == "tank_v3"
    assert captured_plan["plan"].transfer_mode == "single-file"
    assert captured_plan["plan"].submit_request.input_files == (
        f"{tmp_path.name}/fuselage.dat",
        f"{tmp_path.name}/wing.dat",
    )
    assert captured_plan["plan"].job_manifest.logs == {"solver": ".f06", "telemetry": ".f04"}
    assert "Submitted" in result.output
    assert "Tasks" in result.output
    assert "Transfer" in result.output
    assert "12345" in result.output
    assert "001" in result.output
    assert "002" in result.output
    assert "launchpad status 12345" in result.output
    assert "launchpad download 12345" in result.output


def test_submit_dry_run_emits_json_when_requested(monkeypatch, tmp_path: Path) -> None:
    """Submit dry-run should emit a structured payload under the root `--json` flag."""

    (tmp_path / "wing.dat").write_text("SOL 101\n", encoding="utf-8")
    (tmp_path / "fuselage.dat").write_text("SOL 101\n", encoding="utf-8")
    config = LaunchpadConfig(
        ssh=SSHConfig(host="cluster.example.com", username="sergey"),
    )
    resolved = ResolvedConfig(config=config, layers=())

    monkeypatch.setattr(
        submit_module,
        "configure_logging",
        lambda **kwargs: tmp_path / "launchpad.log",
    )
    monkeypatch.setattr(
        submit_module,
        "resolve_config",
        lambda **kwargs: resolved,
    )

    result = CliRunner().invoke(cli, ["--json", "submit", str(tmp_path), "--dry-run"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["mode"] == "dry-run"
    assert payload["run_name"].startswith("nastran-")
    assert payload["transfer_mode"] == "single-file"
    assert payload["logs"] == {"solver": ".f06", "telemetry": ".f04"}
    assert payload["tasks"][0]["alias"] == "001"
    assert payload["tasks"][1]["task_id"] == "1"
    assert payload["primary_inputs"][0]["relative_path"] == "fuselage.dat"
    assert "Generated SLURM Script" not in result.output


def test_submit_emits_json_after_successful_execution(monkeypatch, tmp_path: Path) -> None:
    """Submit execution should emit structured JSON for scripting."""

    (tmp_path / "wing.dat").write_text("SOL 101\n", encoding="utf-8")
    config = LaunchpadConfig(
        ssh=SSHConfig(host="cluster.example.com", username="sergey"),
    )
    resolved = ResolvedConfig(config=config, layers=())

    monkeypatch.setattr(
        submit_module,
        "configure_logging",
        lambda **kwargs: tmp_path / "launchpad.log",
    )
    monkeypatch.setattr(
        submit_module,
        "resolve_config",
        lambda **kwargs: resolved,
    )

    async def fake_execute_submit(plan: submit_module.SubmitPlan) -> submit_module.SubmitExecution:
        return submit_module.SubmitExecution(
            submitted_job=SubmittedJob(
                job_id="12345",
                script_path=plan.submit_request.script_path,
                remote_job_dir=plan.remote_layout.job_dir,
                stdout="12345\n",
                stderr="",
            ),
            effective_streams=3,
        )

    monkeypatch.setattr(submit_module, "_execute_submit", fake_execute_submit)

    result = CliRunner().invoke(cli, ["--json", "submit", str(tmp_path), "--name", "tank_v3"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload == {
        "mode": "submitted",
        "run_name": "tank_v3",
        "solver": "nastran",
        "input_dir": str(tmp_path),
        "remote_job_dir": "/shared/sergey/tank_v3",
        "payload_label": "tank_v3.tar.zst",
        "remote_payload_path": "/shared/sergey/tank_v3/tank_v3.tar.zst",
        "transfer_mode": "single-file",
        "requested_streams": 8,
        "effective_streams": 3,
        "job_id": "12345",
        "monitor_command": "launchpad status 12345",
        "partition": None,
        "time_limit": None,
        "begin": None,
        "primary_inputs": [],
        "package_files": [],
        "manifest_entries": [],
        "logs": {"solver": ".f06", "telemetry": ".f04"},
        "tasks": [
            {
                "task_id": "0",
                "alias": "001",
                "input_relative_path": "wing.dat",
                "input_filename": "wing.dat",
                "input_stem": "wing",
                "display_label": "wing",
                "result_dir": "results_wing_0",
            }
        ],
        "script_preview": None,
    }


def test_submit_uses_configured_workspace_root_for_remote_job_dir(monkeypatch, tmp_path: Path) -> None:
    """Configured workspace roots should override the legacy username-derived remote job path."""

    (tmp_path / "wing.dat").write_text("SOL 101\n", encoding="utf-8")
    resolved = ResolvedConfig(
        config=LaunchpadConfig(
            cluster={"workspace_root": "/shared/launchpad"},
            ssh=SSHConfig(host="cluster.example.com", username="sergey"),
        ),
        layers=(),
    )

    monkeypatch.setattr(submit_module, "resolve_config", lambda **kwargs: resolved)

    plan = submit_module._build_submit_plan(
        input_dir=tmp_path,
        explicit_solver=None,
        run_name="tank_v3",
        cpus=None,
        max_concurrent=None,
        partition=None,
        time_limit=None,
        begin=None,
        transfer_mode=None,
        streams=None,
        compression_level=None,
        no_compress=False,
        extra_files=(),
        include_all=False,
    )

    assert plan.remote_layout.job_dir == "/shared/launchpad/tank_v3"


def test_submit_wraps_asyncssh_errors_as_click_exceptions(monkeypatch, tmp_path: Path) -> None:
    """Submit should surface AsyncSSH failures as normal CLI errors."""

    (tmp_path / "wing.dat").write_text("SOL 101\n", encoding="utf-8")
    config = LaunchpadConfig(
        ssh=SSHConfig(host="cluster.example.com", username="sergey"),
    )
    resolved = ResolvedConfig(config=config, layers=())

    monkeypatch.setattr(
        submit_module,
        "configure_logging",
        lambda **kwargs: tmp_path / "launchpad.log",
    )
    monkeypatch.setattr(
        submit_module,
        "resolve_config",
        lambda **kwargs: resolved,
    )

    async def fake_execute_submit(plan: submit_module.SubmitPlan) -> submit_module.SubmitExecution:
        raise asyncssh.Error(1, "boom")

    monkeypatch.setattr(submit_module, "_execute_submit", fake_execute_submit)

    result = CliRunner().invoke(cli, ["submit", str(tmp_path)])

    assert result.exit_code == 1
    assert not isinstance(result.exception, asyncssh.Error)
    assert "boom" in result.output


def test_build_submit_plan_errors_when_no_supported_inputs(monkeypatch, tmp_path: Path) -> None:
    """Submit planning should fail clearly when the input directory has no solver files."""

    config = LaunchpadConfig(
        ssh=SSHConfig(host="cluster.example.com", username="sergey"),
    )
    resolved = ResolvedConfig(config=config, layers=())

    monkeypatch.setattr(submit_module, "resolve_config", lambda **kwargs: resolved)

    try:
        submit_module._build_submit_plan(
            input_dir=tmp_path,
            explicit_solver=None,
            run_name=None,
            cpus=None,
            max_concurrent=None,
            partition=None,
            time_limit=None,
            begin=None,
            transfer_mode=None,
            streams=None,
            compression_level=None,
            no_compress=False,
            extra_files=(),
            include_all=False,
        )
    except Exception as exc:  # ClickException without invoking CLI
        assert "No supported solver inputs" in str(exc)
    else:
        raise AssertionError("Expected submit planning to fail when no inputs exist.")


def test_build_submit_plan_rejects_multi_file_without_no_compress(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Submit should reject the explicit multi-file mode unless archive creation is disabled."""

    (tmp_path / "wing.dat").write_text("SOL 101\n", encoding="utf-8")
    config = LaunchpadConfig(
        ssh=SSHConfig(host="cluster.example.com", username="sergey"),
    )
    resolved = ResolvedConfig(config=config, layers=())

    monkeypatch.setattr(submit_module, "resolve_config", lambda **kwargs: resolved)

    with pytest.raises(Exception, match="requires `--no-compress`"):
        submit_module._build_submit_plan(
            input_dir=tmp_path,
            explicit_solver=None,
            run_name=None,
            cpus=None,
            max_concurrent=None,
            partition=None,
            time_limit=None,
            begin=None,
            transfer_mode="multi-file",
            streams=None,
            compression_level=None,
            no_compress=False,
            extra_files=(),
            include_all=False,
        )


def test_build_task_references_disambiguates_duplicate_stems_from_relative_paths(tmp_path: Path) -> None:
    """Duplicate stems should use relative-path labels and stable aliases."""

    inputs = (
        DiscoveredInput(
            path=tmp_path / "left" / "wing.dat",
            relative_path=Path("left/wing.dat"),
            stem="wing",
            extension=".dat",
            size_bytes=10,
        ),
        DiscoveredInput(
            path=tmp_path / "right" / "wing.dat",
            relative_path=Path("right/wing.dat"),
            stem="wing",
            extension=".dat",
            size_bytes=10,
        ),
    )

    references = build_task_references(inputs)

    assert [item.alias for item in references] == ["001", "002"]
    assert [item.display_label for item in references] == ["left/wing", "right/wing"]
    assert [item.result_dir for item in references] == ["results_wing_0", "results_wing_1"]


@pytest.mark.asyncio
async def test_execute_submit_writes_launchpad_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Submit execution should persist the manifest alongside the remote job before submission."""

    (tmp_path / "wing.dat").write_text("SOL 101\n", encoding="utf-8")
    config = LaunchpadConfig(
        ssh=SSHConfig(host="cluster.example.com", username="sergey"),
    )
    resolved = ResolvedConfig(config=config, layers=())

    monkeypatch.setattr(submit_module, "resolve_config", lambda **kwargs: resolved)
    plan = submit_module._build_submit_plan(
        input_dir=tmp_path,
        explicit_solver=None,
        run_name="tank_v3",
        cpus=None,
        max_concurrent=None,
        partition=None,
        time_limit=None,
        begin=None,
        transfer_mode=None,
        streams=None,
        compression_level=None,
        no_compress=True,
        extra_files=(),
        include_all=False,
    )

    written: dict[str, str] = {}

    class FakeSftp:
        async def __aenter__(self) -> "FakeSftp":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def exists(self, path: str) -> bool:
            return False

    class FakeConnection:
        def start_sftp_client(self) -> FakeSftp:
            return FakeSftp()

    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    @asynccontextmanager
    async def fake_ssh_session(_config: SSHConfig):  # type: ignore[no-untyped-def]
        yield FakeConnection()

    async def fake_prepare_remote_job_directory(conn, layout):  # type: ignore[no-untyped-def]
        return layout

    async def fake_upload_many(*args, **kwargs):  # type: ignore[no-untyped-def]
        return SimpleNamespace(effective_streams=2)

    async def fake_submit_job(conn, *, solver, request, config, sbatch_binary=None):  # type: ignore[no-untyped-def]
        return SubmittedJob(
            job_id="12345",
            script_path=request.script_path,
            remote_job_dir=request.remote_job_dir,
            stdout="12345\n",
            stderr="",
        )

    async def fake_write_remote_text(conn, path: str, content: str) -> str:  # type: ignore[no-untyped-def]
        written[path] = content
        return path

    monkeypatch.setattr(submit_module, "ssh_session", fake_ssh_session)
    monkeypatch.setattr(submit_module, "prepare_remote_job_directory", fake_prepare_remote_job_directory)
    monkeypatch.setattr(submit_module, "upload_many", fake_upload_many)
    monkeypatch.setattr(submit_module, "submit_job", fake_submit_job)
    monkeypatch.setattr(submit_module, "write_remote_text", fake_write_remote_text)

    execution = await submit_module._execute_submit(plan)

    assert execution.submitted_job.job_id == "12345"
    assert plan.remote_layout.manifest_path in written
    assert '"solver": "nastran"' in written[plan.remote_layout.manifest_path]
    assert '"alias": "001"' in written[plan.remote_layout.manifest_path]


@pytest.mark.asyncio
async def test_execute_submit_rejects_existing_remote_job_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Submit should refuse to reuse an existing remote job directory."""

    (tmp_path / "wing.dat").write_text("SOL 101\n", encoding="utf-8")
    config = LaunchpadConfig(
        ssh=SSHConfig(host="cluster.example.com", username="sergey"),
    )
    resolved = ResolvedConfig(config=config, layers=())

    monkeypatch.setattr(submit_module, "resolve_config", lambda **kwargs: resolved)
    plan = submit_module._build_submit_plan(
        input_dir=tmp_path,
        explicit_solver=None,
        run_name="tank_v3",
        cpus=None,
        max_concurrent=None,
        partition=None,
        time_limit=None,
        begin=None,
        transfer_mode=None,
        streams=None,
        compression_level=None,
        no_compress=False,
        extra_files=(),
        include_all=False,
    )

    class FakeSftp:
        async def __aenter__(self) -> "FakeSftp":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def exists(self, path: str) -> bool:
            return True

    class FakeConnection:
        def start_sftp_client(self) -> FakeSftp:
            return FakeSftp()

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_ssh_session(_config: SSHConfig):  # type: ignore[no-untyped-def]
        yield FakeConnection()

    monkeypatch.setattr(submit_module, "ssh_session", fake_ssh_session)

    with pytest.raises(submit_module.click.ClickException, match="Remote job directory already exists"):
        await submit_module._execute_submit(plan)
