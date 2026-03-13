"""Protocol-compliant ANSYS adapter stub reserved for later work."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from launchpad_cli.core.config import LaunchpadConfig

from .base import DiscoveredInput, SubmitOverrides, normalize_extension


@dataclass(frozen=True, slots=True)
class AnsysAdapter:
    """Document the deferred ANSYS workflow while keeping the contract stable."""

    name: str = "ANSYS"
    input_extensions: tuple[str, ...] = (".dat",)
    output_extensions: tuple[str, ...] = (".out", ".err")

    def discover_inputs(self, input_dir: Path) -> list[DiscoveredInput]:
        """Fail clearly until an ANSYS workflow is defined by the team."""

        self.ensure_supported()
        raise AssertionError("Unreachable after ensure_supported().")

    def build_run_command(
        self,
        input_file: str,
        config: LaunchpadConfig,
        overrides: SubmitOverrides | None = None,
    ) -> str:
        """Fail clearly until an ANSYS runtime contract exists."""

        self.ensure_supported()
        raise AssertionError("Unreachable after ensure_supported().")

    def build_scratch_env(self, scratch_dir: str) -> dict[str, str]:
        """Fail clearly until ANSYS scratch requirements are defined."""

        self.ensure_supported()
        raise AssertionError("Unreachable after ensure_supported().")

    def ensure_supported(self) -> None:
        """Raise the planned stub error until ANSYS support is implemented."""

        raise NotImplementedError(
            "ANSYS submit support is intentionally deferred until the team defines "
            "the input format, executable invocation, and scratch requirements."
        )

    @classmethod
    def from_config(cls, config: LaunchpadConfig) -> AnsysAdapter:
        """Build an adapter instance using the configured discovery extension."""

        extension = normalize_extension(config.solvers.ansys.input_extension)
        return cls(input_extensions=(extension,))
