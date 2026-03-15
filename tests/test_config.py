"""Tests for the Launchpad config and logging foundation."""

from __future__ import annotations

from pathlib import Path

import json
from click.testing import CliRunner
from loguru import logger
from rich.syntax import Syntax

from launchpad_cli.cli import cli
from launchpad_cli.cli import config_cmd as config_cmd_module
from launchpad_cli.core.config import LaunchpadConfig, SSHConfig, dumps_toml, render_config_docs, resolve_config
from launchpad_cli.core.logging import configure_logging
from launchpad_cli.core.workspace import resolve_remote_workspace_root


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
                "",
                "[solvers.nastran.logs]",
                'solver = "F06"',
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
                "",
                "[solvers.nastran.logs]",
                'telemetry = "F04"',
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
    assert resolved.config.solvers.nastran.logs.solver == ".f06"
    assert resolved.config.solvers.nastran.logs.telemetry == ".f04"
    assert resolved.loaded_files == (cluster_config, user_config, project_config)


def test_render_config_docs_includes_key_paths() -> None:
    """The schema renderer should expose the documented config surface."""

    docs = render_config_docs()

    assert "ssh.host" in docs
    assert "cluster.default_partition" in docs
    assert "cluster.workspace_root" in docs
    assert "remote_binaries.sbatch" in docs
    assert "solvers.nastran.logs.solver" in docs


def test_resolve_remote_workspace_root_prefers_configured_root() -> None:
    """Configured workspace roots should override the legacy username fallback."""

    root = resolve_remote_workspace_root(
        LaunchpadConfig(
            cluster={"workspace_root": "/shared/launchpad"},
            ssh=SSHConfig(username="sergey"),
        )
    )

    assert root == "/shared/launchpad"


def test_resolve_remote_workspace_root_falls_back_to_shared_root_username() -> None:
    """Unset workspace roots should preserve the legacy shared_root/username behavior."""

    root = resolve_remote_workspace_root(
        LaunchpadConfig(
            cluster={"shared_root": "/shared"},
            ssh=SSHConfig(username="sergey"),
        )
    )

    assert root == "/shared/sergey"


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
    assert "Config Ready" in result.output
    assert "launchpad doctor" in result.output


def test_config_init_interactive_flow_prompts_with_guided_copy(tmp_path: Path, monkeypatch) -> None:
    """Interactive setup should guide the operator through the required values."""

    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["config", "init"],
        input=f"headnode.example.com\nsergey\n{tmp_path / 'id_ed25519'}\n22\n",
    )

    assert result.exit_code == 0
    assert "Guided Setup" in result.output
    assert "Cluster SSH host or IP" in result.output
    assert "Cluster username" in result.output
    assert "Path to SSH private key" in result.output
    assert "Config Ready" in result.output


def test_config_init_existing_file_has_actionable_error(tmp_path: Path, monkeypatch) -> None:
    """Existing user config errors should point to the recovery path."""

    monkeypatch.setenv("HOME", str(tmp_path))
    config_dir = tmp_path / ".launchpad"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text("[ssh]\nhost = \"cluster\"\n", encoding="utf-8")

    result = CliRunner().invoke(cli, ["config", "init", "--non-interactive"])

    assert result.exit_code == 1
    assert "--force" in result.output
    assert "current settings" in result.output


def test_config_show_supports_docs_output() -> None:
    """The config show command should expose the schema docs output."""

    runner = CliRunner()

    result = runner.invoke(cli, ["config", "show", "--docs"])

    assert result.exit_code == 0
    assert "ssh.host" in result.output
    assert "submit.solver" in result.output


def test_config_show_renders_syntax_highlighted_toml(monkeypatch) -> None:
    """Human-readable config show should print a Rich TOML syntax renderable."""

    printed: dict[str, object] = {}
    expected = {"ssh": {"host": "cluster.example.com", "username": "sergey"}}

    class FakeConsole:
        def print(self, renderable) -> None:  # type: ignore[no-untyped-def]
            printed["renderable"] = renderable

    monkeypatch.setattr(config_cmd_module, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(
        config_cmd_module,
        "resolve_config",
        lambda **kwargs: type("Resolved", (), {"as_dict": lambda self: expected})(),
    )
    monkeypatch.setattr(config_cmd_module, "build_console", lambda **kwargs: FakeConsole())

    result = CliRunner().invoke(cli, ["config", "show"])

    assert result.exit_code == 0
    renderable = printed["renderable"]
    assert isinstance(renderable, Syntax)
    assert renderable.lexer.name.lower() == "toml"
    assert renderable.code == dumps_toml(expected)


def test_config_show_honors_existing_no_color_behavior(monkeypatch) -> None:
    """The highlighted config path should still rely on the existing no-color console flag."""

    captured: dict[str, object] = {}

    class FakeConsole:
        def print(self, renderable) -> None:  # type: ignore[no-untyped-def]
            captured["renderable"] = renderable

    monkeypatch.setattr(config_cmd_module, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(
        config_cmd_module,
        "resolve_config",
        lambda **kwargs: type("Resolved", (), {"as_dict": lambda self: {"ssh": {"host": "cluster"}}})(),
    )

    def fake_build_console(**kwargs):  # type: ignore[no-untyped-def]
        captured["no_color"] = kwargs["no_color"]
        return FakeConsole()

    monkeypatch.setattr(config_cmd_module, "build_console", fake_build_console)

    result = CliRunner().invoke(cli, ["--no-color", "config", "show"])

    assert result.exit_code == 0
    assert captured["no_color"] is True
    assert isinstance(captured["renderable"], Syntax)


def test_config_show_preserves_json_output(monkeypatch) -> None:
    """The root JSON branch for config show should remain plain JSON."""

    monkeypatch.setattr(config_cmd_module, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(
        config_cmd_module,
        "resolve_config",
        lambda **kwargs: type("Resolved", (), {"as_dict": lambda self: {"ssh": {"host": "cluster"}}})(),
    )

    result = CliRunner().invoke(cli, ["--json", "config", "show"])

    assert result.exit_code == 0
    assert json.loads(result.output) == {"ssh": {"host": "cluster"}}
