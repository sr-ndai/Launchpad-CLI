"""Shared Rich display helpers for CLI-facing output."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

from rich.console import Console, Group
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


def build_status_renderable(
    *,
    requested_job_id: str | None,
    queried_user: str | None,
    include_all: bool,
    generated_at: str,
    run_name: str | None,
    partition: str | None,
    array_range: str | None,
    remote_job_dir: str | None,
    state_counts: Mapping[str, int],
    rows: Sequence[Mapping[str, object]],
):
    """Build the Rich renderable used by `launchpad status`."""

    if requested_job_id:
        return _build_job_detail_renderable(
            requested_job_id=requested_job_id,
            generated_at=generated_at,
            run_name=run_name,
            partition=partition,
            array_range=array_range,
            remote_job_dir=remote_job_dir,
            state_counts=state_counts,
            rows=rows,
        )

    return _build_status_overview_renderable(
        queried_user=queried_user,
        include_all=include_all,
        generated_at=generated_at,
        state_counts=state_counts,
        rows=rows,
    )


def _build_status_overview_renderable(
    *,
    queried_user: str | None,
    include_all: bool,
    generated_at: str,
    state_counts: Mapping[str, int],
    rows: Sequence[Mapping[str, object]],
) -> Group:
    summary = Table.grid(padding=(0, 2))
    summary.add_row("User", queried_user or "configured user")
    summary.add_row("Scope", "active + recent completed" if include_all else "active only")
    summary.add_row("Updated", generated_at)
    summary.add_row("Rows", str(len(rows)))
    summary.add_row("Summary", _format_state_counts(state_counts))

    if not rows:
        empty = Panel("No matching SLURM jobs were found.", title="Status", expand=False)
        return Group(Panel(summary, title="Status Overview", expand=False), empty)

    table = Table(title="Jobs", show_header=True, header_style="bold")
    table.add_column("Job", justify="right")
    table.add_column("Task", justify="right")
    table.add_column("Name")
    table.add_column("State")
    table.add_column("Partition")
    table.add_column("Node")
    table.add_column("Elapsed")

    for row in rows:
        table.add_row(
            str(row.get("job_id") or "—"),
            str(row.get("task_id") or "—"),
            str(row.get("run_name") or "—"),
            _styled_state(row.get("state")),
            str(row.get("partition") or "—"),
            str(row.get("node") or "—"),
            str(row.get("elapsed") or "—"),
        )

    return Group(Panel(summary, title="Status Overview", expand=False), table)


def _build_job_detail_renderable(
    *,
    requested_job_id: str,
    generated_at: str,
    run_name: str | None,
    partition: str | None,
    array_range: str | None,
    remote_job_dir: str | None,
    state_counts: Mapping[str, int],
    rows: Sequence[Mapping[str, object]],
) -> Group:
    summary = Table.grid(padding=(0, 2))
    summary.add_row("Job", requested_job_id)
    summary.add_row("Run name", run_name or "—")
    summary.add_row("Partition", partition or "—")
    summary.add_row("Array", array_range or "—")
    summary.add_row("Remote job dir", remote_job_dir or "—")
    summary.add_row("Updated", generated_at)
    summary.add_row("Summary", _format_state_counts(state_counts))

    table = Table(title="Tasks", show_header=True, header_style="bold")
    table.add_column("Task", justify="right")
    table.add_column("State")
    table.add_column("Node")
    table.add_column("Elapsed")

    include_cpu = any(row.get("total_cpu") for row in rows)
    include_mem = any(row.get("max_rss") for row in rows)
    if include_cpu:
        table.add_column("CPU")
    if include_mem:
        table.add_column("Max RSS")

    for row in rows:
        columns = [
            str(row.get("task_id") or "—"),
            _styled_state(row.get("state")),
            str(row.get("node") or "—"),
            str(row.get("elapsed") or "—"),
        ]
        if include_cpu:
            columns.append(str(row.get("total_cpu") or "—"))
        if include_mem:
            columns.append(str(row.get("max_rss") or "—"))
        table.add_row(*columns)

    return Group(Panel(summary, title="Job Status", expand=False), table)


def _format_state_counts(counts: Mapping[str, int]) -> str:
    if not counts:
        return "no jobs"
    return ", ".join(f"{state.lower()}={count}" for state, count in counts.items())


def _styled_state(state: object) -> str:
    text = str(state or "UNKNOWN")
    styles = {
        "RUNNING": "green",
        "COMPLETED": "blue",
        "PENDING": "yellow",
        "FAILED": "red",
        "CANCELLED": "red",
        "TIMEOUT": "red",
    }
    style = styles.get(text.upper(), "white")
    return f"[{style}]{text}[/{style}]"
