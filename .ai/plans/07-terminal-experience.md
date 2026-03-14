# Phase 07 Plan: Terminal Experience

## Objective

Make Launchpad feel intentionally designed, modern, and easy to use by
introducing a shared terminal design system, guided onboarding surfaces, and
consistent visual polish across the implemented commands without breaking the
existing command surface or machine-readable workflows.

## Scope

- Shared CLI theming, badges, panels, prompt wrappers, and the welcome-screen
  shell
- Restrained help-reference improvements that prioritize scan speed over
  branding chrome
- Guided UX improvements for setup, diagnostics, confirmations, and next-step
  messaging
- Human-facing runtime polish for the primary workflows and the remaining
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
| 7.1 | Design system and branded help | Establish the shared visual language, a distinct no-argument welcome screen, and a restrained help-reference shell so later tasks build on the right surface model. | — |
| 7.2 | Guided setup and diagnostics UX | Turn `config init` and `doctor` into the branded onboarding and recovery moments that replace help-surface decoration. | 7.1 |
| 7.3 | Primary workflow terminal experience | Put most of the CLI personality into `submit`, `status`, and `download` runtime feedback, especially success summaries and next steps. | 7.1 |
| 7.4 | Secondary command polish and docs | Bring the remaining implemented commands and docs into the same design language after the welcome, onboarding, and primary flows settle. | 7.2, 7.3 |

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
- Phase 7 now uses three distinct surfaces:
  - bare `launchpad` is the branded welcome screen
  - `launchpad --help` is the full dry reference card
  - `launchpad <command> --help` is a focused command reference
- Root help should use exactly three command groups (`Commands`,
  `Configuration`, `Management`) plus one merged `Options` panel.
- The ASCII Launchpad mark and tagline should not appear on `--help`; reserve
  them for the welcome screen, `config init`, `doctor` all-pass, and selected
  success moments that later tasks own.
- Docs updates should use current output examples from the implemented CLI
  rather than aspirational screenshots.
