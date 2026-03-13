# Phase 01 Plan: Foundation

## Objective

Establish the baseline package, developer workflow, configuration stack, and
cluster connectivity primitives needed for the rest of the Launchpad CLI.

## Milestone

The repository can install as `launchpad-cli`, expose `launchpad` and `lp`,
load layered configuration, connect to the cluster over SSH, and
upload/download a file through the command line.

## Task Breakdown

| Task ID | Title | Depends On | Notes |
|---------|-------|------------|-------|
| 1.1 | Project scaffolding and baseline CLI | — | Convert the repo from the current placeholder script into the planned `src/` package layout with entry points, test harness, and documentation skeletons. |
| 1.2 | Config and logging foundation | 1.1 | Build the layered config loader and logging setup, then expose `launchpad config init/show`. |
| 1.3 | SSH, transfer, and compression primitives | 1.1 | Implement async SSH connection management plus single-stream SFTP and local zstd helpers. |
| 1.4 | Operator commands and diagnostics | 1.2, 1.3 | Add `launchpad ssh` and `launchpad doctor`, wiring them to config and transport primitives. |

## Sequencing Notes

- Keep `1.1` narrow and structural so later tasks can build on stable package
  and test conventions.
- `1.2` and `1.3` may proceed independently after `1.1` is accepted, but the
  repository currently assumes a single active Builder.
- `1.4` should stay focused on user-facing command integration and
  diagnostics rather than revisiting core transport behavior.

## Exit Criteria

- The queue reflects all Phase 1 tasks with correct dependencies.
- Task `1.1` is assigned on its own task branch with a prompt the Builder can
  execute without additional planning.
- `current.md` routes the next agent directly to the active task artifacts.
