"""Tests for the Launchpad config and logging foundation."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner
from loguru import logger

from launchpad_cli.cli import cli
from launchpad_cli.core.config import render_config_docs, resolve_config
from launchpad_cli.core.logging import configure_logging


def test_resolve_config_honors_documented_precedence(tmp_path: Path) -> None:
    """CLI overrides should win over environment, project, user, and cluster config."""

    cluster_config = tmp_path / "cluster.toml"
    user_config = tmp_path / "user.toml"
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    project_config = project_dir / ".launchpad.toml"

    cluster_config.write_text(
        "\n".join(
            [
                "[ssh]",
                'host = "cluster-host"',
                "",
                "[cluster]",
                'default_partition = "cluster-partition"',
                "",
                "[transfer]",
                "parallel_streams = 8",
                "",
                "[solvers.nastran]",
                "default_cpus = 12",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    user_config.write_text(
        "\n".join(
            [
                "[ssh]",
                'username = "sergey"',
                'key_path = "C:\\\\Users\\\\sergey\\\\.ssh\\\\id_ed25519"',
                "",
                "[transfer]",
                "parallel_streams = 10",
                "",
                "[submit]",
                "cpus = 16",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    project_config.write_text(
        "\n".join(
            [
                "[submit]",
                'solver = "nastran"',
                "",
                "[cluster]",
                'default_partition = "project-partition"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    resolved = resolve_config(
        cwd=project_dir,
        env={
            "LAUNCHPAD_HOST": "env-host",
            "LAUNCHPAD_PARTITION": "env-partition",
            "LAUNCHPAD_STREAMS": "12",
            "LAUNCHPAD_SOLVERS__NASTRAN__DEFAULT_CPUS": "20",
        },
        cli_overrides={
            "transfer.parallel_streams": 4,
            "submit": {"solver": "ansys"},
        },
        cluster_config_path=cluster_config,
        user_config_path=user_config,
    )

    assert resolved.config.ssh.host == "env-host"
    assert resolved.config.ssh.username == "sergey"
    assert resolved.config.ssh.key_path == "C:\\Users\\sergey\\.ssh\\id_ed25519"
    assert resolved.config.cluster.default_partition == "env-partition"
    assert resolved.config.transfer.parallel_streams == 4
    assert resolved.config.submit.solver == "ansys"
    assert resolved.config.submit.cpus == 16
    assert resolved.config.solvers.nastran.default_cpus == 20
    assert resolved.loaded_files == (cluster_config, user_config, project_config)


def test_render_config_docs_includes_key_paths() -> None:
    """The schema renderer should expose the documented config surface."""

    docs = render_config_docs()

    assert "ssh.host" in docs
    assert "cluster.default_partition" in docs
    assert "remote_binaries.sbatch" in docs


def test_configure_logging_writes_debug_logs(tmp_path: Path) -> None:
    """Logging bootstrap should always create the file sink."""

    log_file = configure_logging(verbosity=1, log_dir=tmp_path, colorize=False)
    logger.debug("config logging smoke test")

    assert log_file.exists()
    assert "config logging smoke test" in log_file.read_text(encoding="utf-8")


def test_config_init_writes_user_config_non_interactively(tmp_path: Path, monkeypatch) -> None:
    """The init command should create a user config file for local setup."""

    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "config",
            "init",
            "--non-interactive",
            "--host",
            "headnode.example.com",
            "--username",
            "sergey",
            "--key-path",
            str(tmp_path / "id_ed25519"),
        ],
    )

    config_path = tmp_path / ".launchpad" / "config.toml"
    assert result.exit_code == 0
    assert config_path.exists()
    contents = config_path.read_text(encoding="utf-8")
    assert 'host = "headnode.example.com"' in contents
    assert 'username = "sergey"' in contents


def test_config_show_supports_docs_output() -> None:
    """The config show command should expose the schema docs output."""

    runner = CliRunner()

    result = runner.invoke(cli, ["config", "show", "--docs"])

    assert result.exit_code == 0
    assert "ssh.host" in result.output
    assert "submit.solver" in result.output
