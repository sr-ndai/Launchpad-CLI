# Phase 02 Plan: Submission Pipeline

## Objective

Turn the Phase 1 transport and configuration groundwork into a working
`launchpad submit` flow for Nastran, including dry-run visibility and the
remote SLURM submission primitives it depends on.

## Milestone

The repository can discover Nastran inputs, package them with the existing
compression and transfer layers, generate the remote submit artifacts, and
submit a job through `launchpad submit`.

## Task Breakdown

| Task ID | Title | Depends On | Notes |
|---------|-------|------------|-------|
| 2.1 | Solver adapters and input discovery | — | Expand the solver protocol, implement Nastran discovery and run-command behavior, and keep ANSYS as an explicit stub that conforms to the shared interface. |
| 2.2 | SLURM and remote submission primitives | 2.1 | Build the reusable remote directory/archive helpers plus SLURM script generation and submit wrappers consumed by the CLI. |
| 2.3 | Submit orchestration and dry-run UX | 2.1, 2.2 | Wire the CLI command, manifest preview, and submit confirmation output around the established solver, transfer, and remote primitives. |

## Sequencing Notes

- Keep `2.1` focused on stable abstractions and deterministic local behavior so
  the later tasks can test against clear solver contracts.
- `2.2` should stop at reusable primitives and avoid CLI wiring; the objective
  is to make remote submit behavior testable without the command layer.
- `2.3` owns the end-to-end `launchpad submit` experience, including `--dry-run`
  behavior and the Rich-facing confirmation output.

## Exit Criteria

- The queue reflects all planned Phase 2 tasks with correct dependencies.
- Task `2.1` is assigned on its own task branch with a prompt the Builder can
  execute without additional planning.
- `current.md` routes the next agent directly to the active Phase 2 artifacts.
