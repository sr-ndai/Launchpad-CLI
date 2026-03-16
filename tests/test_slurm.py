"""Tests for SLURM submit, status, and accounting helpers."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from launchpad_cli.core.config import LaunchpadConfig, SSHConfig
from launchpad_cli.core.slurm import (
    SubmitRequest,
    build_sstat_command,
    build_slurm_login_shell_command,
    build_submit_script,
    parse_sacct_output,
    parse_sstat_output,
    parse_squeue_output,
    query_sacct,
    query_squeue,
    query_sstat,
    submit_job,
)
from launchpad_cli.solvers import NastranAdapter, SubmitOverrides


class FakeConnection:
    """Connection double capturing remote writes and commands."""

    def __init__(self) -> None:
        self.written: dict[str, bytes] = {}
        self.directories: list[str] = []
        self.commands: list[str] = []
        self.run_result = SimpleNamespace(exit_status=0, stdout="12345\n", stderr="")

    async def run(self, command: str, check: bool = False) -> SimpleNamespace:
        self.commands.append(command)
        return self.run_result

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def start_sftp_client(self):  # type: ignore[no-untyped-def]
        connection = self

        class FakeRemoteFile:
            def __init__(self, path: str) -> None:
                self.path = path

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb) -> None:
                return None

            async def write(self, data: bytes) -> int:
                connection.written[self.path] = data
                return len(data)

        class FakeSFTPClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb) -> None:
                return None

            async def makedirs(self, path: str, exist_ok: bool = False) -> None:
                connection.directories.append(path)

            def open(self, path: str, mode: str) -> FakeRemoteFile:
                return FakeRemoteFile(path)

        yield FakeSFTPClient()


SQUEUE_SAMPLE = json.dumps(
    {
        "meta": {"plugin": "test"},
        "jobs": [
            {
                "job_id": 12345,
                "name": "nastran-20260312-1947-abcd",
                "partition": "simulation-r6i-8x",
                "user_name": "sergey",
                "state": {"current": "RUNNING", "reason": "None"},
                "array": {"job_id": 12345, "task_id": 2},
                "node_list": "compute-dy-2",
                "nodes": 1,
                "cpus": 24,
                "time": {
                    "elapsed": "02:14:33",
                    "limit": "99:00:00",
                    "submission": "2026-03-12T19:47:00",
                    "start": "2026-03-12T19:49:00",
                },
                "comment": "/shared/sergey/nastran-20260312-1947-abcd",
                "current_working_directory": "/shared/sergey/nastran-20260312-1947-abcd/results_wing_2",
                "standard_output": "/shared/sergey/nastran-20260312-1947-abcd/logs/slurm_%A_%a.out",
                "standard_error": "/shared/sergey/nastran-20260312-1947-abcd/logs/slurm_%A_%a.err",
            }
        ],
    }
)

SACCT_SAMPLE = json.dumps(
    {
        "meta": {"plugin": "test"},
        "jobs": [
            {
                "job_id": "12345_2",
                "name": "nastran-20260312-1947-abcd",
                "partition": "simulation-r6i-8x",
                "state": "COMPLETED",
                "node_list": "compute-dy-2",
                "elapsed": "01:45:12",
                "total_cpu": "17:33.221",
                "max_rss": "178G",
                "exit_code": {"return_code": 0, "signal": 0},
                "derived_exit_code": {"return_code": 0, "signal": 0},
                "comment": "/shared/sergey/nastran-20260312-1947-abcd",
                "work_dir": "/shared/sergey/nastran-20260312-1947-abcd/results_wing_2",
                "standard_output": "/shared/sergey/nastran-20260312-1947-abcd/logs/slurm_12345_2.out",
                "standard_error": "/shared/sergey/nastran-20260312-1947-abcd/logs/slurm_12345_2.err",
                "submit_time": "2026-03-12T19:47:00",
                "start_time": "2026-03-12T19:49:00",
                "end_time": "2026-03-12T21:34:12",
            }
        ],
    }
)

SQUEUE_TYPED_WRAPPER_SAMPLE = json.dumps(
    {
        "meta": {"plugin": "test"},
        "jobs": [
            {
                "job_id": 67890,
                "name": "tank_v3",
                "partition": "simulation-r6i-8x",
                "user_name": "sergey",
                "state": {"current": "RUNNING", "reason": "None"},
                "array_job_id": {"set": True, "number": 67890},
                "array_task_id": {"set": True, "number": 7},
                "nodes_alloc": "simulation-r61-8x-dy-r6i-8xlarge7-2",
                "node_count": {"set": True, "number": 1},
                "cpus": {"set": True, "number": 12},
                "cpus_per_task": {"set": True, "number": 12},
                "time": {
                    "elapsed": "00:10:00",
                    "limit": "99:00:00",
                    "submission": "2026-03-14T10:00:00",
                    "start": "2026-03-14T10:01:00",
                },
                "comment": "/shared/launchpad/tank_v3",
            }
        ],
    }
)

SACCT_TYPED_WRAPPER_SAMPLE = json.dumps(
    {
        "meta": {"plugin": "test"},
        "jobs": [
            {
                "job_id": "67890_7",
                "name": "tank_v3",
                "partition": "simulation-r6i-8x",
                "state": "COMPLETED",
                "array_job_id": {"set": True, "number": 67890},
                "array_task_id": {"set": True, "number": 7},
                "nodes_alloc": "simulation-r61-8x-dy-r6i-8xlarge7-2",
                "elapsed": "00:12:00",
                "total_cpu": "02:24.000",
                "max_rss": "12G",
                "comment": "/shared/launchpad/tank_v3",
            }
        ],
    }
)

SSTAT_SAMPLE = "\n".join(
    [
        "12345_2.batch|178G|17:33.221|12001.66M|12000.01M",
        "12346.batch|||N/A|",
    ]
)

# SLURM 21.08+ sacct JSON: resource fields under "stats"/"time", node name under "nodes"
SACCT_NESTED_FIELDS_SAMPLE = json.dumps(
    {
        "meta": {"plugin": "test"},
        "jobs": [
            {
                "job_id": "99001",
                "name": "gpu-job",
                "partition": "gpu",
                "state": {"current": "COMPLETED", "reason": "None"},
                "nodes": "gpu-compute-01",
                "elapsed": "00:30:00",
                "time": {
                    "elapsed": "00:30:00",
                    "total_cpu": "02:00:00",
                    "submission": "2026-03-14T10:00:00",
                    "start": "2026-03-14T10:01:00",
                    "end": "2026-03-14T10:31:00",
                },
                "stats": {
                    "max_rss": {"set": True, "number": 1073741824.0},
                    "max_disk_read": {"set": True, "number": 524288.0},
                    "max_disk_write": {"set": True, "number": 262144.0},
                },
                "comment": "/shared/launchpad/gpu-job",
                "work_dir": "/shared/launchpad/gpu-job/results",
            }
        ],
    }
)

# SLURM squeue JSON where nodelist is under "nodes" (plain string) instead of "node_list"
SQUEUE_NODES_FIELD_SAMPLE = json.dumps(
    {
        "meta": {"plugin": "test"},
        "jobs": [
            {
                "job_id": 88001,
                "name": "cfd-run",
                "partition": "compute",
                "user_name": "alice",
                "state": {"current": "RUNNING", "reason": "None"},
                "nodes": "compute-node-03",
                "node_count": {"set": True, "number": 1},
                "cpus": 8,
                "time": {
                    "elapsed": "01:00:00",
                    "limit": "08:00:00",
                    "submission": "2026-03-14T09:00:00",
                    "start": "2026-03-14T09:01:00",
                },
                "comment": "/shared/launchpad/cfd-run",
            }
        ],
    }
)


def test_build_submit_script_includes_expected_slurm_and_solver_content() -> None:
    """Submit script generation should preserve the documented Phase 2 decisions."""

    config = LaunchpadConfig()
    request = SubmitRequest(
        run_name="nastran-20260312-1947-abcd",
        remote_job_dir="/shared/sergey/nastran-20260312-1947-abcd",
        script_path="/shared/sergey/nastran-20260312-1947-abcd/submit.sbatch",
        input_files=("wing.dat", "fuselage.dat"),
        max_concurrent=1,
        begin="2026-03-13T01:00:00",
        solver_overrides=SubmitOverrides(cpus=24, memory="128Gb"),
    )

    script = build_submit_script(NastranAdapter(), request, config)

    assert "#SBATCH --job-name=nastran-20260312-1947-abcd" in script
    assert "#SBATCH --array=0-1%1" in script
    assert "#SBATCH --cpus-per-task=24" in script
    assert "#SBATCH --partition=simulation-r6i-8x" in script
    assert "#SBATCH --begin=2026-03-13T01:00:00" in script
    assert "#SBATCH --comment=/shared/sergey/nastran-20260312-1947-abcd" in script
    assert 'cat > "$MANIFEST_PATH" <<\'EOF_MANIFEST\'' in script
    assert "wing.dat" in script and "fuselage.dat" in script
    assert 'RESULT_DIR="${JOB_DIR}/results_${INPUT_STEM}_${SLURM_ARRAY_TASK_ID}"' in script
    assert 'export NASTRAN_SCRATCH="${SCRATCH_ROOT}/task_${SLURM_ARRAY_TASK_ID}"' in script
    assert "smp=24" in script
    assert "memory=128Gb" in script


def test_build_submit_script_includes_configured_solver_environment_exports() -> None:
    """Configured solver env vars should be exported into the generated SLURM script."""

    config = LaunchpadConfig(
        solvers={
            "nastran": {
                "environment": {
                    "SPLM_LICENSE_SERVER": "29001@eng-apps-license-01.rs.corp",
                }
            }
        }
    )
    request = SubmitRequest(
        run_name="nastran-20260312-1947-abcd",
        remote_job_dir="/shared/sergey/nastran-20260312-1947-abcd",
        script_path="/shared/sergey/nastran-20260312-1947-abcd/submit.sbatch",
        input_files=("wing.dat",),
    )

    script = build_submit_script(NastranAdapter.from_config(config), request, config)

    assert 'export SPLM_LICENSE_SERVER="29001@eng-apps-license-01.rs.corp"' in script
    assert 'export NASTRAN_SCRATCH="${SCRATCH_ROOT}/task_${SLURM_ARRAY_TASK_ID}"' in script


def test_build_sstat_command_targets_batch_steps() -> None:
    """Live-metric queries should use parsable batch-step targets."""

    command = build_sstat_command(job_steps=("12345.batch", "12345_2.batch"))

    assert command == (
        "sstat --noheader --parsable2 --format=JobID,MaxRSS,AveCPU,MaxDiskRead,MaxDiskWrite "
        "--jobs 12345.batch,12345_2.batch"
    )


def test_build_submit_script_requires_inputs() -> None:
    """Script generation should fail fast when no solver inputs are provided."""

    with pytest.raises(ValueError):
        build_submit_script(
            NastranAdapter(),
            SubmitRequest(
                run_name="empty",
                remote_job_dir="/shared/sergey/empty",
                script_path="/shared/sergey/empty/submit.sbatch",
                input_files=(),
            ),
            LaunchpadConfig(),
        )


def test_parse_squeue_output_returns_structured_job_status() -> None:
    """`squeue --json` parsing should normalize nested scheduler fields."""

    jobs = parse_squeue_output(SQUEUE_SAMPLE)

    assert len(jobs) == 1
    assert jobs[0].job_id == "12345"
    assert jobs[0].job_name == "nastran-20260312-1947-abcd"
    assert jobs[0].state == "RUNNING"
    assert jobs[0].array_job_id == "12345"
    assert jobs[0].array_task_id == "2"
    assert jobs[0].node_list == "compute-dy-2"
    assert jobs[0].cpus == 24
    assert jobs[0].elapsed == "02:14:33"
    assert jobs[0].remote_job_dir == "/shared/sergey/nastran-20260312-1947-abcd"


def test_parse_sacct_output_returns_structured_job_accounting() -> None:
    """`sacct --json` parsing should preserve accounting and tracking fields."""

    jobs = parse_sacct_output(SACCT_SAMPLE)

    assert len(jobs) == 1
    assert jobs[0].job_id == "12345_2"
    assert jobs[0].job_name == "nastran-20260312-1947-abcd"
    assert jobs[0].state == "COMPLETED"
    assert jobs[0].array_job_id == "12345"
    assert jobs[0].array_task_id == "2"
    assert jobs[0].exit_code == "0:0"
    assert jobs[0].derived_exit_code == "0:0"
    assert jobs[0].max_rss == "178G"
    assert jobs[0].remote_job_dir == "/shared/sergey/nastran-20260312-1947-abcd"


def test_parse_squeue_output_handles_typed_wrappers_and_host_style_nodes_alloc() -> None:
    """Wrapper objects and host-style node strings should parse without crashing."""

    jobs = parse_squeue_output(SQUEUE_TYPED_WRAPPER_SAMPLE)

    assert len(jobs) == 1
    assert jobs[0].job_id == "67890"
    assert jobs[0].array_job_id == "67890"
    assert jobs[0].array_task_id == "7"
    assert jobs[0].node_list == "simulation-r61-8x-dy-r6i-8xlarge7-2"
    assert jobs[0].nodes == 1
    assert jobs[0].cpus == 12
    assert jobs[0].remote_job_dir == "/shared/launchpad/tank_v3"


def test_parse_sacct_output_handles_typed_wrappers_and_host_style_nodes_alloc() -> None:
    """Accounting parsing should accept typed wrappers and preserve host-style node names."""

    jobs = parse_sacct_output(SACCT_TYPED_WRAPPER_SAMPLE)

    assert len(jobs) == 1
    assert jobs[0].job_id == "67890_7"
    assert jobs[0].array_job_id == "67890"
    assert jobs[0].array_task_id == "7"
    assert jobs[0].node_list == "simulation-r61-8x-dy-r6i-8xlarge7-2"
    assert jobs[0].total_cpu == "02:24.000"
    assert jobs[0].remote_job_dir == "/shared/launchpad/tank_v3"


def test_parse_sacct_output_handles_nested_slurm21_fields() -> None:
    """sacct parsing should pick up node, cpu, and memory from SLURM 21.08+ nested paths."""

    jobs = parse_sacct_output(SACCT_NESTED_FIELDS_SAMPLE)

    assert len(jobs) == 1
    assert jobs[0].node_list == "gpu-compute-01"
    assert jobs[0].total_cpu == "02:00:00"
    assert jobs[0].max_rss == "1.0 GB"
    assert jobs[0].max_disk_read == "512.0 KB"
    assert jobs[0].max_disk_write == "256.0 KB"


def test_parse_squeue_output_handles_nodes_field_as_nodelist() -> None:
    """squeue parsing should fall back to 'nodes' as a nodelist string when node_list is absent."""

    jobs = parse_squeue_output(SQUEUE_NODES_FIELD_SAMPLE)

    assert len(jobs) == 1
    assert jobs[0].node_list == "compute-node-03"


def test_parse_sstat_output_returns_structured_runtime_stats() -> None:
    """`sstat --parsable2` parsing should normalize job-step identifiers and blanks."""

    rows = parse_sstat_output(SSTAT_SAMPLE)

    assert len(rows) == 2
    assert rows[0].job_id == "12345"
    assert rows[0].task_id == "2"
    assert rows[0].step == "batch"
    assert rows[0].max_rss == "178G"
    assert rows[0].ave_cpu == "17:33.221"
    assert rows[0].max_disk_read == "12001.66M"
    assert rows[0].max_disk_write == "12000.01M"
    assert rows[1].job_id == "12346"
    assert rows[1].task_id is None
    assert rows[1].ave_cpu is None
    assert rows[1].max_disk_read is None


@pytest.mark.asyncio
async def test_submit_job_writes_script_and_parses_parsable_job_id() -> None:
    """Submission should write the script remotely and parse `sbatch --parsable` output."""

    connection = FakeConnection()
    config = LaunchpadConfig()
    request = SubmitRequest(
        run_name="nastran-20260312-1947-abcd",
        remote_job_dir="/shared/sergey/nastran-20260312-1947-abcd",
        script_path="/shared/sergey/nastran-20260312-1947-abcd/submit.sbatch",
        input_files=("wing.dat",),
    )

    result = await submit_job(
        connection,
        solver=NastranAdapter(),
        request=request,
        config=config,
    )

    assert result.job_id == "12345"
    assert request.script_path in connection.written
    assert connection.commands == [
        build_slurm_login_shell_command(
            "sbatch --parsable /shared/sergey/nastran-20260312-1947-abcd/submit.sbatch"
        )
    ]


@pytest.mark.asyncio
async def test_submit_job_raises_on_sbatch_failure() -> None:
    """Submission failures should include the remote stderr payload."""

    connection = FakeConnection()
    connection.run_result = SimpleNamespace(exit_status=1, stdout="", stderr="invalid partition")
    request = SubmitRequest(
        run_name="nastran-20260312-1947-abcd",
        remote_job_dir="/shared/sergey/nastran-20260312-1947-abcd",
        script_path="/shared/sergey/nastran-20260312-1947-abcd/submit.sbatch",
        input_files=("wing.dat",),
    )

    with pytest.raises(RuntimeError, match="invalid partition"):
        await submit_job(
            connection,
            solver=NastranAdapter(),
            request=request,
            config=LaunchpadConfig(),
        )


@pytest.mark.asyncio
async def test_query_squeue_uses_current_user_filter_and_parses_results() -> None:
    """Remote `squeue` queries should default to the configured SSH username."""

    connection = FakeConnection()
    connection.run_result = SimpleNamespace(exit_status=0, stdout=SQUEUE_SAMPLE, stderr="")

    jobs = await query_squeue(
        connection,
        config=LaunchpadConfig(ssh=SSHConfig(username="sergey")),
    )

    assert connection.commands == [build_slurm_login_shell_command("squeue --json --user sergey")]
    assert jobs[0].job_id == "12345"
    assert jobs[0].state == "RUNNING"


@pytest.mark.asyncio
async def test_query_sacct_builds_job_specific_command_and_parses_results() -> None:
    """Remote `sacct` queries should build a narrow job-specific command."""

    connection = FakeConnection()
    connection.run_result = SimpleNamespace(exit_status=0, stdout=SACCT_SAMPLE, stderr="")

    jobs = await query_sacct(
        connection,
        config=LaunchpadConfig(),
        job_id="12345",
        start_time="2026-03-01",
        duplicates=True,
    )

    assert connection.commands == [
        build_slurm_login_shell_command(
            "sacct --json --allocations --duplicates --starttime 2026-03-01 --jobs 12345"
        )
    ]
    assert jobs[0].job_id == "12345_2"
    assert jobs[0].state == "COMPLETED"


@pytest.mark.asyncio
async def test_query_sstat_builds_job_step_command_and_parses_results() -> None:
    """Remote `sstat` queries should target the requested batch steps."""

    connection = FakeConnection()
    connection.run_result = SimpleNamespace(exit_status=0, stdout=SSTAT_SAMPLE, stderr="")

    rows = await query_sstat(
        connection,
        config=LaunchpadConfig(),
        job_steps=("12345.batch", "12345_2.batch"),
    )

    assert connection.commands == [
        build_slurm_login_shell_command(
            "sstat --noheader --parsable2 --format=JobID,MaxRSS,AveCPU,MaxDiskRead,MaxDiskWrite "
            "--jobs 12345.batch,12345_2.batch"
        )
    ]
    assert rows[0].job_id == "12345"
    assert rows[0].task_id == "2"


@pytest.mark.asyncio
async def test_query_squeue_reports_login_shell_guidance_when_scheduler_is_missing() -> None:
    """Missing scheduler binaries should point operators toward login-shell init or absolute paths."""

    connection = FakeConnection()
    connection.run_result = SimpleNamespace(
        exit_status=127,
        stdout="",
        stderr="bash: line 1: squeue: command not found",
    )

    with pytest.raises(RuntimeError) as excinfo:
        await query_squeue(
            connection,
            config=LaunchpadConfig(ssh=SSHConfig(username="sergey")),
        )

    message = str(excinfo.value)
    assert "login shell did not expose `squeue`" in message
    assert "remote_binaries.squeue" in message
