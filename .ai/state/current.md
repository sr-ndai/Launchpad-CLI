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
8.4 — Cluster access diagnostics and Windows SSH

## Queue Snapshot
- pending: —
- ready: —
- in-progress: 8.4
- needs-review: —
- revision-needed: —
- blocked: —

## Repo State
- default branch: `main`
- coordination branch: `phase/08-task-references-and-solver-aware-logs`
- active task branch: `task/8.4-cluster-access-diagnostics`
- last processed builder session: `2026-03-14-1435-builder-8.3.md`

## What Changed Recently
- Reopened Phase 8 with follow-up task `8.4` after field debugging showed that
  `doctor` probes the wrong remote shell environment for binary checks and that
  `launchpad ssh` crashes on Windows during AsyncSSH stdio redirection.
- Assigned task `8.4` on branch `task/8.4-cluster-access-diagnostics` to fix
  the doctor probe alignment, the Windows SSH path, and the related docs/tests
  before PR `#9` is merged.
- Accepted task `8.3` after the interactive picker, retry-by-name follow mode,
  and final docs/help updates passed review and prompt verification.
- Merged `task/8.3-interactive-log-picker` into
  `phase/08-task-references-and-solver-aware-logs`, bringing the TTY-only
  picker, final logs UX, and docs updates onto the shared phase branch.
- Opened PR `#9` from `phase/08-task-references-and-solver-aware-logs` to
  `main` after Phase 8 closed locally.

## Known Blockers
- None.

## Next Recommended Action
Builder should switch to `task/8.4-cluster-access-diagnostics`, read the task
prompt, and implement the doctor probe alignment plus the Windows
`launchpad ssh` fallback.

## Next Agent Read Order
1. `.ai/state/current.md`
2. `.ai/tasks/queue.md`
3. `.ai/tasks/prompts/8.4.md`
4. `.ai/plans/08-task-references-and-solver-aware-logs.md`
5. `.ai/plan.md`
6. `.ai/git-rules.md`
