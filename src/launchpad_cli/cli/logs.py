"""Placeholder registration for the `launchpad logs` command."""

from __future__ import annotations

from ._helpers import placeholder_command

command = placeholder_command(
    name="logs",
    short_help="Inspect remote log output.",
    help_text=(
        "View or follow SLURM and solver logs for a submitted job."
    ),
    command_path="launchpad logs",
)

