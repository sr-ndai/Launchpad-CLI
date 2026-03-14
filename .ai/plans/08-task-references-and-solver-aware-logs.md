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
