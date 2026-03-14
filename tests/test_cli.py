"""CLI smoke tests for the scaffolded Launchpad application."""

from __future__ import annotations

import launchpad_cli.cli as cli_module
from click.testing import CliRunner

from launchpad_cli.cli import cli


def test_root_command_shows_help_when_invoked_without_subcommand() -> None:
    """The root command should boot and present help text."""

    runner = CliRunner()

    result = runner.invoke(cli, [])

    assert result.exit_code == 0
    assert "Launchpad coordinates solver submissions" in result.output
    assert "submit" in result.output
    assert "doctor" in result.output
    assert "Primary Workflows" in result.output
    assert "Operator Tools" in result.output


def test_root_help_lists_global_flags() -> None:
    """The root help output should expose the baseline global options."""

    runner = CliRunner()

    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "--json" in result.output
    assert "--no-color" in result.output
    assert "--version" in result.output
    assert "Start here:" in result.output
    assert "launchpad submit" in result.output
    assert "--dry-run ." in result.output


def test_root_command_suggests_nearby_subcommands_for_typos() -> None:
    """Mistyped root subcommands should include a single close suggestion."""

    runner = CliRunner()

    result = runner.invoke(cli, ["statuz"])

    assert result.exit_code == 2
    assert "No such command 'statuz'. Did you mean 'status'?" in result.output


def test_root_help_shows_wordmark_when_branding_is_allowed(monkeypatch) -> None:
    """TTY-style root help should include the Launchpad ASCII mark."""

    runner = CliRunner()
    monkeypatch.setattr(cli_module, "_stdout_supports_branding", lambda: True)
    monkeypatch.delenv("NO_COLOR", raising=False)

    result = runner.invoke(cli, ["--help"], color=True)

    assert result.exit_code == 0
    assert "Solver jobs, cluster UX, no shell-script drift." in result.output
    assert "| |    __ _ _   _ _ __" in result.output


def test_root_help_suppresses_wordmark_with_no_color(monkeypatch) -> None:
    """The ASCII mark should disappear when `--no-color` is requested."""

    runner = CliRunner()
    monkeypatch.setattr(cli_module, "_stdout_supports_branding", lambda: True)
    monkeypatch.delenv("NO_COLOR", raising=False)

    result = runner.invoke(cli, ["--no-color", "--help"], color=True)

    assert result.exit_code == 0
    assert "Solver jobs, cluster UX, no shell-script drift." not in result.output
    assert "| |    __ _ _   _ _ __" not in result.output


def test_submit_help_uses_grouped_sections_and_examples() -> None:
    """Leaf-command help should expose the shared grouped layout and examples."""

    runner = CliRunner()

    result = runner.invoke(cli, ["submit", "--help"])

    assert result.exit_code == 0
    assert "Solver & Packaging" in result.output
    assert "Scheduling" in result.output
    assert "Transfer" in result.output
    assert "Examples:" in result.output
    assert "launchpad submit --dry-run ." in result.output
