"""Tests for submit command wiring and dry-run behavior."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner

from launchpad_cli.cli import cli
from launchpad_cli.cli import submit as submit_module
from launchpad_cli.core.config import LaunchpadConfig, ResolvedConfig, SSHConfig
from launchpad_cli.core.remote_ops import build_remote_job_layout
from launchpad_cli.core.slurm import SubmitRequest, SubmittedJob
from launchpad_cli.solvers import NastranAdapter


def test_submit_dry_run_previews_detected_inputs(monkeypatch, tmp_path: Path) -> None:
    """Dry-run should render the manifest preview without remote side effects."""

    (tmp_path / "wing.dat").write_text("SOL 101\n", encoding="utf-8")
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
    assert "Dry Run" in result.output
    assert "wing.dat" in result.output
    assert "/shared/sergey/" in result.output
    assert "Generated SLURM Script" in result.output


def test_submit_executes_remote_flow_and_shows_confirmation(monkeypatch, tmp_path: Path) -> None:
    """Submit should wire the resolved plan into the async execution helper."""

    (tmp_path / "wing.dat").write_text("SOL 101\n", encoding="utf-8")
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

    async def fake_execute_submit(plan: submit_module.SubmitPlan) -> SubmittedJob:
        captured_plan["plan"] = plan
        return SubmittedJob(
            job_id="12345",
            script_path=plan.submit_request.script_path,
            remote_job_dir=plan.remote_layout.job_dir,
            stdout="12345\n",
            stderr="",
        )

    monkeypatch.setattr(submit_module, "_execute_submit", fake_execute_submit)

    result = CliRunner().invoke(cli, ["submit", str(tmp_path), "--name", "tank_v3"])

    assert result.exit_code == 0
    assert captured_plan["plan"].run_name == "tank_v3"
    assert captured_plan["plan"].submit_request.input_files == (f"{tmp_path.name}/wing.dat",)
    assert "Submission Complete" in result.output
    assert "12345" in result.output
    assert "launchpad status 12345" in result.output


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
            compression_level=None,
            extra_files=(),
            include_all=False,
        )
    except Exception as exc:  # ClickException without invoking CLI
        assert "No supported solver inputs" in str(exc)
    else:
        raise AssertionError("Expected submit planning to fail when no inputs exist.")
