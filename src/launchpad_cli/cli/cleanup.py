"""Placeholder registration for the `launchpad cleanup` command."""

from __future__ import annotations

from ._helpers import placeholder_command

command = placeholder_command(
    name="cleanup",
    short_help="Remove remote job directories.",
    help_text="Delete remote job directories after results have been collected.",
    command_path="launchpad cleanup",
)

