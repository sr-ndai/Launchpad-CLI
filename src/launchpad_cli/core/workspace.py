"""Shared remote workspace-root resolution helpers."""

from __future__ import annotations

from pathlib import PurePosixPath

import click

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
