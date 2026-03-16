"""Shared remote workspace-root resolution helpers."""

from __future__ import annotations

from pathlib import PurePosixPath

import asyncssh
import click
from loguru import logger

from launchpad_cli.core.config import LaunchpadConfig


def resolve_remote_workspace_root(config: LaunchpadConfig) -> str:
    """Resolve the writable Launchpad workspace root from config."""

    configured_root = config.cluster.workspace_root
    if configured_root:
        root = PurePosixPath(configured_root)
        if not root.is_absolute():
            raise click.ClickException("`cluster.workspace_root` must be an absolute remote path.")
        return str(root)

    username = config.ssh.username
    if not username:
        raise click.ClickException(
            "Cannot resolve the remote workspace root without `ssh.username`. "
            "Set `cluster.workspace_root` or `ssh.username`."
        )
    return str(PurePosixPath(config.cluster.shared_root) / username)


async def infer_remote_job_dir(
    conn: asyncssh.SSHClientConnection,
    config: LaunchpadConfig,
    *,
    run_name: str,
    job_id: str,
) -> str:
    """Derive the remote job directory when the SLURM comment is unavailable.

    Some clusters do not persist the job comment in accounting data. Since the
    submit flow always places the job directory at ``workspace_root / run_name``,
    we reconstruct the path from the job name and verify it exists.
    """
    workspace_root = resolve_remote_workspace_root(config)
    candidate = str(PurePosixPath(workspace_root) / run_name)
    async with conn.start_sftp_client() as sftp:
        if await sftp.exists(candidate):
            logger.debug(
                "Inferred remote_job_dir from workspace root for job {}: {}",
                job_id,
                candidate,
            )
            return candidate
    raise RuntimeError(
        f"No remote job directory metadata is available for job {job_id}. "
        f"Tried inferring from workspace root but {candidate} does not exist. "
        "If the job was submitted from a different machine or workspace root, "
        "check your config with: launchpad config show"
    )
