"""Loguru bootstrap helpers for Launchpad commands."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from .config import default_log_dir


def configure_logging(
    *,
    verbosity: int = 0,
    log_dir: Path | None = None,
    colorize: bool | None = None,
) -> Path:
    """Configure console and file logging for the current command invocation."""

    logger.remove()
    console_level = {0: "WARNING", 1: "DEBUG"}.get(verbosity, "TRACE")
    console_colorize = sys.stderr.isatty() if colorize is None else colorize
    logger.add(
        sys.stderr,
        level=console_level,
        format="<level>{message}</level>",
        colorize=console_colorize,
    )

    resolved_log_dir = (log_dir if log_dir is not None else default_log_dir()).expanduser()
    resolved_log_dir.mkdir(parents=True, exist_ok=True)
    log_file = resolved_log_dir / "launchpad.log"
    logger.add(
        log_file,
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <7} | {name}:{function} | {message}",
        rotation="10 MB",
        retention=5,
    )
    logger.debug("Logging configured with verbosity={} at {}", verbosity, log_file)
    return log_file
