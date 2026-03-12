"""Placeholder registration for the `launchpad download` command."""

from __future__ import annotations

from ._helpers import placeholder_command

command = placeholder_command(
    name="download",
    short_help="Download completed run results.",
    help_text=(
        "Collect remote results, compress them when appropriate, and retrieve "
        "them to the local machine."
    ),
    command_path="launchpad download",
)

