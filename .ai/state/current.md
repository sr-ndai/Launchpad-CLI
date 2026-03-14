# Current State

> This is the **routing artifact**. Every agent reads this first on the active
> phase branch, then follows the branch and file pointers below.
> If this file disagrees with a canonical file, trust the canonical file and
> repair this snapshot before ending the session.

## Last Updated
2026-03-14

## Active Phase
Phase 7 — Terminal Experience

## Active Task
7.3 — Primary workflow terminal experience

## Queue Snapshot
- pending: 7.4
- ready: —
- in-progress: 7.3
- needs-review: —
- revision-needed: —
- blocked: —

## Repo State
- default branch: `main`
- coordination branch: `phase/07-terminal-experience`
- active task branch: `task/7.3-primary-workflow-experience`
- last processed builder session: `2026-03-14-0926-builder-7.2.md`

## What Changed Recently
- Ingested Builder session `2026-03-14-0926-builder-7.2.md`, reviewed the
  guided setup and diagnostics work, and accepted task `7.2`.
- Merged `task/7.2-guided-setup-and-diagnostics` into
  `phase/07-terminal-experience`, carrying forward the three-surface CLI shell,
  the guided `config init` flow, grouped `doctor` output, and the docs/test
  refresh for setup and diagnostics.
- Assigned `7.3` as the next active Builder task now that the shared shell and
  onboarding surfaces are complete.

## Known Blockers
- None.

## Next Recommended Action
Builder should switch to `task/7.3-primary-workflow-experience`, read the
prompt for task `7.3`, and apply the accepted Phase 7 shell to the
`submit`/`status`/`download` runtime surfaces.

## Next Agent Read Order
1. `.ai/state/current.md`
2. `.ai/tasks/queue.md`
3. `.ai/tasks/prompts/7.3.md`
4. `.ai/plans/07-terminal-experience.md`
5. `.ai/plan.md`
