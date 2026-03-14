# Current State

> This is the **routing artifact**. Every agent reads this first on the active
> phase branch, then follows the branch and file pointers below.
> If this file disagrees with a canonical file, trust the canonical file and
> repair this snapshot before ending the session.

## Last Updated
2026-03-14

## Active Phase
Phase 8 — Task References and Solver-Aware Logs

## Active Task
8.1 — Job manifest and task references.

## Queue Snapshot
- pending: 8.2, 8.3
- ready: —
- in-progress: 8.1
- needs-review: —
- revision-needed: —
- blocked: —

## Repo State
- default branch: `main`
- coordination branch: `phase/08-task-references-and-solver-aware-logs`
- active task branch: `task/8.1-job-manifest-and-task-refs`
- last processed builder session: `none`

## What Changed Recently
- Refreshed local `main` after the Phase 7 merge landed and opened
  `phase/08-task-references-and-solver-aware-logs` from the human-approved
  baseline.
- Added the detailed Phase 8 plan plus Builder prompts for tasks `8.1` to
  `8.3`, centered on submitted task metadata, solver-aware log lookup, and the
  interactive logs picker.
- Assigned task `8.1` on `task/8.1-job-manifest-and-task-refs` so Builder work
  can begin from a stable manifest-first contract.

## Known Blockers
- None.

## Next Recommended Action
Builder should switch to `task/8.1-job-manifest-and-task-refs`, read the Phase
8 task prompt, and implement the submitted job-manifest and task-reference
groundwork.

## Next Agent Read Order
1. `.ai/state/current.md`
2. `.ai/tasks/queue.md`
3. `.ai/tasks/prompts/8.1.md`
4. `.ai/plans/08-task-references-and-solver-aware-logs.md`
5. `.ai/plan.md`
6. `.ai/git-rules.md`
