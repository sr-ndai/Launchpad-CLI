"""SLURM submit, status, and accounting helpers."""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Sequence

import asyncssh

from launchpad_cli.core.config import LaunchpadConfig
from launchpad_cli.core.remote_ops import write_remote_text
from launchpad_cli.solvers import SolverAdapter, SubmitOverrides

SLURM_LOGIN_SHELL = "/bin/bash"


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


@dataclass(frozen=True, slots=True)
class JobStatus:
    """Structured status metadata parsed from `squeue --json`."""

    job_id: str
    job_name: str
    state: str
    array_job_id: str | None = None
    array_task_id: str | None = None
    user_name: str | None = None
    partition: str | None = None
    node_list: str | None = None
    nodes: int | None = None
    cpus: int | None = None
    elapsed: str | None = None
    time_limit: str | None = None
    state_reason: str | None = None
    comment: str | None = None
    work_dir: str | None = None
    standard_output: str | None = None
    standard_error: str | None = None
    submit_time: str | None = None
    start_time: str | None = None

    @property
    def remote_job_dir(self) -> str | None:
        """Return the tracked remote job directory when stored in the comment."""

        return self.comment


@dataclass(frozen=True, slots=True)
class JobAccounting:
    """Structured accounting metadata parsed from `sacct --json`."""

    job_id: str
    job_name: str | None
    state: str
    array_job_id: str | None = None
    array_task_id: str | None = None
    partition: str | None = None
    node_list: str | None = None
    elapsed: str | None = None
    total_cpu: str | None = None
    max_rss: str | None = None
    max_disk_read: str | None = None
    max_disk_write: str | None = None
    exit_code: str | None = None
    derived_exit_code: str | None = None
    comment: str | None = None
    work_dir: str | None = None
    standard_output: str | None = None
    standard_error: str | None = None
    submit_time: str | None = None
    start_time: str | None = None
    end_time: str | None = None

    @property
    def remote_job_dir(self) -> str | None:
        """Return the tracked remote job directory when stored in the comment."""

        return self.comment


@dataclass(frozen=True, slots=True)
class JobRuntimeStats:
    """Structured runtime stats parsed from `sstat` output."""

    job_id: str
    task_id: str | None
    step: str
    ave_cpu: str | None = None
    max_rss: str | None = None
    max_disk_read: str | None = None
    max_disk_write: str | None = None


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


def build_squeue_command(
    *,
    job_id: str | None = None,
    user: str | None = None,
    squeue_binary: str = "squeue",
) -> str:
    """Build the remote `squeue --json` command for active-job queries."""

    command = [shlex.quote(squeue_binary), "--json"]
    if job_id:
        command.extend(["--jobs", shlex.quote(job_id)])
    elif user:
        command.extend(["--user", shlex.quote(user)])
    return " ".join(command)


def build_scancel_command(
    *,
    target: str,
    scancel_binary: str = "scancel",
) -> str:
    """Build the remote `scancel` command for whole-job or task cancellation."""

    return " ".join([shlex.quote(scancel_binary), shlex.quote(target)])


def build_sacct_command(
    *,
    job_id: str | None = None,
    user: str | None = None,
    start_time: str | None = None,
    duplicates: bool = False,
    sacct_binary: str = "sacct",
) -> str:
    """Build the remote `sacct --json` command for accounting queries."""

    command = [shlex.quote(sacct_binary), "--json", "--allocations"]
    if duplicates:
        command.append("--duplicates")
    if start_time:
        command.extend(["--starttime", shlex.quote(start_time)])
    if job_id:
        command.extend(["--jobs", shlex.quote(job_id)])
    elif user:
        command.extend(["--user", shlex.quote(user)])
    return " ".join(command)


def build_sstat_command(
    *,
    job_steps: Sequence[str],
    sstat_binary: str = "sstat",
) -> str:
    """Build the remote `sstat` command for running-job resource metrics."""

    if not job_steps:
        raise ValueError("At least one SLURM job step is required for sstat queries.")

    return " ".join(
        [
            shlex.quote(sstat_binary),
            "--noheader",
            "--parsable2",
            "--format=JobID,MaxRSS,AveCPU,MaxDiskRead,MaxDiskWrite",
            "--jobs",
            shlex.quote(",".join(job_steps)),
        ]
    )


def build_slurm_login_shell_command(command: str) -> str:
    """Wrap a scheduler command so the remote login-shell environment is loaded."""

    return f"{shlex.quote(SLURM_LOGIN_SHELL)} -lc {shlex.quote(command)}"


def parse_squeue_output(raw: str) -> tuple[JobStatus, ...]:
    """Parse `squeue --json` output into structured job status records."""

    payload = _load_slurm_json(raw, command_name="squeue")
    jobs = _extract_jobs(payload, command_name="squeue")
    return tuple(_parse_job_status(job) for job in jobs)


def parse_sacct_output(raw: str) -> tuple[JobAccounting, ...]:
    """Parse `sacct --json` output into structured job accounting records."""

    payload = _load_slurm_json(raw, command_name="sacct")
    jobs = _extract_jobs(payload, command_name="sacct")
    return tuple(_parse_job_accounting(job) for job in jobs)


def parse_sstat_output(raw: str) -> tuple[JobRuntimeStats, ...]:
    """Parse `sstat --parsable2` output into structured runtime stats."""

    rows: list[JobRuntimeStats] = []
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        columns = line.split("|")
        if len(columns) != 5:
            raise ValueError("Invalid sstat output: expected 5 parsable columns.")
        job_id, max_rss, ave_cpu, max_disk_read, max_disk_write = columns
        normalized_job_id, task_id, step = _parse_sstat_job_id(job_id)
        rows.append(
            JobRuntimeStats(
                job_id=normalized_job_id,
                task_id=task_id,
                step=step,
                ave_cpu=_normalize_sstat_value(ave_cpu),
                max_rss=_normalize_sstat_value(max_rss),
                max_disk_read=_normalize_sstat_value(max_disk_read),
                max_disk_write=_normalize_sstat_value(max_disk_write),
            )
        )
    return tuple(rows)


async def query_squeue(
    conn: asyncssh.SSHClientConnection,
    *,
    config: LaunchpadConfig,
    job_id: str | None = None,
    user: str | None = None,
    squeue_binary: str | None = None,
) -> tuple[JobStatus, ...]:
    """Run `squeue --json` remotely and parse the returned active-job records."""

    resolved_user = user if job_id else (user or config.ssh.username)
    resolved_squeue = squeue_binary or config.remote_binaries.squeue
    command = build_squeue_command(
        job_id=job_id,
        user=resolved_user,
        squeue_binary=resolved_squeue,
    )
    result = await run_slurm_command(
        conn,
        command,
        failure_prefix="SLURM squeue query failed",
        executable=resolved_squeue,
        config_field="squeue",
    )
    return parse_squeue_output(result.stdout)


async def query_sacct(
    conn: asyncssh.SSHClientConnection,
    *,
    config: LaunchpadConfig,
    job_id: str | None = None,
    user: str | None = None,
    start_time: str | None = None,
    duplicates: bool = False,
    sacct_binary: str | None = None,
) -> tuple[JobAccounting, ...]:
    """Run `sacct --json` remotely and parse the returned accounting records."""

    resolved_user = user if job_id else (user or config.ssh.username)
    resolved_sacct = sacct_binary or config.remote_binaries.sacct
    command = build_sacct_command(
        job_id=job_id,
        user=resolved_user,
        start_time=start_time,
        duplicates=duplicates,
        sacct_binary=resolved_sacct,
    )
    result = await run_slurm_command(
        conn,
        command,
        failure_prefix="SLURM sacct query failed",
        executable=resolved_sacct,
        config_field="sacct",
    )
    return parse_sacct_output(result.stdout)


async def query_sstat(
    conn: asyncssh.SSHClientConnection,
    *,
    config: LaunchpadConfig,
    job_steps: Sequence[str],
    sstat_binary: str | None = None,
) -> tuple[JobRuntimeStats, ...]:
    """Run `sstat` remotely and parse the returned live runtime metrics."""

    if not job_steps:
        return ()

    resolved_sstat = sstat_binary or config.remote_binaries.sstat
    command = build_sstat_command(job_steps=job_steps, sstat_binary=resolved_sstat)
    result = await run_slurm_command(
        conn,
        command,
        failure_prefix="SLURM sstat query failed",
        executable=resolved_sstat,
        config_field="sstat",
    )
    return parse_sstat_output(result.stdout)


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
    result = await run_slurm_command(
        conn,
        command,
        failure_prefix=f"SLURM submission failed for {request.script_path}",
        executable=resolved_sbatch,
        config_field="sbatch",
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


async def run_slurm_command(
    conn: asyncssh.SSHClientConnection,
    command: str,
    *,
    failure_prefix: str,
    executable: str,
    config_field: str | None = None,
) -> Any:
    """Run a scheduler command through the remote login shell."""

    result = await conn.run(build_slurm_login_shell_command(command), check=False)
    if result.exit_status != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise RuntimeError(
            _format_slurm_failure(
                failure_prefix,
                detail=detail,
                executable=executable,
                config_field=config_field,
            )
        )
    return result


async def resolve_slurm_executable(
    conn: asyncssh.SSHClientConnection,
    executable: str,
) -> str | None:
    """Resolve a scheduler executable through the cluster login-shell environment."""

    result = await conn.run(
        build_slurm_login_shell_command(_build_executable_resolution_command(executable)),
        check=False,
    )
    if result.exit_status != 0:
        return None
    return result.stdout.strip() or executable


def _load_slurm_json(raw: str, *, command_name: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid {command_name} JSON payload: {exc.msg}.") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"Invalid {command_name} JSON payload: expected an object root.")
    return payload


def _extract_jobs(payload: dict[str, Any], *, command_name: str) -> list[dict[str, Any]]:
    jobs = payload.get("jobs")
    if jobs is None:
        raise ValueError(f"Invalid {command_name} JSON payload: missing `jobs`.")
    if not isinstance(jobs, list):
        raise ValueError(f"Invalid {command_name} JSON payload: `jobs` must be a list.")

    normalized_jobs: list[dict[str, Any]] = []
    for job in jobs:
        if isinstance(job, dict):
            normalized_jobs.append(job)
            continue
        raise ValueError(f"Invalid {command_name} JSON payload: each job entry must be an object.")
    return normalized_jobs


def _parse_job_status(job: dict[str, Any]) -> JobStatus:
    job_id = _required_string(job, "job_id", "job_id_raw")
    derived_array_job_id, derived_array_task_id = _derive_array_ids(job_id)
    return JobStatus(
        job_id=job_id,
        job_name=_required_string(job, "name", "job_name"),
        state=_required_string(job, "state.current", "job_state", "state"),
        array_job_id=_optional_string(job, "array.job_id", "array_job_id") or derived_array_job_id,
        array_task_id=_optional_string(job, "array.task_id", "array_task_id") or derived_array_task_id,
        user_name=_optional_string(job, "user_name", "user"),
        partition=_optional_string(job, "partition"),
        node_list=_optional_string(job, "node_list", "nodes_alloc"),
        nodes=_optional_int(job, "node_count", "nodes"),
        cpus=_optional_int(job, "cpus", "cpus_per_task", "num_cpus"),
        elapsed=_optional_string(job, "time.elapsed", "elapsed", "elapsed_time"),
        time_limit=_optional_string(job, "time.limit", "time_limit", "limit"),
        state_reason=_optional_string(job, "state.reason", "state_reason", "reason"),
        comment=_optional_string(job, "comment"),
        work_dir=_optional_string(
            job,
            "current_working_directory",
            "working_directory",
            "work_dir",
        ),
        standard_output=_optional_string(job, "standard_output"),
        standard_error=_optional_string(job, "standard_error"),
        submit_time=_optional_string(job, "time.submission", "submit_time"),
        start_time=_optional_string(job, "time.start", "start_time"),
    )


def _parse_job_accounting(job: dict[str, Any]) -> JobAccounting:
    job_id = _required_string(job, "job_id", "job_id_raw")
    derived_array_job_id, derived_array_task_id = _derive_array_ids(job_id)
    return JobAccounting(
        job_id=job_id,
        job_name=_optional_string(job, "name", "job_name"),
        state=_required_string(job, "state.current", "job_state", "state"),
        array_job_id=_optional_string(job, "array.job_id", "array_job_id") or derived_array_job_id,
        array_task_id=_optional_string(job, "array.task_id", "array_task_id") or derived_array_task_id,
        partition=_optional_string(job, "partition"),
        node_list=_optional_string(job, "node_list", "nodes_alloc"),
        elapsed=_optional_string(job, "elapsed", "time.elapsed", "elapsed_time"),
        total_cpu=_optional_string(job, "total_cpu"),
        max_rss=_optional_string(job, "max_rss"),
        max_disk_read=_optional_string(job, "max_disk_read"),
        max_disk_write=_optional_string(job, "max_disk_write"),
        exit_code=_optional_exit_code(job, "exit_code"),
        derived_exit_code=_optional_exit_code(job, "derived_exit_code"),
        comment=_optional_string(job, "comment"),
        work_dir=_optional_string(job, "work_dir", "working_directory", "current_working_directory"),
        standard_output=_optional_string(job, "standard_output"),
        standard_error=_optional_string(job, "standard_error"),
        submit_time=_optional_string(job, "submit_time", "time.submission"),
        start_time=_optional_string(job, "start_time", "time.start"),
        end_time=_optional_string(job, "end_time", "time.end"),
    )


_MISSING = object()


def _lookup(record: dict[str, Any], path: str) -> Any:
    current: Any = record
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _coalesce(record: dict[str, Any], *paths: str) -> Any:
    for path in paths:
        value = _normalize_slurm_value(_lookup(record, path))
        if value is _MISSING or value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return _MISSING


def _required_string(record: dict[str, Any], *paths: str) -> str:
    value = _coalesce(record, *paths)
    rendered = _render_string(value)
    if rendered is None:
        joined = ", ".join(paths)
        raise ValueError(f"SLURM payload is missing required field(s): {joined}.")
    return rendered


def _optional_string(record: dict[str, Any], *paths: str) -> str | None:
    return _render_string(_coalesce(record, *paths))


def _optional_int(record: dict[str, Any], *paths: str) -> int | None:
    value = _normalize_slurm_value(_coalesce(record, *paths))
    if value is _MISSING:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return None
    return None


def _optional_exit_code(record: dict[str, Any], *paths: str) -> str | None:
    value = _coalesce(record, *paths)
    if value is _MISSING:
        return None
    if isinstance(value, dict):
        return_code = _render_string(
            value.get("return_code", value.get("returncode", value.get("status")))
        )
        signal = _render_string(value.get("signal"))
        if return_code is not None and signal is not None:
            return f"{return_code}:{signal}"
    return _render_string(value)


def _render_string(value: Any) -> str | None:
    value = _normalize_slurm_value(value)
    if value is _MISSING or value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        rendered_items = [item for item in (_render_string(item) for item in value) if item]
        return ",".join(rendered_items) or None
    return None


def _normalize_sstat_value(value: str) -> str | None:
    cleaned = value.strip()
    if not cleaned or cleaned.upper() == "N/A":
        return None
    return cleaned


def _parse_sstat_job_id(job_id: str) -> tuple[str, str | None, str]:
    base, _, step = job_id.partition(".")
    if not step:
        raise ValueError("Invalid sstat output: missing job step suffix.")

    array_job_id, array_task_id = _derive_array_ids(base)
    return array_job_id or base, array_task_id, step


def _normalize_slurm_value(value: Any) -> Any:
    if value is _MISSING:
        return _MISSING
    if not isinstance(value, dict) or "set" not in value:
        return value
    if not bool(value.get("set")):
        return None

    for key in ("number", "string", "value", "boolean", "bool", "float", "data", "name"):
        if key in value:
            return _normalize_slurm_value(value[key])
    return None


def _build_executable_resolution_command(executable: str) -> str:
    quoted_executable = shlex.quote(executable)
    return (
        f"candidate={quoted_executable}; "
        'path=$(command -v "$candidate" 2>/dev/null || true); '
        'if [ -n "$path" ] && [ -x "$path" ]; then printf "%s" "$path"; '
        'elif [ -x "$candidate" ]; then printf "%s" "$candidate"; '
        "else exit 1; fi"
    )


def _format_slurm_failure(
    failure_prefix: str,
    *,
    detail: str,
    executable: str,
    config_field: str | None = None,
) -> str:
    message = f"{failure_prefix}: {detail}"
    if not _is_command_not_found(detail, executable):
        return message

    guidance = (
        f"The cluster login shell did not expose `{PurePosixPath(executable).name}`. "
        "Ensure the head-node login-shell initialization loads SLURM"
    )
    if config_field is not None:
        guidance += f", or set `remote_binaries.{config_field}` to an absolute path."
    else:
        guidance += "."
    return f"{message}. {guidance}"


def _is_command_not_found(detail: str, executable: str) -> bool:
    lowered = detail.lower()
    basename = PurePosixPath(executable).name.lower()
    return "command not found" in lowered and basename in lowered


def _derive_array_ids(job_id: str) -> tuple[str | None, str | None]:
    if "_" not in job_id:
        return (None, None)
    parent, task_id = job_id.split("_", 1)
    if parent and task_id.isdigit():
        return (parent, task_id)
    return (None, None)
