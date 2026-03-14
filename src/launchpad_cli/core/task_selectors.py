"""Shared manifest loading and task-selector resolution helpers."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Collection, Sequence

import asyncssh

from launchpad_cli.core.job_manifest import JobManifest, TaskReference, parse_job_manifest
from launchpad_cli.core.remote_ops import read_remote_text

MANIFEST_FILENAME = "launchpad-manifest.json"


async def load_job_manifest(
    conn: asyncssh.SSHClientConnection,
    remote_job_dir: str | None,
) -> JobManifest | None:
    """Load a submitted manifest when the remote job directory provides one."""

    if not remote_job_dir:
        return None

    manifest_path = str(PurePosixPath(remote_job_dir) / MANIFEST_FILENAME)
    try:
        raw = await read_remote_text(conn, manifest_path)
    except FileNotFoundError:
        return None
    return parse_job_manifest(raw)


def resolve_manifest_task_reference(
    manifest: JobManifest,
    selector: str,
    *,
    job_id: str,
) -> TaskReference:
    """Resolve a single selector against the manifest task catalog."""

    cleaned = selector.strip()
    if not cleaned:
        raise ValueError("Task selectors must not be empty.")

    direct_match = _match_unique(manifest.tasks, lambda item: item.task_id == cleaned)
    if direct_match is not None:
        return direct_match

    alias_match = _match_unique(manifest.tasks, lambda item: item.alias == cleaned)
    if alias_match is not None:
        return alias_match

    normalized_path = _normalize_relative_path(cleaned)
    path_match = _match_unique(
        manifest.tasks,
        lambda item: _normalize_relative_path(item.input_relative_path) == normalized_path,
    )
    if path_match is not None:
        return path_match

    filename_matches = tuple(item for item in manifest.tasks if item.input_filename == cleaned)
    if len(filename_matches) == 1:
        return filename_matches[0]
    if len(filename_matches) > 1:
        raise ValueError(_ambiguous_selector_message(job_id, cleaned, filename_matches))

    stem_matches = tuple(item for item in manifest.tasks if item.input_stem == cleaned)
    if len(stem_matches) == 1:
        return stem_matches[0]
    if len(stem_matches) > 1:
        raise ValueError(_ambiguous_selector_message(job_id, cleaned, stem_matches))

    raise ValueError(
        f"Task selector `{cleaned}` was not found for job {job_id}. "
        "Use a raw task ID, alias, input stem, exact filename, or relative path."
    )


def resolve_manifest_task_references(
    manifest: JobManifest,
    selectors: Sequence[str],
    *,
    job_id: str,
) -> tuple[TaskReference, ...]:
    """Resolve multiple selectors, deduplicating repeated task matches."""

    resolved: list[TaskReference] = []
    seen_task_ids: set[str] = set()

    for selector in selectors:
        task_ref = resolve_manifest_task_reference(manifest, selector, job_id=job_id)
        if task_ref.task_id in seen_task_ids:
            continue
        resolved.append(task_ref)
        seen_task_ids.add(task_ref.task_id)

    return tuple(resolved)


def resolve_task_ids(
    selectors: Sequence[str],
    *,
    manifest: JobManifest | None,
    available_task_ids: Collection[str],
    job_id: str,
) -> tuple[str, ...]:
    """Resolve command selectors to raw SLURM task IDs."""

    if not selectors:
        return ()

    cleaned = tuple(dict.fromkeys(_clean_selector(selector) for selector in selectors))

    if manifest is None:
        invalid = tuple(selector for selector in cleaned if not selector.isdigit())
        if invalid:
            raise ValueError(
                f"Job {job_id} has no {MANIFEST_FILENAME}. "
                "Only raw numeric task IDs are supported for this command."
            )
        resolved = tuple(str(item) for item in sorted(int(selector) for selector in cleaned))
    else:
        resolved = tuple(
            item.task_id
            for item in resolve_manifest_task_references(manifest, cleaned, job_id=job_id)
        )

    if available_task_ids:
        available = set(available_task_ids)
        missing = [task_id for task_id in resolved if task_id not in available]
        if missing:
            raise ValueError(
                f"Task selection did not match job rows for {job_id}: {', '.join(missing)}"
            )

    return resolved


def _clean_selector(selector: str) -> str:
    cleaned = selector.strip()
    if not cleaned:
        raise ValueError("Task selectors must not be empty.")
    return cleaned


def _match_unique(
    tasks: Sequence[TaskReference],
    predicate,
) -> TaskReference | None:
    matches = tuple(task for task in tasks if predicate(task))
    if len(matches) == 1:
        return matches[0]
    return None


def _normalize_relative_path(value: str) -> str:
    return PurePosixPath(value.replace("\\", "/")).as_posix()


def _ambiguous_selector_message(
    job_id: str,
    selector: str,
    matches: Sequence[TaskReference],
) -> str:
    refs = ", ".join(item.display_ref for item in matches)
    return (
        f"Task selector `{selector}` is ambiguous for job {job_id}. "
        f"Matches: {refs}. Use a raw task ID, alias, or relative path."
    )
