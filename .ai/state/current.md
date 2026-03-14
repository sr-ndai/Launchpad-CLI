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
- in-progress: —
- needs-review: —
- revision-needed: 8.1
- blocked: —

## Repo State
- default branch: `main`
- coordination branch: `phase/08-task-references-and-solver-aware-logs`
- active task branch: `task/8.1-job-manifest-and-task-refs`
- last processed builder session: `2026-03-14-1353-builder-8.1.md`

## What Changed Recently
- Refreshed local `main` after the Phase 7 merge landed and opened
  `phase/08-task-references-and-solver-aware-logs` from the human-approved
  baseline.
- Added the detailed Phase 8 plan plus Builder prompts for tasks `8.1` to
  `8.3`, centered on submitted task metadata, solver-aware log lookup, and the
  interactive logs picker.
- Reviewed Builder handoff `2026-03-14-1353-builder-8.1.md`, reran the prompt
  verification, and requested a targeted revision because the new alias
  contract was implemented as `tNN` instead of the approved plain zero-padded
  numeric format.

## Known Blockers
- None.

## Next Recommended Action
Builder should stay on `task/8.1-job-manifest-and-task-refs`, read
`.ai/reviews/8.1.md`, and update the alias contract to the approved plain
zero-padded numeric format before resubmitting task `8.1`.

## Next Agent Read Order
1. `.ai/state/current.md`
2. `.ai/tasks/queue.md`
3. `.ai/tasks/prompts/8.1.md`
4. `.ai/reviews/8.1.md`
5. `.ai/sessions/2026-03-14-1353-builder-8.1.md`
6. `.ai/plans/08-task-references-and-solver-aware-logs.md`
7. `.ai/git-rules.md`
