"""Tests for solver adapter behavior and input discovery."""

from __future__ import annotations

from pathlib import Path

import pytest

from launchpad_cli.core.config import LaunchpadConfig
from launchpad_cli.solvers import AnsysAdapter, NastranAdapter, SolverAdapter, SubmitOverrides
from launchpad_cli.solvers.base import DiscoveredInput


def test_nastran_adapter_conforms_to_solver_protocol() -> None:
    """The concrete Nastran adapter should satisfy the shared protocol."""

    adapter = NastranAdapter()

    assert isinstance(adapter, SolverAdapter)
    assert adapter.output_extensions == (".f06", ".op2", ".log")


def test_nastran_discovery_returns_sorted_metadata(tmp_path: Path) -> None:
    """Discovery should scan the top-level directory deterministically."""

    (tmp_path / "b.dat").write_text("BEGIN BULK\n", encoding="utf-8")
    (tmp_path / "a.DAT").write_text("SOL 101\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignore me\n", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "c.dat").write_text("nested\n", encoding="utf-8")

    discovered = NastranAdapter().discover_inputs(tmp_path)

    assert [item.basename for item in discovered] == ["a.DAT", "b.dat"]
    assert discovered[0] == DiscoveredInput(
        path=tmp_path / "a.DAT",
        relative_path=Path("a.DAT"),
        stem="a",
        extension=".dat",
        size_bytes=len("SOL 101\n"),
    )


def test_nastran_discovery_raises_for_missing_directory(tmp_path: Path) -> None:
    """Discovery should fail clearly when the input directory is missing."""

    with pytest.raises(FileNotFoundError):
        NastranAdapter().discover_inputs(tmp_path / "missing")


def test_nastran_build_run_command_uses_config_defaults_and_overrides() -> None:
    """Run command construction should be deterministic and override-aware."""

    config = LaunchpadConfig()
    adapter = NastranAdapter.from_config(config)

    default_command = adapter.build_run_command("wing_box.dat", config)
    override_command = adapter.build_run_command(
        "wing_box.dat",
        config,
        SubmitOverrides(cpus=24, memory="128Gb"),
    )

    assert "/shared/siemens/nastran2312/bin/nastran" in default_command
    assert "wing_box.dat" in default_command
    assert "smp=12" in default_command
    assert "memory=236Gb" in default_command
    assert "buffpool=5Gb" in default_command
    assert "memorymaximum=236Gb" in default_command
    assert "smp=24" in override_command
    assert "memory=128Gb" in override_command


def test_nastran_build_scratch_env_uses_shared_filesystem_path() -> None:
    """Scratch environment setup should point all temp paths at the shared root."""

    scratch_env = NastranAdapter().build_scratch_env("/shared/sergey/run/scratch")

    assert scratch_env == {
        "NASTRAN_SCRATCH": "/shared/sergey/run/scratch",
        "TMPDIR": "/shared/sergey/run/scratch",
        "TMP": "/shared/sergey/run/scratch",
        "TEMP": "/shared/sergey/run/scratch",
    }


def test_ansys_adapter_raises_clear_stub_errors() -> None:
    """ANSYS should remain an explicit stub until the workflow is defined."""

    adapter = AnsysAdapter()
    config = LaunchpadConfig()

    with pytest.raises(NotImplementedError, match="ANSYS submit support is intentionally deferred"):
        adapter.discover_inputs(Path.cwd())

    with pytest.raises(NotImplementedError, match="ANSYS submit support is intentionally deferred"):
        adapter.build_run_command("model.dat", config)

    with pytest.raises(NotImplementedError, match="ANSYS submit support is intentionally deferred"):
        adapter.build_scratch_env("/shared/sergey/scratch")
