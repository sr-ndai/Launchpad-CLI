"""Placeholder registration for the `launchpad config` command group."""

from __future__ import annotations

import click

from ._helpers import not_implemented


@click.group(
    name="config",
    short_help="Inspect and manage Launchpad configuration.",
    help="Inspect, initialize, edit, and validate Launchpad configuration layers.",
)
def command() -> None:
    """Manage Launchpad configuration."""


@command.command("show", short_help="Show the resolved configuration.")
def show_command() -> None:
    """Display the resolved configuration values."""

    raise not_implemented("launchpad config show")


@command.command("edit", short_help="Open the user configuration file.")
def edit_command() -> None:
    """Open the user-level Launchpad configuration for editing."""

    raise not_implemented("launchpad config edit")


@command.command("init", short_help="Create an initial user configuration.")
def init_command() -> None:
    """Create a starter Launchpad configuration file."""

    raise not_implemented("launchpad config init")


@command.command("validate", short_help="Validate configuration inputs.")
def validate_command() -> None:
    """Validate configuration files and environment variables."""

    raise not_implemented("launchpad config validate")

