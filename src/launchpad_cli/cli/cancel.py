"""`launchpad cancel` command for remote SLURM cancellation."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, replace
from pathlib import Path

import asyncssh
import click
from loguru import logger
from rich.console import Group
from rich.text import Text

from launchpad_cli.core.config import LaunchpadConfig, resolve_config
from launchpad_cli.core.logging import configure_logging
from launchpad_cli.core.slurm import (
    JobAccounting,
    JobStatus,
    build_scancel_command,
    query_sacct,
    query_squeue,
    run_slurm_command,
)
from launchpad_cli.core.ssh import ssh_session
from launchpad_cli.core.task_selectors import load_job_manifest, resolve_task_ids
from launchpad_cli.display import (
    build_console,
    build_detail_panel,
    build_next_steps_panel,
    build_summary_table,
)


@dataclass(frozen=True, slots=True)
class CancelJobRow:
    """Minimal scheduler metadata needed to resolve task selectors."""

    job_id: str
    task_id: str | None
    remote_job_dir: str | None = None
    source: str = "squeue"


@dataclass(frozen=True, slots=True)
class CancelResult:
    """Structured cancellation response."""

    job_id: str
    task_ids: tuple[str, ...]
    target: str

    @property
    def message(self) -> str:
        """Return the human-readable cancellation summary."""

        return _success_text(self.job_id, self.task_ids)

    def as_dict(self) -> dict[str, object]:
        """Serialize the cancellation response for `--json` output."""

        return {
            "job_id": self.job_id,
            "task_ids": list(self.task_ids),
            "target": self.target,
            "message": self.message,
        }


@click.command(
    name="cancel",
    short_help="Cancel a running or queued job.",
    help="Cancel an entire SLURM job or selected array tasks.",
)
@click.argument("job_id")
@click.argument("task_refs", nargs=-1)
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
@click.pass_context
def command(
    ctx: click.Context,
    job_id: str,
    task_refs: tuple[str, ...],
    yes: bool,
) -> None:
    """Cancel the requested SLURM job or selected array tasks."""

    json_output = _json_output(ctx)
    configure_logging(
        verbosity=_verbosity(ctx),
        colorize=_colorize_output(ctx),
    )
    console = build_console(stderr=json_output, no_color=not _colorize_output(ctx))

    try:
        normalized_task_refs = _normalize_task_refs(task_refs)
        resolved_task_ids = _resolve_local_task_ids(normalized_task_refs)
        if resolved_task_ids is None:
            resolved_task_ids = asyncio.run(
                _resolve_cancel_task_ids(
                    cwd=Path.cwd(),
                    env=os.environ,
                    job_id=job_id,
                    task_refs=normalized_task_refs,
                )
            )
        if not yes and not json_output:
            console.print(_build_cancel_preview(job_id, resolved_task_ids))
        if not yes and not click.confirm(
            _confirmation_text(job_id, resolved_task_ids),
            default=True,
            err=json_output,
        ):
            raise click.ClickException("Cancellation aborted.")

        result = asyncio.run(
            _run_cancel(
                cwd=Path.cwd(),
                env=os.environ,
                job_id=job_id,
                task_ids=resolved_task_ids,
            )
        )
    except (asyncssh.Error, RuntimeError, OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    if json_output:
        click.echo(json.dumps(result.as_dict(), indent=2))
    else:
        console.print(_build_cancel_result_renderable(result))


async def _run_cancel(
    *,
    cwd: Path,
    env: dict[str, str],
    job_id: str,
    task_ids: tuple[str, ...],
) -> CancelResult:
    """Resolve config, invoke remote `scancel`, and summarize the action."""

    resolved = resolve_config(cwd=cwd, env=env)

    async with ssh_session(resolved.config.ssh) as conn:
        target = _cancel_target(job_id, task_ids)
        logger.trace("Cancelling SLURM target {}", target)
        command = build_scancel_command(target=target)
        await run_slurm_command(
            conn,
            command,
            failure_prefix=f"SLURM cancellation failed for {target}",
            executable="scancel",
        )

    return CancelResult(job_id=job_id, task_ids=task_ids, target=target)


async def _resolve_cancel_task_ids(
    *,
    cwd: Path,
    env: dict[str, str],
    job_id: str,
    task_refs: tuple[str, ...],
) -> tuple[str, ...]:
    """Resolve manifest-backed task refs into concrete SLURM task IDs."""

    if not task_refs:
        return ()

    resolved = resolve_config(cwd=cwd, env=env)

    async with ssh_session(resolved.config.ssh) as conn:
        rows = await _query_job_rows(conn, resolved.config, job_id=job_id)
        manifest = await load_job_manifest(conn, _remote_job_dir(rows))
        return resolve_task_ids(
            task_refs,
            manifest=manifest,
            available_task_ids=tuple(row.task_id for row in rows if row.task_id is not None),
            job_id=job_id,
        )


async def _query_job_rows(
    conn: asyncssh.SSHClientConnection,
    config: LaunchpadConfig,
    *,
    job_id: str,
) -> tuple[CancelJobRow, ...]:
    """Fetch enough scheduler state to validate cancel selectors."""

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

    merged: dict[str, CancelJobRow] = {
        _row_identity(row): row for row in (_row_from_accounting(item) for item in accounting_jobs)
    }
    for active_job in active_jobs:
        row = _row_from_status(active_job)
        merged[_row_identity(row)] = _merge_rows(merged.get(_row_identity(row)), row)

    if merged:
        return tuple(sorted(merged.values(), key=_row_sort_key))
    if errors:
        raise RuntimeError(" ; ".join(errors))
    raise RuntimeError(f"No SLURM job data found for {job_id}.")


def _normalize_task_refs(task_refs: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for task_ref in task_refs:
        cleaned = task_ref.strip()
        if not cleaned:
            raise click.ClickException("Task references must not be empty.")
        normalized.append(cleaned)
    return tuple(dict.fromkeys(normalized))


def _resolve_local_task_ids(task_refs: tuple[str, ...]) -> tuple[str, ...] | None:
    if not task_refs:
        return ()
    if not all(task_ref.isdigit() for task_ref in task_refs):
        return None
    if any(task_ref != str(int(task_ref)) for task_ref in task_refs):
        return None
    return tuple(task_refs)


def _cancel_target(job_id: str, task_ids: tuple[str, ...]) -> str:
    if not task_ids:
        return job_id
    return ",".join(f"{job_id}_{task_id}" for task_id in task_ids)


def _confirmation_text(job_id: str, task_ids: tuple[str, ...]) -> str:
    if not task_ids:
        return f"Proceed with cancellation for SLURM job {job_id}?"
    return f"Proceed with cancellation for SLURM job {job_id} task(s) {', '.join(task_ids)}?"


def _success_text(job_id: str, task_ids: tuple[str, ...]) -> str:
    if not task_ids:
        return f"Cancelled job {job_id}."
    return f"Cancelled job {job_id} task(s): {', '.join(task_ids)}."


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


def _build_cancel_preview(job_id: str, task_ids: tuple[str, ...]) -> Group:
    """Render the human-facing preview before a destructive cancel action."""

    intro = Text()
    intro.append("This sends ", style="lp.brand.subtle")
    intro.append("scancel", style="lp.brand.secondary")
    intro.append(
        " immediately once you confirm.",
        style="lp.brand.subtle",
    )
    return Group(
        build_detail_panel(
            Group(intro, _build_cancel_summary(job_id, task_ids, target=_cancel_target(job_id, task_ids))),
            title="Cancel Preview",
            tone="warn",
        ),
        build_next_steps_panel(
            [
                "Review the target below before confirming.",
                "Use Ctrl+C now if you do not want to send the cancellation request.",
            ],
            title="What Happens Next",
        ),
    )


def _build_cancel_result_renderable(result: CancelResult) -> Group:
    """Render the post-cancel success summary."""

    intro = Text()
    intro.append("Cancellation requested. ", style="lp.brand.secondary")
    intro.append(
        "SLURM may take a moment to reflect the new state.",
        style="lp.brand.subtle",
    )
    summary = _build_cancel_summary(result.job_id, result.task_ids, target=result.target)
    summary.add_row("Result", result.message)
    return Group(
        build_detail_panel(
            Group(intro, summary),
            title="Cancellation Requested",
            tone="success",
        ),
        build_next_steps_panel(
            [
                f"launchpad status {result.job_id}",
                f"launchpad logs {result.job_id}",
            ]
        ),
    )


def _build_cancel_summary(job_id: str, task_ids: tuple[str, ...], *, target: str):
    summary = build_summary_table()
    summary.add_row("Job", job_id)
    summary.add_row("Scope", _task_scope_label(task_ids))
    summary.add_row("Tasks", ", ".join(task_ids) if task_ids else "all tasks")
    summary.add_row("Target", target)
    return summary


def _task_scope_label(task_ids: tuple[str, ...]) -> str:
    if not task_ids:
        return "whole job"
    return f"{len(task_ids)} selected task(s)"


def _row_from_status(job: JobStatus) -> CancelJobRow:
    return CancelJobRow(
        job_id=job.array_job_id or job.job_id,
        task_id=job.array_task_id,
        remote_job_dir=job.remote_job_dir,
        source="squeue",
    )


def _row_from_accounting(job: JobAccounting) -> CancelJobRow:
    return CancelJobRow(
        job_id=job.array_job_id or job.job_id,
        task_id=job.array_task_id,
        remote_job_dir=job.remote_job_dir,
        source="sacct",
    )


def _merge_rows(existing: CancelJobRow | None, incoming: CancelJobRow) -> CancelJobRow:
    if existing is None:
        return incoming
    return replace(
        existing,
        remote_job_dir=incoming.remote_job_dir or existing.remote_job_dir,
        source=incoming.source,
    )


def _row_identity(row: CancelJobRow) -> str:
    return f"{row.job_id}:{row.task_id or ''}"


def _row_sort_key(row: CancelJobRow) -> tuple[int, int]:
    return (_sort_int(row.job_id), _sort_int(row.task_id))


def _sort_int(value: str | None) -> int:
    if value is None:
        return -1
    try:
        return int(value)
    except ValueError:
        return 10**9


def _remote_job_dir(rows: tuple[CancelJobRow, ...]) -> str | None:
    for row in rows:
        if row.remote_job_dir:
            return row.remote_job_dir
    return None
