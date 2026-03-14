"""`launchpad cleanup` command for remote job-directory removal."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Mapping

import asyncssh
import click
from loguru import logger
from rich.table import Table

from launchpad_cli.core.config import LaunchpadConfig, resolve_config
from launchpad_cli.core.logging import configure_logging
from launchpad_cli.core.remote_ops import delete_remote_path, list_remote_directory, measure_remote_path
from launchpad_cli.core.slurm import JobAccounting, JobStatus, query_sacct, query_squeue
from launchpad_cli.core.ssh import ssh_session
from launchpad_cli.display import build_console

TERMINAL_STATES = {
    "BOOT_FAIL",
    "CANCELLED",
    "COMPLETED",
    "DEADLINE",
    "FAILED",
    "NODE_FAIL",
    "OUT_OF_MEMORY",
    "PREEMPTED",
    "TIMEOUT",
}
AGE_PATTERN = re.compile(r"^(?P<value>\d+)(?P<unit>[smhdw])$")
AGE_MULTIPLIERS = {
    "s": 1,
    "m": 60,
    "h": 60 * 60,
    "d": 60 * 60 * 24,
    "w": 60 * 60 * 24 * 7,
}


@dataclass(frozen=True, slots=True)
class CleanupJobRow:
    """Minimal scheduler metadata needed to resolve cleanup targets."""

    job_id: str
    task_id: str | None
    state: str
    remote_job_dir: str | None = None


@dataclass(frozen=True, slots=True)
class CleanupTarget:
    """A concrete remote directory candidate for cleanup."""

    label: str
    path: str
    size_bytes: int
    modified_epoch: float | None
    source: str


@dataclass(frozen=True, slots=True)
class CleanupResult:
    """Structured cleanup response for human and JSON output."""

    requested_job_ids: tuple[str, ...]
    older_than: str | None
    selected_targets: tuple[CleanupTarget, ...]
    deleted_paths: tuple[str, ...]

    @property
    def message(self) -> str:
        """Return the human-readable cleanup summary."""

        if not self.selected_targets:
            return "No matching remote job directories found."
        return _cleanup_summary(list(self.deleted_paths))

    def as_dict(self) -> dict[str, object]:
        """Serialize the cleanup result for `--json` output."""

        return {
            "requested_job_ids": list(self.requested_job_ids),
            "older_than": self.older_than,
            "selected_targets": [asdict(target) for target in self.selected_targets],
            "deleted_paths": list(self.deleted_paths),
            "deleted_count": len(self.deleted_paths),
            "message": self.message,
        }


@click.command(
    name="cleanup",
    short_help="Remove remote job directories.",
    help="Delete remote job directories after results have been collected.",
)
@click.argument("job_ids", nargs=-1)
@click.option(
    "--older-than",
    help="Only consider directories older than the supplied age, for example `30d`.",
)
@click.option("--yes", is_flag=True, help="Delete the selected directories without confirmation.")
@click.pass_context
def command(
    ctx: click.Context,
    job_ids: tuple[str, ...],
    older_than: str | None,
    yes: bool,
) -> None:
    """Delete remote job directories resolved from job IDs or the user root."""

    json_output = _json_output(ctx)
    configure_logging(
        verbosity=_verbosity(ctx),
        colorize=_colorize_output(ctx),
    )

    console = build_console(stderr=json_output, no_color=not _colorize_output(ctx))

    try:
        result = asyncio.run(
            _run_cleanup(
                cwd=Path.cwd(),
                env=os.environ,
                console=console,
                job_ids=job_ids,
                older_than=older_than,
                yes=yes,
                json_output=json_output,
            )
        )
    except (asyncssh.Error, RuntimeError, OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    if json_output:
        click.echo(json.dumps(result.as_dict(), indent=2))
    elif result.message:
        click.echo(result.message)


async def _run_cleanup(
    *,
    cwd: Path,
    env: Mapping[str, str],
    console,
    job_ids: tuple[str, ...],
    older_than: str | None,
    yes: bool,
    json_output: bool,
) -> CleanupResult:
    """Resolve cleanup targets, confirm the selection, and delete remotely."""

    resolved = resolve_config(cwd=cwd, env=env)
    older_than_seconds = _parse_older_than(older_than)

    async with ssh_session(resolved.config.ssh) as conn:
        if job_ids:
            targets = await _cleanup_targets_for_job_ids(
                conn,
                resolved.config,
                job_ids=job_ids,
                older_than_seconds=older_than_seconds,
            )
        else:
            targets = await _discover_cleanup_targets(
                conn,
                resolved.config,
                older_than_seconds=older_than_seconds,
                now=time.time(),
            )

        if not targets:
            logger.trace("Cleanup found no matching remote job directories")
            return CleanupResult(
                requested_job_ids=job_ids,
                older_than=older_than,
                selected_targets=(),
                deleted_paths=(),
            )

        if not job_ids:
            console.print(_build_target_table(targets, title="Cleanup Candidates"))
            selected_targets = _select_targets_from_prompt(targets, yes=yes, err=json_output)
        else:
            selected_targets = targets

        if not selected_targets:
            raise click.ClickException("Cleanup aborted.")

        if not yes and not click.confirm(_confirmation_text(selected_targets), default=False, err=json_output):
            raise click.ClickException("Cleanup aborted.")

        deleted_paths: list[str] = []
        logger.trace("Deleting {} remote cleanup target(s)", len(selected_targets))
        for target in selected_targets:
            deleted_paths.append(await delete_remote_path(conn, target.path))

    return CleanupResult(
        requested_job_ids=job_ids,
        older_than=older_than,
        selected_targets=selected_targets,
        deleted_paths=tuple(deleted_paths),
    )


async def _cleanup_targets_for_job_ids(
    conn: asyncssh.SSHClientConnection,
    config: LaunchpadConfig,
    *,
    job_ids: tuple[str, ...],
    older_than_seconds: int | None,
) -> tuple[CleanupTarget, ...]:
    """Resolve remote job directories from scheduler metadata for specific job IDs."""

    targets: list[CleanupTarget] = []
    seen: set[str] = set()
    cutoff = time.time() - older_than_seconds if older_than_seconds is not None else None

    for job_id in job_ids:
        rows = await _query_job_rows(conn, config, job_id=job_id)
        if any(row.state.upper() not in TERMINAL_STATES for row in rows):
            raise click.ClickException(
                f"Cleanup only supports terminal jobs. Job {job_id} still has non-terminal task state."
            )

        remote_dirs = {row.remote_job_dir for row in rows if row.remote_job_dir}
        if not remote_dirs:
            raise click.ClickException(f"No remote job directory was found for job {job_id}.")
        if len(remote_dirs) != 1:
            raise click.ClickException(f"Cleanup target for job {job_id} is ambiguous.")

        remote_path = remote_dirs.pop()
        if remote_path in seen:
            continue

        target = await _load_cleanup_target(
            conn,
            remote_path,
            label=job_id,
            source="job-id",
        )
        if cutoff is not None and (target.modified_epoch is None or target.modified_epoch > cutoff):
            continue
        targets.append(target)
        seen.add(remote_path)

    return tuple(targets)


async def _discover_cleanup_targets(
    conn: asyncssh.SSHClientConnection,
    config: LaunchpadConfig,
    *,
    older_than_seconds: int | None,
    now: float,
) -> tuple[CleanupTarget, ...]:
    """List candidate directories beneath the configured user root."""

    remote_root = _default_remote_root(config)
    entries = await list_remote_directory(conn, remote_root, recursive=False)
    cutoff = now - older_than_seconds if older_than_seconds is not None else None

    targets: list[CleanupTarget] = []
    for entry in entries:
        if not entry.is_dir:
            continue
        if cutoff is not None and (entry.modified_epoch is None or entry.modified_epoch > cutoff):
            continue
        targets.append(
            CleanupTarget(
                label=entry.name,
                path=entry.path,
                size_bytes=await measure_remote_path(conn, entry.path),
                modified_epoch=entry.modified_epoch,
                source="root-scan",
            )
        )

    return tuple(sorted(targets, key=lambda item: item.label))


async def _load_cleanup_target(
    conn: asyncssh.SSHClientConnection,
    remote_path: str,
    *,
    label: str,
    source: str,
) -> CleanupTarget:
    """Load size and timestamp metadata for a concrete remote directory path."""

    normalized = str(PurePosixPath(remote_path))
    parent = str(PurePosixPath(normalized).parent)
    entries = await list_remote_directory(conn, parent, recursive=False)
    entry = next((candidate for candidate in entries if candidate.path == normalized), None)
    if entry is None:
        raise click.ClickException(f"Cleanup target does not exist: {normalized}")

    return CleanupTarget(
        label=label,
        path=normalized,
        size_bytes=await measure_remote_path(conn, normalized),
        modified_epoch=entry.modified_epoch,
        source=source,
    )


def _select_targets_from_prompt(
    targets: tuple[CleanupTarget, ...],
    *,
    yes: bool,
    err: bool,
) -> tuple[CleanupTarget, ...]:
    """Select cleanup targets interactively when no explicit job IDs were provided."""

    if yes:
        return targets

    response = click.prompt(
        "Directories to delete (comma-separated numbers, `all`, or `none`)",
        default="none",
        show_default=False,
        err=err,
    ).strip()

    if not response or response.lower() == "none":
        return ()
    if response.lower() == "all":
        return targets

    selected_indices: list[int] = []
    for part in response.split(","):
        cleaned = part.strip()
        if not cleaned.isdigit():
            raise click.ClickException(f"Cleanup selection must use numbers, `all`, or `none`. Received `{cleaned}`.")
        index = int(cleaned)
        if index < 1 or index > len(targets):
            raise click.ClickException(f"Cleanup selection `{index}` is out of range.")
        if index not in selected_indices:
            selected_indices.append(index)

    return tuple(targets[index - 1] for index in selected_indices)


def _parse_older_than(raw: str | None) -> int | None:
    if raw is None:
        return None

    match = AGE_PATTERN.fullmatch(raw.strip().lower())
    if match is None:
        raise click.ClickException(
            "`--older-than` must use a duration like `30d`, `12h`, or `90m`."
        )

    value = int(match.group("value"))
    unit = match.group("unit")
    return value * AGE_MULTIPLIERS[unit]


def _default_remote_root(config: LaunchpadConfig) -> str:
    username = config.ssh.username
    if not username:
        raise click.ClickException("Cannot resolve cleanup targets without `ssh.username`.")
    return str(PurePosixPath(config.cluster.shared_root) / username)


async def _query_job_rows(
    conn: asyncssh.SSHClientConnection,
    config: LaunchpadConfig,
    *,
    job_id: str,
) -> tuple[CleanupJobRow, ...]:
    """Fetch and merge scheduler rows for the requested cleanup job."""

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

    merged: dict[str, CleanupJobRow] = {
        _row_key(row): row for row in (_row_from_accounting(item) for item in accounting_jobs)
    }
    for active_job in active_jobs:
        row = _row_from_status(active_job)
        merged[_row_key(row)] = _merge_rows(merged.get(_row_key(row)), row)

    if merged:
        return tuple(sorted(merged.values(), key=_row_sort_key))
    if errors:
        raise RuntimeError(" ; ".join(errors))
    raise click.ClickException(f"No SLURM job data found for {job_id}.")


def _row_from_status(job: JobStatus) -> CleanupJobRow:
    return CleanupJobRow(
        job_id=job.array_job_id or job.job_id,
        task_id=job.array_task_id,
        state=job.state,
        remote_job_dir=job.remote_job_dir,
    )


def _row_from_accounting(job: JobAccounting) -> CleanupJobRow:
    return CleanupJobRow(
        job_id=job.array_job_id or job.job_id,
        task_id=job.array_task_id,
        state=job.state,
        remote_job_dir=job.remote_job_dir,
    )


def _merge_rows(existing: CleanupJobRow | None, incoming: CleanupJobRow) -> CleanupJobRow:
    if existing is None:
        return incoming
    return replace(
        existing,
        state=incoming.state,
        remote_job_dir=incoming.remote_job_dir or existing.remote_job_dir,
    )


def _row_key(row: CleanupJobRow) -> str:
    return f"{row.job_id}:{row.task_id or ''}"


def _row_sort_key(row: CleanupJobRow) -> tuple[int, int, int]:
    return (
        _sort_int(row.job_id),
        1 if row.task_id is None else 0,
        _sort_int(row.task_id),
    )


def _sort_int(value: str | None) -> int:
    if value is None:
        return -1
    try:
        return int(value)
    except ValueError:
        return 10**9


def _build_target_table(targets: tuple[CleanupTarget, ...], *, title: str) -> Table:
    table = Table(title=title, show_header=True, header_style="bold")
    table.add_column("#", justify="right")
    table.add_column("Label")
    table.add_column("Size", justify="right")
    table.add_column("Modified")
    table.add_column("Path")

    for index, target in enumerate(targets, start=1):
        table.add_row(
            str(index),
            target.label,
            _format_bytes(target.size_bytes),
            _format_timestamp(target.modified_epoch),
            target.path,
        )

    return table


def _confirmation_text(targets: tuple[CleanupTarget, ...]) -> str:
    labels = ", ".join(target.label for target in targets)
    return f"Delete remote director{'y' if len(targets) == 1 else 'ies'}: {labels}?"


def _cleanup_summary(paths: list[str]) -> str:
    joined = ", ".join(paths)
    return f"Deleted {len(paths)} remote director{'y' if len(paths) == 1 else 'ies'}: {joined}"


def _format_bytes(size_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    value = float(size_bytes)
    unit = units[0]
    for unit in units:
        if abs(value) < 1024 or unit == units[-1]:
            break
        value /= 1024
    if unit == "B":
        return f"{int(value)} {unit}"
    return f"{value:.1f} {unit}"


def _format_timestamp(value: float | None) -> str:
    if value is None:
        return "—"
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(value))


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
