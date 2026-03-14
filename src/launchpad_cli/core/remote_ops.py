"""Remote filesystem helpers used by submit, download, and cleanup workflows."""

from __future__ import annotations

import re
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
    manifest_path: str


@dataclass(frozen=True, slots=True)
class RemotePathEntry:
    """Typed metadata for an entry returned by a remote directory listing."""

    path: str
    size_bytes: int
    entry_type: str
    modified_epoch: float | None = None

    @property
    def name(self) -> str:
        """Return the basename for display-oriented workflows."""

        return PurePosixPath(self.path).name

    @property
    def is_dir(self) -> bool:
        """Return whether this entry represents a directory."""

        return self.entry_type == "directory"


def build_remote_job_layout(
    *,
    remote_job_dir: str,
    archive_name: str = "inputs.tar.zst",
    script_name: str = "submit.sbatch",
    manifest_name: str = "launchpad-manifest.json",
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
        manifest_path=str(PurePosixPath(job_dir) / manifest_name),
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


async def read_remote_text(
    conn: asyncssh.SSHClientConnection,
    path: str,
) -> str:
    """Read UTF-8 text from a remote file."""

    normalized = str(PurePosixPath(path))
    async with conn.start_sftp_client() as sftp:
        if not await sftp.exists(normalized):
            raise FileNotFoundError(normalized)
        async with sftp.open(normalized, "rb") as remote_file:
            payload = await remote_file.read()
    if isinstance(payload, bytes):
        return payload.decode("utf-8")
    return str(payload)


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


async def measure_remote_path(
    conn: asyncssh.SSHClientConnection,
    path: str,
    *,
    du_binary: str = "du",
) -> int:
    """Return the size of a remote path in bytes."""

    normalized = str(PurePosixPath(path))
    command = " ".join(
        [
            shlex.quote(du_binary),
            "-sb",
            "--",
            shlex.quote(normalized),
        ]
    )
    result = await conn.run(command, check=False)
    if result.exit_status != 0:
        raise RuntimeError(
            f"Remote size query failed for {normalized}: {result.stderr.strip() or result.stdout.strip() or 'unknown error'}"
        )

    size_text = (result.stdout or "").strip().split(maxsplit=1)[0] if result.stdout else ""
    if not size_text.isdigit():
        raise ValueError(f"Unexpected remote size output for {normalized}: {result.stdout!r}")
    return int(size_text)


async def compute_remote_sha256(
    conn: asyncssh.SSHClientConnection,
    path: str,
    *,
    sha256_binary: str = "sha256sum",
) -> str:
    """Return the SHA-256 checksum for a remote file."""

    normalized = str(PurePosixPath(path))
    command = " ".join(
        [
            shlex.quote(sha256_binary),
            "--",
            shlex.quote(normalized),
        ]
    )
    result = await conn.run(command, check=False)
    if result.exit_status != 0:
        raise RuntimeError(
            f"Remote checksum query failed for {normalized}: {result.stderr.strip() or result.stdout.strip() or 'unknown error'}"
        )

    match = re.match(r"^([0-9a-fA-F]{64})\b", (result.stdout or "").strip())
    if match is None:
        raise ValueError(f"Unexpected remote checksum output for {normalized}: {result.stdout!r}")
    return match.group(1).lower()


async def list_remote_directory(
    conn: asyncssh.SSHClientConnection,
    path: str,
    *,
    recursive: bool = False,
    find_binary: str = "find",
) -> tuple[RemotePathEntry, ...]:
    """List entries beneath a remote directory with typed metadata."""

    normalized = str(PurePosixPath(path))
    max_depth_clause = "" if recursive else " -maxdepth 1"
    command = (
        f"{shlex.quote(find_binary)} {shlex.quote(normalized)} -mindepth 1{max_depth_clause} "
        "-printf '%y\\t%s\\t%T@\\t%p\\n'"
    )
    result = await conn.run(command, check=False)
    if result.exit_status != 0:
        raise RuntimeError(
            f"Remote directory listing failed for {normalized}: {result.stderr.strip() or result.stdout.strip() or 'unknown error'}"
        )

    entries: list[RemotePathEntry] = []
    for line in sorted((result.stdout or "").splitlines()):
        if not line.strip():
            continue
        kind, size_text, modified_text, entry_path = line.split("\t", maxsplit=3)
        entries.append(
            RemotePathEntry(
                path=entry_path,
                size_bytes=int(size_text),
                entry_type=_remote_entry_type(kind),
                modified_epoch=float(modified_text),
            )
        )
    return tuple(entries)


async def delete_remote_path(
    conn: asyncssh.SSHClientConnection,
    path: str,
    *,
    recursive: bool = True,
    rm_binary: str = "rm",
) -> str:
    """Delete a remote path and return its normalized form."""

    normalized = str(PurePosixPath(path))
    if normalized in {".", "/"} or not str(path).strip():
        raise ValueError(f"Refusing to delete unsafe remote path: {path!r}")
    command = " ".join(
        [
            shlex.quote(rm_binary),
            "-rf" if recursive else "-f",
            "--",
            shlex.quote(normalized),
        ]
    )
    result = await conn.run(command, check=False)
    if result.exit_status != 0:
        raise RuntimeError(
            f"Remote delete failed for {normalized}: {result.stderr.strip() or result.stdout.strip() or 'unknown error'}"
        )
    return normalized


def _remote_entry_type(kind: str) -> str:
    """Map GNU `find -printf %y` type codes onto stable names."""

    return {
        "d": "directory",
        "f": "file",
        "l": "symlink",
    }.get(kind, "other")
