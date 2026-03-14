# Phase 05 Plan: Performance & Polish

## Objective

Validate whether Launchpad should move beyond the current single-stream SFTP
transfer design, then finish the remaining CLI polish needed for a production-
ready Nastran rollout.

## Milestone

The repository has a documented transfer decision backed by benchmark evidence,
the chosen transfer path is hardened for interruptions and operator errors, and
the remaining JSON/UX/logging polish is complete across the CLI.

## Task Breakdown

| Task ID | Title | Depends On | Notes |
|---------|-------|------------|-------|
| 5.1 | Transfer benchmark and strategy decision | — | Benchmark at least three transfer candidates against the real cluster workflow, capture the evidence in-repo, and choose the direction for implementation. |
| 5.2 | Transfer implementation and resume hardening | 5.1 | Implement the chosen transfer direction, or explicitly keep single-stream if the benchmark says to, while tightening interrupted-transfer recovery and operator-facing error behavior. |
| 5.3 | CLI polish and logging audit | 5.2 | Finish the remaining `--json`, typo-suggestion, edge-case, and logging work after the transfer behavior is stable. |

## Sequencing Notes

- `5.1` must land first so the repo has measured evidence before any transfer
  optimization work begins.
- `5.2` owns the transfer/runtime changes and should preserve the roadmap's
  bias toward correctness and resume safety over raw throughput.
- `5.3` should follow the transfer work so any JSON, edge-case, and logging
  polish can describe and test the settled transfer behavior rather than a
  moving target.

## Exit Criteria

- The queue reflects all planned Phase 5 tasks with correct dependencies.
- Task `5.1` is assigned on its own task branch with a prompt the Builder can
  execute without additional planning.
- `current.md` routes the next agent directly to the active Phase 5 artifacts.
