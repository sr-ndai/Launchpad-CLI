"""ANSYS solver placeholder reserved for future implementation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AnsysAdapter:
    """Stub ANSYS adapter that documents the deferred implementation."""

    name: str = "ANSYS"
    input_extensions: tuple[str, ...] = (".dat",)

    def ensure_supported(self) -> None:
        """Raise the planned stub error until ANSYS support is implemented."""

        raise NotImplementedError(
            "ANSYS support is intentionally deferred in Phase 1."
        )

