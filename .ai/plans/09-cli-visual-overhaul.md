# Phase 09 Plan: CLI Visual Overhaul

## Objective

Deliver a full human-facing terminal redesign for Launchpad that replaces the
current panel-heavy Phase 7 presentation with a restrained, semantic design
system while preserving all established command behavior and machine-readable
interfaces.

## Scope

- Redesign the full human-facing CLI surface area except the interactive
  `launchpad ssh` session body itself
- Keep bare `launchpad` as the only branded wordmark surface and move all
  other surfaces to the restrained visual grammar
- Replace default human `launchpad config show` with the new sectioned summary
  while preserving `--json` and `--docs`
- Land shared display primitives, prompt/progress helpers, and root shell
  changes before migrating command-specific runtime surfaces
- Refresh help, docs, and regression coverage to match the redesigned output

## Out of Scope

- Changing command names, flags, exit codes, JSON payloads, or selector rules
- Rewriting solver, transfer, scheduler, or workspace behavior beyond the
  display-layer changes needed to expose existing data differently
- Pushing Rich rendering concerns into `core/` modules or swapping away from
  the existing `click` + `rich` + `rich-click` stack
- Rebuilding the interactive `launchpad ssh` session body or adding a TUI
- Real-cluster rollout validation, fresh-Windows validation, or team training

## Entry Criteria

- `origin/main` contains the merged Phase 8 history from PR `#12`
- No active Builder task remains for Phase 8
- The redesign brief at `.ai/plans/LAUNCHPAD_UI_REDESIGN_PLAN.md` is available
  as the detailed design reference for this phase

## Exit Criteria

- Every human-readable surface except the `launchpad ssh` session body uses
  the new display primitives and emits no more than one hero panel per command
- Bare `launchpad` is the only wordmark surface; onboarding, runtime, and
  operator commands all use the restrained grammar
- Human `launchpad config show` renders the grouped summary by default while
  `--json` and `--docs` remain backward compatible
- The queue, docs, and tests reflect the redesigned CLI and no stale Phase 7
  titles or panel assumptions remain in the active regression suite

## Task Breakdown

| Task ID | Title | Why It Exists | Depends On |
|---------|-------|---------------|------------|
| 9.1 | Display foundation and root shell | Replace the current panel/badge design system with semantic display primitives, no-color fallbacks, prompt/progress helpers, and the new welcome/help shell before any command migrations begin. | — |
| 9.2 | Onboarding, config, and diagnostics redesign | `config init`, `config show`, and `doctor` still carry the old Phase 7 panel stack and wordmark usage; they need to move to the new restrained layout early because later docs and help text depend on that settled direction. | 9.1 |
| 9.3 | Submit and status redesign | Submit and status already depend heavily on shared rendering helpers, so they should be the first primary workflows migrated to the new hero-card, borderless-table, and inline-metadata model. | 9.1 |
| 9.4 | Download and transfer feedback redesign | Download still uses panel summaries and plain confirmations; it needs the new preflight summary, shared progress/spinner feedback, and restrained completion layout after the display foundation is stable. | 9.1, 9.3 |
| 9.5 | Logs and utility command redesign | Logs, ls, cancel, and cleanup still use command-local panel-heavy renderers and destructive-flow copy that should be unified after the primary workflow patterns settle. | 9.1, 9.4 |
| 9.6 | Help, docs, and regression hardening | After all surfaces move, the remaining help/examples/docs and regression coverage must be refreshed so the new UX is documented and protected without relying on brittle snapshots. | 9.2, 9.3, 9.4, 9.5 |

## Risks

- Existing CLI tests assert many current titles and panel-oriented strings, so
  this phase will create broad but intentional output-test churn
- Shared prompt/progress changes can leak into `--json`, `--quiet`, or non-TTY
  paths if the Builder does not keep the display helpers tightly scoped
- The `config show` redesign intentionally supersedes the recent Rich TOML
  default from `8.7`, so docs and help text must make the human vs machine
  paths explicit

## Notes

- Hybrid branding means the welcome screen keeps the only wordmark-capable
  surface; every other command should drop Phase 7 ASCII/panel chrome
- Rich display concerns stay in `src/launchpad_cli/display.py` and the CLI
  layer; `core/` modules should continue returning plain data and callbacks
- Keep the current testing style: semantic CLI assertions plus focused helper
  coverage, not brittle full-output snapshot files
