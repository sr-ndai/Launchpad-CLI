"""Placeholder registration for the `launchpad ls` command."""

from __future__ import annotations

from ._helpers import placeholder_command

command = placeholder_command(
    name="ls",
    short_help="List remote files and directories.",
    help_text="Browse files on the cluster without leaving the Launchpad CLI.",
    command_path="launchpad ls",
)

