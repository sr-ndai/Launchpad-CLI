"""SLURM submit-script generation and submission helpers."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import PurePosixPath

import asyncssh

from launchpad_cli.core.config import LaunchpadConfig
from launchpad_cli.core.remote_ops import write_remote_text
from launchpad_cli.solvers import SolverAdapter, SubmitOverrides


@dataclass(frozen=True, slots=True)
class SubmitRequest:
    """Reusable inputs required to build and submit a SLURM job."""

    run_name: str
    remote_job_dir: str
    script_path: str
    input_files: tuple[str, ...]
    max_concurrent: int | None = None
    partition: str | None = None
    time_limit: str | None = None
    begin: str | None = None
    solver_overrides: SubmitOverrides = SubmitOverrides()


@dataclass(frozen=True, slots=True)
class SubmittedJob:
    """Structured result from a successful `sbatch` invocation."""

    job_id: str
    script_path: str
    remote_job_dir: str
    stdout: str
    stderr: str


def build_submit_script(
    solver: SolverAdapter,
    request: SubmitRequest,
    config: LaunchpadConfig,
) -> str:
    """Generate the SLURM batch script content for a solver invocation."""

    if not request.input_files:
        raise ValueError("Cannot build a submit script without at least one input file.")

    logs_dir = str(PurePosixPath(request.remote_job_dir) / config.cluster.logs_subdir)
    scratch_root = config.cluster.scratch_root.format(job_dir=request.remote_job_dir)
    manifest_path = str(PurePosixPath(request.remote_job_dir) / "input-manifest.txt")
    task_scratch = "${SCRATCH_ROOT}/task_${SLURM_ARRAY_TASK_ID}"
    cpus = request.solver_overrides.cpus or config.submit.cpus or _default_solver_cpus(solver, config)
    partition = request.partition or config.submit.partition or config.cluster.default_partition
    time_limit = request.time_limit or config.cluster.default_wall_time
    array_spec = _array_spec(len(request.input_files), request.max_concurrent)
    job_comment = request.remote_job_dir
    log_stdout = str(PurePosixPath(logs_dir) / "slurm_%A_%a.out")
    log_stderr = str(PurePosixPath(logs_dir) / "slurm_%A_%a.err")

    manifest_lines = "\n".join(request.input_files)
    scratch_exports = "\n".join(
        f'export {key}="{value}"' for key, value in solver.build_scratch_env(task_scratch).items()
    )
    run_command = solver.build_run_command(
        '"${JOB_DIR}/${INPUT_FILE}"',
        config,
        request.solver_overrides,
    )

    begin_directive = f"#SBATCH --begin={request.begin}" if request.begin else ""

    script_lines = [
        "#!/usr/bin/env bash",
        f"#SBATCH --job-name={request.run_name}",
        f"#SBATCH --array={array_spec}",
        f"#SBATCH --cpus-per-task={cpus}",
        f"#SBATCH --partition={partition}",
        f"#SBATCH --time={time_limit}",
        f"#SBATCH --output={log_stdout}",
        f"#SBATCH --error={log_stderr}",
        f"#SBATCH --comment={job_comment}",
    ]
    if begin_directive:
        script_lines.append(begin_directive)

    script_lines.extend(
        [
            "",
            "set -euo pipefail",
            "",
            f"JOB_DIR={shlex.quote(request.remote_job_dir)}",
            f"LOG_DIR={shlex.quote(logs_dir)}",
            f"SCRATCH_ROOT={shlex.quote(scratch_root)}",
            f"MANIFEST_PATH={shlex.quote(manifest_path)}",
            "",
            "cat > \"$MANIFEST_PATH\" <<'EOF_MANIFEST'",
            manifest_lines,
            "EOF_MANIFEST",
            "",
            "mapfile -t INPUT_FILES < \"$MANIFEST_PATH\"",
            'INPUT_FILE="${INPUT_FILES[$SLURM_ARRAY_TASK_ID]}"',
            'INPUT_BASENAME="$(basename "$INPUT_FILE")"',
            'INPUT_STEM="${INPUT_BASENAME%.*}"',
            'RESULT_DIR="${JOB_DIR}/results_${INPUT_STEM}_${SLURM_ARRAY_TASK_ID}"',
            'TASK_SCRATCH_DIR="${SCRATCH_ROOT}/task_${SLURM_ARRAY_TASK_ID}"',
            'mkdir -p "$LOG_DIR" "$SCRATCH_ROOT" "$TASK_SCRATCH_DIR" "$RESULT_DIR"',
            scratch_exports,
            'trap \'rm -rf "$TASK_SCRATCH_DIR"\' EXIT',
            'cd "$RESULT_DIR"',
            run_command,
        ]
    )

    return "\n".join(script_lines) + "\n"


async def submit_job(
    conn: asyncssh.SSHClientConnection,
    *,
    solver: SolverAdapter,
    request: SubmitRequest,
    config: LaunchpadConfig,
    sbatch_binary: str | None = None,
) -> SubmittedJob:
    """Write the submit script remotely and invoke `sbatch --parsable`."""

    script = build_submit_script(solver, request, config)
    await write_remote_text(conn, request.script_path, script)

    resolved_sbatch = sbatch_binary or config.remote_binaries.sbatch
    command = " ".join(
        [
            shlex.quote(resolved_sbatch),
            "--parsable",
            shlex.quote(request.script_path),
        ]
    )
    result = await conn.run(command, check=False)
    if result.exit_status != 0:
        raise RuntimeError(
            f"SLURM submission failed for {request.script_path}: {result.stderr.strip() or result.stdout.strip() or 'unknown error'}"
        )

    stdout = result.stdout.strip()
    job_id = stdout.split(";", 1)[0].strip()
    if not job_id:
        raise RuntimeError(f"SLURM submission returned no job id for {request.script_path}.")

    return SubmittedJob(
        job_id=job_id,
        script_path=request.script_path,
        remote_job_dir=request.remote_job_dir,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _array_spec(count: int, max_concurrent: int | None) -> str:
    if count <= 0:
        raise ValueError("Array jobs require at least one input file.")

    upper_bound = count - 1
    if max_concurrent is None or max_concurrent >= count:
        return f"0-{upper_bound}"
    if max_concurrent <= 0:
        raise ValueError("max_concurrent must be positive when provided.")
    return f"0-{upper_bound}%{max_concurrent}"


def _default_solver_cpus(solver: SolverAdapter, config: LaunchpadConfig) -> int:
    name = solver.name.lower()
    if name == "nastran":
        return config.solvers.nastran.default_cpus
    if name == "ansys":
        return config.solvers.ansys.default_cpus
    raise ValueError(f"No default CPU configuration is available for solver `{solver.name}`.")
