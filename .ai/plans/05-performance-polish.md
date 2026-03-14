# Phase 05 Plan: Performance & Polish

## Objective

Document the deferred transfer-validation plan, harden the current single-
stream SFTP design, and finish the remaining CLI polish needed for a
production-ready Nastran rollout.

## Milestone

The repository has a documented transfer-validation plan and provisional
single-stream direction, the current transfer path is hardened for
interruptions and operator errors, and the remaining JSON/UX/logging polish is
complete across the CLI.

## Task Breakdown

| Task ID | Title | Depends On | Notes |
|---------|-------|------------|-------|
| 5.1 | Transfer benchmark plan and provisional direction | — | Record the benchmark matrix, prerequisite checklist, deferred validation path, and provisional recommendation to keep single-stream until real-cluster access exists. |
| 5.2 | Single-stream hardening and resume improvements | 5.1 | Tighten the current transfer path, recovery behavior, and operator-facing errors without introducing unvalidated parallel-transfer behavior. |
| 5.3 | CLI polish and logging audit | 5.2 | Finish the remaining `--json`, typo-suggestion, edge-case, and logging work after the transfer behavior is stable. |

## Sequencing Notes

- `5.1` now captures the deferred validation plan and provisional direction so
  later work can proceed without pretending local-only measurements replace the
  missing real-cluster benchmark.
- `5.2` owns the transfer/runtime changes and should preserve the roadmap's
  bias toward correctness and resume safety over raw throughput while the real-
  cluster benchmark remains deferred.
- `5.3` should follow the transfer work so any JSON, edge-case, and logging
  polish can describe and test the settled transfer behavior rather than a
  moving target.

## Exit Criteria

- The queue reflects all planned Phase 5 tasks with correct dependencies.
- Task `5.1` is assigned on its own task branch with a prompt the Builder can
  execute without additional planning.
- `current.md` routes the next agent directly to the active Phase 5 artifacts.
