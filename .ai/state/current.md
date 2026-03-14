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
8.5 — SLURM login-shell execution and diagnostics

## Queue Snapshot
- pending: —
- ready: —
- in-progress: 8.5
- needs-review: —
- revision-needed: —
- blocked: —

## Repo State
- default branch: `main`
- coordination branch: `phase/08-task-references-and-solver-aware-logs`
- active task branch: `task/8.5-slurm-login-shell`
- last processed builder session: `2026-03-14-1558-builder-8.4.md`

## What Changed Recently
- Reopened Phase 8 again with task `8.5` after field debugging showed that
  `status` and `logs` still fail when `squeue` and `sacct` are only available
  through the head node's login-shell initialization.
- Committed the repository-level `.gitignore` follow-up to ignore `*.pem`
  private-key files without mixing that housekeeping into product task work.
- Accepted task `8.4` after review and prompt verification, then merged
  `task/8.4-cluster-access-diagnostics` into the phase branch.
- Phase 8 now includes the doctor exec-environment fix, the Windows
  `launchpad ssh` OpenSSH fallback, the related docs updates, and regression
  coverage from `8.4`.
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
Builder should switch to `task/8.5-slurm-login-shell`, read the task prompt,
and implement the shared SLURM login-shell execution fix plus aligned doctor
diagnostics.

## Next Agent Read Order
1. `.ai/state/current.md`
2. `.ai/tasks/queue.md`
3. `.ai/tasks/prompts/8.5.md`
4. `.ai/plans/08-task-references-and-solver-aware-logs.md`
5. `.ai/plan.md`
6. `.ai/git-rules.md`
