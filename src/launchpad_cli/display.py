"""Shared Rich display helpers for CLI-facing output."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from launchpad_cli.solvers import DiscoveredInput


def build_console(*, stderr: bool = False, no_color: bool = False) -> Console:
    """Create a Rich console with the repository's baseline output defaults."""

    return Console(stderr=stderr, no_color=no_color)


def render_submit_dry_run(
    console: Console,
    *,
    run_name: str,
    solver_name: str,
    input_dir: Path,
    primary_inputs: Sequence[DiscoveredInput],
    package_files: Sequence[Path],
    remote_job_dir: str,
    archive_name: str,
    partition: str,
    time_limit: str,
    begin: str | None,
    script_preview: str,
) -> None:
    """Render a Rich dry-run preview for `launchpad submit`."""

    summary = Table.grid(padding=(0, 2))
    summary.add_row("Run name", run_name)
    summary.add_row("Solver", solver_name)
    summary.add_row("Input dir", str(input_dir))
    summary.add_row("Archive", archive_name)
    summary.add_row("Remote job dir", remote_job_dir)
    summary.add_row("Partition", partition)
    summary.add_row("Time", time_limit)
    summary.add_row("Begin", begin or "immediate")

    manifest = Table(title="Manifest", show_header=True, header_style="bold")
    manifest.add_column("Primary input")
    manifest.add_column("Size (bytes)", justify="right")
    for item in primary_inputs:
        manifest.add_row(item.relative_path.as_posix(), str(item.size_bytes))

    package_table = Table(title="Packaged Files", show_header=True, header_style="bold")
    package_table.add_column("Path")
    for path in package_files:
        package_table.add_row(str(path))

    console.print(Panel(summary, title="Dry Run", expand=False))
    console.print(manifest)
    console.print(package_table)
    console.print(Panel(script_preview, title="Generated SLURM Script", expand=False))


def render_submit_confirmation(
    console: Console,
    *,
    run_name: str,
    job_id: str,
    remote_job_dir: str,
    archive_path: str,
) -> None:
    """Render the Rich submit confirmation panel."""

    summary = Table.grid(padding=(0, 2))
    summary.add_row("Run name", run_name)
    summary.add_row("Job ID", job_id)
    summary.add_row("Remote job dir", remote_job_dir)
    summary.add_row("Remote archive", archive_path)
    summary.add_row("Monitor", f"launchpad status {job_id}")

    console.print(Panel(summary, title="Submission Complete", expand=False))
