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
