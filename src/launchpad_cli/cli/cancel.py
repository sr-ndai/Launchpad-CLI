"""`launchpad cancel` command for remote SLURM cancellation."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
from dataclasses import dataclass
from pathlib import Path

import asyncssh
import click
from loguru import logger

from launchpad_cli.core.config import resolve_config
from launchpad_cli.core.logging import configure_logging
from launchpad_cli.core.ssh import ssh_session


@dataclass(frozen=True, slots=True)
class CancelResult:
    """Structured cancellation response."""

    job_id: str
    task_ids: tuple[str, ...]
    target: str

    @property
    def message(self) -> str:
        """Return the human-readable cancellation summary."""

        return _success_text(self.job_id, self.task_ids)

    def as_dict(self) -> dict[str, object]:
        """Serialize the cancellation response for `--json` output."""

        return {
            "job_id": self.job_id,
            "task_ids": list(self.task_ids),
            "target": self.target,
            "message": self.message,
        }


@click.command(
    name="cancel",
    short_help="Cancel a running or queued job.",
    help="Cancel an entire SLURM job or selected array tasks.",
)
@click.argument("job_id")
@click.argument("task_ids", nargs=-1)
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
@click.pass_context
def command(
    ctx: click.Context,
    job_id: str,
    task_ids: tuple[str, ...],
    yes: bool,
) -> None:
    """Cancel the requested SLURM job or selected array tasks."""

    json_output = _json_output(ctx)
    configure_logging(
        verbosity=_verbosity(ctx),
        colorize=_colorize_output(ctx),
    )

    normalized_task_ids = _normalize_task_ids(task_ids)
    if not yes and not click.confirm(
        _confirmation_text(job_id, normalized_task_ids),
        default=True,
        err=json_output,
    ):
        raise click.ClickException("Cancellation aborted.")

    try:
        result = asyncio.run(
            _run_cancel(
                cwd=Path.cwd(),
                env=os.environ,
                job_id=job_id,
                task_ids=normalized_task_ids,
            )
        )
    except (asyncssh.Error, RuntimeError, OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    if json_output:
        click.echo(json.dumps(result.as_dict(), indent=2))
    else:
        click.echo(result.message)


async def _run_cancel(
    *,
    cwd: Path,
    env: dict[str, str],
    job_id: str,
    task_ids: tuple[str, ...],
) -> CancelResult:
    """Resolve config, invoke remote `scancel`, and summarize the action."""

    resolved = resolve_config(cwd=cwd, env=env)

    async with ssh_session(resolved.config.ssh) as conn:
        target = _cancel_target(job_id, task_ids)
        logger.trace("Cancelling SLURM target {}", target)
        command = _build_scancel_command(target)
        result = await conn.run(command, check=False)
        if result.exit_status != 0:
            raise RuntimeError(
                f"SLURM cancellation failed for {target}: "
                f"{result.stderr.strip() or result.stdout.strip() or 'unknown error'}"
            )

    return CancelResult(job_id=job_id, task_ids=task_ids, target=target)


def _normalize_task_ids(task_ids: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for task_id in task_ids:
        cleaned = task_id.strip()
        if not cleaned or not cleaned.isdigit():
            raise click.ClickException(f"Task IDs must be numeric. Received `{task_id}`.")
        normalized.append(cleaned)
    return tuple(normalized)


def _cancel_target(job_id: str, task_ids: tuple[str, ...]) -> str:
    if not task_ids:
        return job_id
    return ",".join(f"{job_id}_{task_id}" for task_id in task_ids)


def _build_scancel_command(target: str) -> str:
    return " ".join([shlex.quote("scancel"), shlex.quote(target)])


def _confirmation_text(job_id: str, task_ids: tuple[str, ...]) -> str:
    if not task_ids:
        return f"Cancel SLURM job {job_id}?"
    return f"Cancel SLURM job {job_id} task(s) {', '.join(task_ids)}?"


def _success_text(job_id: str, task_ids: tuple[str, ...]) -> str:
    if not task_ids:
        return f"Cancelled job {job_id}."
    return f"Cancelled job {job_id} task(s): {', '.join(task_ids)}."


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
