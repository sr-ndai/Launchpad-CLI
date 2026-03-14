"""`launchpad logs` command for remote SLURM and solver log inspection."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Callable

import asyncssh
import click
from loguru import logger
from rich.console import Group
from rich.text import Text

from launchpad_cli.core.config import LaunchpadConfig, resolve_config
from launchpad_cli.core.logging import configure_logging
from launchpad_cli.core.slurm import JobAccounting, JobStatus, query_sacct, query_squeue
from launchpad_cli.core.ssh import ssh_session
from launchpad_cli.display import (
    build_console,
    build_detail_panel,
    build_next_steps_panel,
    build_status_badge,
    build_summary_table,
)
from launchpad_cli.solvers import AnsysAdapter, NastranAdapter


@dataclass(frozen=True, slots=True)
class JobLogRow:
    """Minimal job metadata needed to resolve remote log paths."""

    job_id: str
    task_id: str | None
    run_name: str | None
    state: str
    stdout_path: str | None = None
    stderr_path: str | None = None
    work_dir: str | None = None
    remote_job_dir: str | None = None
    source: str = "squeue"


@dataclass(frozen=True, slots=True)
class LogsResult:
    """Structured response for buffered log reads."""

    job_id: str
    task_id: str | None
    run_name: str | None
    state: str
    log_kind: str
    remote_path: str
    lines: int
    content: str

    def as_dict(self) -> dict[str, object]:
        """Serialize the log read for `--json` output."""

        return {
            "job_id": self.job_id,
            "task_id": self.task_id,
            "run_name": self.run_name,
            "state": self.state,
            "log_kind": self.log_kind,
            "remote_path": self.remote_path,
            "lines": self.lines,
            "content": self.content,
        }


@click.command(
    name="logs",
    short_help="Inspect remote log output.",
    help="View or follow SLURM and solver logs for a submitted job.",
)
@click.argument("job_id")
@click.argument("task_id", required=False)
@click.option("--follow", "-f", is_flag=True, help="Continuously follow the remote log output.")
@click.option(
    "--lines",
    "-n",
    type=click.IntRange(1),
    default=50,
    show_default=True,
    help="Number of lines to show from the end of the log.",
)
@click.option("--solver-log", is_flag=True, help="View the solver log instead of the SLURM stdout log.")
@click.option("--err", is_flag=True, help="View the SLURM stderr log instead of stdout.")
@click.pass_context
def command(
    ctx: click.Context,
    job_id: str,
    task_id: str | None,
    follow: bool,
    lines: int,
    solver_log: bool,
    err: bool,
) -> None:
    """Resolve the requested remote log path and print or follow its content."""

    json_output = _json_output(ctx)
    if solver_log and err:
        raise click.ClickException("`launchpad logs` accepts either `--solver-log` or `--err`, not both.")
    if follow and json_output:
        raise click.ClickException("`launchpad logs --follow` does not support `--json` output.")

    configure_logging(
        verbosity=_verbosity(ctx),
        colorize=_colorize_output(ctx),
    )
    console = build_console(no_color=not _colorize_output(ctx))

    try:
        result = asyncio.run(
            _run_logs(
                cwd=Path.cwd(),
                env=os.environ,
                job_id=job_id,
                task_id=task_id,
                follow=follow,
                lines=lines,
                solver_log=solver_log,
                err=err,
                on_ready=(
                    lambda item: console.print(_build_live_logs_renderable(item))
                    if follow and not json_output
                    else None
                ),
            )
        )
    except KeyboardInterrupt:
        click.echo("Interrupted.")
        raise click.exceptions.Exit(130) from None
    except (asyncssh.Error, RuntimeError, OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    if follow:
        return
    if json_output:
        click.echo(json.dumps(result.as_dict(), indent=2))
    else:
        console.print(_build_logs_renderable(result))


async def _run_logs(
    *,
    cwd: Path,
    env: dict[str, str],
    job_id: str,
    task_id: str | None,
    follow: bool,
    lines: int,
    solver_log: bool,
    err: bool,
    on_ready: Callable[[LogsResult], None] | None = None,
) -> LogsResult:
    """Resolve config, locate the remote log path, and fetch its contents."""

    resolved = resolve_config(cwd=cwd, env=env)

    async with ssh_session(resolved.config.ssh) as conn:
        rows = await _query_job_rows(conn, resolved.config, job_id=job_id)
        row = _select_row(rows, job_id=job_id, requested_task_id=task_id)
        log_kind = _log_kind(solver_log=solver_log, err=err)
        remote_path = _resolve_remote_log_path(
            row,
            requested_task_id=task_id,
            solver_log=solver_log,
            err=err,
        )
        preview = LogsResult(
            job_id=row.job_id,
            task_id=row.task_id,
            run_name=row.run_name,
            state=row.state,
            log_kind=log_kind,
            remote_path=remote_path,
            lines=lines,
            content="",
        )
        if on_ready is not None:
            on_ready(preview)
        logger.trace("Reading {} log for job {} from {}", log_kind, job_id, remote_path)
        content = await _read_remote_log(
            conn,
            remote_path=remote_path,
            lines=lines,
            follow=follow,
        )
        return replace(preview, content=content)


async def _query_job_rows(
    conn: asyncssh.SSHClientConnection,
    config: LaunchpadConfig,
    *,
    job_id: str,
) -> tuple[JobLogRow, ...]:
    """Fetch and merge `squeue` and `sacct` data for the requested job."""

    active_jobs: tuple[JobStatus, ...] = ()
    accounting_jobs: tuple[JobAccounting, ...] = ()
    errors: list[str] = []

    try:
        active_jobs = await query_squeue(conn, config=config, job_id=job_id)
    except RuntimeError as exc:
        errors.append(str(exc))

    try:
        accounting_jobs = await query_sacct(conn, config=config, job_id=job_id, duplicates=True)
    except RuntimeError as exc:
        errors.append(str(exc))

    merged: dict[str, JobLogRow] = {
        _row_key(row): row for row in (_row_from_accounting(item) for item in accounting_jobs)
    }
    for active_job in active_jobs:
        row = _row_from_status(active_job)
        merged[_row_key(row)] = _merge_rows(merged.get(_row_key(row)), row)

    if merged:
        return tuple(sorted(merged.values(), key=_row_sort_key))
    if errors:
        raise RuntimeError(" ; ".join(errors))
    raise RuntimeError(f"No SLURM job data found for {job_id}.")


def _select_row(rows: tuple[JobLogRow, ...], *, job_id: str, requested_task_id: str | None) -> JobLogRow:
    """Select the requested task row or fail clearly if the choice is ambiguous."""

    if requested_task_id is not None:
        for row in rows:
            if row.task_id == requested_task_id:
                return row
        raise click.ClickException(f"No task `{requested_task_id}` was found for job {job_id}.")

    task_rows = tuple(row for row in rows if row.task_id is not None)
    if len(task_rows) == 1:
        return task_rows[0]
    if len(task_rows) > 1:
        raise click.ClickException(
            f"Job {job_id} has multiple task logs. Specify a TASK_ID explicitly."
        )
    return rows[0]


def _resolve_remote_log_path(
    row: JobLogRow,
    *,
    requested_task_id: str | None,
    solver_log: bool,
    err: bool,
) -> str:
    """Resolve the requested remote log path from the selected scheduler row."""

    if solver_log:
        return _solver_log_path(row, requested_task_id=requested_task_id)

    raw_path = row.stderr_path if err else row.stdout_path
    if not raw_path:
        kind = "stderr" if err else "stdout"
        raise RuntimeError(f"No SLURM {kind} path is available for job {row.job_id}.")

    return _substitute_slurm_tokens(raw_path, job_id=row.job_id, task_id=row.task_id or requested_task_id)


def _solver_log_path(row: JobLogRow, *, requested_task_id: str | None) -> str:
    """Build the conventional solver-log path within the task work directory."""

    if not row.work_dir:
        raise RuntimeError(f"No task work directory is available for job {row.job_id}.")

    work_dir = PurePosixPath(row.work_dir)
    effective_task_id = row.task_id or requested_task_id
    stem = _derive_input_stem(work_dir.name, task_id=effective_task_id)
    extension = _solver_output_extension(row.run_name)
    return str(work_dir / f"{stem}{extension}")


def _derive_input_stem(work_dir_name: str, *, task_id: str | None) -> str:
    prefix = "results_"
    if work_dir_name.startswith(prefix):
        stem = work_dir_name[len(prefix) :]
        if task_id and stem.endswith(f"_{task_id}"):
            stem = stem[: -(len(task_id) + 1)]
        return stem
    return work_dir_name


def _solver_output_extension(run_name: str | None) -> str:
    normalized = (run_name or "").lower()
    if normalized.startswith("ansys"):
        for extension in AnsysAdapter().output_extensions:
            if extension != ".err":
                return extension
        return AnsysAdapter().output_extensions[0]

    for extension in NastranAdapter().output_extensions:
        if extension != ".log":
            return extension
    return NastranAdapter().output_extensions[0]


async def _read_remote_log(
    conn: asyncssh.SSHClientConnection,
    *,
    remote_path: str,
    lines: int,
    follow: bool,
) -> str:
    """Read or follow a remote log file using `tail` on the cluster head node."""

    if follow:
        return await _stream_remote_log(conn, remote_path=remote_path, lines=lines)

    command = _build_tail_command(remote_path=remote_path, lines=lines, follow=follow)
    result = await conn.run(command, check=False)
    if result.exit_status != 0:
        raise RuntimeError(
            f"Remote log read failed for {remote_path}: "
            f"{result.stderr.strip() or result.stdout.strip() or 'unknown error'}"
        )
    return result.stdout


async def _stream_remote_log(
    conn: asyncssh.SSHClientConnection,
    *,
    remote_path: str,
    lines: int,
) -> str:
    """Stream a remote `tail -f` session line-by-line to the local terminal."""

    command = _build_tail_command(remote_path=remote_path, lines=lines, follow=True)
    process = await conn.create_process(command)
    captured: list[str] = []

    try:
        async for chunk in process.stdout:
            text = chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)
            captured.append(text)
            click.echo(text, nl=False)
    except asyncio.CancelledError:
        process.close()
        await process.wait_closed()
        raise

    await process.wait_closed()
    if process.exit_status not in (0, None):
        stderr = await _read_process_stream(process.stderr)
        raise RuntimeError(
            f"Remote log read failed for {remote_path}: {stderr.strip() or 'unknown error'}"
        )
    return "".join(captured)


def _build_tail_command(*, remote_path: str, lines: int, follow: bool) -> str:
    parts = ["tail", "-n", str(lines)]
    if follow:
        parts.append("-f")
    parts.append(str(PurePosixPath(remote_path)))
    return " ".join(shlex.quote(part) for part in parts)


def _substitute_slurm_tokens(path: str, *, job_id: str, task_id: str | None) -> str:
    resolved = path.replace("%A", job_id)
    if task_id is not None:
        resolved = resolved.replace("%a", task_id)
    return resolved


async def _read_process_stream(stream: object) -> str:
    reader = getattr(stream, "read", None)
    if not callable(reader):
        return ""
    payload = await reader()
    if isinstance(payload, bytes):
        return payload.decode("utf-8", errors="replace")
    return str(payload)


def _row_from_status(job: JobStatus) -> JobLogRow:
    return JobLogRow(
        job_id=job.array_job_id or job.job_id,
        task_id=job.array_task_id,
        run_name=job.job_name,
        state=job.state,
        stdout_path=job.standard_output,
        stderr_path=job.standard_error,
        work_dir=job.work_dir,
        remote_job_dir=job.remote_job_dir,
        source="squeue",
    )


def _row_from_accounting(job: JobAccounting) -> JobLogRow:
    return JobLogRow(
        job_id=job.array_job_id or job.job_id,
        task_id=job.array_task_id,
        run_name=job.job_name,
        state=job.state,
        stdout_path=job.standard_output,
        stderr_path=job.standard_error,
        work_dir=job.work_dir,
        remote_job_dir=job.remote_job_dir,
        source="sacct",
    )


def _merge_rows(existing: JobLogRow | None, incoming: JobLogRow) -> JobLogRow:
    if existing is None:
        return incoming
    return replace(
        existing,
        run_name=incoming.run_name or existing.run_name,
        state=incoming.state,
        stdout_path=incoming.stdout_path or existing.stdout_path,
        stderr_path=incoming.stderr_path or existing.stderr_path,
        work_dir=incoming.work_dir or existing.work_dir,
        remote_job_dir=incoming.remote_job_dir or existing.remote_job_dir,
        source=incoming.source,
    )


def _row_key(row: JobLogRow) -> str:
    return f"{row.job_id}:{row.task_id or ''}"


def _row_sort_key(row: JobLogRow) -> tuple[int, int]:
    task_value = int(row.task_id) if row.task_id and row.task_id.isdigit() else 10**9
    return (int(row.job_id) if row.job_id.isdigit() else 10**9, task_value)


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


def _log_kind(*, solver_log: bool, err: bool) -> str:
    if solver_log:
        return "solver"
    if err:
        return "stderr"
    return "stdout"


def _build_logs_renderable(result: LogsResult) -> Group:
    """Render the buffered log view in the shared Phase 7 layout."""

    intro = Text()
    intro.append("Remote log snapshot", style="lp.brand.secondary")
    intro.append(
        " for the selected SLURM target and log file.",
        style="lp.brand.subtle",
    )

    renderables = [
        build_detail_panel(
            Group(intro, _build_logs_summary(result)),
            title="Log Snapshot",
        )
    ]
    if result.content.strip():
        renderables.append(
            build_detail_panel(
                Text(result.content.rstrip("\n")),
                title="Tail Output",
            )
        )
    else:
        renderables.append(
            build_detail_panel(
                "The selected log is empty right now. The job may still be starting or this file has not been written yet.",
                title="No Log Output Yet",
                tone="warn",
            )
        )

    renderables.append(build_next_steps_panel(_logs_next_steps(result)))
    return Group(*renderables)


def _build_live_logs_renderable(result: LogsResult) -> Group:
    """Render the pre-stream banner for `launchpad logs --follow`."""

    intro = Text()
    intro.append("Streaming", style="lp.brand.secondary")
    intro.append(
        " the selected remote log. Press Ctrl+C to stop.",
        style="lp.brand.subtle",
    )
    return Group(
        build_detail_panel(
            Group(intro, _build_logs_summary(result)),
            title="Live Log Tail",
        )
    )


def _build_logs_summary(result: LogsResult):
    summary = build_summary_table()
    summary.add_row("Job", result.job_id)
    summary.add_row("Task", result.task_id or "—")
    summary.add_row("Run name", result.run_name or "—")
    summary.add_row("State", build_status_badge(result.state))
    summary.add_row("Log kind", result.log_kind)
    summary.add_row("Path", result.remote_path)
    summary.add_row("Lines", f"last {result.lines}")
    return summary


def _logs_next_steps(result: LogsResult) -> list[str]:
    steps = [f"launchpad status {result.job_id}"]
    if result.log_kind != "stderr":
        steps.append(f"{_logs_command(result)} --err")
    elif result.log_kind != "solver":
        steps.append(f"{_logs_command(result)} --solver-log")
    else:
        steps.append(f"{_logs_command(result)} --follow")

    if result.state.upper() == "COMPLETED":
        steps.append(f"launchpad download {result.job_id}")
    return steps


def _logs_command(result: LogsResult) -> str:
    parts = ["launchpad", "logs", result.job_id]
    if result.task_id:
        parts.append(result.task_id)
    return " ".join(parts)
