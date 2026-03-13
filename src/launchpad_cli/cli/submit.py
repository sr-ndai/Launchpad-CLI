"""`launchpad submit` command and dry-run orchestration."""

from __future__ import annotations

import asyncio
import os
import secrets
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import asyncssh
import click

from launchpad_cli.core.compress import compress_path
from launchpad_cli.core.config import LaunchpadConfig, ResolvedConfig, resolve_config
from launchpad_cli.core.logging import configure_logging
from launchpad_cli.core.remote_ops import (
    RemoteJobLayout,
    build_remote_job_layout,
    extract_remote_archive,
    prepare_remote_job_directory,
)
from launchpad_cli.core.slurm import SubmitRequest, SubmittedJob, build_submit_script, submit_job
from launchpad_cli.core.ssh import ssh_session
from launchpad_cli.core.transfer import upload
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
    package_files: tuple[Path, ...]
    manifest_entries: tuple[str, ...]
    archive_root_name: str
    archive_name: str
    remote_layout: RemoteJobLayout
    submit_request: SubmitRequest


@click.command(
    name="submit",
    short_help="Package inputs and submit a SLURM job.",
    help=(
        "Discover solver inputs, package them into a `.tar.zst` archive, upload "
        "the payload, generate a remote SLURM script, and submit the job."
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
    "--compression-level",
    type=click.IntRange(1, 19),
    help="Override the zstd compression level for the packaged archive.",
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
    help="Preview the resolved manifest, remote paths, and generated SLURM script without executing.",
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
    compression_level: int | None,
    extra_files: tuple[Path, ...],
    include_all: bool,
    dry_run: bool,
) -> None:
    """Build the first functional Nastran submit workflow."""

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
        compression_level=compression_level,
        extra_files=extra_files,
        include_all=include_all,
    )

    console = build_console(no_color=not _colorize_output(ctx))
    script_preview = build_submit_script(
        plan.solver_adapter,
        plan.submit_request,
        plan.resolved_config.config,
    )

    if dry_run:
        render_submit_dry_run(
            console,
            run_name=plan.run_name,
            solver_name=plan.solver_key,
            input_dir=plan.input_dir,
            primary_inputs=plan.primary_inputs,
            package_files=plan.package_files,
            remote_job_dir=plan.remote_layout.job_dir,
            archive_name=plan.archive_name,
            partition=plan.submit_request.partition
            or plan.resolved_config.config.submit.partition
            or plan.resolved_config.config.cluster.default_partition,
            time_limit=plan.submit_request.time_limit or plan.resolved_config.config.cluster.default_wall_time,
            begin=plan.submit_request.begin,
            script_preview=script_preview,
        )
        return

    try:
        submitted_job = asyncio.run(_execute_submit(plan))
    except (asyncssh.Error, RuntimeError, OSError, ValueError, NotImplementedError) as exc:
        raise click.ClickException(str(exc)) from exc

    render_submit_confirmation(
        console,
        run_name=plan.run_name,
        job_id=submitted_job.job_id,
        remote_job_dir=plan.remote_layout.job_dir,
        archive_path=plan.remote_layout.archive_path,
    )


async def _execute_submit(plan: SubmitPlan) -> SubmittedJob:
    """Execute the end-to-end submit flow once planning is complete."""

    compression_level = plan.resolved_config.config.transfer.compression_level

    with TemporaryDirectory(prefix="launchpad-submit-") as temp_dir:
        temp_root = Path(temp_dir)
        archive_path = _materialize_archive(plan, temp_root, compression_level=compression_level)

        async with ssh_session(plan.resolved_config.config.ssh) as conn:
            await prepare_remote_job_directory(conn, plan.remote_layout)
            await upload(
                conn,
                archive_path,
                plan.remote_layout.archive_path,
                resume=plan.resolved_config.config.transfer.resume_enabled,
            )
            await extract_remote_archive(
                conn,
                archive_path=plan.remote_layout.archive_path,
                destination_dir=plan.remote_layout.job_dir,
                tar_binary=plan.resolved_config.config.remote_binaries.tar,
                zstd_binary=plan.resolved_config.config.remote_binaries.zstd,
            )
            return await submit_job(
                conn,
                solver=plan.solver_adapter,
                request=plan.submit_request,
                config=plan.resolved_config.config,
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
    compression_level: int | None,
    extra_files: tuple[Path, ...],
    include_all: bool,
) -> SubmitPlan:
    """Resolve config, inputs, packaging, and remote paths for submit work."""

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
            "transfer.compression_level": compression_level,
        },
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

    return SubmitPlan(
        resolved_config=resolved_config,
        solver_key=solver_key,
        solver_adapter=solver_adapter,
        input_dir=resolved_input_dir,
        run_name=resolved_run_name,
        primary_inputs=primary_inputs,
        package_files=package_files,
        manifest_entries=manifest_entries,
        archive_root_name=archive_root_name,
        archive_name=f"{resolved_run_name}.tar.zst",
        remote_layout=remote_layout,
        submit_request=submit_request,
    )


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
    """Resolve the local files which should be packaged into the archive."""

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
                f"Extra files must live under the input directory for this Phase 2 workflow: {resolved}"
            ) from exc
        if resolved not in seen:
            seen.add(resolved)
            selected.append(resolved)

    return selected


def _build_remote_layout(config: LaunchpadConfig, *, run_name: str) -> RemoteJobLayout:
    """Resolve the remote job layout from the config and run name."""

    username = config.ssh.username
    if not username:
        raise click.ClickException(
            "Submit requires `ssh.username` to resolve the remote job directory."
        )

    remote_job_dir = str(Path(config.cluster.shared_root) / username / run_name).replace("\\", "/")
    return build_remote_job_layout(
        remote_job_dir=remote_job_dir,
        logs_subdir=config.cluster.logs_subdir,
        scratch_root_template=config.cluster.scratch_root,
        archive_name=f"{run_name}.tar.zst",
    )


def _materialize_archive(plan: SubmitPlan, temp_root: Path, *, compression_level: int) -> Path:
    """Stage the selected package files and compress them into a local archive."""

    payload_root = temp_root / plan.archive_root_name
    payload_root.mkdir(parents=True, exist_ok=True)

    for source in plan.package_files:
        relative = source.relative_to(plan.input_dir)
        destination = payload_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    archive_path = temp_root / plan.archive_name
    return compress_path(payload_root, archive_path, level=compression_level)


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


def _colorize_output(ctx: click.Context) -> bool:
    options = getattr(ctx.find_root(), "obj", None)
    no_color = bool(getattr(options, "no_color", False))
    return not no_color and "NO_COLOR" not in os.environ
