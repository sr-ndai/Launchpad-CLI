"""Placeholder registration for the `launchpad doctor` command."""

from __future__ import annotations

from ._helpers import placeholder_command

command = placeholder_command(
    name="doctor",
    short_help="Run environment and connectivity diagnostics.",
    help_text="Check the local environment, config, SSH access, and cluster tooling.",
    command_path="launchpad doctor",
)

