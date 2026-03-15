"""`launchpad config` commands for local setup and inspection."""

from __future__ import annotations

import json
import os
from pathlib import Path

import click
from rich.text import Text

from launchpad_cli.core.config import (
    DEFAULT_CLUSTER_CONFIG_PATH,
    ConfigLayer,
    ResolvedConfig,
    default_user_config_path,
    render_config_docs,
    resolve_config,
    write_toml_file,
)
from launchpad_cli.core.logging import configure_logging
from launchpad_cli.display import (
    build_console,
    build_inline_kv,
    build_next_steps,
    build_section_rule,
    build_status_line,
    build_success_line,
)

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

    console = build_console(no_color=not _colorize_output(ctx))
    _render_config_show(console, resolved=resolved, no_color=not _colorize_output(ctx))


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
    console = build_console(no_color=not _colorize_output(ctx))

    if user_config_path.exists() and not force:
        raise click.ClickException(
            "Launchpad user config already exists at "
            f"{user_config_path}. Re-run `launchpad config init --force` to "
            "overwrite it, or use `launchpad config show` to inspect the "
            "current settings."
        )

    if not non_interactive:
        _render_init_intro(
            console,
            user_config_path=user_config_path,
        )

    resolved_host = _resolve_init_value(
        provided=host,
        fallback=defaults.host,
        prompt_text="Cluster SSH host or IP",
        option_hint="--host",
        non_interactive=non_interactive,
    )
    resolved_username = _resolve_init_value(
        provided=username,
        fallback=defaults.username,
        prompt_text="Cluster username",
        option_hint="--username",
        non_interactive=non_interactive,
    )
    resolved_key_path = _resolve_init_path(
        provided=key_path,
        fallback=defaults.key_path,
        prompt_text="Path to SSH private key",
        option_hint="--key-path",
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
    _render_init_success(
        console,
        user_config_path=user_config_path,
        payload=payload,
        shared_config_available=DEFAULT_CLUSTER_CONFIG_PATH.exists(),
        no_color=not _colorize_output(ctx),
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
    option_hint: str,
    non_interactive: bool,
) -> str:
    if provided:
        return provided
    if non_interactive and fallback:
        return fallback
    if non_interactive:
        raise click.ClickException(
            f"Non-interactive setup still needs {prompt_text.lower()}. "
            f"Re-run with `{option_hint}` or drop `--non-interactive` to "
            "answer the prompt."
        )
    return click.prompt(prompt_text, type=str, default=fallback, show_default=bool(fallback))


def _resolve_init_path(
    *,
    provided: Path | None,
    fallback: str | None,
    prompt_text: str,
    option_hint: str,
    non_interactive: bool,
) -> str:
    if provided is not None:
        return str(provided)
    if non_interactive and fallback:
        return fallback
    if non_interactive:
        raise click.ClickException(
            f"Non-interactive setup still needs {prompt_text.lower()}. "
            f"Re-run with `{option_hint}` or drop `--non-interactive` to "
            "answer the prompt."
        )
    prompted_path = click.prompt(
        prompt_text,
        type=click.Path(path_type=Path, dir_okay=False),
        default=fallback,
        show_default=bool(fallback),
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
    return click.prompt("SSH port", default=fallback, type=click.IntRange(1, 65535))


def _render_init_intro(
    console,
    *,
    user_config_path: Path,
) -> None:
    console.print(build_section_rule("Guided Setup"))
    console.print(Text("Set up Launchpad for your cluster.", style="lp.value"))
    console.print(build_inline_kv("config_file", user_config_path, indent=2, label_width=18))
    console.print(
        build_inline_kv("required_prompts", "host, username, key_path, port", indent=2, label_width=18)
    )
    console.print(
        build_inline_kv(
            "optional",
            "known_hosts_path stays inherited unless you pass a flag",
            indent=2,
            label_width=18,
        )
    )


def _render_init_success(
    console,
    *,
    user_config_path: Path,
    payload: dict[str, object],
    shared_config_available: bool,
    no_color: bool,
) -> None:
    ssh_payload = payload["ssh"]
    assert isinstance(ssh_payload, dict)
    console.print(build_section_rule("Config Ready"))
    console.print(build_success_line(f"Saved user config at {user_config_path}", no_color=no_color))
    console.print(Text("  SSH", style="lp.label" if not no_color else None))
    console.print(build_inline_kv("host", ssh_payload["host"], indent=4, label_width=18))
    console.print(build_inline_kv("port", ssh_payload["port"], indent=4, label_width=18))
    console.print(build_inline_kv("username", ssh_payload["username"], indent=4, label_width=18))
    console.print(build_inline_kv("key_path", ssh_payload["key_path"], indent=4, label_width=18))
    console.print(
        build_inline_kv(
            "known_hosts_path",
            ssh_payload.get("known_hosts_path") or "system default / inherited",
            indent=4,
            label_width=18,
        )
    )
    console.print()
    console.print(Text("  Shared Config", style="lp.label" if not no_color else None))
    console.print(
        build_status_line(
            "success" if shared_config_available else "muted",
            "shared config",
            (
                f"detected at {DEFAULT_CLUSTER_CONFIG_PATH}"
                if shared_config_available
                else "not detected; user, project, env, and CLI overrides still work"
            ),
            indent=4,
            no_color=no_color,
        )
    )
    console.print()
    console.print(
        build_next_steps(
            [
                "launchpad config show",
                "launchpad doctor",
                "launchpad submit --dry-run .",
            ],
            no_color=no_color,
        )
    )


def _render_config_show(console, *, resolved: ResolvedConfig, no_color: bool) -> None:
    console.print(build_section_rule("Resolved Configuration"))
    console.print(Text("  Sources (highest to lowest priority)", style="lp.label" if not no_color else None))
    for index, layer in enumerate(reversed(resolved.layers), start=1):
        console.print(
            build_inline_kv(
                f"{index}. {_layer_heading(layer)}",
                _layer_detail(layer),
                indent=4,
                label_width=30,
            )
        )

    for section_name, section_value in resolved.as_dict().items():
        if not isinstance(section_value, dict) or not section_value:
            continue
        console.print()
        _render_mapping_section(
            console,
            title=_display_section_name(section_name),
            mapping=section_value,
            no_color=no_color,
            indent=2,
        )


def _render_mapping_section(
    console,
    *,
    title: str,
    mapping: dict[str, object],
    no_color: bool,
    indent: int,
) -> None:
    console.print(Text(" " * indent + title, style="lp.label" if not no_color else None))
    for key, value in mapping.items():
        if isinstance(value, dict):
            console.print(
                Text(" " * (indent + 2) + _display_section_name(key), style="lp.label" if not no_color else None)
            )
            _render_nested_mapping(console, mapping=value, no_color=no_color, indent=indent + 4)
            continue
        console.print(build_inline_kv(key, _render_value(value), indent=indent + 2, label_width=18))


def _render_nested_mapping(
    console,
    *,
    mapping: dict[str, object],
    no_color: bool,
    indent: int,
) -> None:
    for key, value in mapping.items():
        if isinstance(value, dict):
            console.print(Text(" " * indent + _display_section_name(key), style="lp.label" if not no_color else None))
            _render_nested_mapping(console, mapping=value, no_color=no_color, indent=indent + 2)
            continue
        console.print(build_inline_kv(key, _render_value(value), indent=indent, label_width=18))


def _display_section_name(name: str) -> str:
    aliases = {
        "ssh": "SSH",
        "remote_binaries": "Remote Binaries",
    }
    if name in aliases:
        return aliases[name]
    return name.replace("_", " ").title()


def _render_value(value: object) -> str:
    if isinstance(value, bool):
        return "enabled" if value else "disabled"
    return str(value)


def _layer_heading(layer: ConfigLayer) -> str:
    headings = {
        "cli": "CLI flags",
        "environment": "Environment variables",
        "project": "Project config",
        "user": "User config",
        "cluster": "Shared config",
    }
    return headings.get(layer.name, layer.name.replace("_", " "))


def _layer_detail(layer: ConfigLayer) -> str:
    if layer.name in {"cluster", "user", "project"}:
        if layer.loaded and layer.path is not None:
            return str(layer.path)
        return "not found"

    if not layer.loaded:
        return "none"

    flattened = ", ".join(_flatten_keys(layer.data))
    return flattened or "overrides applied"


def _flatten_keys(data: dict[str, object], prefix: str = "") -> list[str]:
    keys: list[str] = []
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            keys.extend(_flatten_keys(value, prefix=path))
        else:
            keys.append(path)
    return keys
