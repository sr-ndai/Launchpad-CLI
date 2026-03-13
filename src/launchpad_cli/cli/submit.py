"""Placeholder registration for the `launchpad submit` command."""

from __future__ import annotations

from ._helpers import placeholder_command

command = placeholder_command(
    name="submit",
    short_help="Package inputs and submit a SLURM job.",
    help_text=(
        "Discover solver inputs, package them, transfer the archive, and submit "
        "the run to SLURM."
    ),
    command_path="launchpad submit",
)

