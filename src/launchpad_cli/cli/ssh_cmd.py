"""Placeholder registration for the `launchpad ssh` command."""

from __future__ import annotations

from ._helpers import placeholder_command

command = placeholder_command(
    name="ssh",
    short_help="Open an SSH session to the cluster.",
    help_text="Start an interactive SSH session using the resolved Launchpad config.",
    command_path="launchpad ssh",
)

