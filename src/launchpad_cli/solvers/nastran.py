"""Nastran solver adapter behavior used by the Phase 2 submit pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from launchpad_cli.core.config import LaunchpadConfig

from .base import (
    DiscoveredInput,
    SubmitOverrides,
    discover_inputs_by_extension,
    normalize_extension,
    quote_arg,
)


@dataclass(frozen=True, slots=True)
class NastranAdapter:
    """Concrete Nastran adapter for local discovery and command generation."""

    name: str = "Nastran"
    input_extensions: tuple[str, ...] = (".dat",)
    output_extensions: tuple[str, ...] = (".f06", ".op2", ".log")
    log_catalog: dict[str, str] = field(
        default_factory=lambda: {"solver": ".f06", "telemetry": ".f04"}
    )

    def discover_inputs(self, input_dir: Path) -> list[DiscoveredInput]:
        """Discover Nastran inputs using the configured extension rules."""

        return discover_inputs_by_extension(input_dir, extensions=self.input_extensions)

    def build_run_command(
        self,
        input_file: str,
        config: LaunchpadConfig,
        overrides: SubmitOverrides | None = None,
    ) -> str:
        """Build the remote Nastran invocation for a single input file.

        `input_file` is treated as a shell-ready path expression so later
        submit scripts can pass quoted variables directly.
        """

        solver_defaults = config.solvers.nastran
        resolved_overrides = overrides if overrides is not None else SubmitOverrides()
        cpus = resolved_overrides.cpus or config.submit.cpus or solver_defaults.default_cpus
        memory = resolved_overrides.memory or solver_defaults.memory

        arguments = [
            quote_arg(solver_defaults.executable_path),
            input_file,
            f"smp={cpus}",
            f"memory={quote_arg(memory)}",
            f"buffpool={quote_arg(solver_defaults.buffpool)}",
            f"buffsize={solver_defaults.buffsize}",
            f"smemory={quote_arg(solver_defaults.smemory)}",
            f"memorymaximum={quote_arg(solver_defaults.memorymaximum)}",
        ]
        return " ".join(arguments)

    def build_scratch_env(self, scratch_dir: str) -> dict[str, str]:
        """Return shared-filesystem scratch environment variables."""

        return {
            "NASTRAN_SCRATCH": scratch_dir,
            "TMPDIR": scratch_dir,
            "TMP": scratch_dir,
            "TEMP": scratch_dir,
        }

    @classmethod
    def from_config(cls, config: LaunchpadConfig) -> NastranAdapter:
        """Build an adapter instance using the configured discovery extension."""

        extension = normalize_extension(config.solvers.nastran.input_extension)
        return cls(
            input_extensions=(extension,),
            log_catalog=config.solvers.nastran.logs.model_dump(mode="python", exclude_none=True),
        )
