"""Tests for the `launchpad ls` command."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from click.testing import CliRunner

from launchpad_cli.cli import cli
from launchpad_cli.cli import ls as ls_module
from launchpad_cli.core.config import LaunchpadConfig, ResolvedConfig, SSHConfig
from launchpad_cli.core.remote_ops import RemotePathEntry


def test_ls_command_renders_short_listing(monkeypatch: pytest.MonkeyPatch) -> None:
    """The ls command should render a short listing for returned entries."""

    monkeypatch.setattr(ls_module, "configure_logging", lambda **kwargs: None)

    async def fake_run_ls(**kwargs) -> ls_module.ListingResult:  # type: ignore[no-untyped-def]
        return ls_module.ListingResult(
            requested_path="/shared/sergey",
            base_path="/shared/sergey",
            long_format=False,
            pattern=None,
            entries=(
                RemotePathEntry(
                    path="/shared/sergey/tank_v3",
                    size_bytes=0,
                    entry_type="directory",
                    modified_epoch=1710451200.0,
                ),
                RemotePathEntry(
                    path="/shared/sergey/notes.txt",
                    size_bytes=12,
                    entry_type="file",
                    modified_epoch=1710451201.0,
                ),
            ),
        )

    monkeypatch.setattr(ls_module, "_run_ls", fake_run_ls)

    result = CliRunner().invoke(cli, ["ls"])

    assert result.exit_code == 0
    assert "tank_v3/" in result.output
    assert "notes.txt" in result.output


@pytest.mark.asyncio
async def test_run_ls_uses_remote_root_for_relative_glob_patterns(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Glob listings should search from the stable non-glob prefix beneath the user root."""

    resolved = ResolvedConfig(
        config=LaunchpadConfig(
            ssh=SSHConfig(host="cluster.example.com", username="sergey"),
        ),
        layers=(),
    )
    recorded: dict[str, object] = {}

    monkeypatch.setattr(ls_module, "resolve_config", lambda **kwargs: resolved)

    @asynccontextmanager
    async def fake_ssh_session(_config: SSHConfig):  # type: ignore[no-untyped-def]
        yield object()

    async def fake_list_remote_directory(conn, path: str, *, recursive: bool, **kwargs):  # type: ignore[no-untyped-def]
        recorded["path"] = path
        recorded["recursive"] = recursive
        return (
            RemotePathEntry(
                path="/shared/sergey/tank_v3/summary.txt",
                size_bytes=32,
                entry_type="file",
                modified_epoch=1710451200.0,
            ),
            RemotePathEntry(
                path="/shared/sergey/tank_v3/result.bin",
                size_bytes=64,
                entry_type="file",
                modified_epoch=1710451201.0,
            ),
        )

    monkeypatch.setattr(ls_module, "ssh_session", fake_ssh_session)
    monkeypatch.setattr(ls_module, "list_remote_directory", fake_list_remote_directory)

    result = await ls_module._run_ls(
        cwd=tmp_path,
        env={},
        remote_path="tank_v3/*.txt",
        long_format=True,
    )

    assert recorded == {"path": "/shared/sergey/tank_v3", "recursive": True}
    assert result.pattern == "/shared/sergey/tank_v3/*.txt"
    assert [entry.path for entry in result.entries] == ["/shared/sergey/tank_v3/summary.txt"]
