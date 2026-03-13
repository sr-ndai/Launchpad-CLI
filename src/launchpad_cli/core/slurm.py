"""SLURM request builders and parser placeholders."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class JobStatus:
    """Structured view of a job returned from SLURM."""

    job_id: str
    state: str


def build_submit_script() -> str:
    """Build a SLURM submit script for a solver invocation."""

    raise NotImplementedError("SLURM script generation is not implemented yet.")


def parse_squeue_output(raw: str) -> list[JobStatus]:
    """Parse `squeue` output into structured job state."""

    raise NotImplementedError("SLURM status parsing is not implemented yet.")

