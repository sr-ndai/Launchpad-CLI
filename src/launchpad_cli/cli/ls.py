"""`launchpad ls` command for remote directory inspection."""

from __future__ import annotations

import asyncio
import fnmatch
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Mapping

import asyncssh
import click
from rich.panel import Panel
from rich.table import Table

from launchpad_cli.core.config import resolve_config
from launchpad_cli.core.logging import configure_logging
from launchpad_cli.core.remote_ops import RemotePathEntry, list_remote_directory
from launchpad_cli.core.ssh import ssh_session
from launchpad_cli.display import build_console

GLOB_CHARS = "*?[]"


@dataclass(frozen=True, slots=True)
class ListingResult:
    """Structured remote listing response for display-oriented rendering."""

    requested_path: str
    base_path: str
    long_format: bool
    pattern: str | None
    entries: tuple[RemotePathEntry, ...]


@click.command(
    name="ls",
    short_help="List remote files and directories.",
    help="Browse files on the cluster without leaving the Launchpad CLI.",
)
@click.argument("remote_path", required=False)
@click.option(
    "--long",
    "long_format",
    "-l",
    is_flag=True,
    help="Show type, size, and modification time for each entry.",
)
@click.pass_context
def command(
    ctx: click.Context,
    remote_path: str | None,
    long_format: bool,
) -> None:
    """List remote files beneath the configured user root or a selected path."""

    configure_logging(
        verbosity=_verbosity(ctx),
        colorize=_colorize_output(ctx),
    )

    console = build_console(no_color=not _colorize_output(ctx))

    try:
        result = asyncio.run(
            _run_ls(
                cwd=Path.cwd(),
                env=os.environ,
                remote_path=remote_path,
                long_format=long_format,
            )
        )
    except (asyncssh.Error, RuntimeError, OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    console.print(_build_listing_renderable(result))


async def _run_ls(
    *,
    cwd: Path,
    env: Mapping[str, str],
    remote_path: str | None,
    long_format: bool,
) -> ListingResult:
    """Resolve config, fetch the remote listing, and apply any glob filter."""

    resolved = resolve_config(cwd=cwd, env=env)
    remote_root = _default_remote_root(resolved.config)
    requested_path = _normalize_remote_path(remote_path, remote_root=remote_root)
    pattern = requested_path if _contains_glob(requested_path) else None
    base_path = _glob_base_path(requested_path) if pattern is not None else requested_path

    async with ssh_session(resolved.config.ssh) as conn:
        entries = await list_remote_directory(
            conn,
            base_path,
            recursive=pattern is not None,
        )

    if pattern is not None:
        entries = tuple(entry for entry in entries if fnmatch.fnmatch(entry.path, pattern))

    return ListingResult(
        requested_path=requested_path,
        base_path=base_path,
        long_format=long_format,
        pattern=pattern,
        entries=entries,
    )


def _default_remote_root(config) -> str:  # type: ignore[no-untyped-def]
    username = config.ssh.username
    if not username:
        raise click.ClickException("Cannot resolve a default remote path without `ssh.username`.")
    return str(PurePosixPath(config.cluster.shared_root) / username)


def _normalize_remote_path(remote_path: str | None, *, remote_root: str) -> str:
    if not remote_path:
        return remote_root

    candidate = PurePosixPath(remote_path)
    if candidate.is_absolute():
        return str(candidate)
    return str(PurePosixPath(remote_root) / candidate)


def _contains_glob(path: str) -> bool:
    return any(char in path for char in GLOB_CHARS)


def _glob_base_path(pattern: str) -> str:
    path = PurePosixPath(pattern)
    base_parts: list[str] = []
    for part in path.parts:
        if any(char in part for char in GLOB_CHARS):
            break
        base_parts.append(part)

    if not base_parts:
        return "."
    return str(PurePosixPath(*base_parts))


def _build_listing_renderable(result: ListingResult):
    """Render either a short or long listing view."""

    if not result.entries:
        return Panel(f"No remote entries matched `{result.requested_path}`.", title="Remote Listing", expand=False)

    if result.long_format:
        return _build_long_listing(result)
    return _build_short_listing(result)


def _build_short_listing(result: ListingResult) -> Table:
    table = Table(title=f"Remote Listing: {result.requested_path}", show_header=False)
    table.add_column("Entry")

    for entry in result.entries:
        path_text = _display_path(entry, result=result)
        suffix = "/" if entry.is_dir else ""
        table.add_row(f"{path_text}{suffix}")

    return table


def _build_long_listing(result: ListingResult) -> Table:
    table = Table(title=f"Remote Listing: {result.requested_path}", show_header=True, header_style="bold")
    table.add_column("Type")
    table.add_column("Size", justify="right")
    table.add_column("Modified")
    table.add_column("Path")

    for entry in result.entries:
        table.add_row(
            entry.entry_type,
            _format_bytes(entry.size_bytes),
            _format_timestamp(entry.modified_epoch),
            _display_path(entry, result=result),
        )

    return table


def _display_path(entry: RemotePathEntry, *, result: ListingResult) -> str:
    if result.pattern is None:
        return entry.name

    try:
        return PurePosixPath(entry.path).relative_to(PurePosixPath(result.base_path)).as_posix()
    except ValueError:
        return entry.path


def _format_timestamp(value: float | None) -> str:
    if value is None:
        return "—"
    return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M")


def _format_bytes(size_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    value = float(size_bytes)
    unit = units[0]
    for unit in units:
        if abs(value) < 1024 or unit == units[-1]:
            break
        value /= 1024
    if unit == "B":
        return f"{int(value)} {unit}"
    return f"{value:.1f} {unit}"


def _verbosity(ctx: click.Context) -> int:
    options = getattr(ctx.find_root(), "obj", None)
    return int(getattr(options, "verbose", 0))


def _colorize_output(ctx: click.Context) -> bool:
    options = getattr(ctx.find_root(), "obj", None)
    no_color = bool(getattr(options, "no_color", False))
    return not no_color and "NO_COLOR" not in os.environ
