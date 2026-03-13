# Task Queue

> This file is a **summary dashboard** of task status. The Coordinator is the
> primary owner and updates it on the active phase branch.

## Status Key

| Status | Meaning |
|--------|---------|
| `pending` | Not yet actionable (dependencies unmet or not prioritized) |
| `ready` | All dependencies met, available for assignment |
| `in-progress` | Builder is actively working |
| `needs-review` | Builder signaled `READY_FOR_REVIEW`; Coordinator review is pending |
| `revision-needed` | Coordinator found issues, Builder must address |
| `done` | Accepted and merged into phase branch |
| `blocked` | Cannot proceed due to external dependency |

## Edit Permissions

- **Coordinator:** May edit any field, any row, on the active phase branch.
- **Builder:** Does **not** edit this file. The Builder signals
  `READY_FOR_REVIEW` or `BLOCKED` through a Builder session note on the active
  task branch, and the Coordinator records the queue transition.

## Queue

| Task ID | Phase | Title | Status | Depends On | Branch | Assigned |
|---------|-------|-------|--------|------------|--------|----------|
| 1.1 | 1 | Project scaffolding and baseline CLI | done | — | task/1.1-project-scaffolding | — |
| 1.2 | 1 | Config and logging foundation | done | 1.1 | task/1.2-config-and-logging | — |
| 1.3 | 1 | SSH, transfer, and compression primitives | done | 1.1 | task/1.3-ssh-transfer-compression | — |
| 1.4 | 1 | Operator commands and diagnostics | done | 1.2, 1.3 | task/1.4-operator-commands-diagnostics | — |
| 2.1 | 2 | Solver adapters and input discovery | done | — | task/2.1-solver-adapters-discovery | — |
| 2.2 | 2 | SLURM and remote submission primitives | done | 2.1 | task/2.2-slurm-and-remote-submission | — |
| 2.3 | 2 | Submit orchestration and dry-run UX | done | 2.1, 2.2 | task/2.3-submit-orchestration-dry-run | — |
