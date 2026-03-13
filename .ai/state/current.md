# Current State

> This is the **routing artifact**. Every agent reads this first on the active
> phase branch, then follows the branch and file pointers below.
> If this file disagrees with a canonical file, trust the canonical file and
> repair this snapshot before ending the session.

## Last Updated
2026-03-12

## Active Phase
Phase 2 — Submission Pipeline

## Active Task
2.2 — SLURM and remote submission primitives

## Queue Snapshot
- pending: 2.3
- ready: —
- in-progress: 2.2
- needs-review: —
- revision-needed: —
- blocked: —

## Repo State
- default branch: `main`
- coordination branch: `phase/02-submission-pipeline`
- active task branch: `task/2.2-slurm-and-remote-submission`
- last processed builder session: `2026-03-12-1947-builder-2.1.md`

## What Changed Recently
- Recorded Builder handoff `2026-03-12-1947-builder-2.1.md` and reviewed task
  `2.1`.
- Accepted task `2.1` and merged `task/2.1-solver-adapters-discovery` into
  `phase/02-submission-pipeline`.
- Advanced the queue so task `2.2` is now the active Builder task.

## Known Blockers
- None.

## Next Recommended Action
Builder: switch to `task/2.2-slurm-and-remote-submission`, execute
`.ai/tasks/prompts/2.2.md`, and record the handoff with `Outcome:
READY_FOR_REVIEW` or `BLOCKED`.

## Next Agent Read Order
1. `.ai/state/current.md`
2. `.ai/plans/02-submission-pipeline.md`
3. `.ai/tasks/prompts/2.2.md`
4. `.ai/plan.md`
