"""Application logging entry points reserved for later Phase 1 work."""

from __future__ import annotations

from loguru import logger


def configure_logging(*, verbose: int = 0) -> None:
    """Configure the shared application logger."""

    logger.remove()
    logger.add(
        sink=lambda message: None,
        level="DEBUG" if verbose else "INFO",
    )

