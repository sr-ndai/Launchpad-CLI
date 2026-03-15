"""CLI smoke tests for the scaffolded Launchpad application."""

from __future__ import annotations

import launchpad_cli.cli as cli_module
from click.testing import CliRunner

from launchpad_cli.cli import cli


def test_root_command_shows_welcome_screen_when_invoked_without_subcommand() -> None:
    """Bare `launchpad` should render the welcome surface, not root help."""

    runner = CliRunner()

    result = runner.invoke(cli, [])

    assert result.exit_code == 0
    assert "Launchpad  v0.1.0" in result.output
    assert "Submit, monitor, and retrieve solver jobs on your SLURM cluster." in result.output
    assert "launchpad submit" in result.output
    assert "launchpad doctor" in result.output
    assert "Run launchpad -h for all commands." in result.output
    assert "Key Commands" not in result.output
    assert "Get started: launchpad config init -> doctor -> submit --dry-run ." not in result.output
    assert "Usage:" not in result.output


def test_root_help_is_a_compact_reference_card() -> None:
    """`launchpad --help` should stay dry and grouped into the four root panels."""

    runner = CliRunner()

    result = runner.invoke(cli, ["--help"], prog_name="launchpad")

    assert result.exit_code == 0
    assert "Usage: launchpad [OPTIONS] COMMAND [ARGS]..." in result.output
    assert "Commands" in result.output
    assert "Configuration" in result.output
    assert "Management" in result.output
    assert "Options" in result.output
    assert "--json" in result.output
    assert "--no-color" in result.output
    assert "--version" in result.output
    assert "Use launchpad <command> --help for command-specific examples." in result.output
    assert "From folder to cluster in one command." not in result.output
    assert "Launchpad  v0.1.0" not in result.output
    assert "Key Commands" not in result.output
    assert "Examples:" not in result.output
    assert "Primary Workflows" not in result.output
    assert "Operator Tools" not in result.output


def test_root_command_suggests_nearby_subcommands_for_typos() -> None:
    """Mistyped root subcommands should include a single close suggestion."""

    runner = CliRunner()

    result = runner.invoke(cli, ["statuz"])

    assert result.exit_code == 2
    assert "No such command 'statuz'. Did you mean 'status'?" in result.output


def test_root_welcome_shows_wordmark_when_branding_is_allowed(monkeypatch) -> None:
    """TTY-style bare invocation should include the welcome wordmark."""

    runner = CliRunner()
    monkeypatch.setattr(cli_module, "_stdout_supports_branding", lambda: True)
    monkeypatch.setattr(cli_module, "_detect_terminal_width", lambda: 120)
    monkeypatch.delenv("NO_COLOR", raising=False)

    result = runner.invoke(cli, [], color=True)

    assert result.exit_code == 0
    assert "Submit, monitor, and retrieve solver jobs on your SLURM cluster." in result.output
    assert "____ ___  ______" in result.output
    assert "→ launchpad submit" in result.output


def test_root_welcome_uses_compact_wordmark_on_narrow_ttys(monkeypatch) -> None:
    """Narrow terminals should avoid wrapping the full wordmark."""

    runner = CliRunner()
    monkeypatch.setattr(cli_module, "_stdout_supports_branding", lambda: True)
    monkeypatch.setattr(cli_module, "_detect_terminal_width", lambda: 16)
    monkeypatch.delenv("NO_COLOR", raising=False)

    result = runner.invoke(cli, [], color=True)

    assert result.exit_code == 0
    assert "Launchpad" in result.output
    assert "____ ___  ______" not in result.output
    assert "Run launchpad -h for all commands." in result.output


def test_root_welcome_suppresses_wordmark_with_no_color(monkeypatch) -> None:
    """The welcome wordmark should disappear when `--no-color` is requested."""

    runner = CliRunner()
    monkeypatch.setattr(cli_module, "_stdout_supports_branding", lambda: True)
    monkeypatch.setattr(cli_module, "_detect_terminal_width", lambda: 120)
    monkeypatch.delenv("NO_COLOR", raising=False)

    result = runner.invoke(cli, ["--no-color"], color=True)

    assert result.exit_code == 0
    assert "Submit, monitor, and retrieve solver jobs on your SLURM cluster." in result.output
    assert "____ ___  ______" not in result.output
    assert "-> launchpad submit" in result.output


def test_submit_help_uses_grouped_sections_and_examples() -> None:
    """Leaf-command help should expose the shared grouped layout and examples."""

    runner = CliRunner()

    result = runner.invoke(cli, ["submit", "--help"], prog_name="launchpad")

    assert result.exit_code == 0
    assert "Solver & Packaging" in result.output
    assert "Scheduling" in result.output
    assert "Transfer" in result.output
    assert "Examples:" in result.output
    assert "launchpad submit --dry-run ." in result.output
    assert "From folder to cluster in one command." not in result.output
    assert "Get started: launchpad config init -> doctor -> submit --dry-run ." not in result.output


def test_logs_help_mentions_task_refs_and_log_kind() -> None:
    """Logs help should document the final Phase 8 selector and log-kind surface."""

    runner = CliRunner()

    result = runner.invoke(cli, ["logs", "--help"], prog_name="launchpad")

    assert result.exit_code == 0
    assert "TASK_REF" in result.output
    assert "--log-kind" in result.output
    assert "launchpad logs 12345 --follow" in result.output
    assert "launchpad logs 12345 001 --log-kind telemetry" in result.output
