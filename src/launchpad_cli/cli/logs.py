"""`launchpad logs` command for remote SLURM and solver log inspection."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import sys
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Callable

import asyncssh
import click
from loguru import logger
from rich.console import Group
from rich.rule import Rule
from rich.text import Text

from launchpad_cli.core.config import LaunchpadConfig, resolve_config
from launchpad_cli.core.job_manifest import JobManifest, TaskReference
from launchpad_cli.core.logging import configure_logging
from launchpad_cli.core.slurm import JobAccounting, JobStatus, query_sacct, query_squeue
from launchpad_cli.core.ssh import ssh_session
from launchpad_cli.core.task_selectors import load_job_manifest, resolve_manifest_task_reference
from launchpad_cli.core.workspace import infer_remote_job_dir
from launchpad_cli.display import (
    build_console,
    build_inline_kv,
    build_next_steps,
    build_logs_picker_panel,
    build_spinner,
    build_warning_line,
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


@dataclass(frozen=True, slots=True)
class LogSelection:
    """Resolved task selection used to locate a remote log file."""

    row: JobLogRow
    task_ref: TaskReference | None = None


@dataclass(frozen=True, slots=True)
class LogPickerOption:
    """Resolved row metadata shown inside the interactive task picker."""

    row: JobLogRow
    task_ref: TaskReference | None
    label: str
    alias: str
    state: str
    log_kind: str
    filename: str


@click.command(
    name="logs",
    short_help="Inspect remote log output.",
    help="View or follow SLURM and solver logs for a submitted job.",
)
@click.argument("job_id")
@click.argument("task_ref", required=False)
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
@click.option(
    "--log-kind",
    help="View a named solver log kind from the submitted manifest, for example `telemetry`.",
)
@click.option("--err", is_flag=True, help="View the SLURM stderr log instead of stdout.")
@click.pass_context
def command(
    ctx: click.Context,
    job_id: str,
    task_ref: str | None,
    follow: bool,
    lines: int,
    solver_log: bool,
    log_kind: str | None,
    err: bool,
) -> None:
    """Resolve the requested remote log path and print or follow its content."""

    json_output = _json_output(ctx)
    colorize_output = _colorize_output(ctx)
    if sum(bool(item) for item in (solver_log, log_kind, err)) > 1:
        raise click.ClickException(
            "`launchpad logs` accepts only one of `--solver-log`, `--log-kind`, or `--err`. "
            "Specify exactly one log flag at a time."
        )
    if follow and json_output:
        raise click.ClickException(
            "`launchpad logs --follow` does not support `--json` output. "
            "Run without --follow or --json to get a buffered snapshot."
        )

    configure_logging(
        verbosity=_verbosity(ctx),
        colorize=colorize_output,
    )
    console = build_console(no_color=not colorize_output)

    try:
        result = asyncio.run(
            _run_logs(
                cwd=Path.cwd(),
                env=os.environ,
                console=console,
                job_id=job_id,
                task_ref=task_ref,
                follow=follow,
                lines=lines,
                solver_log=solver_log,
                log_kind=log_kind,
                err=err,
                colorize_output=colorize_output,
                on_ready=(
                    lambda item: console.print(_build_live_logs_renderable(item))
                    if follow and not json_output
                    else None
                ),
                on_picker=(lambda item: console.print(item)) if not json_output else None,
            )
        )
    except KeyboardInterrupt:
        console.print("  Interrupted.", style="lp.text.tertiary")
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
    console=None,
    job_id: str,
    task_ref: str | None,
    follow: bool,
    lines: int,
    solver_log: bool,
    log_kind: str | None,
    err: bool,
    colorize_output: bool,
    on_ready: Callable[[LogsResult], None] | None = None,
    on_picker: Callable[[object], None] | None = None,
) -> LogsResult:
    """Resolve config, locate the remote log path, and fetch its contents."""

    resolved = resolve_config(cwd=cwd, env=env)

    async with ssh_session(resolved.config.ssh) as conn:
        rows = await _query_job_rows(conn, resolved.config, job_id=job_id)
        remote_job_dir = _remote_job_dir(rows)
        if remote_job_dir is None:
            run_name = next((row.run_name for row in rows if row.run_name), None)
            if run_name:
                try:
                    remote_job_dir = await infer_remote_job_dir(
                        conn, resolved.config, run_name=run_name, job_id=job_id
                    )
                except Exception:
                    pass
        manifest = await load_job_manifest(conn, remote_job_dir)
        effective_log_kind = _log_kind(solver_log=solver_log, log_kind=log_kind, err=err)
        selection = await _select_row(
            rows,
            job_id=job_id,
            requested_task_ref=task_ref,
            manifest=manifest,
            remote_job_dir=remote_job_dir,
            log_kind=effective_log_kind,
            err=err,
            interactive=_supports_interactive_picker(),
            colorize_output=colorize_output,
            on_picker=on_picker,
        )
        remote_path = _resolve_remote_log_path(
            selection.row,
            remote_job_dir=remote_job_dir,
            manifest=manifest,
            selected_task_ref=selection.task_ref,
            log_kind=effective_log_kind,
            err=err,
        )
        preview = LogsResult(
            job_id=selection.row.job_id,
            task_id=selection.row.task_id,
            run_name=selection.row.run_name,
            state=selection.row.state,
            log_kind=effective_log_kind,
            remote_path=remote_path,
            lines=lines,
            content="",
        )
        if on_ready is not None:
            on_ready(preview)
        logger.trace("Reading {} log for job {} from {}", effective_log_kind, job_id, remote_path)
        if not follow and console is not None:
            with build_spinner(console, "Reading log..."):
                content = await _read_remote_log(
                    conn,
                    remote_path=remote_path,
                    lines=lines,
                    follow=follow,
                )
        else:
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


async def _select_row(
    rows: tuple[JobLogRow, ...],
    *,
    job_id: str,
    requested_task_ref: str | None,
    manifest: JobManifest | None,
    remote_job_dir: str | None,
    log_kind: str,
    err: bool,
    interactive: bool,
    colorize_output: bool,
    on_picker: Callable[[object], None] | None,
) -> LogSelection:
    """Select the requested task row or fail clearly if the choice is ambiguous."""

    task_rows = tuple(row for row in rows if row.task_id is not None)
    if requested_task_ref is not None:
        resolved_task_id, task_ref = _resolve_requested_task_id(
            requested_task_ref,
            job_id=job_id,
            task_rows=task_rows,
            manifest=manifest,
        )
        for row in rows:
            if row.task_id == resolved_task_id:
                return LogSelection(row=row, task_ref=task_ref)
        raise ValueError(f"No task `{resolved_task_id}` was found for job {job_id}.")

    if len(task_rows) == 1:
        return LogSelection(row=task_rows[0], task_ref=_task_ref_for_row(task_rows[0], manifest))
    if len(task_rows) > 1:
        if interactive:
            return await _pick_task_interactively(
                job_id=job_id,
                task_rows=task_rows,
                manifest=manifest,
                remote_job_dir=remote_job_dir,
                log_kind=log_kind,
                err=err,
                colorize_output=colorize_output,
                on_picker=on_picker,
            )
        raise click.ClickException(
            f"Job {job_id} has multiple task logs. Specify a TASK_REF explicitly. "
            f"Run launchpad status {job_id} to see available task IDs."
        )
    return LogSelection(row=rows[0])


def _resolve_requested_task_id(
    requested_task_ref: str,
    *,
    job_id: str,
    task_rows: tuple[JobLogRow, ...],
    manifest: JobManifest | None,
) -> tuple[str, TaskReference | None]:
    if manifest is not None:
        task_ref = resolve_manifest_task_reference(manifest, requested_task_ref, job_id=job_id)
        available = {row.task_id for row in task_rows if row.task_id is not None}
        if available and task_ref.task_id not in available:
            raise ValueError(
                f"Task selection did not match job rows for {job_id}: {task_ref.task_id}"
            )
        return task_ref.task_id, task_ref

    cleaned = requested_task_ref.strip()
    if not cleaned.isdigit():
        raise ValueError(
            f"Job {job_id} has no launchpad-manifest.json. "
            "Use a raw numeric task ID or resubmit the job to use aliases and file-based selectors."
        )
    return cleaned, None


def _task_ref_for_row(row: JobLogRow, manifest: JobManifest | None) -> TaskReference | None:
    if manifest is None or row.task_id is None:
        return None
    for item in manifest.tasks:
        if item.task_id == row.task_id:
            return item
    return None


async def _pick_task_interactively(
    *,
    job_id: str,
    task_rows: tuple[JobLogRow, ...],
    manifest: JobManifest | None,
    remote_job_dir: str | None,
    log_kind: str,
    err: bool,
    colorize_output: bool,
    on_picker: Callable[[object], None] | None,
) -> LogSelection:
    """Open the interactive task picker for ambiguous human `logs` flows."""

    options = _build_log_picker_options(
        task_rows,
        manifest=manifest,
        remote_job_dir=remote_job_dir,
        log_kind=log_kind,
        err=err,
    )
    if on_picker is not None:
        on_picker(
            build_logs_picker_panel(
                job_id=job_id,
                log_kind=log_kind,
                task_count=len(options),
            )
        )

    selected = await _launch_log_picker(options, colorize_output=colorize_output)
    if selected is None:
        raise click.ClickException("Log selection aborted.")
    return LogSelection(row=selected.row, task_ref=selected.task_ref)


def _build_log_picker_options(
    task_rows: tuple[JobLogRow, ...],
    *,
    manifest: JobManifest | None,
    remote_job_dir: str | None,
    log_kind: str,
    err: bool,
) -> tuple[LogPickerOption, ...]:
    """Build the human-facing picker rows for interactive task selection."""

    options: list[LogPickerOption] = []
    for row in task_rows:
        task_ref = _task_ref_for_row(row, manifest)
        remote_path = _resolve_remote_log_path(
            row,
            remote_job_dir=remote_job_dir,
            manifest=manifest,
            selected_task_ref=task_ref,
            log_kind=log_kind,
            err=err,
        )
        options.append(
            LogPickerOption(
                row=row,
                task_ref=task_ref,
                label=_picker_label(row, task_ref),
                alias=task_ref.alias if task_ref is not None else "-",
                state=row.state,
                log_kind=log_kind,
                filename=PurePosixPath(remote_path).name,
            )
        )
    return tuple(options)


def _picker_label(row: JobLogRow, task_ref: TaskReference | None) -> str:
    if task_ref is not None:
        return task_ref.display_label
    if row.work_dir:
        return _derive_input_stem(PurePosixPath(row.work_dir).name, task_id=row.task_id)
    if row.task_id is not None:
        return f"task {row.task_id}"
    return row.run_name or "job"


async def _launch_log_picker(
    options: tuple[LogPickerOption, ...],
    *,
    colorize_output: bool,
) -> LogPickerOption | None:
    """Run the dependency-backed interactive log picker and return the selection."""

    import questionary
    from prompt_toolkit.styles import Style
    from questionary import Choice

    widths = _picker_column_widths(options)
    message = "\n".join(
        [
            "Select the task log to open",
            _format_picker_row(
                label="Label",
                alias="Alias",
                task_id="Task",
                state="State",
                log_kind="Kind",
                filename="File",
                widths=widths,
            ),
        ]
    )
    style = (
        Style(
            [
                ("qmark", "fg:#3cc5d9 bold"),
                ("question", "fg:#d9edf7 bold"),
                ("pointer", "fg:#3cc5d9 bold"),
                ("highlighted", "fg:#d9edf7 bold"),
                ("answer", "fg:#3cc5d9 bold"),
                ("instruction", "fg:#7f9aab"),
            ]
        )
        if colorize_output
        else Style(
            [
                ("qmark", ""),
                ("question", ""),
                ("pointer", ""),
                ("highlighted", ""),
                ("answer", ""),
                ("instruction", ""),
            ]
        )
    )
    choices = [
        Choice(
            title=_format_picker_row(
                label=option.label,
                alias=option.alias,
                task_id=option.row.task_id or "-",
                state=option.state,
                log_kind=option.log_kind,
                filename=option.filename,
                widths=widths,
            ),
            value=option,
        )
        for option in options
    ]
    return await questionary.select(
        message,
        choices=choices,
        instruction="Use arrows to move and Enter to select",
        qmark="",
        pointer=">",
        use_shortcuts=False,
        style=style,
    ).ask_async()


def _picker_column_widths(options: tuple[LogPickerOption, ...]) -> dict[str, int]:
    return {
        "label": max(len("Label"), *(len(option.label) for option in options)),
        "alias": max(len("Alias"), *(len(option.alias) for option in options)),
        "task": max(len("Task"), *(len(option.row.task_id or "-") for option in options)),
        "state": max(len("State"), *(len(option.state) for option in options)),
        "kind": max(len("Kind"), *(len(option.log_kind) for option in options)),
    }


def _format_picker_row(
    *,
    label: str,
    alias: str,
    task_id: str,
    state: str,
    log_kind: str,
    filename: str,
    widths: dict[str, int],
) -> str:
    return (
        f"{label:<{widths['label']}}  "
        f"{alias:<{widths['alias']}}  "
        f"{task_id:>{widths['task']}}  "
        f"{state:<{widths['state']}}  "
        f"{log_kind:<{widths['kind']}}  "
        f"{filename}"
    )


def _resolve_remote_log_path(
    row: JobLogRow,
    *,
    remote_job_dir: str | None,
    manifest: JobManifest | None,
    selected_task_ref: TaskReference | None,
    log_kind: str,
    err: bool,
) -> str:
    """Resolve the requested remote log path from the selected scheduler row."""

    if log_kind not in {"stdout", "stderr"}:
        return _solver_log_path(
            row,
            remote_job_dir=remote_job_dir,
            manifest=manifest,
            selected_task_ref=selected_task_ref,
            log_kind=log_kind,
        )

    raw_path = row.stderr_path if err else row.stdout_path
    if not raw_path:
        kind = "stderr" if err else "stdout"
        raise RuntimeError(f"No SLURM {kind} path is available for job {row.job_id}.")

    return _substitute_slurm_tokens(raw_path, job_id=row.job_id, task_id=row.task_id)


def _solver_log_path(
    row: JobLogRow,
    *,
    remote_job_dir: str | None,
    manifest: JobManifest | None,
    selected_task_ref: TaskReference | None,
    log_kind: str,
) -> str:
    """Resolve solver-log paths from the submitted manifest when available."""

    if manifest is not None:
        if selected_task_ref is None:
            raise RuntimeError(f"No submitted task metadata is available for job {row.job_id}.")
        if not remote_job_dir:
            raise RuntimeError(f"No remote job directory metadata is available for job {row.job_id}.")

        extension = manifest.logs.get(log_kind)
        if not extension:
            available = ", ".join(sorted(manifest.logs))
            raise RuntimeError(
                f"Job {row.job_id} does not define log kind `{log_kind}` in launchpad-manifest.json. "
                f"Available kinds: {available}."
            )
        return str(
            PurePosixPath(remote_job_dir)
            / selected_task_ref.result_dir
            / f"{selected_task_ref.input_stem}{extension}"
        )

    if log_kind != "solver":
        raise RuntimeError(
            f"Job {row.job_id} has no launchpad-manifest.json. "
            f"`--log-kind {log_kind}` is unavailable for legacy jobs; use `--solver-log` instead."
        )

    if not row.work_dir:
        raise RuntimeError(f"No task work directory is available for job {row.job_id}.")

    work_dir = PurePosixPath(row.work_dir)
    stem = _derive_input_stem(work_dir.name, task_id=row.task_id)
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
        parts.extend(["--follow=name", "--retry"])
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


def _remote_job_dir(rows: tuple[JobLogRow, ...]) -> str | None:
    for row in rows:
        if row.remote_job_dir:
            return row.remote_job_dir
    return None


def _supports_interactive_picker() -> bool:
    return (
        hasattr(sys.stdin, "isatty")
        and sys.stdin.isatty()
        and hasattr(sys.stdout, "isatty")
        and sys.stdout.isatty()
    )


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


def _log_kind(*, solver_log: bool, log_kind: str | None, err: bool) -> str:
    if solver_log:
        return "solver"
    if log_kind:
        cleaned = log_kind.strip().lower()
        if not cleaned:
            raise ValueError("`--log-kind` requires a non-empty value.")
        return cleaned
    if err:
        return "stderr"
    return "stdout"


def _build_logs_renderable(result: LogsResult) -> Group:
    """Render the buffered log view with a minimal header and raw content."""

    renderables = [
        _build_logs_header(result),
        build_inline_kv("path", result.remote_path, label_width=8),
        Rule(style="lp.rule", align="left"),
    ]
    if result.content.strip():
        renderables.extend([Text(), Text(result.content.rstrip("\n"))])
    else:
        renderables.extend(
            [
                Text(),
                build_warning_line(
                    "No log output yet. The job may still be starting or this file has not been written yet."
                ),
                Text(),
                build_next_steps(_logs_next_steps(result)),
            ]
        )
    return Group(*renderables)


def _build_live_logs_renderable(result: LogsResult) -> Group:
    """Render the single header shown before `launchpad logs --follow` starts streaming."""

    return Group(
        _build_logs_header(result),
        build_inline_kv("path", result.remote_path, label_width=8),
        Rule(style="lp.rule", align="left"),
    )


def _build_logs_header(result: LogsResult) -> Text:
    """Return the minimal log identity line used by snapshot and follow flows."""

    header = Text("  Job ")
    header.append(result.job_id, style="lp.label")
    if result.task_id:
        header.append(f" · Task {result.task_id}", style="lp.value")
    if result.run_name:
        header.append(f" ({result.run_name})", style="lp.text.tertiary")
    header.append(f" · {_log_kind_label(result.log_kind)}", style="lp.text.secondary")
    return header


def _log_kind_label(log_kind: str) -> str:
    """Return the restrained display label for a resolved log kind."""

    if log_kind == "stdout":
        return "SLURM log"
    if log_kind == "stderr":
        return "SLURM stderr"
    if log_kind == "solver":
        return "solver log"
    return f"{log_kind} log"


def _logs_next_steps(result: LogsResult) -> list[str]:
    steps = [f"launchpad status {result.job_id}"]
    if result.log_kind != "stderr":
        steps.append(f"{_logs_command(result)} --err")
    if result.log_kind != "solver":
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
