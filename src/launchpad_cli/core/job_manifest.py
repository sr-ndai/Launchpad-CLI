"""Submitted job-manifest contract and task-reference helpers."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Mapping, Sequence

from launchpad_cli.solvers import DiscoveredInput

MANIFEST_VERSION = 1


@dataclass(frozen=True, slots=True)
class TaskReference:
    """Stable per-task metadata persisted for a submitted array job."""

    task_id: str
    alias: str
    input_relative_path: str
    input_filename: str
    input_stem: str
    display_label: str
    result_dir: str

    @property
    def display_ref(self) -> str:
        """Return the combined human-facing task reference."""

        return f"{self.display_label} [{self.alias} / task {self.task_id}]"

    def as_dict(self) -> dict[str, str]:
        """Serialize the task reference for JSON output."""

        return {
            "task_id": self.task_id,
            "alias": self.alias,
            "input_relative_path": self.input_relative_path,
            "input_filename": self.input_filename,
            "input_stem": self.input_stem,
            "display_label": self.display_label,
            "result_dir": self.result_dir,
        }


@dataclass(frozen=True, slots=True)
class JobManifest:
    """Authoritative submitted metadata stored alongside a remote job."""

    version: int
    solver: str
    logs: dict[str, str]
    tasks: tuple[TaskReference, ...]

    def as_dict(self) -> dict[str, object]:
        """Serialize the manifest for remote persistence and later reads."""

        return {
            "version": self.version,
            "solver": self.solver,
            "logs": dict(self.logs),
            "tasks": [task.as_dict() for task in self.tasks],
        }


def build_task_references(inputs: Sequence[DiscoveredInput]) -> tuple[TaskReference, ...]:
    """Build stable per-task references from ordered solver discovery results."""

    if not inputs:
        return ()

    stem_counts = Counter(item.stem for item in inputs)
    alias_width = max(2, len(str(len(inputs))))
    references: list[TaskReference] = []

    for index, item in enumerate(inputs):
        task_id = str(index)
        input_relative_path = item.relative_path.as_posix()
        display_label = item.stem
        if stem_counts[item.stem] > 1:
            display_label = str(PurePosixPath(input_relative_path).with_suffix(""))

        references.append(
            TaskReference(
                task_id=task_id,
                alias=f"t{index + 1:0{alias_width}d}",
                input_relative_path=input_relative_path,
                input_filename=item.basename,
                input_stem=item.stem,
                display_label=display_label,
                result_dir=f"results_{item.stem}_{task_id}",
            )
        )

    return tuple(references)


def build_job_manifest(
    *,
    solver: str,
    logs: Mapping[str, str],
    tasks: Sequence[TaskReference],
) -> JobManifest:
    """Build the versioned manifest payload for a new submission."""

    return JobManifest(
        version=MANIFEST_VERSION,
        solver=solver,
        logs={key: value for key, value in logs.items()},
        tasks=tuple(tasks),
    )


def render_job_manifest(manifest: JobManifest) -> str:
    """Render the manifest as readable JSON for remote persistence."""

    return json.dumps(manifest.as_dict(), indent=2) + "\n"


def parse_job_manifest(raw: str) -> JobManifest:
    """Parse a persisted manifest into the typed task-reference model."""

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid launchpad-manifest.json payload: {exc.msg}.") from exc

    version = payload.get("version")
    if version != MANIFEST_VERSION:
        raise ValueError(
            f"Unsupported launchpad-manifest.json version: {version!r}. Expected {MANIFEST_VERSION}."
        )

    solver = payload.get("solver")
    if not isinstance(solver, str) or not solver.strip():
        raise ValueError("launchpad-manifest.json is missing a valid `solver` field.")

    logs_payload = payload.get("logs")
    if not isinstance(logs_payload, Mapping):
        raise ValueError("launchpad-manifest.json is missing a valid `logs` mapping.")
    logs = {
        str(key): str(value)
        for key, value in logs_payload.items()
        if isinstance(key, str) and isinstance(value, str)
    }

    tasks_payload = payload.get("tasks")
    if not isinstance(tasks_payload, list):
        raise ValueError("launchpad-manifest.json is missing a valid `tasks` list.")

    tasks: list[TaskReference] = []
    for item in tasks_payload:
        if not isinstance(item, Mapping):
            raise ValueError("launchpad-manifest.json contains an invalid task entry.")
        tasks.append(
            TaskReference(
                task_id=str(item.get("task_id", "")),
                alias=str(item.get("alias", "")),
                input_relative_path=str(item.get("input_relative_path", "")),
                input_filename=str(item.get("input_filename", "")),
                input_stem=str(item.get("input_stem", "")),
                display_label=str(item.get("display_label", "")),
                result_dir=str(item.get("result_dir", "")),
            )
        )

    if any(
        not all(
            (
                task.task_id,
                task.alias,
                task.input_relative_path,
                task.input_filename,
                task.input_stem,
                task.display_label,
                task.result_dir,
            )
        )
        for task in tasks
    ):
        raise ValueError("launchpad-manifest.json contains incomplete task metadata.")

    return JobManifest(
        version=MANIFEST_VERSION,
        solver=solver,
        logs=logs,
        tasks=tuple(tasks),
    )
