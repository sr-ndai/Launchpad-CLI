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
| 3.1 | 3 | SLURM status parsing and query primitives | done | — | task/3.1-slurm-status-parsing | — |
| 3.2 | 3 | Status command and live monitoring UI | done | 3.1 | task/3.2-status-command-watch | — |
| 3.3 | 3 | Logs and cancel operator commands | done | 3.1 | task/3.3-logs-and-cancel | — |
| 4.1 | 4 | Download primitives and filesystem groundwork | done | — | task/4.1-download-primitives | — |
| 4.2 | 4 | Download command orchestration | done | 4.1 | task/4.2-download-command-orchestration | — |
| 4.3 | 4 | Remote listing and cleanup commands | done | 4.2 | task/4.3-remote-ls-and-cleanup | — |
| 5.1 | 5 | Transfer architecture and precedent review | done | — | task/5.1-transfer-benchmark-direction | — |
| 5.2 | 5 | Hybrid transfer engine and CLI surfaces | done | 5.1 | task/5.2-transfer-implementation-hardening | — |
| 5.3 | 5 | UX, logging, and fallback polish | done | 5.2 | task/5.3-cli-polish-and-logging | — |
| 7.1 | 7 | Design system and branded help | done | — | task/7.1-design-system-and-help | — |
| 7.2 | 7 | Guided setup and diagnostics UX | done | 7.1 | task/7.2-guided-setup-and-diagnostics | — |
| 7.3 | 7 | Primary workflow terminal experience | done | 7.1 | task/7.3-primary-workflow-experience | — |
| 7.4 | 7 | Secondary command polish and docs | done | 7.2, 7.3 | task/7.4-secondary-command-polish-and-docs | — |
| 8.1 | 8 | Job manifest and task references | done | — | task/8.1-job-manifest-and-task-refs | — |
| 8.2 | 8 | Solver-aware log resolution and selector support | done | 8.1 | task/8.2-solver-aware-log-resolution | — |
| 8.3 | 8 | Interactive log picker and docs | done | 8.2 | task/8.3-interactive-log-picker | — |
| 8.4 | 8 | Cluster access diagnostics and Windows SSH | done | 8.3 | task/8.4-cluster-access-diagnostics | — |
| 8.5 | 8 | SLURM login-shell execution and diagnostics | done | 8.4 | task/8.5-slurm-login-shell | — |
| 8.6 | 8 | Configurable remote workspace root | done | 8.5 | task/8.6-configurable-workspace-root | — |
| 8.7 | 8 | Syntax-highlighted config show output | done | 8.6 | task/8.7-config-show-syntax-highlighting | — |
| 8.8 | 8 | Harden SLURM numeric field parsing | in-progress | 8.7 | task/8.8-slurm-parser-hardening | Builder |
