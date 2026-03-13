"""`launchpad status` command and live monitoring UI."""

from __future__ import annotations

import asyncio
import json
import os
from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable, Mapping

import asyncssh
import click
from rich.live import Live

from launchpad_cli.core.config import LaunchpadConfig, resolve_config
from launchpad_cli.core.logging import configure_logging
from launchpad_cli.core.slurm import JobAccounting, JobStatus, query_sacct, query_squeue
from launchpad_cli.core.ssh import ssh_session
from launchpad_cli.display import build_console, build_status_renderable

RECENT_ACCOUNTING_START = "now-7days"


@dataclass(frozen=True, slots=True)
class StatusRow:
    """Normalized scheduler row used for status rendering and JSON output."""

    job_id: str
    task_id: str | None
    run_name: str | None
    state: str
    partition: str | None = None
    node: str | None = None
    elapsed: str | None = None
    total_cpu: str | None = None
    max_rss: str | None = None
    remote_job_dir: str | None = None
    stdout_path: str | None = None
    stderr_path: str | None = None
    work_dir: str | None = None
    source: str = "squeue"


@dataclass(frozen=True, slots=True)
class StatusSnapshot:
    """Structured status response for overview and job-detail flows."""

    requested_job_id: str | None
    queried_user: str | None
    include_all: bool
    generated_at: str
    rows: tuple[StatusRow, ...]
    run_name: str | None = None
    partition: str | None = None
    array_range: str | None = None
    remote_job_dir: str | None = None

    def state_counts(self) -> dict[str, int]:
        """Return a stable state-count mapping for display and JSON output."""

        counts = Counter(row.state for row in self.rows)
        return dict(sorted(counts.items()))

    def as_dict(self) -> dict[str, object]:
        """Serialize the snapshot for machine-readable output."""

        return {
            "requested_job_id": self.requested_job_id,
            "queried_user": self.queried_user,
            "include_all": self.include_all,
            "generated_at": self.generated_at,
            "run_name": self.run_name,
            "partition": self.partition,
            "array_range": self.array_range,
            "remote_job_dir": self.remote_job_dir,
            "state_counts": self.state_counts(),
            "rows": [asdict(row) for row in self.rows],
        }

    def to_display_payload(self) -> dict[str, object]:
        """Return the primitive payload expected by `display.py`."""

        return {
            "requested_job_id": self.requested_job_id,
            "queried_user": self.queried_user,
            "include_all": self.include_all,
            "generated_at": self.generated_at,
            "run_name": self.run_name,
            "partition": self.partition,
            "array_range": self.array_range,
            "remote_job_dir": self.remote_job_dir,
            "state_counts": self.state_counts(),
            "rows": [asdict(row) for row in self.rows],
        }


@click.command(
    name="status",
    short_help="Inspect SLURM job state.",
    help=(
        "Show running, pending, or completed SLURM job status for the current "
        "user or for a specific job."
    ),
)
@click.argument("job_id", required=False)
@click.option(
    "--all",
    "include_all",
    is_flag=True,
    help="Include recent completed and failed jobs from accounting data.",
)
@click.option(
    "--watch",
    "-w",
    is_flag=True,
    help="Refresh status continuously until interrupted.",
)
@click.option(
    "--interval",
    type=click.IntRange(1),
    default=30,
    show_default=True,
    help="Refresh interval in seconds when using --watch.",
)
@click.pass_context
def command(
    ctx: click.Context,
    job_id: str | None,
    include_all: bool,
    watch: bool,
    interval: int,
) -> None:
    """Render the first functional SLURM status workflow."""

    configure_logging(
        verbosity=_verbosity(ctx),
        colorize=_colorize_output(ctx),
    )

    json_output = _json_output(ctx)
    if watch and json_output:
        raise click.ClickException("`launchpad status --watch` does not support `--json` output.")

    console = build_console(no_color=not _colorize_output(ctx))

    try:
        if watch:
            with Live(console=console, refresh_per_second=4, vertical_overflow="visible") as live:
                snapshot = asyncio.run(
                    _run_status(
                        cwd=Path.cwd(),
                        env=os.environ,
                        job_id=job_id,
                        include_all=include_all,
                        watch=watch,
                        interval=interval,
                        on_snapshot=lambda item: live.update(
                            build_status_renderable(**item.to_display_payload()),
                            refresh=True,
                        ),
                    )
                )
        else:
            snapshot = asyncio.run(
                _run_status(
                    cwd=Path.cwd(),
                    env=os.environ,
                    job_id=job_id,
                    include_all=include_all,
                    watch=False,
                    interval=interval,
                )
            )
    except KeyboardInterrupt:
        click.echo("Interrupted.")
        raise click.exceptions.Exit(130) from None
    except (asyncssh.Error, RuntimeError, OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    if json_output:
        click.echo(json.dumps(snapshot.as_dict(), indent=2))
    elif not watch:
        console.print(build_status_renderable(**snapshot.to_display_payload()))


async def _run_status(
    *,
    cwd: Path,
    env: Mapping[str, str],
    job_id: str | None,
    include_all: bool,
    watch: bool,
    interval: int,
    on_snapshot: Callable[[StatusSnapshot], None] | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    max_iterations: int | None = None,
) -> StatusSnapshot:
    """Resolve config, query SLURM, and optionally poll for live updates."""

    resolved = resolve_config(cwd=cwd, env=env)

    async with ssh_session(resolved.config.ssh) as conn:
        async def fetch_snapshot() -> StatusSnapshot:
            return await _collect_status_snapshot(
                conn=conn,
                config=resolved.config,
                job_id=job_id,
                include_all=include_all,
            )

        if watch:
            return await _poll_status(
                fetch_snapshot,
                interval=interval,
                on_snapshot=on_snapshot,
                sleep=sleep,
                max_iterations=max_iterations,
            )

        snapshot = await fetch_snapshot()
        if on_snapshot is not None:
            on_snapshot(snapshot)
        return snapshot


async def _poll_status(
    fetch_snapshot: Callable[[], Awaitable[StatusSnapshot]],
    *,
    interval: int,
    on_snapshot: Callable[[StatusSnapshot], None] | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    max_iterations: int | None = None,
) -> StatusSnapshot:
    """Poll status repeatedly for `--watch`, emitting each new snapshot."""

    iteration = 0
    latest: StatusSnapshot | None = None

    while True:
        latest = await fetch_snapshot()
        if on_snapshot is not None:
            on_snapshot(latest)

        iteration += 1
        if max_iterations is not None and iteration >= max_iterations:
            return latest
        await sleep(interval)


async def _collect_status_snapshot(
    *,
    conn: asyncssh.SSHClientConnection,
    config: LaunchpadConfig,
    job_id: str | None,
    include_all: bool,
) -> StatusSnapshot:
    """Query SLURM and normalize the response into a status snapshot."""

    if job_id:
        active_jobs = await query_squeue(conn, config=config, job_id=job_id)
        accounting_jobs = await query_sacct(
            conn,
            config=config,
            job_id=job_id,
            duplicates=True,
        )
        return _build_detail_snapshot(
            requested_job_id=job_id,
            queried_user=config.ssh.username,
            active_jobs=active_jobs,
            accounting_jobs=accounting_jobs,
        )

    active_jobs = await query_squeue(conn, config=config)
    accounting_jobs: tuple[JobAccounting, ...] = ()
    if include_all:
        accounting_jobs = await query_sacct(
            conn,
            config=config,
            start_time=RECENT_ACCOUNTING_START,
        )

    return _build_overview_snapshot(
        queried_user=config.ssh.username,
        include_all=include_all,
        active_jobs=active_jobs,
        accounting_jobs=accounting_jobs,
    )


def _build_overview_snapshot(
    *,
    queried_user: str | None,
    include_all: bool,
    active_jobs: tuple[JobStatus, ...],
    accounting_jobs: tuple[JobAccounting, ...],
) -> StatusSnapshot:
    """Build the overview snapshot shown for current-user status queries."""

    active_rows = tuple(_row_from_status(item) for item in active_jobs)
    rows = list(active_rows)
    if include_all:
        seen = {_row_identity(row) for row in active_rows}
        for accounting_job in accounting_jobs:
            row = _row_from_accounting(accounting_job)
            if _row_identity(row) not in seen:
                rows.append(row)

    ordered_rows = tuple(sorted(rows, key=_row_sort_key))
    return StatusSnapshot(
        requested_job_id=None,
        queried_user=queried_user,
        include_all=include_all,
        generated_at=_timestamp_now(),
        rows=ordered_rows,
    )


def _build_detail_snapshot(
    *,
    requested_job_id: str,
    queried_user: str | None,
    active_jobs: tuple[JobStatus, ...],
    accounting_jobs: tuple[JobAccounting, ...],
) -> StatusSnapshot:
    """Build the detailed job snapshot shown for a specific job ID."""

    merged: dict[str, StatusRow] = {
        _row_identity(row): row for row in (_row_from_accounting(item) for item in accounting_jobs)
    }
    for active_job in active_jobs:
        status_row = _row_from_status(active_job)
        key = _row_identity(status_row)
        merged[key] = _merge_rows(merged.get(key), status_row)

    if not merged:
        raise click.ClickException(f"No SLURM job data found for {requested_job_id}.")

    ordered_rows = tuple(sorted(merged.values(), key=_row_sort_key))
    task_rows = tuple(row for row in ordered_rows if row.task_id is not None)
    display_rows = task_rows or ordered_rows
    primary_row = next((row for row in ordered_rows if row.task_id is None), None) or display_rows[0]

    return StatusSnapshot(
        requested_job_id=requested_job_id,
        queried_user=queried_user,
        include_all=True,
        generated_at=_timestamp_now(),
        rows=display_rows,
        run_name=primary_row.run_name,
        partition=primary_row.partition,
        array_range=_array_range(display_rows),
        remote_job_dir=primary_row.remote_job_dir,
    )


def _row_from_status(job: JobStatus) -> StatusRow:
    """Normalize a live `squeue` record to the command's row model."""

    return StatusRow(
        job_id=job.array_job_id or job.job_id,
        task_id=job.array_task_id,
        run_name=job.job_name,
        state=job.state,
        partition=job.partition,
        node=job.node_list,
        elapsed=job.elapsed,
        remote_job_dir=job.remote_job_dir,
        stdout_path=job.standard_output,
        stderr_path=job.standard_error,
        work_dir=job.work_dir,
        source="squeue",
    )


def _row_from_accounting(job: JobAccounting) -> StatusRow:
    """Normalize an accounting `sacct` record to the command's row model."""

    return StatusRow(
        job_id=job.array_job_id or job.job_id,
        task_id=job.array_task_id,
        run_name=job.job_name,
        state=job.state,
        partition=job.partition,
        node=job.node_list,
        elapsed=job.elapsed,
        total_cpu=job.total_cpu,
        max_rss=job.max_rss,
        remote_job_dir=job.remote_job_dir,
        stdout_path=job.standard_output,
        stderr_path=job.standard_error,
        work_dir=job.work_dir,
        source="sacct",
    )


def _merge_rows(existing: StatusRow | None, incoming: StatusRow) -> StatusRow:
    """Prefer live `squeue` fields while retaining accounting-only metrics."""

    if existing is None:
        return incoming

    return replace(
        existing,
        run_name=incoming.run_name or existing.run_name,
        state=incoming.state,
        partition=incoming.partition or existing.partition,
        node=incoming.node or existing.node,
        elapsed=incoming.elapsed or existing.elapsed,
        remote_job_dir=incoming.remote_job_dir or existing.remote_job_dir,
        stdout_path=incoming.stdout_path or existing.stdout_path,
        stderr_path=incoming.stderr_path or existing.stderr_path,
        work_dir=incoming.work_dir or existing.work_dir,
        source=incoming.source,
    )


def _row_identity(row: StatusRow) -> str:
    task_id = row.task_id or ""
    return f"{row.job_id}:{task_id}"


def _row_sort_key(row: StatusRow) -> tuple[int, int, int, str]:
    return (
        _sort_int(row.job_id),
        1 if row.task_id is None else 0,
        _sort_int(row.task_id),
        row.run_name or "",
    )


def _sort_int(value: str | None) -> int:
    if value is None:
        return -1
    try:
        return int(value)
    except ValueError:
        return 10**9


def _array_range(rows: tuple[StatusRow, ...]) -> str | None:
    task_ids = [row.task_id for row in rows if row.task_id is not None]
    if not task_ids:
        return None

    if all(task_id.isdigit() for task_id in task_ids):
        ordered = sorted(int(task_id) for task_id in task_ids)
        lower = ordered[0]
        upper = ordered[-1]
        return str(lower) if lower == upper else f"{lower}-{upper}"

    return ",".join(sorted(task_ids))


def _timestamp_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _verbosity(ctx: click.Context) -> int:
    options = getattr(ctx.find_root(), "obj", None)
    return int(getattr(options, "verbose", 0))


def _json_output(ctx: click.Context) -> bool:
    options = getattr(ctx.find_root(), "obj", None)
    return bool(getattr(options, "json_output", False))


def _colorize_output(ctx: click.Context) -> bool:
    options = getattr(ctx.find_root(), "obj", None)
    no_color = bool(getattr(options, "no_color", False))
    return not no_color and "NO_COLOR" not in os.environ
