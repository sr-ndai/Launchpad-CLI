"""`launchpad doctor` diagnostics for local and remote prerequisites."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import shlex
import sys
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Mapping

import asyncssh
import click
from rich.table import Table
from rich.text import Text

from launchpad_cli.core.config import DEFAULT_CLUSTER_CONFIG_PATH, LaunchpadConfig, SSHConfig, resolve_config
from launchpad_cli.core.logging import configure_logging
from launchpad_cli.core.ssh import ssh_session
from launchpad_cli.display import (
    build_badge,
    build_console,
    build_detail_panel,
    build_launchpad_wordmark,
    build_next_steps_panel,
    build_summary_table,
)


@dataclass(slots=True)
class DiagnosticResult:
    """A single doctor check outcome."""

    name: str
    status: str
    detail: str
    suggestion: str | None = None

    def as_dict(self) -> dict[str, object]:
        """Serialize the result for JSON output."""

        return asdict(self)


@click.command(
    name="doctor",
    short_help="Run environment and connectivity diagnostics.",
    help="Check local config, SSH access, remote binaries, and writable cluster paths.",
)
@click.pass_context
def command(ctx: click.Context) -> None:
    """Run the configured Launchpad diagnostics."""

    configure_logging(
        verbosity=_verbosity(ctx),
        colorize=_colorize_output(ctx),
    )

    results = asyncio.run(_collect_diagnostics(cwd=Path.cwd(), env=os.environ))

    if _json_output(ctx):
        click.echo(json.dumps([result.as_dict() for result in results], indent=2))
    else:
        _render_results(results, no_color=not _colorize_output(ctx))

    if any(result.status == "fail" for result in results):
        raise click.exceptions.Exit(1)


async def _collect_diagnostics(
    *,
    cwd: Path,
    env: Mapping[str, str],
) -> list[DiagnosticResult]:
    """Collect local and remote diagnostic checks for the current configuration."""

    results = [_python_version_check()]

    try:
        resolved = resolve_config(cwd=cwd, env=env)
    except Exception as exc:
        results.append(
            DiagnosticResult(
                name="config",
                status="fail",
                detail=f"Launchpad could not resolve the active configuration: {exc}",
                suggestion="Run `launchpad config show --docs`, fix the invalid value, then retry `launchpad doctor`.",
            )
        )
        return results

    config_result = _config_resolution_check(resolved.loaded_files, resolved.config)
    results.append(config_result)
    key_result = _ssh_key_check(resolved.config.ssh)
    shared_config_result = _shared_config_check()
    results.extend([key_result, shared_config_result])

    if config_result.status == "fail" or key_result.status == "fail":
        results.append(
            DiagnosticResult(
                name="ssh-connection",
                status="skip",
                detail="Skipped remote checks because local SSH configuration is incomplete.",
            )
        )
        results.append(
            DiagnosticResult(
                name="remote-binaries",
                status="skip",
                detail="Skipped remote binary checks because local SSH configuration is incomplete.",
            )
        )
        results.append(
            DiagnosticResult(
                name="remote-root",
                status="skip",
                detail="Skipped remote writable-path checks because local SSH configuration is incomplete.",
            )
        )
        return results

    try:
        async with ssh_session(resolved.config.ssh) as conn:
            results.append(
                DiagnosticResult(
                    name="ssh-connection",
                    status="pass",
                    detail=f"Connected to {resolved.config.ssh.host}:{resolved.config.ssh.port} as {resolved.config.ssh.username}.",
                )
            )
            results.append(await _remote_binaries_check(conn, resolved.config))
            results.append(await _remote_root_check(conn, resolved.config))
    except (asyncssh.Error, OSError, ValueError) as exc:
        results.append(
            DiagnosticResult(
                name="ssh-connection",
                status="fail",
                detail=f"SSH connection failed: {exc}",
                suggestion="Verify `ssh.host`, `ssh.username`, and `ssh.key_path`, then retry.",
            )
        )
        results.append(
            DiagnosticResult(
                name="remote-binaries",
                status="skip",
                detail="Skipped remote binary checks because the SSH connection did not succeed.",
            )
        )
        results.append(
            DiagnosticResult(
                name="remote-root",
                status="skip",
                detail="Skipped remote writable-path checks because the SSH connection did not succeed.",
            )
        )

    return results


def _python_version_check() -> DiagnosticResult:
    """Report the active Python runtime version."""

    version = sys.version_info
    if version >= (3, 12):
        return DiagnosticResult(
            name="python",
            status="pass",
            detail=f"Python {version.major}.{version.minor}.{version.micro}",
        )

    return DiagnosticResult(
        name="python",
        status="fail",
        detail=f"Python {version.major}.{version.minor}.{version.micro}",
        suggestion="Install Python 3.12 or newer before using Launchpad.",
    )


def _config_resolution_check(loaded_files: tuple[Path, ...], config: LaunchpadConfig) -> DiagnosticResult:
    """Summarize the resolved configuration inputs relevant to operator commands."""

    source_text = ", ".join(str(path) for path in loaded_files) if loaded_files else "defaults only"
    missing_fields: list[str] = []
    if not config.ssh.host:
        missing_fields.append("ssh.host")
    if not config.ssh.username:
        missing_fields.append("ssh.username")

    host = config.ssh.host or "<missing>"
    username = config.ssh.username or "<missing>"

    if missing_fields:
        return DiagnosticResult(
            name="config",
            status="fail",
            detail=(
                f"Config resolved from {source_text}, but required SSH fields are missing: "
                f"{', '.join(missing_fields)}."
            ),
            suggestion=(
                "Set the missing SSH values with `launchpad config init`, a user/project config "
                "file, or `LAUNCHPAD_HOST` / `LAUNCHPAD_USER`."
            ),
        )

    return DiagnosticResult(
        name="config",
        status="pass",
        detail=f"Config resolved from {source_text}; ssh.host={host}, ssh.username={username}.",
    )


def _ssh_key_check(config: SSHConfig) -> DiagnosticResult:
    """Validate that the configured SSH key exists locally."""

    if not config.key_path:
        return DiagnosticResult(
            name="ssh-key",
            status="fail",
            detail="No SSH private key is configured.",
            suggestion="Run `launchpad config init` or set `LAUNCHPAD_KEY` to a valid private key path.",
        )

    key_path = Path(config.key_path).expanduser()
    if not key_path.is_file():
        return DiagnosticResult(
            name="ssh-key",
            status="fail",
            detail=f"SSH private key not found: {key_path}",
            suggestion="Update `ssh.key_path` to a readable private key file.",
        )

    return DiagnosticResult(
        name="ssh-key",
        status="pass",
        detail=f"SSH private key found: {key_path}",
    )


def _shared_config_check() -> DiagnosticResult:
    """Validate access to the shared cluster configuration file."""

    if DEFAULT_CLUSTER_CONFIG_PATH.is_file():
        return DiagnosticResult(
            name="shared-config",
            status="pass",
            detail=f"Shared config readable: {DEFAULT_CLUSTER_CONFIG_PATH}",
        )

    return DiagnosticResult(
        name="shared-config",
        status="fail",
        detail=f"Shared config not found: {DEFAULT_CLUSTER_CONFIG_PATH}",
        suggestion="Mount the shared `/shared` filesystem or rely on user/project/env config overrides.",
    )


async def _remote_binaries_check(conn: asyncssh.SSHClientConnection, config: LaunchpadConfig) -> DiagnosticResult:
    """Ensure the configured remote binaries resolve to executables."""

    resolved_paths: list[str] = []
    missing: list[str] = []

    for name, configured_value in config.remote_binaries.model_dump(mode="python").items():
        result = await _resolve_remote_executable(conn, str(configured_value))
        if result is None:
            missing.append(f"{name}={configured_value}")
        else:
            resolved_paths.append(f"{name}={result}")

    if missing:
        return DiagnosticResult(
            name="remote-binaries",
            status="fail",
            detail=(
                "Launchpad's remote exec environment could not resolve these executables: "
                f"{', '.join(missing)}"
            ),
            suggestion=(
                "Set `remote_binaries.*` to absolute paths or make the tools available on the "
                "PATH for non-interactive SSH exec sessions, then rerun `launchpad doctor`."
            ),
        )

    return DiagnosticResult(
        name="remote-binaries",
        status="pass",
        detail=f"Remote binaries resolved: {', '.join(resolved_paths)}",
    )


async def _remote_root_check(conn: asyncssh.SSHClientConnection, config: LaunchpadConfig) -> DiagnosticResult:
    """Verify that the user's shared remote root exists and is writable."""

    username = config.ssh.username
    if not username:
        return DiagnosticResult(
            name="remote-root",
            status="fail",
            detail="Cannot determine remote root without `ssh.username`.",
            suggestion="Set `ssh.username` in config or `LAUNCHPAD_USER` before retrying.",
        )

    remote_root = PurePosixPath(config.cluster.shared_root) / username
    quoted_root = shlex.quote(str(remote_root))
    result = await conn.run(f"test -d {quoted_root} && test -w {quoted_root}", check=False)

    if result.exit_status == 0:
        return DiagnosticResult(
            name="remote-root",
            status="pass",
            detail=f"Remote root is present and writable: {remote_root}",
        )

    return DiagnosticResult(
        name="remote-root",
        status="fail",
        detail=f"Remote root is missing or not writable: {remote_root}",
        suggestion="Create the directory or fix permissions on the shared cluster filesystem.",
    )


async def _resolve_remote_executable(
    conn: asyncssh.SSHClientConnection,
    executable: str,
) -> str | None:
    """Resolve a remote executable path using the active SSH session."""

    quoted_executable = shlex.quote(executable)
    result = await conn.run(
        (
            f"candidate={quoted_executable}; "
            'path=$(command -v "$candidate" 2>/dev/null || true); '
            'if [ -n "$path" ] && [ -x "$path" ]; then printf "%s" "$path"; '
            'elif [ -x "$candidate" ]; then printf "%s" "$candidate"; '
            "else exit 1; fi"
        ),
        check=False,
    )
    if result.exit_status != 0:
        return None
    return result.stdout.strip() or executable


def _render_results(results: list[DiagnosticResult], *, no_color: bool) -> None:
    """Render diagnostics in a human-readable form."""

    console = build_console(no_color=no_color)
    passed = sum(result.status == "pass" for result in results)
    failed = sum(result.status == "fail" for result in results)
    skipped = sum(result.status == "skip" for result in results)
    all_passed = failed == 0 and skipped == 0

    if all_passed:
        wordmark = build_launchpad_wordmark(width=_detect_terminal_width())
        if wordmark is not None and not no_color and _stdout_supports_branding():
            console.print(wordmark)
        console.print(Text("Doctor checks passed. Launchpad is ready for the next run.", style="lp.brand.secondary"))

    summary = build_summary_table()
    summary.add_row("Checks", str(len(results)))
    summary.add_row("Passed", str(passed))
    summary.add_row("Failed", str(failed))
    summary.add_row("Skipped", str(skipped))
    summary.add_row("Overall", "ready" if all_passed else "needs attention")
    console.print(
        build_detail_panel(
            summary,
            title="Doctor Summary",
            tone="success" if all_passed else ("danger" if failed else "warn"),
        )
    )

    local_results, remote_results = _partition_results(results)
    if local_results:
        console.print(_build_diagnostic_panel("Local Setup", local_results))
    if remote_results:
        console.print(_build_diagnostic_panel("Cluster Access", remote_results))

    console.print(build_next_steps_panel(_doctor_next_steps(results)))


def _build_diagnostic_panel(title: str, results: list[DiagnosticResult]):
    table = Table.grid(expand=True, padding=(0, 1))
    table.add_column(width=10)
    table.add_column()
    for result in results:
        body = Text(_diagnostic_title(result.name), style="lp.label")
        body.append(f"\n{result.detail}", style="lp.value")
        if result.suggestion:
            body.append("\nNext: ", style="lp.brand.subtle")
            body.append(result.suggestion, style="lp.brand.subtle")
        table.add_row(_diagnostic_badge(result.status), body)
    return build_detail_panel(table, title=title, tone=_panel_tone(results))


def _diagnostic_badge(status: str) -> Text:
    mapping = {
        "pass": ("pass", "success"),
        "fail": ("fail", "danger"),
        "skip": ("skip", "warn"),
    }
    label, tone = mapping.get(status, (status, "neutral"))
    return build_badge(label, tone=tone)


def _diagnostic_title(name: str) -> str:
    titles = {
        "python": "Python Runtime",
        "config": "Config Resolution",
        "ssh-key": "SSH Key",
        "shared-config": "Shared Config",
        "ssh-connection": "SSH Connection",
        "remote-binaries": "Remote Binaries",
        "remote-root": "Remote Writable Root",
    }
    return titles.get(name, name.replace("-", " ").title())


def _panel_tone(results: list[DiagnosticResult]) -> str:
    if any(result.status == "fail" for result in results):
        return "danger"
    if any(result.status == "skip" for result in results):
        return "warn"
    return "success"


def _partition_results(results: list[DiagnosticResult]) -> tuple[list[DiagnosticResult], list[DiagnosticResult]]:
    local_names = {"python", "config", "ssh-key", "shared-config"}
    local_results = [result for result in results if result.name in local_names]
    remote_results = [result for result in results if result.name not in local_names]
    return local_results, remote_results


def _doctor_next_steps(results: list[DiagnosticResult]) -> list[str]:
    statuses = {result.name: result.status for result in results}

    if all(result.status == "pass" for result in results):
        return [
            "launchpad submit --dry-run .",
            "launchpad submit .",
            "launchpad status <JOB_ID>",
        ]

    if statuses.get("config") == "fail" or statuses.get("ssh-key") == "fail":
        return [
            "launchpad config init",
            "launchpad config show",
            "launchpad doctor",
        ]

    if statuses.get("ssh-connection") == "fail":
        return [
            "launchpad config show",
            "Fix the SSH host, username, key, or network issue listed above.",
            "launchpad doctor",
        ]

    if statuses.get("remote-binaries") == "fail" or statuses.get("remote-root") == "fail":
        return [
            "Fix the cluster-side prerequisite listed above.",
            "launchpad doctor",
            "launchpad submit --dry-run .",
        ]

    if any(result.status == "skip" for result in results):
        return [
            "Resolve the blocking local setup issue above.",
            "launchpad config init",
            "launchpad doctor",
        ]

    return ["launchpad doctor"]


def _stdout_supports_branding() -> bool:
    return "NO_COLOR" not in os.environ and hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _detect_terminal_width() -> int | None:
    try:
        return shutil.get_terminal_size(fallback=(80, 24)).columns
    except OSError:
        return None


def _verbosity(ctx: click.Context) -> int:
    options = getattr(ctx.find_root(), "obj", None)
    return int(getattr(options, "verbose", 0))


def _json_output(ctx: click.Context) -> bool:
    options = getattr(ctx.find_root(), "obj", None)
    return bool(getattr(options, "json_output", False))


def _colorize_output(ctx: click.Context) -> bool:
    options = getattr(ctx.find_root(), "obj", None)
    no_color = bool(getattr(options, "no_color", False))
    return not no_color and "NO_COLOR" not in os.environ
