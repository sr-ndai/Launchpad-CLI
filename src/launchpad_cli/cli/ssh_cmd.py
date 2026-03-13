"""`launchpad ssh` command for interactive cluster access."""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path

import asyncssh
import click

from launchpad_cli.core.config import resolve_config
from launchpad_cli.core.logging import configure_logging
from launchpad_cli.core.ssh import ssh_session


@click.command(
    name="ssh",
    short_help="Open an interactive SSH session to the cluster.",
    help="Open an interactive shell on the configured cluster head node.",
)
@click.pass_context
def command(ctx: click.Context) -> None:
    """Start an interactive SSH session using the resolved Launchpad config."""

    configure_logging(
        verbosity=_verbosity(ctx),
        colorize=_colorize_output(ctx),
    )
    resolved = resolve_config(cwd=Path.cwd(), env=os.environ)

    try:
        exit_code = asyncio.run(_open_interactive_shell(resolved.config.ssh))
    except (asyncssh.Error, OSError, ValueError) as exc:
        raise click.ClickException(f"SSH session failed: {exc}") from exc

    if exit_code:
        raise click.exceptions.Exit(exit_code)


async def _open_interactive_shell(config) -> int:
    """Open the remote login shell and pass the local terminal through to it."""

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise click.ClickException("`launchpad ssh` requires an interactive terminal.")

    term_size = shutil.get_terminal_size(fallback=(80, 24))
    term_type = os.environ.get("TERM", "xterm-256color")

    async with ssh_session(config) as conn:
        async with conn.create_process(
            request_pty=True,
            term_type=term_type,
            term_size=(term_size.columns, term_size.lines),
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
        ) as process:
            await process.wait_closed()
            return int(process.exit_status or 0)


def _verbosity(ctx: click.Context) -> int:
    options = getattr(ctx.find_root(), "obj", None)
    return int(getattr(options, "verbose", 0))


def _colorize_output(ctx: click.Context) -> bool:
    options = getattr(ctx.find_root(), "obj", None)
    no_color = bool(getattr(options, "no_color", False))
    return not no_color and "NO_COLOR" not in os.environ
