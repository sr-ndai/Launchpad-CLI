# Phase 03 Plan: Monitoring & Logs

## Objective

Extend the submission pipeline into operational visibility so engineers can
inspect SLURM state, watch live job progress, view remote logs, and cancel work
without leaving the local CLI.

## Milestone

The repository can query and parse SLURM status data, render a useful
`launchpad status` experience including watch mode, and provide functional
`launchpad logs` and `launchpad cancel` commands for the submitted jobs created
in Phase 2.

## Task Breakdown

| Task ID | Title | Depends On | Notes |
|---------|-------|------------|-------|
| 3.1 | SLURM status parsing and query primitives | — | Extend `core/slurm.py` with `squeue`/`sacct` JSON parsing and the reusable remote query helpers that Phase 3 commands will consume. |
| 3.2 | Status command and live monitoring UI | 3.1 | Replace the `launchpad status` placeholder with the first functional status flow, including `--watch` behavior and Rich status formatting. |
| 3.3 | Logs and cancel operator commands | 3.1 | Implement `launchpad logs` and `launchpad cancel`, including the remote log-viewing/cancellation paths and the command-level confirmation behavior. |

## Sequencing Notes

- Keep `3.1` focused on stable SLURM data contracts and remote query wrappers so
  later CLI tasks can stay thin and testable.
- `3.2` owns the first substantial status-facing UI work for Rich tables and
  live refresh behavior.
- `3.3` should build on the same SLURM metadata model and preserve the human-
  friendly command behavior described in the roadmap, including confirmation for
  cancellation.

## Exit Criteria

- The queue reflects all planned Phase 3 tasks with correct dependencies.
- Task `3.1` is assigned on its own task branch with a prompt the Builder can
  execute without additional planning.
- `current.md` routes the next agent directly to the active Phase 3 artifacts.
