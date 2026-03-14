"""`launchpad download` command and result-retrieval orchestration."""

from __future__ import annotations

import asyncio
import fnmatch
import os
import shlex
from collections import Counter
from contextlib import suppress
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Mapping

import asyncssh
import click
from rich.panel import Panel
from rich.table import Table

from launchpad_cli.core.compress import (
    create_remote_archive,
    compute_sha256,
    decompress_path,
    inspect_archive,
)
from launchpad_cli.core.config import LaunchpadConfig, resolve_config
from launchpad_cli.core.local_ops import ensure_directory, inspect_disk_space, resolve_download_destination
from launchpad_cli.core.logging import configure_logging
from launchpad_cli.core.remote_ops import (
    RemotePathEntry,
    compute_remote_sha256,
    delete_remote_path,
    list_remote_directory,
    measure_remote_path,
)
from launchpad_cli.core.slurm import JobAccounting, JobStatus, query_sacct, query_squeue
from launchpad_cli.core.ssh import ssh_session
from launchpad_cli.core.transfer import download as transfer_download
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
COMPRESSED_SIZE_ESTIMATE_RATIO = 0.25


@dataclass(frozen=True, slots=True)
class DownloadJobRow:
    """Minimal scheduler metadata needed for result retrieval."""

    job_id: str
    task_id: str | None
    run_name: str | None
    state: str
    remote_job_dir: str | None = None
    work_dir: str | None = None
    source: str = "squeue"


@dataclass(frozen=True, slots=True)
class RemoteSource:
    """A selected remote source directory for download work."""

    absolute_path: str
    relative_path: str


@dataclass(frozen=True, slots=True)
class DownloadPlan:
    """Resolved remote and local state for a single download execution."""

    job_id: str
    run_name: str
    remote_job_dir: str
    selected_rows: tuple[DownloadJobRow, ...]
    selected_tasks: tuple[str, ...]
    destination_dir: Path
    source_roots: tuple[RemoteSource, ...]
    raw_size_bytes: int
    transfer_mode: str
    transfer_size_estimate_bytes: int
    cleanup: bool
    force: bool
    exclude_patterns: tuple[str, ...]
    compression_level: int
    verify_checksums: bool
    local_archive_path: Path | None = None
    remote_archive_path: str | None = None

    @property
    def partial(self) -> bool:
        """Return whether the selection includes non-terminal task states."""

        return any(row.state.upper() not in TERMINAL_STATES for row in self.selected_rows)

    @property
    def required_local_bytes(self) -> int:
        """Return the local-space requirement for this transfer mode."""

        if self.transfer_mode == "archive":
            return self.raw_size_bytes + self.transfer_size_estimate_bytes
        return self.raw_size_bytes

    @property
    def state_counts(self) -> dict[str, int]:
        """Return a stable per-state summary for the selected rows."""

        counts = Counter(row.state for row in self.selected_rows)
        return dict(sorted(counts.items()))


@dataclass(frozen=True, slots=True)
class DownloadResult:
    """Structured result returned after a successful download."""

    job_id: str
    run_name: str
    destination_dir: Path
    remote_job_dir: str
    transfer_mode: str
    downloaded_bytes: int
    file_count: int
    cleaned_up: bool
    selected_tasks: tuple[str, ...]
    partial: bool

    def as_dict(self) -> dict[str, object]:
        """Serialize the result for future machine-readable output."""

        return {
            "job_id": self.job_id,
            "run_name": self.run_name,
            "destination_dir": str(self.destination_dir),
            "remote_job_dir": self.remote_job_dir,
            "transfer_mode": self.transfer_mode,
            "downloaded_bytes": self.downloaded_bytes,
            "file_count": self.file_count,
            "cleaned_up": self.cleaned_up,
            "selected_tasks": list(self.selected_tasks),
            "partial": self.partial,
        }


@click.command(
    name="download",
    short_help="Retrieve completed job results.",
    help=(
        "Resolve a submitted job's remote result directories, check local space, "
        "transfer the payload, verify it locally, and optionally clean up the "
        "remote job directory."
    ),
)
@click.argument("job_id")
@click.argument(
    "local_dir",
    required=False,
    type=click.Path(path_type=Path, file_okay=False),
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path, file_okay=False),
    help="Local destination directory for the downloaded results.",
)
@click.option("--cleanup", is_flag=True, help="Delete the remote job directory after success.")
@click.option("--force", is_flag=True, help="Proceed even if the local space check fails.")
@click.option(
    "--exclude",
    "exclude_patterns",
    multiple=True,
    help="Glob pattern to exclude from the transferred results.",
)
@click.option(
    "--include-scratch",
    is_flag=True,
    help="Include task scratch directories alongside task result folders.",
)
@click.option(
    "--remote-compress",
    type=click.Choice(["auto", "always", "never"], case_sensitive=False),
    default="auto",
    show_default=True,
    help="Remote compression policy before transfer.",
)
@click.option(
    "--tasks",
    help="Comma-separated task IDs to download instead of the full job selection.",
)
@click.option(
    "--streams",
    type=click.IntRange(1),
    default=1,
    show_default=True,
    help="Transfer stream count. Phase 4 currently supports single-stream downloads only.",
)
@click.option(
    "--compression-level",
    type=click.IntRange(1, 19),
    help="zstd compression level when remote compression is enabled.",
)
@click.pass_context
def command(
    ctx: click.Context,
    job_id: str,
    local_dir: Path | None,
    output: Path | None,
    cleanup: bool,
    force: bool,
    exclude_patterns: tuple[str, ...],
    include_scratch: bool,
    remote_compress: str,
    tasks: str | None,
    streams: int,
    compression_level: int | None,
) -> None:
    """Download task result directories for a previously submitted SLURM job."""

    configure_logging(
        verbosity=_verbosity(ctx),
        colorize=_colorize_output(ctx),
    )

    console = build_console(no_color=not _colorize_output(ctx))

    try:
        result = asyncio.run(
            _run_download(
                cwd=Path.cwd(),
                env=os.environ,
                console=console,
                job_id=job_id,
                local_dir=local_dir,
                output=output,
                cleanup=cleanup,
                force=force,
                exclude_patterns=exclude_patterns,
                include_scratch=include_scratch,
                remote_compress=remote_compress.lower(),
                tasks=tasks,
                streams=streams,
                compression_level=compression_level,
            )
        )
    except KeyboardInterrupt:
        click.echo("Interrupted.")
        raise click.exceptions.Exit(130) from None
    except (asyncssh.Error, RuntimeError, OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    console.print(_build_completion_panel(result))


async def _run_download(
    *,
    cwd: Path,
    env: Mapping[str, str],
    console,
    job_id: str,
    local_dir: Path | None,
    output: Path | None,
    cleanup: bool,
    force: bool,
    exclude_patterns: tuple[str, ...],
    include_scratch: bool,
    remote_compress: str,
    tasks: str | None,
    streams: int,
    compression_level: int | None,
) -> DownloadResult:
    """Resolve job metadata, confirm the plan, and execute the download flow."""

    if output is not None and local_dir is not None:
        raise click.ClickException("Use either `LOCAL_DIR` or `--output`, not both.")
    if streams != 1:
        raise click.ClickException(
            "Phase 4 download currently supports only `--streams 1`; parallel download work remains out of scope."
        )

    resolved = resolve_config(
        cwd=cwd,
        env=env,
        cli_overrides={"transfer.compression_level": compression_level},
    )
    destination = output or local_dir
    requested_tasks = _parse_task_selection(tasks)

    async with ssh_session(resolved.config.ssh) as conn:
        rows = await _query_job_rows(conn, resolved.config, job_id=job_id)
        plan = await _build_download_plan(
            conn=conn,
            config=resolved.config,
            job_id=job_id,
            rows=rows,
            destination=destination,
            requested_tasks=requested_tasks,
            cleanup=cleanup,
            force=force,
            exclude_patterns=exclude_patterns,
            include_scratch=include_scratch,
            remote_compress=remote_compress,
            compression_level=compression_level or resolved.config.transfer.compression_level,
        )

        console.print(_build_summary_panel(plan))
        if not click.confirm("Proceed with download?", default=True):
            raise click.Abort()

        if plan.transfer_mode == "archive":
            return await _execute_archive_download(
                conn=conn,
                config=resolved.config,
                plan=plan,
            )
        return await _execute_raw_download(
            conn=conn,
            config=resolved.config,
            plan=plan,
        )


async def _build_download_plan(
    *,
    conn: asyncssh.SSHClientConnection,
    config: LaunchpadConfig,
    job_id: str,
    rows: tuple[DownloadJobRow, ...],
    destination: Path | None,
    requested_tasks: tuple[str, ...],
    cleanup: bool,
    force: bool,
    exclude_patterns: tuple[str, ...],
    include_scratch: bool,
    remote_compress: str,
    compression_level: int,
) -> DownloadPlan:
    """Resolve the selected remote paths, transfer mode, and local requirements."""

    selected_rows = _select_download_rows(rows, requested_tasks=requested_tasks)
    primary_row = selected_rows[0]
    run_name = primary_row.run_name or f"job-{job_id}"
    remote_job_dir = primary_row.remote_job_dir
    if not remote_job_dir:
        raise RuntimeError(f"No remote job directory metadata is available for job {job_id}.")

    destination_dir = resolve_download_destination(destination, run_name=run_name)
    if destination_dir.exists() and any(destination_dir.iterdir()):
        raise click.ClickException(
            f"Download destination already exists and is not empty: {destination_dir}"
        )

    source_roots = _build_source_roots(
        selected_rows=selected_rows,
        remote_job_dir=remote_job_dir,
        include_scratch=include_scratch,
    )

    raw_size_bytes = 0
    for source in source_roots:
        raw_size_bytes += await measure_remote_path(conn, source.absolute_path)

    transfer_mode = await _select_transfer_mode(
        conn,
        config=config,
        remote_compress=remote_compress,
    )
    transfer_size_estimate_bytes = (
        _estimate_compressed_bytes(raw_size_bytes)
        if transfer_mode == "archive"
        else raw_size_bytes
    )

    required_bytes = raw_size_bytes + transfer_size_estimate_bytes if transfer_mode == "archive" else raw_size_bytes
    space_report = inspect_disk_space(destination_dir, required_bytes=required_bytes)
    if not space_report.sufficient and not force:
        raise RuntimeError(
            f"Insufficient local disk space for {destination_dir}: "
            f"needs {_format_bytes(required_bytes)}, available {_format_bytes(space_report.bytes_available)}. "
            "Use --force to continue anyway."
        )

    remote_archive_path = None
    local_archive_path = None
    if transfer_mode == "archive":
        remote_archive_path = str(
            PurePosixPath(remote_job_dir) / f".launchpad-download-{job_id}.tar.zst"
        )
        local_archive_path = destination_dir.parent / f".launchpad-download-{job_id}.tar.zst"

    selected_tasks = tuple(row.task_id for row in selected_rows if row.task_id is not None)
    return DownloadPlan(
        job_id=job_id,
        run_name=run_name,
        remote_job_dir=remote_job_dir,
        selected_rows=selected_rows,
        selected_tasks=selected_tasks,
        destination_dir=destination_dir,
        source_roots=source_roots,
        raw_size_bytes=raw_size_bytes,
        transfer_mode=transfer_mode,
        transfer_size_estimate_bytes=transfer_size_estimate_bytes,
        cleanup=cleanup,
        force=force,
        exclude_patterns=exclude_patterns,
        compression_level=compression_level,
        verify_checksums=config.transfer.verify_checksums,
        local_archive_path=local_archive_path,
        remote_archive_path=remote_archive_path,
    )


async def _execute_archive_download(
    *,
    conn: asyncssh.SSHClientConnection,
    config: LaunchpadConfig,
    plan: DownloadPlan,
) -> DownloadResult:
    """Create a remote archive, download it, verify it, and unpack locally."""

    if plan.remote_archive_path is None or plan.local_archive_path is None:
        raise RuntimeError("Archive download requires local and remote archive paths.")

    ensure_directory(plan.destination_dir)
    archive_downloaded = False
    actual_archive_size = 0

    await create_remote_archive(
        conn,
        source_paths=[source.relative_path for source in plan.source_roots],
        archive_path=plan.remote_archive_path,
        base_dir=plan.remote_job_dir,
        exclude_patterns=plan.exclude_patterns,
        tar_binary=config.remote_binaries.tar,
        zstd_binary=config.remote_binaries.zstd,
        compression_level=plan.compression_level,
        compression_threads=config.transfer.compression_threads,
    )

    actual_archive_size = await measure_remote_path(conn, plan.remote_archive_path)
    if not plan.force:
        report = inspect_disk_space(
            plan.destination_dir,
            required_bytes=plan.raw_size_bytes + actual_archive_size,
        )
        if not report.sufficient:
            raise RuntimeError(
                f"Insufficient local disk space for {plan.destination_dir}: "
                f"needs {_format_bytes(plan.raw_size_bytes + actual_archive_size)}, "
                f"available {_format_bytes(report.bytes_available)}."
            )

    await transfer_download(
        conn,
        plan.remote_archive_path,
        plan.local_archive_path,
        resume=config.transfer.resume_enabled,
    )
    archive_downloaded = True

    if plan.verify_checksums:
        remote_digest = await compute_remote_sha256(conn, plan.remote_archive_path)
        local_digest = compute_sha256(plan.local_archive_path)
        if remote_digest != local_digest:
            raise RuntimeError(
                f"Archive checksum mismatch for job {plan.job_id}: remote {remote_digest}, local {local_digest}."
            )

    inspection = inspect_archive(plan.local_archive_path)
    decompress_path(plan.local_archive_path, plan.destination_dir)

    extracted_files = _count_local_files(plan.destination_dir)
    if extracted_files != inspection.file_count:
        raise RuntimeError(
            f"Archive verification failed for job {plan.job_id}: "
            f"expected {inspection.file_count} files, extracted {extracted_files}."
        )

    if plan.cleanup:
        await delete_remote_path(conn, plan.remote_job_dir)
    else:
        await delete_remote_path(conn, plan.remote_archive_path, recursive=False)

    if archive_downloaded:
        with suppress(FileNotFoundError):
            plan.local_archive_path.unlink()

    return DownloadResult(
        job_id=plan.job_id,
        run_name=plan.run_name,
        destination_dir=plan.destination_dir,
        remote_job_dir=plan.remote_job_dir,
        transfer_mode=plan.transfer_mode,
        downloaded_bytes=actual_archive_size,
        file_count=inspection.file_count,
        cleaned_up=plan.cleanup,
        selected_tasks=plan.selected_tasks,
        partial=plan.partial,
    )


async def _execute_raw_download(
    *,
    conn: asyncssh.SSHClientConnection,
    config: LaunchpadConfig,
    plan: DownloadPlan,
) -> DownloadResult:
    """Transfer the selected remote files directly without a remote archive."""

    ensure_directory(plan.destination_dir)
    expected_file_count = 0

    for source in plan.source_roots:
        target_root = plan.destination_dir / Path(source.relative_path)
        ensure_directory(target_root)
        entries = await list_remote_directory(conn, source.absolute_path, recursive=True)
        filtered_entries = _filter_remote_entries(
            entries,
            source_root=source,
            exclude_patterns=plan.exclude_patterns,
        )

        for entry in filtered_entries:
            relative_path = PurePosixPath(entry.path).relative_to(PurePosixPath(source.absolute_path))
            local_path = target_root.joinpath(*relative_path.parts)
            if entry.is_dir:
                ensure_directory(local_path)
                continue

            ensure_directory(local_path.parent)
            await transfer_download(
                conn,
                entry.path,
                local_path,
                resume=config.transfer.resume_enabled,
            )

            if plan.verify_checksums:
                remote_digest = await compute_remote_sha256(conn, entry.path)
                local_digest = compute_sha256(local_path)
                if remote_digest != local_digest:
                    raise RuntimeError(
                        f"Checksum mismatch for {entry.path}: remote {remote_digest}, local {local_digest}."
                    )

            expected_file_count += 1

    actual_files = _count_local_files(plan.destination_dir)
    if actual_files != expected_file_count:
        raise RuntimeError(
            f"Downloaded file-count mismatch for job {plan.job_id}: "
            f"expected {expected_file_count}, found {actual_files}."
        )

    if plan.cleanup:
        await delete_remote_path(conn, plan.remote_job_dir)

    return DownloadResult(
        job_id=plan.job_id,
        run_name=plan.run_name,
        destination_dir=plan.destination_dir,
        remote_job_dir=plan.remote_job_dir,
        transfer_mode=plan.transfer_mode,
        downloaded_bytes=plan.raw_size_bytes,
        file_count=expected_file_count,
        cleaned_up=plan.cleanup,
        selected_tasks=plan.selected_tasks,
        partial=plan.partial,
    )


async def _select_transfer_mode(
    conn: asyncssh.SSHClientConnection,
    *,
    config: LaunchpadConfig,
    remote_compress: str,
) -> str:
    """Resolve the transfer mode from the requested remote-compression policy."""

    if remote_compress == "never":
        return "raw"
    if remote_compress == "always":
        return "archive"
    if await _remote_compression_available(conn, config=config):
        return "archive"
    return "raw"


async def _remote_compression_available(
    conn: asyncssh.SSHClientConnection,
    *,
    config: LaunchpadConfig,
) -> bool:
    """Return whether the configured remote tar and zstd binaries appear usable."""

    command = " && ".join(
        [
            f"{shlex.quote(config.remote_binaries.tar)} --version >/dev/null 2>&1",
            f"{shlex.quote(config.remote_binaries.zstd)} --version >/dev/null 2>&1",
        ]
    )
    result = await conn.run(command, check=False)
    return result.exit_status == 0


async def _query_job_rows(
    conn: asyncssh.SSHClientConnection,
    config: LaunchpadConfig,
    *,
    job_id: str,
) -> tuple[DownloadJobRow, ...]:
    """Fetch and merge scheduler rows for the requested job ID."""

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

    merged: dict[str, DownloadJobRow] = {
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


def _select_download_rows(
    rows: tuple[DownloadJobRow, ...],
    *,
    requested_tasks: tuple[str, ...],
) -> tuple[DownloadJobRow, ...]:
    """Select the requested task rows or the full task set when unspecified."""

    task_rows = tuple(row for row in rows if row.task_id is not None)
    candidate_rows = task_rows or rows
    if not candidate_rows:
        raise RuntimeError("No downloadable scheduler rows were found.")

    if not requested_tasks:
        return candidate_rows

    selected = tuple(row for row in candidate_rows if row.task_id in requested_tasks)
    missing = [task_id for task_id in requested_tasks if all(row.task_id != task_id for row in selected)]
    if missing:
        raise click.ClickException(
            f"Task selection did not match job rows for {rows[0].job_id}: {', '.join(missing)}"
        )
    return selected


def _build_source_roots(
    *,
    selected_rows: tuple[DownloadJobRow, ...],
    remote_job_dir: str,
    include_scratch: bool,
) -> tuple[RemoteSource, ...]:
    """Resolve the remote result directories selected for download."""

    sources: list[RemoteSource] = []
    seen: set[str] = set()

    for row in selected_rows:
        if not row.work_dir:
            raise RuntimeError(
                f"No remote work directory is available for job {row.job_id}"
                + (f" task {row.task_id}" if row.task_id is not None else "")
                + "."
            )

        work_dir = str(PurePosixPath(row.work_dir))
        if work_dir not in seen:
            sources.append(
                RemoteSource(
                    absolute_path=work_dir,
                    relative_path=_relative_remote_path(work_dir, remote_job_dir),
                )
            )
            seen.add(work_dir)

        if include_scratch and row.task_id is not None:
            scratch_dir = str(PurePosixPath(remote_job_dir) / "scratch" / f"task_{row.task_id}")
            if scratch_dir not in seen:
                sources.append(
                    RemoteSource(
                        absolute_path=scratch_dir,
                        relative_path=_relative_remote_path(scratch_dir, remote_job_dir),
                    )
                )
                seen.add(scratch_dir)

    return tuple(sources)


def _filter_remote_entries(
    entries: tuple[RemotePathEntry, ...],
    *,
    source_root: RemoteSource,
    exclude_patterns: tuple[str, ...],
) -> tuple[RemotePathEntry, ...]:
    """Apply user exclude patterns to recursive raw-transfer entries."""

    if not exclude_patterns:
        return entries

    filtered: list[RemotePathEntry] = []
    root = PurePosixPath(source_root.absolute_path)
    base = PurePosixPath(source_root.relative_path)

    for entry in entries:
        relative_under_source = PurePosixPath(entry.path).relative_to(root)
        relative_to_job = (base / relative_under_source).as_posix()
        if any(fnmatch.fnmatch(relative_to_job, pattern) for pattern in exclude_patterns):
            continue
        filtered.append(entry)

    return tuple(filtered)


def _parse_task_selection(raw: str | None) -> tuple[str, ...]:
    """Parse a comma-separated task selection string into a stable tuple."""

    if raw is None:
        return ()

    parts = [part.strip() for part in raw.split(",")]
    selected = [part for part in parts if part]
    if not selected:
        raise click.ClickException("`--tasks` requires at least one task id.")

    deduplicated = list(dict.fromkeys(selected))
    if all(item.isdigit() for item in deduplicated):
        return tuple(str(item) for item in sorted((int(item) for item in deduplicated)))
    return tuple(deduplicated)


def _relative_remote_path(path: str, root: str) -> str:
    """Return the stable path beneath the remote job root for archive/raw copies."""

    candidate = PurePosixPath(path)
    try:
        return PurePosixPath(candidate).relative_to(PurePosixPath(root)).as_posix()
    except ValueError:
        return candidate.name


def _estimate_compressed_bytes(raw_size_bytes: int) -> int:
    """Return a conservative compressed-transfer estimate for user confirmation."""

    if raw_size_bytes <= 0:
        return 0
    return max(int(raw_size_bytes * COMPRESSED_SIZE_ESTIMATE_RATIO), 1)


def _count_local_files(path: Path) -> int:
    """Count regular files beneath a local directory tree."""

    return sum(1 for candidate in path.rglob("*") if candidate.is_file())


def _row_from_status(job: JobStatus) -> DownloadJobRow:
    return DownloadJobRow(
        job_id=job.array_job_id or job.job_id,
        task_id=job.array_task_id,
        run_name=job.job_name,
        state=job.state,
        remote_job_dir=job.remote_job_dir,
        work_dir=job.work_dir,
        source="squeue",
    )


def _row_from_accounting(job: JobAccounting) -> DownloadJobRow:
    return DownloadJobRow(
        job_id=job.array_job_id or job.job_id,
        task_id=job.array_task_id,
        run_name=job.job_name,
        state=job.state,
        remote_job_dir=job.remote_job_dir,
        work_dir=job.work_dir,
        source="sacct",
    )


def _merge_rows(existing: DownloadJobRow | None, incoming: DownloadJobRow) -> DownloadJobRow:
    if existing is None:
        return incoming

    return replace(
        existing,
        run_name=incoming.run_name or existing.run_name,
        state=incoming.state,
        remote_job_dir=incoming.remote_job_dir or existing.remote_job_dir,
        work_dir=incoming.work_dir or existing.work_dir,
        source=incoming.source,
    )


def _row_identity(row: DownloadJobRow) -> str:
    return f"{row.job_id}:{row.task_id or ''}"


def _row_sort_key(row: DownloadJobRow) -> tuple[int, int, int, str]:
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


def _build_summary_panel(plan: DownloadPlan) -> Panel:
    """Render the pre-download summary shown before confirmation."""

    summary = Table.grid(padding=(0, 2))
    summary.add_row("Job", f"{plan.job_id} ({plan.run_name})")
    summary.add_row("Tasks", _format_selected_tasks(plan.selected_tasks))
    summary.add_row("States", _format_state_counts(plan.state_counts))
    summary.add_row("Destination", str(plan.destination_dir))
    summary.add_row("Remote job dir", plan.remote_job_dir)
    summary.add_row("Transfer mode", "remote archive" if plan.transfer_mode == "archive" else "raw files")
    summary.add_row("Remote results", _format_bytes(plan.raw_size_bytes))
    if plan.transfer_mode == "archive":
        summary.add_row("Compressed estimate", f"~{_format_bytes(plan.transfer_size_estimate_bytes)}")
    summary.add_row("Local required", _format_bytes(plan.required_local_bytes))
    if plan.cleanup:
        summary.add_row("Cleanup", "remote job directory will be deleted after success")
    if plan.partial:
        summary.add_row("Warning", "selection includes non-terminal tasks; results may be partial")
    if plan.exclude_patterns:
        summary.add_row("Excludes", ", ".join(plan.exclude_patterns))

    return Panel(summary, title="Download Plan", expand=False)


def _build_completion_panel(result: DownloadResult) -> Panel:
    """Render the final success summary after a completed download."""

    summary = Table.grid(padding=(0, 2))
    summary.add_row("Job", f"{result.job_id} ({result.run_name})")
    summary.add_row("Destination", str(result.destination_dir))
    summary.add_row("Transfer mode", result.transfer_mode)
    summary.add_row("Files", str(result.file_count))
    summary.add_row("Transferred", _format_bytes(result.downloaded_bytes))
    summary.add_row("Tasks", _format_selected_tasks(result.selected_tasks))
    summary.add_row("Remote cleanup", "completed" if result.cleaned_up else "not requested")
    return Panel(summary, title="Download Complete", expand=False)


def _format_state_counts(counts: Mapping[str, int]) -> str:
    return ", ".join(f"{state.lower()}={count}" for state, count in counts.items())


def _format_selected_tasks(task_ids: tuple[str, ...]) -> str:
    if not task_ids:
        return "all"
    return ", ".join(task_ids)


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


def _verbosity(ctx: click.Context) -> int:
    options = getattr(ctx.find_root(), "obj", None)
    return int(getattr(options, "verbose", 0))


def _colorize_output(ctx: click.Context) -> bool:
    options = getattr(ctx.find_root(), "obj", None)
    no_color = bool(getattr(options, "no_color", False))
    return not no_color and "NO_COLOR" not in os.environ
