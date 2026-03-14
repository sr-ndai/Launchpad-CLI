"""CLI smoke tests for the scaffolded Launchpad application."""

from __future__ import annotations

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


def test_root_help_lists_global_flags() -> None:
    """The root help output should expose the baseline global options."""

    runner = CliRunner()

    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "--json" in result.output
    assert "--no-color" in result.output
    assert "--version" in result.output


def test_root_command_suggests_nearby_subcommands_for_typos() -> None:
    """Mistyped root subcommands should include a single close suggestion."""

    runner = CliRunner()

    result = runner.invoke(cli, ["statuz"])

    assert result.exit_code == 2
    assert "No such command 'statuz'. Did you mean 'status'?" in result.output
