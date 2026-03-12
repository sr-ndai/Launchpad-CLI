"""Placeholder registration for the `launchpad cancel` command."""

from __future__ import annotations

from ._helpers import placeholder_command

command = placeholder_command(
    name="cancel",
    short_help="Cancel a running or queued job.",
    help_text="Cancel an entire SLURM job or selected array tasks.",
    command_path="launchpad cancel",
)

