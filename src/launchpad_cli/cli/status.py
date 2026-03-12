"""Placeholder registration for the `launchpad status` command."""

from __future__ import annotations

from ._helpers import placeholder_command

command = placeholder_command(
    name="status",
    short_help="Inspect SLURM job state.",
    help_text=(
        "Show running, pending, or completed job status for the current user or "
        "for a specific job."
    ),
    command_path="launchpad status",
)

