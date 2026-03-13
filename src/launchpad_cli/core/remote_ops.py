"""Remote filesystem helpers used by submit-oriented workflows."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import PurePosixPath

import asyncssh


@dataclass(frozen=True, slots=True)
class RemoteJobLayout:
    """Canonical remote paths used by a submission job."""

    job_dir: str
    logs_dir: str
    scratch_root: str
    archive_path: str
    script_path: str


def build_remote_job_layout(
    *,
    remote_job_dir: str,
    archive_name: str = "inputs.tar.zst",
    script_name: str = "submit.sbatch",
    logs_subdir: str = "logs",
    scratch_root_template: str = "{job_dir}/scratch",
) -> RemoteJobLayout:
    """Build the standard remote path layout for a submit job."""

    job_dir = str(PurePosixPath(remote_job_dir))
    return RemoteJobLayout(
        job_dir=job_dir,
        logs_dir=str(PurePosixPath(job_dir) / logs_subdir),
        scratch_root=scratch_root_template.format(job_dir=job_dir),
        archive_path=str(PurePosixPath(job_dir) / archive_name),
        script_path=str(PurePosixPath(job_dir) / script_name),
    )


async def ensure_remote_directory(
    conn: asyncssh.SSHClientConnection,
    path: str,
) -> str:
    """Ensure a remote directory exists and return its normalized path."""

    normalized = str(PurePosixPath(path))
    async with conn.start_sftp_client() as sftp:
        await sftp.makedirs(normalized, exist_ok=True)
    return normalized


async def write_remote_text(
    conn: asyncssh.SSHClientConnection,
    path: str,
    content: str,
) -> str:
    """Write UTF-8 text to a remote file, creating parent directories as needed."""

    normalized = str(PurePosixPath(path))
    parent = str(PurePosixPath(normalized).parent)
    async with conn.start_sftp_client() as sftp:
        if parent not in ("", ".", "/"):
            await sftp.makedirs(parent, exist_ok=True)
        async with sftp.open(normalized, "wb") as remote_file:
            await remote_file.write(content.encode("utf-8"))
    return normalized


async def prepare_remote_job_directory(
    conn: asyncssh.SSHClientConnection,
    layout: RemoteJobLayout,
) -> RemoteJobLayout:
    """Create the remote job root plus its logs and scratch directories."""

    await ensure_remote_directory(conn, layout.job_dir)
    await ensure_remote_directory(conn, layout.logs_dir)
    await ensure_remote_directory(conn, layout.scratch_root)
    return layout


async def extract_remote_archive(
    conn: asyncssh.SSHClientConnection,
    *,
    archive_path: str,
    destination_dir: str,
    tar_binary: str = "tar",
    zstd_binary: str = "zstd",
) -> None:
    """Extract a `.tar.zst` archive on the remote host using configured binaries."""

    destination = str(PurePosixPath(destination_dir))
    command = " ".join(
        [
            shlex.quote(tar_binary),
            f"--use-compress-program={shlex.quote(zstd_binary)}",
            "-xf",
            shlex.quote(str(PurePosixPath(archive_path))),
            "-C",
            shlex.quote(destination),
        ]
    )
    result = await conn.run(command, check=False)
    if result.exit_status != 0:
        raise RuntimeError(
            f"Remote archive extraction failed for {archive_path}: {result.stderr.strip() or result.stdout.strip() or 'unknown error'}"
        )
