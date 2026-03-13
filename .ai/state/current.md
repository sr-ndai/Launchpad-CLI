# Current State

> This is the **routing artifact**. Every agent reads this first on the active
> phase branch, then follows the branch and file pointers below.
> If this file disagrees with a canonical file, trust the canonical file and
> repair this snapshot before ending the session.

## Last Updated
2026-03-12

## Active Phase
Phase 3 — Monitoring & Logs

## Active Task
3.1 — SLURM status parsing and query primitives

## Queue Snapshot
- pending: 3.2, 3.3
- ready: —
- in-progress: 3.1
- needs-review: —
- revision-needed: —
- blocked: —

## Repo State
- default branch: `main`
- coordination branch: `phase/03-monitoring-logs`
- active task branch: `task/3.1-slurm-status-parsing`
- last processed builder session: `2026-03-12-2110-builder-2.3.md`

## What Changed Recently
- Phase 2 was merged to `main`, so the submission-pipeline work is now in the
  human-approved baseline.
- Created the new coordination branch `phase/03-monitoring-logs` from the
  updated `main` baseline.
- Seeded Phase 3 with tasks `3.1` through `3.3` and assigned task `3.1` to the
  Builder.

## Known Blockers
- None.

## Next Recommended Action
Builder: switch to `task/3.1-slurm-status-parsing`, execute
`.ai/tasks/prompts/3.1.md`, and record the handoff with `Outcome:
READY_FOR_REVIEW` or `BLOCKED`.

## Next Agent Read Order
1. `.ai/state/current.md`
2. `.ai/plans/03-monitoring-logs.md`
3. `.ai/tasks/prompts/3.1.md`
4. `.ai/plan.md`
