"""Repository scaffold verification tests."""

from __future__ import annotations

import tomllib
from pathlib import Path

from launchpad_cli.solvers.ansys import AnsysAdapter
from launchpad_cli.solvers.nastran import NastranAdapter

ROOT = Path(__file__).resolve().parents[1]


def test_console_scripts_register_both_launchpad_entry_points() -> None:
    """The package metadata should expose both documented CLI entry points."""

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    scripts = project["project"]["scripts"]

    assert scripts["launchpad"] == "launchpad_cli.cli:main"
    assert scripts["lp"] == "launchpad_cli.cli:main"


def test_expected_package_scaffold_exists() -> None:
    """The task should create the planned package skeleton for later phases."""

    expected_paths = [
        ROOT / "src/launchpad_cli/cli/__init__.py",
        ROOT / "src/launchpad_cli/core/config.py",
        ROOT / "src/launchpad_cli/core/ssh.py",
        ROOT / "src/launchpad_cli/core/transfer.py",
        ROOT / "src/launchpad_cli/core/compress.py",
        ROOT / "src/launchpad_cli/solvers/base.py",
        ROOT / "ARCHITECTURE.md",
    ]

    assert all(path.exists() for path in expected_paths)


def test_solver_placeholders_match_the_documented_defaults() -> None:
    """The reserved solver adapters should already expose their baseline identity."""

    assert NastranAdapter().name == "Nastran"
    assert NastranAdapter().input_extensions == (".dat",)
    assert AnsysAdapter().name == "ANSYS"
