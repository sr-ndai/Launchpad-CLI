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
None.

## Queue Snapshot
- pending: —
- ready: —
- in-progress: —
- needs-review: —
- revision-needed: —
- blocked: —

## Repo State
- default branch: `main`
- coordination branch: `phase/08-task-references-and-solver-aware-logs`
- active task branch: `none`
- last processed builder session: `2026-03-14-1723-builder-8.7.md`

## What Changed Recently
- Merged the latest `main` into
  `phase/08-task-references-and-solver-aware-logs` to resolve the current PR
  conflict set, keeping the accepted `8.6` workspace-root changes and `8.7`
  config-show highlighting intact.
- Opened PR `#11` from `phase/08-task-references-and-solver-aware-logs` to
  `main` for the post-merge follow-ups after confirming that PR `#10` had
  already been merged into `main` on 2026-03-14.
- Accepted task `8.7` after review and prompt verification, then merged
  `task/8.7-config-show-syntax-highlighting` into the phase branch.
- Phase 8 now also includes syntax-highlighted human-readable
  `launchpad config show` output, the shared syntax helper, and the related
  docs/tests from `8.7`.
- Reopened Phase 8 with task `8.7` after field feedback showed that
  `launchpad config show` still renders resolved TOML as plain text instead of
  using Rich syntax highlighting in the primary human-readable path.
- Assigned task `8.7` on branch `task/8.7-config-show-syntax-highlighting` to
  add syntax-highlighted `config show` rendering while preserving the existing
  `--json` and `--docs` outputs.
- Accepted task `8.6` after review and prompt verification, then merged
  `task/8.6-configurable-workspace-root` into the phase branch.
- Phase 8 now also includes the configurable `cluster.workspace_root` model,
  the shared workspace-root resolver, and the aligned submit, doctor, ls,
  cleanup, docs, and regression updates from `8.6`.
- Reopened Phase 8 with task `8.6` after field debugging showed that
  Launchpad still hardcodes the writable remote workspace as
  `<shared_root>/<ssh.username>` even when the cluster uses a different shared
  writable directory such as `/shared/launchpad`.
- Assigned task `8.6` on branch `task/8.6-configurable-workspace-root` to add
  a dedicated workspace-root config field, centralize the resolver, and align
  submit, doctor, ls, cleanup, docs, and regression coverage around it.
- Merged the latest `main` into
  `phase/08-task-references-and-solver-aware-logs` to resolve the PR conflict
  set, keeping the Phase 8 follow-up state and the `8.5` scheduler-shell
  implementation intact.
- Opened PR `#10` from `phase/08-task-references-and-solver-aware-logs` to
  `main` after confirming GitHub no longer had the older Phase 8 PR open.
- Accepted task `8.5` after review and prompt verification, then merged
  `task/8.5-slurm-login-shell` into the phase branch.
- Phase 8 now also includes the shared SLURM login-shell execution path, the
  aligned doctor scheduler-binary checks, and the related docs/tests from
  `8.5`.
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
Human should review PR `#11` from
`phase/08-task-references-and-solver-aware-logs` to `main`, now including the
workspace-root follow-up from task `8.6` and the syntax-highlighted
`config show` follow-up from task `8.7`.

## Next Agent Read Order
1. `.ai/state/current.md`
2. `.ai/tasks/queue.md`
3. `.ai/sessions/2026-03-14-1737-coordinator-resolve-phase-8-main-conflicts.md`
4. `.ai/sessions/2026-03-14-1730-coordinator-open-phase-8-pr-11.md`
5. `.ai/sessions/2026-03-14-1725-coordinator-accept-8.7-update-pr.md`
6. `.ai/reviews/8.7.md`
7. `.ai/plans/08-task-references-and-solver-aware-logs.md`
8. `.ai/plan.md`
9. `.ai/git-rules.md`
