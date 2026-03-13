"""`launchpad doctor` diagnostics for local and remote prerequisites."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import sys
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Mapping

import asyncssh
import click

from launchpad_cli.core.config import DEFAULT_CLUSTER_CONFIG_PATH, LaunchpadConfig, SSHConfig, resolve_config
from launchpad_cli.core.logging import configure_logging
from launchpad_cli.core.ssh import ssh_session
from launchpad_cli.display import build_console


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
                detail=f"Failed to resolve config: {exc}",
                suggestion="Run `launchpad config show --docs` and fix invalid values before retrying.",
            )
        )
        return results

    results.append(_config_resolution_check(resolved.loaded_files, resolved.config))
    key_result = _ssh_key_check(resolved.config.ssh)
    shared_config_result = _shared_config_check()
    results.extend([key_result, shared_config_result])

    if key_result.status == "fail":
        results.append(
            DiagnosticResult(
                name="ssh-connection",
                status="skip",
                detail="Skipped remote checks because local SSH key configuration is incomplete.",
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
    host = config.ssh.host or "<missing>"
    username = config.ssh.username or "<missing>"
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
            detail=f"Missing remote executables: {', '.join(missing)}",
            suggestion="Install the missing tools on the cluster head node or update `remote_binaries.*` paths.",
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
    result = await conn.run(
        f"sh -lc 'test -d {quoted_root} && test -w {quoted_root}'",
        check=False,
    )

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
        "sh -lc "
        + shlex.quote(
            f"path=$(command -v {quoted_executable} 2>/dev/null || true); "
            'if [ -n "$path" ] && [ -x "$path" ]; then printf "%s" "$path"; else exit 1; fi'
        ),
        check=False,
    )
    if result.exit_status != 0:
        return None
    return result.stdout.strip() or executable


def _render_results(results: list[DiagnosticResult], *, no_color: bool) -> None:
    """Render diagnostics in a human-readable form."""

    console = build_console(no_color=no_color)
    styles = {"pass": "green", "fail": "red", "skip": "yellow"}
    labels = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP"}

    for result in results:
        style = styles.get(result.status, "white")
        label = labels.get(result.status, result.status.upper())
        console.print(f"[{style}]{label}[/{style}] {result.detail}")
        if result.suggestion:
            console.print(f"  fix: {result.suggestion}")


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
