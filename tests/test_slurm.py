"""Tests for SLURM submit-script generation and submission helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from launchpad_cli.core.config import LaunchpadConfig
from launchpad_cli.core.slurm import SubmitRequest, build_submit_script, submit_job
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
    assert connection.commands == ["sbatch --parsable /shared/sergey/nastran-20260312-1947-abcd/submit.sbatch"]


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
