"""Root Click application for Launchpad."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import get_close_matches

import click
import rich_click

from launchpad_cli import __version__

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

rich_click.USE_MARKDOWN = True
rich_click.SHOW_METAVARS_COLUMN = False
rich_click.APPEND_METAVARS_HELP = True


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


@click.group(
    cls=SuggestingGroup,
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
