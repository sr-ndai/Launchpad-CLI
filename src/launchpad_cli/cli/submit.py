"""`launchpad submit` command and dry-run orchestration."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

import asyncssh
import click
from loguru import logger

from launchpad_cli.core.compress import compress_path
from launchpad_cli.core.config import LaunchpadConfig, ResolvedConfig, resolve_config
from launchpad_cli.core.job_manifest import (
    JobManifest,
    TaskReference,
    build_job_manifest,
    build_task_references,
    render_job_manifest,
)
from launchpad_cli.core.logging import configure_logging
from launchpad_cli.core.remote_ops import (
    RemoteJobLayout,
    build_remote_job_layout,
    extract_remote_archive,
    prepare_remote_job_directory,
    write_remote_text,
)
from launchpad_cli.core.slurm import SubmitRequest, SubmittedJob, build_submit_script, submit_job
from launchpad_cli.core.ssh import ssh_session
from launchpad_cli.core.transfer import (
    UploadItem,
    striped_upload,
    upload_many,
)
from launchpad_cli.core.workspace import resolve_remote_workspace_root
from launchpad_cli.display import build_console, render_submit_confirmation, render_submit_dry_run
from launchpad_cli.solvers import AnsysAdapter, DiscoveredInput, NastranAdapter, SolverAdapter, SubmitOverrides


@dataclass(frozen=True, slots=True)
class SubmitPlan:
    """Resolved local and remote state needed for submit or dry-run output."""

    resolved_config: ResolvedConfig
    solver_key: str
    solver_adapter: SolverAdapter
    input_dir: Path
    run_name: str
    primary_inputs: tuple[DiscoveredInput, ...]
    task_references: tuple[TaskReference, ...]
    package_files: tuple[Path, ...]
    manifest_entries: tuple[str, ...]
    archive_root_name: str
    archive_name: str | None
    transfer_mode: str
    requested_streams: int
    remote_layout: RemoteJobLayout
    submit_request: SubmitRequest
    job_manifest: JobManifest

    @property
    def remote_payload_path(self) -> str:
        """Return the primary remote transfer target for user-facing summaries."""

        if self.transfer_mode == "single-file":
            return self.remote_layout.archive_path
        return str(PurePosixPath(self.remote_layout.job_dir) / self.archive_root_name)

    @property
    def payload_label(self) -> str:
        """Return the local payload label shown in dry-run and confirmation output."""

        if self.archive_name is not None:
            return self.archive_name
        return f"{self.archive_root_name}/"


@dataclass(frozen=True, slots=True)
class SubmitExecution:
    """Structured result from a completed submit transfer plus `sbatch` call."""

    submitted_job: SubmittedJob
    effective_streams: int


@dataclass(frozen=True, slots=True)
class SubmitResult:
    """Structured JSON-friendly submit response."""

    mode: str
    run_name: str
    solver: str
    input_dir: Path
    remote_job_dir: str
    payload_label: str
    remote_payload_path: str
    transfer_mode: str
    requested_streams: int
    script_preview: str | None = None
    job_id: str | None = None
    effective_streams: int | None = None
    primary_inputs: tuple[dict[str, object], ...] = ()
    package_files: tuple[str, ...] = ()
    manifest_entries: tuple[str, ...] = ()
    logs: dict[str, str] | None = None
    tasks: tuple[dict[str, object], ...] = ()
    partition: str | None = None
    time_limit: str | None = None
    begin: str | None = None
    monitor_command: str | None = None

    def as_dict(self) -> dict[str, object]:
        """Serialize the submit response for `--json` output."""

        return {
            "mode": self.mode,
            "run_name": self.run_name,
            "solver": self.solver,
            "input_dir": str(self.input_dir),
            "remote_job_dir": self.remote_job_dir,
            "payload_label": self.payload_label,
            "remote_payload_path": self.remote_payload_path,
            "transfer_mode": self.transfer_mode,
            "requested_streams": self.requested_streams,
            "effective_streams": self.effective_streams,
            "job_id": self.job_id,
            "monitor_command": self.monitor_command,
            "partition": self.partition,
            "time_limit": self.time_limit,
            "begin": self.begin,
            "primary_inputs": list(self.primary_inputs),
            "package_files": list(self.package_files),
            "manifest_entries": list(self.manifest_entries),
            "logs": self.logs or {},
            "tasks": list(self.tasks),
            "script_preview": self.script_preview,
        }


@click.command(
    name="submit",
    short_help="Package inputs and submit a SLURM job.",
    help=(
        "Discover solver inputs, stage the payload, transfer it with the selected "
        "Phase 5 transfer mode, generate a remote SLURM script, and submit the job."
    ),
)
@click.argument(
    "input_dir",
    required=False,
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
)
@click.option(
    "--solver",
    type=click.Choice(["nastran", "ansys"], case_sensitive=False),
    help="Explicit solver selection. Defaults to auto-detection.",
)
@click.option("--name", help="Override the generated run name.")
@click.option("--cpus", type=click.IntRange(1), help="Override CPUs per task.")
@click.option("--max-concurrent", type=click.IntRange(1), help="Override the SLURM array throttle.")
@click.option("--partition", help="Override the SLURM partition.")
@click.option("--time", "time_limit", help="Override the SLURM wall time.")
@click.option("--begin", help="Schedule the SLURM job to begin later.")
@click.option(
    "--transfer-mode",
    type=click.Choice(["auto", "single-file", "multi-file"], case_sensitive=False),
    help="Transfer mode. Defaults to auto selection from the accepted Phase 5 rules.",
)
@click.option(
    "--streams",
    type=click.IntRange(1),
    help="Transfer stream budget. Defaults to the resolved `transfer.parallel_streams` config value.",
)
@click.option(
    "--compression-level",
    type=click.IntRange(1, 19),
    help="Override the zstd compression level for the packaged archive.",
)
@click.option(
    "--no-compress",
    is_flag=True,
    help="Skip archive creation and transfer the selected files directly.",
)
@click.option(
    "--extra-files",
    multiple=True,
    type=click.Path(path_type=Path, dir_okay=False),
    help="Additional files to package alongside discovered solver inputs.",
)
@click.option(
    "--include-all",
    is_flag=True,
    help="Package the entire input directory instead of only discovered solver inputs.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Preview the resolved manifest, transfer plan, remote paths, and generated SLURM script without executing.",
)
@click.pass_context
def command(
    ctx: click.Context,
    input_dir: Path | None,
    solver: str | None,
    name: str | None,
    cpus: int | None,
    max_concurrent: int | None,
    partition: str | None,
    time_limit: str | None,
    begin: str | None,
    transfer_mode: str | None,
    streams: int | None,
    compression_level: int | None,
    no_compress: bool,
    extra_files: tuple[Path, ...],
    include_all: bool,
    dry_run: bool,
) -> None:
    """Build the Phase 5 submit workflow."""

    json_output = _json_output(ctx)
    configure_logging(
        verbosity=_verbosity(ctx),
        colorize=_colorize_output(ctx),
    )

    plan = _build_submit_plan(
        input_dir=input_dir or Path("."),
        explicit_solver=solver.lower() if solver else None,
        run_name=name,
        cpus=cpus,
        max_concurrent=max_concurrent,
        partition=partition,
        time_limit=time_limit,
        begin=begin,
        transfer_mode=transfer_mode.lower() if transfer_mode else None,
        streams=streams,
        compression_level=compression_level,
        no_compress=no_compress,
        extra_files=extra_files,
        include_all=include_all,
    )
    logger.trace(
        "Prepared submit plan for {} using {} transfer mode with {} requested stream(s)",
        plan.run_name,
        plan.transfer_mode,
        plan.requested_streams,
    )

    console = build_console(no_color=not _colorize_output(ctx))
    script_preview = build_submit_script(
        plan.solver_adapter,
        plan.submit_request,
        plan.resolved_config.config,
    )

    if dry_run:
        if json_output:
            click.echo(json.dumps(_build_submit_dry_run_result(plan, script_preview).as_dict(), indent=2))
            return
        render_submit_dry_run(
            console,
            run_name=plan.run_name,
            solver_name=plan.solver_key,
            input_dir=plan.input_dir,
            primary_inputs=plan.primary_inputs,
            task_references=plan.task_references,
            package_files=plan.package_files,
            remote_job_dir=plan.remote_layout.job_dir,
            payload_label=plan.payload_label,
            transfer_mode=plan.transfer_mode,
            requested_streams=plan.requested_streams,
            partition=plan.submit_request.partition
            or plan.resolved_config.config.submit.partition
            or plan.resolved_config.config.cluster.default_partition,
            time_limit=plan.submit_request.time_limit or plan.resolved_config.config.cluster.default_wall_time,
            begin=plan.submit_request.begin,
            script_preview=script_preview,
        )
        return

    try:
        execution = asyncio.run(_execute_submit(plan))
    except (asyncssh.Error, RuntimeError, OSError, ValueError, NotImplementedError) as exc:
        raise click.ClickException(str(exc)) from exc

    logger.trace(
        "Submitted {} as SLURM job {} with {} effective stream(s)",
        plan.run_name,
        execution.submitted_job.job_id,
        execution.effective_streams,
    )
    if json_output:
        click.echo(json.dumps(_build_submit_result(plan, execution).as_dict(), indent=2))
        return

    render_submit_confirmation(
        console,
        run_name=plan.run_name,
        job_id=execution.submitted_job.job_id,
        task_references=plan.task_references,
        remote_job_dir=plan.remote_layout.job_dir,
        payload_label=plan.payload_label,
        remote_payload_path=plan.remote_payload_path,
        transfer_mode=plan.transfer_mode,
        requested_streams=plan.requested_streams,
        effective_streams=execution.effective_streams,
    )


async def _execute_submit(plan: SubmitPlan) -> SubmitExecution:
    """Execute the end-to-end submit flow once planning is complete."""

    config = plan.resolved_config.config

    with TemporaryDirectory(prefix="launchpad-submit-") as temp_dir:
        temp_root = Path(temp_dir)

        async with ssh_session(config.ssh) as conn:
            await _ensure_remote_job_dir_available(conn, plan.remote_layout.job_dir)
            await prepare_remote_job_directory(conn, plan.remote_layout)

            if plan.transfer_mode == "single-file":
                logger.trace(
                    "Submitting {} via single-file archive upload to {}",
                    plan.run_name,
                    plan.remote_layout.archive_path,
                )
                archive_path = _materialize_archive(
                    plan,
                    temp_root,
                    compression_level=config.transfer.compression_level,
                )
                transfer_execution = await striped_upload(
                    conn,
                    config.ssh,
                    archive_path,
                    plan.remote_layout.archive_path,
                    streams=plan.requested_streams,
                    chunk_size=config.transfer.chunk_size_bytes,
                    resume=config.transfer.resume_enabled,
                )
                await extract_remote_archive(
                    conn,
                    archive_path=plan.remote_layout.archive_path,
                    destination_dir=plan.remote_layout.job_dir,
                    tar_binary=config.remote_binaries.tar,
                    zstd_binary=config.remote_binaries.zstd,
                )
            else:
                logger.trace(
                    "Submitting {} via multi-file upload into {}",
                    plan.run_name,
                    plan.remote_layout.job_dir,
                )
                payload_root = _materialize_payload_root(plan, temp_root)
                upload_items = _build_multi_file_upload_items(plan, payload_root)
                transfer_execution = await upload_many(
                    config.ssh,
                    upload_items,
                    streams=plan.requested_streams,
                    resume=config.transfer.resume_enabled,
                )

            await write_remote_text(
                conn,
                plan.remote_layout.manifest_path,
                render_job_manifest(plan.job_manifest),
            )

            submitted_job = await submit_job(
                conn,
                solver=plan.solver_adapter,
                request=plan.submit_request,
                config=config,
            )
            return SubmitExecution(
                submitted_job=submitted_job,
                effective_streams=transfer_execution.effective_streams,
            )


def _build_submit_plan(
    *,
    input_dir: Path,
    explicit_solver: str | None,
    run_name: str | None,
    cpus: int | None,
    max_concurrent: int | None,
    partition: str | None,
    time_limit: str | None,
    begin: str | None,
    transfer_mode: str | None,
    streams: int | None,
    compression_level: int | None,
    no_compress: bool,
    extra_files: tuple[Path, ...],
    include_all: bool,
) -> SubmitPlan:
    """Resolve config, inputs, packaging, transfer mode, and remote paths for submit work."""

    resolved_input_dir = input_dir.expanduser().resolve()
    if not resolved_input_dir.exists():
        raise click.ClickException(f"Input directory does not exist: {resolved_input_dir}")
    if not resolved_input_dir.is_dir():
        raise click.ClickException(f"Input path is not a directory: {resolved_input_dir}")

    resolved_config = resolve_config(
        cwd=resolved_input_dir,
        env=os.environ,
        cli_overrides={
            "submit.solver": explicit_solver,
            "submit.cpus": cpus,
            "submit.partition": partition,
            "transfer.parallel_streams": streams,
            "transfer.compression_level": compression_level,
        },
    )

    resolved_transfer_mode = _resolve_submit_transfer_mode(
        requested_mode=transfer_mode,
        no_compress=no_compress,
    )

    solver_key, solver_adapter = _resolve_solver(
        explicit_solver=explicit_solver or resolved_config.config.submit.solver,
        config=resolved_config.config,
        input_dir=resolved_input_dir,
    )

    try:
        primary_inputs = tuple(solver_adapter.discover_inputs(resolved_input_dir))
    except NotImplementedError as exc:
        raise click.ClickException(str(exc)) from exc

    if not primary_inputs:
        raise click.ClickException(
            f"No supported {solver_key} input files were found in {resolved_input_dir}."
        )

    package_files = tuple(
        _collect_package_files(
            input_dir=resolved_input_dir,
            primary_inputs=primary_inputs,
            extra_files=extra_files,
            include_all=include_all,
        )
    )
    archive_root_name = resolved_input_dir.name
    manifest_entries = tuple(
        f"{archive_root_name}/{path.relative_to(resolved_input_dir).as_posix()}"
        for path in primary_inputs_to_paths(primary_inputs)
    )
    task_references = build_task_references(primary_inputs)

    resolved_run_name = run_name or _generate_run_name(
        solver_key,
        name_prefix=resolved_config.config.submit.name_prefix,
    )
    remote_layout = _build_remote_layout(
        resolved_config.config,
        run_name=resolved_run_name,
    )
    submit_request = SubmitRequest(
        run_name=resolved_run_name,
        remote_job_dir=remote_layout.job_dir,
        script_path=remote_layout.script_path,
        input_files=manifest_entries,
        max_concurrent=max_concurrent or len(primary_inputs),
        partition=partition,
        time_limit=time_limit,
        begin=begin,
        solver_overrides=SubmitOverrides(cpus=cpus),
    )
    job_manifest = build_job_manifest(
        solver=solver_key,
        logs=dict(solver_adapter.log_catalog),
        tasks=task_references,
    )

    return SubmitPlan(
        resolved_config=resolved_config,
        solver_key=solver_key,
        solver_adapter=solver_adapter,
        input_dir=resolved_input_dir,
        run_name=resolved_run_name,
        primary_inputs=primary_inputs,
        task_references=task_references,
        package_files=package_files,
        manifest_entries=manifest_entries,
        archive_root_name=archive_root_name,
        archive_name=f"{resolved_run_name}.tar.zst" if resolved_transfer_mode == "single-file" else None,
        transfer_mode=resolved_transfer_mode,
        requested_streams=resolved_config.config.transfer.parallel_streams,
        remote_layout=remote_layout,
        submit_request=submit_request,
        job_manifest=job_manifest,
    )


def _resolve_submit_transfer_mode(*, requested_mode: str | None, no_compress: bool) -> str:
    """Resolve the Phase 5 submit transfer mode and validate explicit overrides."""

    mode = requested_mode or "auto"
    if mode == "auto":
        return "multi-file" if no_compress else "single-file"
    if mode == "single-file" and no_compress:
        raise click.ClickException(
            "`--transfer-mode single-file` requires archive creation and cannot be combined with `--no-compress`."
        )
    if mode == "multi-file" and not no_compress:
        raise click.ClickException(
            "`--transfer-mode multi-file` requires `--no-compress` for the Phase 5 submit workflow."
        )
    return mode


def _resolve_solver(
    *,
    explicit_solver: str | None,
    config: LaunchpadConfig,
    input_dir: Path,
) -> tuple[str, SolverAdapter]:
    """Resolve the active solver adapter or auto-detect the default Nastran path."""

    if explicit_solver == "nastran":
        return "nastran", NastranAdapter.from_config(config)
    if explicit_solver == "ansys":
        return "ansys", AnsysAdapter.from_config(config)

    nastran_adapter = NastranAdapter.from_config(config)
    if nastran_adapter.discover_inputs(input_dir):
        return "nastran", nastran_adapter

    raise click.ClickException(
        f"No supported solver inputs were found in {input_dir}. Use --solver to select a supported solver explicitly."
    )


def _collect_package_files(
    *,
    input_dir: Path,
    primary_inputs: tuple[DiscoveredInput, ...],
    extra_files: tuple[Path, ...],
    include_all: bool,
) -> list[Path]:
    """Resolve the local files which should be staged for transfer."""

    selected: list[Path] = []
    seen: set[Path] = set()

    if include_all:
        for candidate in sorted(input_dir.rglob("*")):
            if candidate.is_file():
                seen.add(candidate.resolve())
                selected.append(candidate.resolve())
    else:
        for discovered in primary_inputs:
            resolved = discovered.path.resolve()
            seen.add(resolved)
            selected.append(resolved)

    for extra_file in extra_files:
        resolved = (input_dir / extra_file).resolve() if not extra_file.is_absolute() else extra_file.resolve()
        if not resolved.exists() or not resolved.is_file():
            raise click.ClickException(f"Extra file does not exist: {resolved}")
        try:
            resolved.relative_to(input_dir)
        except ValueError as exc:
            raise click.ClickException(
                f"Extra files must live under the input directory for this submit workflow: {resolved}"
            ) from exc
        if resolved not in seen:
            seen.add(resolved)
            selected.append(resolved)

    return selected


def _build_remote_layout(config: LaunchpadConfig, *, run_name: str) -> RemoteJobLayout:
    """Resolve the remote job layout from the config and run name."""

    remote_job_dir = str(PurePosixPath(resolve_remote_workspace_root(config)) / run_name)
    return build_remote_job_layout(
        remote_job_dir=remote_job_dir,
        logs_subdir=config.cluster.logs_subdir,
        scratch_root_template=config.cluster.scratch_root,
        archive_name=f"{run_name}.tar.zst",
    )


def _materialize_payload_root(plan: SubmitPlan, temp_root: Path) -> Path:
    """Stage the selected package files into a deterministic local payload tree."""

    payload_root = temp_root / plan.archive_root_name
    payload_root.mkdir(parents=True, exist_ok=True)

    for source in plan.package_files:
        relative = source.relative_to(plan.input_dir)
        destination = payload_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    return payload_root


def _materialize_archive(plan: SubmitPlan, temp_root: Path, *, compression_level: int) -> Path:
    """Stage the selected package files and compress them into a local archive."""

    payload_root = _materialize_payload_root(plan, temp_root)
    archive_path = temp_root / (plan.archive_name or f"{plan.run_name}.tar.zst")
    return compress_path(payload_root, archive_path, level=compression_level)


def _build_multi_file_upload_items(plan: SubmitPlan, payload_root: Path) -> tuple[UploadItem, ...]:
    """Build remote upload targets for the Phase 5 multi-file submit path."""

    upload_items: list[UploadItem] = []
    for source in sorted(payload_root.rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(payload_root)
        remote_path = str(PurePosixPath(plan.remote_layout.job_dir) / plan.archive_root_name / relative.as_posix())
        upload_items.append(UploadItem(local_path=source, remote_path=remote_path))
    return tuple(upload_items)


async def _ensure_remote_job_dir_available(
    conn: asyncssh.SSHClientConnection,
    remote_job_dir: str,
) -> None:
    """Fail clearly when a submit run name would reuse an existing remote directory."""

    async with conn.start_sftp_client() as sftp:
        if await sftp.exists(remote_job_dir):
            logger.warning("Remote submit directory already exists: {}", remote_job_dir)
            raise click.ClickException(
                f"Remote job directory already exists: {remote_job_dir}. "
                "Use `--name` to choose a new run name or remove the old directory with `launchpad cleanup`."
            )


def _generate_run_name(solver_key: str, *, name_prefix: str | None) -> str:
    """Generate the default run name described in the plan."""

    prefix = name_prefix or solver_key
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    suffix = secrets.token_hex(2)
    return f"{prefix}-{timestamp}-{suffix}"


def primary_inputs_to_paths(inputs: tuple[DiscoveredInput, ...]) -> list[Path]:
    """Project discovery metadata down to the package paths used in the manifest."""

    return [item.path.resolve() for item in inputs]


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


def _build_submit_dry_run_result(plan: SubmitPlan, script_preview: str) -> SubmitResult:
    """Build the machine-readable dry-run response."""

    config = plan.resolved_config.config
    return SubmitResult(
        mode="dry-run",
        run_name=plan.run_name,
        solver=plan.solver_key,
        input_dir=plan.input_dir,
        remote_job_dir=plan.remote_layout.job_dir,
        payload_label=plan.payload_label,
        remote_payload_path=plan.remote_payload_path,
        transfer_mode=plan.transfer_mode,
        requested_streams=plan.requested_streams,
        script_preview=script_preview,
        primary_inputs=tuple(_serialize_discovered_input(item) for item in plan.primary_inputs),
        package_files=tuple(str(path) for path in plan.package_files),
        manifest_entries=plan.manifest_entries,
        logs=dict(plan.job_manifest.logs),
        tasks=tuple(_serialize_task_reference(item) for item in plan.task_references),
        partition=plan.submit_request.partition
        or config.submit.partition
        or config.cluster.default_partition,
        time_limit=plan.submit_request.time_limit or config.cluster.default_wall_time,
        begin=plan.submit_request.begin,
    )


def _build_submit_result(plan: SubmitPlan, execution: SubmitExecution) -> SubmitResult:
    """Build the machine-readable response for an executed submit."""

    return SubmitResult(
        mode="submitted",
        run_name=plan.run_name,
        solver=plan.solver_key,
        input_dir=plan.input_dir,
        remote_job_dir=plan.remote_layout.job_dir,
        payload_label=plan.payload_label,
        remote_payload_path=plan.remote_payload_path,
        transfer_mode=plan.transfer_mode,
        requested_streams=plan.requested_streams,
        job_id=execution.submitted_job.job_id,
        effective_streams=execution.effective_streams,
        monitor_command=f"launchpad status {execution.submitted_job.job_id}",
        logs=dict(plan.job_manifest.logs),
        tasks=tuple(_serialize_task_reference(item) for item in plan.task_references),
    )


def _serialize_discovered_input(item: DiscoveredInput) -> dict[str, object]:
    """Serialize a discovered input for JSON output."""

    return {
        "path": str(item.path),
        "relative_path": item.relative_path.as_posix(),
        "stem": item.stem,
        "extension": item.extension,
        "size_bytes": item.size_bytes,
    }


def _serialize_task_reference(item: TaskReference) -> dict[str, object]:
    """Serialize a task reference for CLI JSON responses."""

    return item.as_dict()
