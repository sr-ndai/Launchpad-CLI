"""Tests for the `launchpad ls` command."""

from __future__ import annotations

from contextlib import asynccontextmanager
import json
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
    assert "/shared/sergey" in result.output
    assert "Type" in result.output
    assert "Name" in result.output
    assert "tank_v3/" in result.output
    assert "notes.txt" in result.output


def test_ls_command_emits_json_when_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    """The ls command should honor the root JSON flag."""

    monkeypatch.setattr(ls_module, "configure_logging", lambda **kwargs: None)

    async def fake_run_ls(**kwargs) -> ls_module.ListingResult:  # type: ignore[no-untyped-def]
        return ls_module.ListingResult(
            requested_path="/shared/sergey",
            base_path="/shared/sergey",
            long_format=True,
            pattern=None,
            entries=(
                RemotePathEntry(
                    path="/shared/sergey/tank_v3",
                    size_bytes=0,
                    entry_type="directory",
                    modified_epoch=1710451200.0,
                ),
            ),
        )

    monkeypatch.setattr(ls_module, "_run_ls", fake_run_ls)

    result = CliRunner().invoke(cli, ["--json", "ls"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["requested_path"] == "/shared/sergey"
    assert payload["long_format"] is True
    assert payload["entries"][0]["path"] == "/shared/sergey/tank_v3"


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


@pytest.mark.asyncio
async def test_run_ls_uses_configured_workspace_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Configured workspace roots should become the default base for relative ls paths."""

    resolved = ResolvedConfig(
        config=LaunchpadConfig(
            cluster={"workspace_root": "/shared/launchpad"},
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
        return ()

    monkeypatch.setattr(ls_module, "ssh_session", fake_ssh_session)
    monkeypatch.setattr(ls_module, "list_remote_directory", fake_list_remote_directory)

    result = await ls_module._run_ls(
        cwd=tmp_path,
        env={},
        remote_path="tank_v3",
        long_format=False,
    )

    assert recorded == {"path": "/shared/launchpad/tank_v3", "recursive": False}
    assert result.requested_path == "/shared/launchpad/tank_v3"


def test_ls_command_renders_empty_state_when_no_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty remote listings should produce a visible empty-state panel."""

    monkeypatch.setattr(ls_module, "configure_logging", lambda **kwargs: None)

    async def fake_run_ls(**kwargs) -> ls_module.ListingResult:  # type: ignore[no-untyped-def]
        return ls_module.ListingResult(
            requested_path="/shared/sergey/missing*",
            base_path="/shared/sergey",
            long_format=False,
            pattern="/shared/sergey/missing*",
            entries=(),
        )

    monkeypatch.setattr(ls_module, "_run_ls", fake_run_ls)

    result = CliRunner().invoke(cli, ["ls", "missing*"])

    assert result.exit_code == 0
    assert "No remote entries matched" in result.output
    assert "/shared/sergey/missing*" in result.output
