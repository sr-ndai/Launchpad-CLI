# Phase 04 Plan: Download & Cleanup

## Objective

Complete the post-submit lifecycle so engineers can retrieve results safely,
inspect remote output directories, and clean up cluster-side job data from the
local CLI.

## Milestone

The repository can download completed job results with safety checks and
verification, list remote files for operator inspection, and clean up remote
job directories without leaving the local terminal.

## Task Breakdown

| Task ID | Title | Depends On | Notes |
|---------|-------|------------|-------|
| 4.1 | Download primitives and filesystem groundwork | — | Extend the core local/remote/compression helpers with the disk, archive, and remote filesystem operations required by Phase 4 commands. |
| 4.2 | Download command orchestration | 4.1 | Replace the placeholder `launchpad download` command with the full retrieval flow, including remote compression policy, local space checks, decompression, and verification. |
| 4.3 | Remote listing and cleanup commands | 4.2 | Replace the placeholder `launchpad ls` and `launchpad cleanup` commands with the documented operator workflows on top of the established Phase 4 primitives. |

## Sequencing Notes

- Keep `4.1` focused on reusable primitives so command tasks can remain thin
  and testable.
- `4.2` owns the end-to-end result retrieval experience, including confirmation
  behavior and integrity validation.
- `4.3` should reuse the same remote filesystem model introduced in `4.1`
  rather than inventing parallel command-specific path logic.

## Exit Criteria

- The queue reflects all planned Phase 4 tasks with correct dependencies.
- Task `4.1` is assigned on its own task branch with a prompt the Builder can
  execute without additional planning.
- `current.md` routes the next agent directly to the active Phase 4 artifacts.
