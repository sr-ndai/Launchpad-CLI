# Phase 10 Plan - Cluster Environment and Live Metrics

## Goal

Land the deferred cluster-facing follow-up that was intentionally kept out of
the Phase 9 merge: project-configurable Nastran environment exports plus live
running-job metrics via `sstat`, with graceful degraded behavior when SLURM
accounting is unavailable.

## Task Breakdown

| Task ID | Title | Summary | Depends On |
|---------|-------|---------|------------|
| 10.1 | Nastran env exports and live running-job metrics | Add `solvers.nastran.environment`, thread it into submit script generation, introduce `remote_binaries.sstat` plus `sstat` query/parsing, surface live metrics in human `status` output, degrade cleanly when accounting is unavailable, and update docs/tests. | — |

## Notes

- This phase exists because the change was prototyped locally after Phase 9,
  but was explicitly restored before the Phase 9 merge when the Coordinator
  role boundaries were reasserted.
- The human has now explicitly requested that the work be landed with a proper
  `.ai` paper trail rather than remaining out-of-band.
- The first iteration keeps `launchpad --json status ...` unchanged and limits
  live metrics to human-readable status surfaces.
