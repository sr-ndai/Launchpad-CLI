"""Utilities for defining scaffolded Click commands."""

from __future__ import annotations

import click


def not_implemented(command_path: str) -> click.ClickException:
    """Create a consistent placeholder error for scaffolded commands."""

    return click.ClickException(
        f"`{command_path}` is scaffolded but not implemented yet."
    )


def placeholder_command(
    *,
    name: str,
    short_help: str,
    help_text: str,
    command_path: str,
) -> click.Command:
    """Build a placeholder command that reserves the final CLI surface."""

    @click.command(name=name, short_help=short_help, help=help_text)
    def command() -> None:
        raise not_implemented(command_path)

    return command

