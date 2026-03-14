"""Tests for operator command wiring and diagnostics."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from launchpad_cli.cli import cli
from launchpad_cli.cli import doctor as doctor_module
from launchpad_cli.cli import ssh_cmd as ssh_module
from launchpad_cli.core.config import LaunchpadConfig, SSHConfig


def test_ssh_command_invokes_interactive_shell(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The SSH command should resolve config and invoke the async shell helper."""

    called: dict[str, SSHConfig] = {}

    monkeypatch.setattr(
        ssh_module,
        "configure_logging",
        lambda **kwargs: tmp_path / "launchpad.log",
    )
    monkeypatch.setattr(
        ssh_module,
        "resolve_config",
        lambda **kwargs: SimpleNamespace(
            config=LaunchpadConfig(
                ssh=SSHConfig(host="cluster.example.com", username="sergey")
            )
        ),
    )

    async def fake_open_interactive_shell(config: SSHConfig) -> int:
        called["config"] = config
        return 0

    monkeypatch.setattr(ssh_module, "_open_interactive_shell", fake_open_interactive_shell)

    result = CliRunner().invoke(cli, ["ssh"])

    assert result.exit_code == 0
    assert called["config"].host == "cluster.example.com"
    assert called["config"].username == "sergey"


def test_doctor_command_supports_json_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The doctor command should emit structured JSON when requested."""

    monkeypatch.setattr(
        doctor_module,
        "configure_logging",
        lambda **kwargs: tmp_path / "launchpad.log",
    )

    async def fake_collect_diagnostics(*, cwd: Path, env: dict[str, str]) -> list[doctor_module.DiagnosticResult]:
        return [
            doctor_module.DiagnosticResult(
                name="python",
                status="pass",
                detail="Python 3.12.13",
            )
        ]

    monkeypatch.setattr(doctor_module, "_collect_diagnostics", fake_collect_diagnostics)

    result = CliRunner().invoke(cli, ["--json", "doctor"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload == [
        {
            "name": "python",
            "status": "pass",
            "detail": "Python 3.12.13",
            "suggestion": None,
        }
    ]


def test_doctor_command_groups_results_and_points_to_next_steps(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Human-readable doctor output should group checks and suggest recovery steps."""

    monkeypatch.setattr(
        doctor_module,
        "configure_logging",
        lambda **kwargs: tmp_path / "launchpad.log",
    )

    async def fake_collect_diagnostics(*, cwd: Path, env: dict[str, str]) -> list[doctor_module.DiagnosticResult]:
        return [
            doctor_module.DiagnosticResult("python", "pass", "Python 3.12.13"),
            doctor_module.DiagnosticResult(
                "config",
                "fail",
                "Config resolved from defaults only; ssh.host is missing.",
                "Run `launchpad config init`.",
            ),
            doctor_module.DiagnosticResult(
                "ssh-connection",
                "skip",
                "Skipped remote checks because local SSH configuration is incomplete.",
            ),
        ]

    monkeypatch.setattr(doctor_module, "_collect_diagnostics", fake_collect_diagnostics)

    result = CliRunner().invoke(cli, ["doctor"])

    assert result.exit_code == 1
    assert "Doctor Summary" in result.output
    assert "Local Setup" in result.output
    assert "Cluster Access" in result.output
    assert "Config Resolution" in result.output
    assert "Next Steps" in result.output
    assert "launchpad config init" in result.output
    assert "launchpad doctor" in result.output


def test_doctor_render_results_shows_branded_success_when_all_checks_pass(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Doctor should reserve branding for the all-green success path."""

    monkeypatch.setattr(doctor_module, "_stdout_supports_branding", lambda: True)
    monkeypatch.setattr(doctor_module, "_detect_terminal_width", lambda: 120)
    results = [
        doctor_module.DiagnosticResult("python", "pass", "Python 3.12.13"),
        doctor_module.DiagnosticResult("config", "pass", "Resolved config is complete."),
        doctor_module.DiagnosticResult("ssh-key", "pass", "SSH key found."),
        doctor_module.DiagnosticResult("shared-config", "pass", "Shared config readable."),
        doctor_module.DiagnosticResult("ssh-connection", "pass", "Connected successfully."),
        doctor_module.DiagnosticResult("remote-binaries", "pass", "All binaries resolved."),
        doctor_module.DiagnosticResult("remote-root", "pass", "Remote root is writable."),
    ]

    doctor_module._render_results(results, no_color=False)
    captured = capsys.readouterr()

    assert "Doctor checks passed." in captured.out
    assert "____ ___  ______" in captured.out


def test_doctor_ssh_key_check_requires_existing_key(tmp_path: Path) -> None:
    """Local SSH key validation should fail for missing key files."""

    result = doctor_module._ssh_key_check(
        SSHConfig(
            host="cluster.example.com",
            username="sergey",
            key_path=str(tmp_path / "missing_key"),
        )
    )

    assert result.status == "fail"
    assert "not found" in result.detail


def test_doctor_config_check_fails_when_required_ssh_fields_are_missing() -> None:
    """Config validity should fail when SSH connection fields are unresolved."""

    result = doctor_module._config_resolution_check((), LaunchpadConfig())

    assert result.status == "fail"
    assert "ssh.host" in result.detail
    assert "ssh.username" in result.detail
    assert result.suggestion is not None


def test_doctor_config_check_passes_for_complete_ssh_configuration() -> None:
    """Config validity should pass when the SSH session requirements are present."""

    result = doctor_module._config_resolution_check(
        (),
        LaunchpadConfig(
            ssh=SSHConfig(
                host="cluster.example.com",
                username="sergey",
            )
        ),
    )

    assert result.status == "pass"
    assert "cluster.example.com" in result.detail
    assert "sergey" in result.detail


@pytest.mark.asyncio
async def test_doctor_remote_binary_check_reports_missing_tools() -> None:
    """Remote binary validation should fail when a configured tool is absent."""

    class FakeConnection:
        async def run(self, command: str, check: bool = False) -> SimpleNamespace:
            if "command -v sbatch" in command:
                return SimpleNamespace(exit_status=0, stdout="/usr/bin/sbatch")
            return SimpleNamespace(exit_status=1, stdout="")

    config = LaunchpadConfig(
        ssh=SSHConfig(host="cluster.example.com", username="sergey"),
    )

    result = await doctor_module._remote_binaries_check(FakeConnection(), config)

    assert result.status == "fail"
    assert "squeue" in result.detail
