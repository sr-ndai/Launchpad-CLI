# Phase 07 Plan: Terminal Experience

## Objective

Make Launchpad feel intentionally designed, modern, and easy to use by
introducing a shared terminal design system, guided onboarding surfaces, and
consistent visual polish across the implemented commands without breaking the
existing command surface or machine-readable workflows.

## Scope

- Shared CLI theming, badges, panels, prompt wrappers, and branded help output
- Guided UX improvements for setup, diagnostics, confirmations, and next-step
  messaging
- Human-facing output polish for the primary workflows and the remaining
  operator commands
- Documentation updates that reflect the refreshed terminal experience

## Out of Scope

- Replacing `click` or `rich` with a heavier TUI framework
- Adding new major command families or changing existing flag names
- Changing established `--json` payload shapes for existing commands
- Real-cluster rollout validation, shared cluster config authoring, or ANSYS
  workflow implementation

## Entry Criteria

- `main` already includes the Phase 6 documentation merge and is the baseline
  for new work
- Rich-based output exists in the repo, but current help and prompt styling are
  still minimal and inconsistent
- The user explicitly chose a bold, colorful direction with guided UX and a
  compact ASCII brand treatment

## Exit Criteria

- The queue reflects all planned Phase 7 tasks with correct dependencies
- Task `7.1` is assigned on its own task branch with a prompt the Builder can
  execute without more planning
- The shared roadmap and routing state reflect Phase 7 as the active product
  phase
- Phase 7 work is scoped to preserve `--json`, `--quiet`, `--no-color`, and
  non-TTY behavior

## Task Breakdown

| Task ID | Title | Why It Exists | Depends On |
|---------|-------|---------------|------------|
| 7.1 | Design system and branded help | Establish the shared visual language, help layout, and ASCII brand treatment once so later command work can reuse a stable presentation layer. | — |
| 7.2 | Guided setup and diagnostics UX | Turn the first-run and troubleshooting surfaces into stepwise, actionable operator workflows built on the new design system. | 7.1 |
| 7.3 | Primary workflow terminal experience | Apply the design system to the busiest commands (`submit`, `status`, `download`) where the visual and guidance improvements matter most. | 7.1 |
| 7.4 | Secondary command polish and docs | Bring the remaining implemented commands and the user docs into the same design language after the primary surfaces settle. | 7.2, 7.3 |

## Risks

- Richer output can accidentally leak into machine-oriented paths; every task
  must explicitly preserve `--json`, `--quiet`, `--no-color`, and non-TTY
  behavior.
- Visual polish can sprawl into a framework rewrite; stay on the current
  `click` + `rich` + `rich-click` stack unless a narrow helper is clearly
  justified.
- Repeated redesign across commands will waste time; `7.1` must land shared
  helpers and conventions before the command-focused tasks proceed.

## Notes

- Design references for this phase: CLIG, GitHub CLI, Charm Gum, Vercel CLI,
  uv, and the current `rich-click` theming capabilities.
- The ASCII Launchpad mark should appear only on root help and selected
  first-run or success surfaces, never in watch loops or machine-readable
  output.
- Docs updates should use current output examples from the implemented CLI
  rather than aspirational screenshots.
