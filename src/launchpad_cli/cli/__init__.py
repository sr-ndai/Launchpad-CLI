"""Root Click application for Launchpad."""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from difflib import get_close_matches

import click
import rich_click
import rich_click.rich_click as rich_config
from rich_click.patch import patch as patch_rich_click
from rich.text import Text

from launchpad_cli import __version__
from launchpad_cli.display import PALETTE, build_launchpad_wordmark

patch_rich_click()

from .cancel import command as cancel_command
from .cleanup import command as cleanup_command
from .config_cmd import command as config_command
from .doctor import command as doctor_command
from .download import command as download_command
from .logs import command as logs_command
from .ls import command as ls_command
from .ssh_cmd import command as ssh_command
from .status import command as status_command
from .submit import command as submit_command

rich_config.TEXT_MARKUP = "markdown"
rich_config.COMMANDS_BEFORE_OPTIONS = True
rich_config.OPTIONS_TABLE_COLUMN_TYPES = ["opt_short", "opt_long", "help"]
rich_config.OPTIONS_TABLE_HELP_SECTIONS = ["help", "metavar", "deprecated", "envvar", "default", "required"]
rich_config.STYLE_OPTION = f"bold {PALETTE['ice']}"
rich_config.STYLE_SWITCH = f"bold {PALETTE['cyan']}"
rich_config.STYLE_METAVAR = PALETTE["amber"]
rich_config.STYLE_USAGE = f"bold {PALETTE['mist']}"
rich_config.STYLE_USAGE_COMMAND = f"bold {PALETTE['ice']}"
rich_config.STYLE_HEADER_TEXT = f"bold {PALETTE['ice']}"
rich_config.STYLE_FOOTER_TEXT = f"dim {PALETTE['mist']}"
rich_config.STYLE_HELPTEXT_FIRST_LINE = f"bold {PALETTE['ice']}"
rich_config.STYLE_HELPTEXT = PALETTE["ice"]
rich_config.STYLE_OPTION_HELP = PALETTE["ice"]
rich_config.STYLE_COMMAND_HELP = PALETTE["ice"]
rich_config.STYLE_OPTIONS_PANEL_BORDER = PALETTE["cyan"]
rich_config.STYLE_COMMANDS_PANEL_BORDER = PALETTE["cyan"]
rich_config.STYLE_ERRORS_PANEL_BORDER = PALETTE["red"]
rich_config.STYLE_DEPRECATED = PALETTE["amber"]
rich_config.STYLE_ABORTED = f"bold {PALETTE['red']}"
rich_config.OPTIONS_PANEL_TITLE = "Flags"
rich_config.COMMANDS_PANEL_TITLE = "Commands"
rich_config.ERRORS_SUGGESTION = "Try `[bold]launchpad -h[/]` for help."
rich_config.FOOTER_TEXT = None
rich_config.HEADER_TEXT = None


@dataclass(slots=True)
class GlobalOptions:
    """Baseline global CLI options shared across commands."""

    verbose: int
    quiet: bool
    json_output: bool
    no_color: bool


class SuggestingGroup(click.Group):
    """Click group which suggests nearby subcommands for typos."""

    def resolve_command(
        self,
        ctx: click.Context,
        args: list[str],
    ) -> tuple[str | None, click.Command | None, list[str]]:
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError as exc:
            if args:
                suggestion = _closest_command(args[0], self.list_commands(ctx))
                if suggestion is not None:
                    raise click.UsageError(
                        f"No such command '{args[0]}'. Did you mean '{suggestion}'?",
                        ctx=ctx,
                    ) from exc
            raise


class LaunchpadGroup(SuggestingGroup):
    """Root group with per-invocation rich-help configuration."""

    def main(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        argv = kwargs.get("args")
        if argv is None and args:
            argv = args[0]
        normalized_argv = list(argv or sys.argv[1:])
        with _configured_help_runtime(normalized_argv):
            return super().main(*args, **kwargs)


@click.group(
    cls=LaunchpadGroup,
    context_settings={"help_option_names": ["-h", "--help"]},
    invoke_without_command=True,
)
@click.option("-v", "--verbose", count=True, help="Increase output verbosity.")
@click.option(
    "-q",
    "--quiet",
    is_flag=True,
    help="Suppress non-essential output.",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Emit JSON where the selected command supports it.",
)
@click.option(
    "--no-color",
    is_flag=True,
    help="Disable Rich color output.",
)
@click.version_option(version=__version__, prog_name="launchpad")
@click.pass_context
def cli(
    ctx: click.Context,
    verbose: int,
    quiet: bool,
    json_output: bool,
    no_color: bool,
) -> None:
    """Launchpad coordinates solver submissions, monitoring, and result retrieval."""

    ctx.obj = GlobalOptions(
        verbose=verbose,
        quiet=quiet,
        json_output=json_output,
        no_color=no_color,
    )
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


cli.add_command(submit_command)
cli.add_command(status_command)
cli.add_command(logs_command)
cli.add_command(download_command)
cli.add_command(cancel_command)
cli.add_command(ls_command)
cli.add_command(config_command)
cli.add_command(ssh_command)
cli.add_command(cleanup_command)
cli.add_command(doctor_command)


def main() -> None:
    """Run the Launchpad CLI."""

    cli()


def _closest_command(candidate: str, commands: list[str]) -> str | None:
    matches = get_close_matches(candidate, commands, n=1, cutoff=0.6)
    if not matches:
        return None
    return matches[0]


@contextmanager
def _configured_help_runtime(argv: list[str]):
    saved = {
        "HEADER_TEXT": rich_config.HEADER_TEXT,
        "FOOTER_TEXT": rich_config.FOOTER_TEXT,
        "COLOR_SYSTEM": rich_config.COLOR_SYSTEM,
    }
    rich_config.COLOR_SYSTEM = None if _no_color_requested(argv) else "auto"
    if _is_root_help_request(argv):
        rich_config.HEADER_TEXT = None
        rich_config.FOOTER_TEXT = _root_help_footer(show_wordmark=_show_wordmark(argv))
    else:
        rich_config.HEADER_TEXT = None
        rich_config.FOOTER_TEXT = None
    try:
        yield
    finally:
        for key, value in saved.items():
            setattr(rich_config, key, value)


def _apply_help_groups() -> None:
    """Register grouped command and option sections for rich-click help."""

    command_groups = [
        {
            "name": "Primary Workflows",
            "commands": ["submit", "status", "download"],
        },
        {
            "name": "Operator Tools",
            "commands": ["logs", "cancel", "ls", "cleanup", "ssh", "doctor"],
        },
        {
            "name": "Setup",
            "commands": ["config"],
        },
    ]
    config_groups = [
        {
            "name": "Inspect",
            "commands": ["show", "validate"],
        },
        {
            "name": "Edit",
            "commands": ["init", "edit"],
        },
    ]
    for path in ("launchpad", "cli"):
        rich_config.COMMAND_GROUPS[path] = command_groups
    for path in ("launchpad config", "cli config"):
        rich_config.COMMAND_GROUPS[path] = config_groups

    root_option_groups = [
        {
            "name": "Display",
            "options": ["verbose", "quiet", "json_output", "no_color"],
        },
        {
            "name": "Help",
            "options": ["version", "help"],
        },
    ]
    submit_option_groups = [
        {
            "name": "Solver & Packaging",
            "options": ["solver", "name", "compression_level", "no_compress", "extra_files", "include_all"],
        },
        {
            "name": "Scheduling",
            "options": ["cpus", "max_concurrent", "partition", "time_limit", "begin"],
        },
        {
            "name": "Transfer",
            "options": ["transfer_mode", "streams"],
        },
        {
            "name": "Preview",
            "options": ["dry_run", "help"],
        },
    ]
    status_option_groups = [
        {
            "name": "Filters",
            "options": ["include_all"],
        },
        {
            "name": "Live View",
            "options": ["watch", "interval", "help"],
        },
    ]
    logs_option_groups = [
        {
            "name": "Read Mode",
            "options": ["follow", "lines"],
        },
        {
            "name": "Source",
            "options": ["solver_log", "err", "help"],
        },
    ]
    download_option_groups = [
        {
            "name": "Destination & Scope",
            "options": ["output", "tasks", "exclude_patterns", "include_scratch"],
        },
        {
            "name": "Transfer",
            "options": ["transfer_mode", "remote_compress", "streams", "compression_level", "force"],
        },
        {
            "name": "Cleanup",
            "options": ["cleanup", "help"],
        },
    ]
    cancel_option_groups = [
        {
            "name": "Confirmation",
            "options": ["yes", "help"],
        },
    ]
    ls_option_groups = [
        {
            "name": "Display",
            "options": ["long_format", "help"],
        },
    ]
    cleanup_option_groups = [
        {
            "name": "Selection",
            "options": ["older_than"],
        },
        {
            "name": "Confirmation",
            "options": ["yes", "help"],
        },
    ]
    option_group_aliases = {
        "launchpad": root_option_groups,
        "cli": root_option_groups,
        "launchpad submit": submit_option_groups,
        "cli submit": submit_option_groups,
        "launchpad status": status_option_groups,
        "cli status": status_option_groups,
        "launchpad logs": logs_option_groups,
        "cli logs": logs_option_groups,
        "launchpad download": download_option_groups,
        "cli download": download_option_groups,
        "launchpad cancel": cancel_option_groups,
        "cli cancel": cancel_option_groups,
        "launchpad ls": ls_option_groups,
        "cli ls": ls_option_groups,
        "launchpad cleanup": cleanup_option_groups,
        "cli cleanup": cleanup_option_groups,
    }
    rich_config.OPTION_GROUPS.update(option_group_aliases)


def _apply_help_examples() -> None:
    """Attach a shared examples block to implemented commands."""

    examples = {
        cli: [
            "launchpad config init",
            "launchpad doctor",
            "launchpad submit --dry-run .",
        ],
        submit_command: [
            "launchpad submit --dry-run .",
            "launchpad submit --name wing-v2 --cpus 16",
        ],
        status_command: [
            "launchpad status",
            "launchpad status 12345 --watch --interval 10",
        ],
        logs_command: [
            "launchpad logs 12345 0 --follow",
            "launchpad logs 12345 2 --solver-log --lines 100",
        ],
        download_command: [
            "launchpad download 12345 .\\results",
            "launchpad download 12345 --tasks 0,2 --transfer-mode multi-file",
        ],
        cancel_command: [
            "launchpad cancel 12345",
            "launchpad cancel 12345 2 4 --yes",
        ],
        ls_command: [
            "launchpad ls",
            "launchpad ls tank_v3/*.txt --long",
        ],
        cleanup_command: [
            "launchpad cleanup 12345 --yes",
            "launchpad cleanup --older-than 30d",
        ],
        config_command: [
            "launchpad config show",
            "launchpad config init --host cluster.example.com --username sergey",
        ],
        doctor_command: [
            "launchpad doctor",
            "launchpad --json doctor",
        ],
        ssh_command: [
            "launchpad ssh",
        ],
    }
    for command, lines in examples.items():
        command.epilog = _examples_epilog(lines)


def _examples_epilog(lines: list[str]) -> str:
    body = "\n".join(f"  {line}" for line in lines)
    return f"Examples:\n{body}"


def _root_help_footer(*, show_wordmark: bool) -> Text:
    footer = Text()
    if show_wordmark:
        footer.append(build_launchpad_wordmark().plain)
        footer.append("\n\n")
    footer.append("Start here: ", style=f"bold {PALETTE['ice']}")
    footer.append("launchpad config init", style=f"bold {PALETTE['cyan']}")
    footer.append(" -> ", style=f"dim {PALETTE['mist']}")
    footer.append("launchpad doctor", style=f"bold {PALETTE['cyan']}")
    footer.append(" -> ", style=f"dim {PALETTE['mist']}")
    footer.append("launchpad submit --dry-run .", style=f"bold {PALETTE['cyan']}")
    return footer


def _is_root_help_request(argv: list[str]) -> bool:
    if not argv:
        return True
    if "--help" not in argv and "-h" not in argv:
        return False
    return _first_command_token(argv) is None


def _first_command_token(argv: list[str]) -> str | None:
    for token in argv:
        if token.startswith("-"):
            continue
        if token in cli.commands:
            return token
    return None


def _show_wordmark(argv: list[str]) -> bool:
    if _no_color_requested(argv):
        return False
    if "--json" in argv or "--quiet" in argv or "-q" in argv:
        return False
    return _stdout_supports_branding()


def _no_color_requested(argv: list[str]) -> bool:
    if "--no-color" in argv or "NO_COLOR" in os.environ:
        return True
    return not _stdout_supports_branding()


def _stdout_supports_branding() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


_apply_help_groups()
_apply_help_examples()
