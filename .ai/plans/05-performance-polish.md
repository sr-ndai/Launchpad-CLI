# Phase 05 Plan: Performance & Polish

## Objective

Choose and implement the Phase 5 hybrid transfer architecture so Launchpad
supports both fast single-payload transfer and concurrent many-file transfer,
then finish the remaining CLI polish needed for a production-ready Nastran
rollout.

## Milestone

The repository has a documented transfer-architecture decision, functional
`single-file` and `multi-file` transfer modes with shared stream controls, and
the remaining JSON/UX/logging polish complete across the CLI.

## Task Breakdown

| Task ID | Title | Depends On | Notes |
|---------|-------|------------|-------|
| 5.1 | Transfer architecture and precedent review | — | Turn the blocked benchmark note into the implementation-ready architecture decision for `single-file`, `multi-file`, and `auto` transfer modes using external precedent plus current repo constraints. |
| 5.2 | Hybrid transfer engine and CLI surfaces | 5.1 | Implement striped single-file transfer, worker-pool multi-file transfer, and the new submit/download transfer-mode controls with safe fallback behavior. |
| 5.3 | UX, logging, and fallback polish | 5.2 | Finish the remaining JSON, typo-suggestion, edge-case, logging, and operator-feedback work after the new transfer modes land. |

## Sequencing Notes

- `5.1` must choose the architecture up front so task `5.2` can implement the
  system without open design questions.
- `5.2` owns the transport/runtime changes and should preserve the roadmap's
  bias toward correctness and resume safety while still delivering real
  concurrency for both single-file and many-file workflows.
- `5.3` should follow the transfer work so JSON output, operator guidance,
  logging, and fallback behavior all describe the settled transfer model rather
  than a moving target.

## Exit Criteria

- The queue reflects all planned Phase 5 tasks with correct dependencies.
- Task `5.1` is assigned on its own task branch with a prompt the Builder can
  execute without additional planning.
- `current.md` routes the next agent directly to the active Phase 5 artifacts.
