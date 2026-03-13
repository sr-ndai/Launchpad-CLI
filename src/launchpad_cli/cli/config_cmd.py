"""`launchpad config` commands for local setup and inspection."""

from __future__ import annotations

import json
import os
from pathlib import Path

import click

from launchpad_cli.core.config import (
    DEFAULT_CLUSTER_CONFIG_PATH,
    default_user_config_path,
    dumps_toml,
    render_config_docs,
    resolve_config,
    write_toml_file,
)
from launchpad_cli.core.logging import configure_logging

from ._helpers import not_implemented


@click.group(
    name="config",
    short_help="Inspect and manage Launchpad configuration.",
    help="Inspect, initialize, edit, and validate Launchpad configuration layers.",
)
def command() -> None:
    """Manage Launchpad configuration."""


@command.command("show", short_help="Show the resolved configuration.")
@click.option(
    "--docs",
    is_flag=True,
    help="Show the documented config schema instead of resolved values.",
)
@click.pass_context
def show_command(ctx: click.Context, docs: bool) -> None:
    """Display the resolved configuration values."""

    configure_logging(
        verbosity=_verbosity(ctx),
        colorize=_colorize_output(ctx),
    )
    if docs:
        click.echo(render_config_docs())
        return

    resolved = resolve_config(cwd=Path.cwd(), env=os.environ)
    if _json_output(ctx):
        click.echo(json.dumps(resolved.as_dict(), indent=2))
        return

    click.echo(dumps_toml(resolved.as_dict()))


@command.command("edit", short_help="Open the user configuration file.")
def edit_command() -> None:
    """Open the user-level Launchpad configuration for editing."""

    raise not_implemented("launchpad config edit")


@command.command("init", short_help="Create an initial user configuration.")
@click.option("--host", help="Cluster SSH hostname or IP address.")
@click.option("--username", help="SSH username for the cluster.")
@click.option(
    "--key-path",
    type=click.Path(path_type=Path, dir_okay=False),
    help="Path to the SSH private key file.",
)
@click.option(
    "--port",
    type=click.IntRange(1, 65535),
    help="SSH port for the cluster head node.",
)
@click.option(
    "--known-hosts-path",
    type=click.Path(path_type=Path, dir_okay=False),
    help="Optional path to a known_hosts file.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite an existing user config file.",
)
@click.option(
    "--non-interactive",
    is_flag=True,
    help="Fail instead of prompting for any missing values.",
)
@click.pass_context
def init_command(
    ctx: click.Context,
    host: str | None,
    username: str | None,
    key_path: Path | None,
    port: int | None,
    known_hosts_path: Path | None,
    force: bool,
    non_interactive: bool,
) -> None:
    """Create a starter Launchpad configuration file."""

    configure_logging(
        verbosity=_verbosity(ctx),
        colorize=_colorize_output(ctx),
    )

    resolved = resolve_config(cwd=Path.cwd(), env=os.environ)
    defaults = resolved.config.ssh
    user_config_path = default_user_config_path()

    if user_config_path.exists() and not force:
        raise click.ClickException(
            f"User config already exists at {user_config_path}. Re-run with --force to overwrite it."
        )

    resolved_host = _resolve_init_value(
        provided=host,
        fallback=defaults.host,
        prompt_text="SSH host",
        non_interactive=non_interactive,
    )
    resolved_username = _resolve_init_value(
        provided=username,
        fallback=defaults.username,
        prompt_text="SSH username",
        non_interactive=non_interactive,
    )
    resolved_key_path = _resolve_init_path(
        provided=key_path,
        fallback=defaults.key_path,
        prompt_text="SSH key path",
        non_interactive=non_interactive,
    )
    resolved_port = _resolve_init_port(
        provided=port,
        fallback=defaults.port,
        non_interactive=non_interactive,
    )
    resolved_known_hosts = _resolve_optional_path(
        provided=known_hosts_path,
        fallback=defaults.known_hosts_path,
    )

    payload = {
        "ssh": {
            "host": resolved_host,
            "port": resolved_port,
            "username": resolved_username,
            "key_path": resolved_key_path,
        }
    }
    if resolved_known_hosts is not None:
        payload["ssh"]["known_hosts_path"] = resolved_known_hosts

    write_toml_file(user_config_path, payload)
    click.echo(f"Wrote user config to {user_config_path}")
    if DEFAULT_CLUSTER_CONFIG_PATH.exists():
        click.echo(f"Detected shared config at {DEFAULT_CLUSTER_CONFIG_PATH}")
    else:
        click.echo(
            f"Shared config not found at {DEFAULT_CLUSTER_CONFIG_PATH}; Launchpad will rely on user, project, environment, and CLI overrides.",
            err=True,
        )


@command.command("validate", short_help="Validate configuration inputs.")
def validate_command() -> None:
    """Validate configuration files and environment variables."""

    raise not_implemented("launchpad config validate")


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


def _resolve_init_value(
    *,
    provided: str | None,
    fallback: str | None,
    prompt_text: str,
    non_interactive: bool,
) -> str:
    if provided:
        return provided
    if fallback:
        return fallback
    if non_interactive:
        raise click.ClickException(
            f"Missing required value for {prompt_text.lower()}. Provide the flag explicitly in non-interactive mode."
        )
    return click.prompt(prompt_text, type=str)


def _resolve_init_path(
    *,
    provided: Path | None,
    fallback: str | None,
    prompt_text: str,
    non_interactive: bool,
) -> str:
    if provided is not None:
        return str(provided)
    if fallback:
        return fallback
    if non_interactive:
        raise click.ClickException(
            f"Missing required value for {prompt_text.lower()}. Provide the flag explicitly in non-interactive mode."
        )
    prompted_path = click.prompt(
        prompt_text,
        type=click.Path(path_type=Path, dir_okay=False),
    )
    return str(prompted_path)


def _resolve_optional_path(*, provided: Path | None, fallback: str | None) -> str | None:
    if provided is not None:
        return str(provided)
    return fallback


def _resolve_init_port(
    *,
    provided: int | None,
    fallback: int,
    non_interactive: bool,
) -> int:
    if provided is not None:
        return provided
    if non_interactive:
        return fallback
    return click.prompt("SSH port", default=fallback, type=int)
