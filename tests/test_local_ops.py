"""Tests for local download filesystem helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from launchpad_cli.core import local_ops


def test_resolve_download_destination_defaults_to_results_dir(tmp_path: Path) -> None:
    """Download destinations should default to a run-scoped results directory."""

    destination = local_ops.resolve_download_destination(
        None,
        run_name="tank_v3",
        cwd=tmp_path,
    )

    assert destination == tmp_path / "results_tank_v3"


def test_resolve_download_destination_rejects_existing_file(tmp_path: Path) -> None:
    """Download destinations must resolve to directories, not files."""

    destination = tmp_path / "results.txt"
    destination.write_text("placeholder", encoding="utf-8")

    with pytest.raises(NotADirectoryError):
        local_ops.resolve_download_destination(
            destination,
            run_name="tank_v3",
            cwd=tmp_path,
        )


def test_resolve_download_destination_expands_home_before_joining_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Home-relative paths should resolve from the user's home, not the cwd."""

    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))

    destination = local_ops.resolve_download_destination(
        Path("~/Downloads"),
        run_name="tank_v3",
        cwd=tmp_path / "workspace",
    )

    assert destination == home_dir / "Downloads"


def test_inspect_disk_space_uses_nearest_existing_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disk checks should probe the closest existing directory for missing targets."""

    seen: list[Path] = []

    def fake_disk_usage(path: Path) -> SimpleNamespace:
        seen.append(path)
        return SimpleNamespace(total=1_000, used=400, free=600)

    monkeypatch.setattr(local_ops.shutil, "disk_usage", fake_disk_usage)

    report = local_ops.inspect_disk_space(
        tmp_path / "results" / "run-123",
        required_bytes=550,
        reserve_bytes=100,
    )

    assert seen == [tmp_path]
    assert report.probe_path == tmp_path
    assert report.bytes_available == 500
    assert report.sufficient is False
    assert report.bytes_missing == 50
