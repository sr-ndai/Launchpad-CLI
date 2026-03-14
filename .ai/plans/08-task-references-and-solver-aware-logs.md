# Phase 08 Plan: Task References and Solver-Aware Logs

## Objective

Make batched jobs feel per-file addressable by persisting task references and
submitted solver metadata, then use that metadata to power solver-aware log
lookup and an interactive multi-task log selection flow.

## Scope

- A new remote `launchpad-manifest.json` artifact that records solver identity,
  resolved solver-log kinds, and per-task reference metadata
- Stable task references for batched jobs: display label, alias, and raw task
  ID, with deterministic duplicate-stem disambiguation
- Human-facing submit and status updates that expose the new task references
- Cross-command task selector support for `logs`, `download`, and `cancel`
- Solver-aware log resolution driven by submitted metadata rather than
  `run_name` heuristics
- A human TTY picker for ambiguous multi-task `logs` invocations
- Docs and regression coverage for the new task-reference and solver-log model

## Out of Scope

- Changing the one-job-per-submit model; batched runs remain one SLURM array
- Encoding solver metadata into the SLURM comment in this phase
- Broadening the interactive model beyond `launchpad logs`
- Pattern-based log matching or multiple extensions per named log kind
- Full ANSYS runtime support beyond keeping the config and adapter interfaces
  consistent

## Entry Criteria

- Phase 7 is merged on `main`, including the current terminal design system
- Batched submits currently rely on numeric array task IDs only
- `logs` currently infers solver-log extensions from `run_name` and offers no
  interactive task selection

## Exit Criteria

- The queue reflects all planned Phase 8 tasks with correct dependencies
- Task `8.1` is assigned on its own task branch with an implementation-ready
  prompt
- The roadmap and routing state reflect Phase 8 as the active coordination
  phase
- The chosen manifest-only metadata model is documented clearly enough that
  later tasks do not revisit it ad hoc

## Task Breakdown

| Task ID | Title | Why It Exists | Depends On |
|---------|-------|---------------|------------|
| 8.1 | Job manifest and task references | Establish the submitted metadata contract, the per-task reference model, and the submit/status UX that later commands will consume. | — |
| 8.2 | Solver-aware log resolution and selector support | Make solver-log lookup and task selection resolve from submitted metadata across `logs`, `download`, and `cancel`. | 8.1 |
| 8.3 | Interactive log picker and docs | Finish the user-facing logs experience with the TTY picker, help/docs updates, and regression coverage. | 8.2 |

## Risks

- If the manifest shape is unstable, later command work will thrash; `8.1`
  must settle the metadata contract before selector or picker work starts.
- Solver-log configuration can drift if commands rely on current local config
  instead of submitted metadata; the manifest must be the authority for new
  jobs.
- Interactive logs UX must not leak into non-TTY or `--json` modes; `8.3` must
  keep deterministic script behavior intact.

## Notes

- The manifest is authoritative for new jobs and should include the resolved
  solver log catalog captured at submit time.
- `--solver-log` remains the main user-facing entry point and maps to the named
  `solver` log kind; `--log-kind KIND` selects non-primary solver logs such as
  Nastran telemetry.
- Legacy jobs without `launchpad-manifest.json` may use best-effort fallback
  only for the primary solver log; secondary log kinds should fail clearly.
- The interactive picker should reuse the Phase 7 design language and the
  chosen lightweight dependency rather than introducing a full TUI framework.

## Revision 2026-03-14

### Follow-up Scope

- Reopen Phase 8 with task `8.4` to fix field-reported cluster-access
  regressions before PR `#9` is merged.
- Make `launchpad doctor` probe remote binaries and writable paths through the
  same remote exec environment Launchpad uses elsewhere, avoiding false
  negatives caused by the current forced `sh -lc` wrapper.
- Replace Windows `launchpad ssh` interactive shell startup with the local
  OpenSSH client while continuing to honor existing `ssh.*` config values.
- Add docs and regression coverage for the doctor probe alignment and the
  Windows SSH behavior.

### Task Breakdown Addendum

| Task ID | Title | Why It Exists | Depends On |
|---------|-------|---------------|------------|
| 8.4 | Cluster access diagnostics and Windows SSH | Field debugging found that `doctor` can report missing remote binaries under the wrong shell environment and that `launchpad ssh` crashes on Windows when AsyncSSH redirects stdio through the Proactor loop. | 8.3 |

### Additional Risks

- If `doctor` validates an interactive shell instead of Launchpad's normal
  remote exec model, it can hide real failures in submit/status/download flows.
- Windows interactive SSH should not introduce a new config surface or depend
  on unsupported console behavior; the local OpenSSH client must be treated as
  the supported transport for that one command.

## Revision 2026-03-14 (Scheduler Shell Follow-up)

### Follow-up Scope

- Reopen Phase 8 with task `8.5` after field debugging showed that SLURM
  commands still fail in Launchpad's non-login SSH exec environment even though
  operators can access them in a manual head-node login shell.
- Make Launchpad execute scheduler binaries through a login-shell wrapper so
  `sbatch`, `squeue`, `sacct`, and `scancel` see the same initialized
  environment that operators use manually.
- Re-align `launchpad doctor` so its scheduler-binary checks validate that same
  login-shell SLURM environment while leaving non-scheduler checks on their
  current non-interactive path.
- Add docs and regression coverage for the new scheduler-shell behavior and the
  improved operator guidance when login-shell initialization is still missing.

### Task Breakdown Addendum

| Task ID | Title | Why It Exists | Depends On |
|---------|-------|---------------|------------|
| 8.5 | SLURM login-shell execution and diagnostics | Field debugging after `8.4` showed that scheduler commands are available only after the cluster's login-shell initialization, so Launchpad still fails on `status` and `logs` when it invokes `squeue` and `sacct` directly. | 8.4 |

### Additional Risks

- Fixing only `status` and `logs` would leave the same scheduler PATH problem
  in `submit`, `cancel`, `download`, and `cleanup`; the shared SLURM command
  path has to change together.
- Doctor must distinguish scheduler binaries, which should follow the login
  shell, from non-scheduler binaries like `tar` and `zstd`, which should keep
  the existing non-interactive exec behavior unless a later requirement says
  otherwise.

## Revision 2026-03-14 (Workspace Root Follow-up)

### Follow-up Scope

- Reopen Phase 8 with task `8.6` after field debugging showed that Launchpad
  still assumes the writable remote workspace lives at
  `<cluster.shared_root>/<ssh.username>`, which is not true on the reported
  cluster.
- Introduce a dedicated configurable workspace-root setting so operators can
  point Launchpad at a writable shared directory such as `/shared/launchpad`
  without changing the SSH login username or overloading `cluster.shared_root`.
- Reuse that shared workspace-root resolution everywhere Launchpad currently
  derives the default remote root from `shared_root` plus `ssh.username`,
  including submit job-directory creation, doctor writable-root checks, remote
  listing defaults, and cleanup discovery.
- Add docs and regression coverage for the new workspace-root model and the
  backward-compatible fallback behavior.

### Task Breakdown Addendum

| Task ID | Title | Why It Exists | Depends On |
|---------|-------|---------------|------------|
| 8.6 | Configurable remote workspace root | Field debugging showed that Launchpad hardcodes the writable remote root as `<shared_root>/<ssh.username>`, but some clusters expose a different shared writable directory such as `/shared/launchpad`. | 8.5 |

### Additional Risks

- Repointing only `doctor` would leave `submit`, `ls`, and `cleanup` deriving
  incompatible remote roots, so the workspace-root logic has to be centralized
  and reused across commands.
- Overloading `cluster.shared_root` would blur the distinction between the
  shared filesystem mount and the Launchpad-managed writable workspace, which
  would make docs and future config harder to reason about.
