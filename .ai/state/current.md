# Current State

> This is the **routing artifact**. Every agent reads this first on the active
> phase branch, then follows the branch and file pointers below.
> If this file disagrees with a canonical file, trust the canonical file and
> repair this snapshot before ending the session.

## Last Updated
2026-03-12

## Active Phase
Phase 1 — Foundation

## Active Task
1.1 — Project scaffolding and baseline CLI

## Queue Snapshot
- pending: 1.2, 1.3, 1.4
- ready: —
- in-progress: 1.1
- needs-review: —
- revision-needed: —
- blocked: —

## Repo State
- default branch: `main`
- coordination branch: `phase/01-foundation`
- active task branch: `task/1.1-project-scaffolding`
- last processed builder session: `none`

## What Changed Recently
- Initialized the coordination workflow on `main` and `phase/01-foundation`.
- Decomposed Phase 1 into tasks `1.1` through `1.4`.
- Assigned task `1.1` to the Builder and prepared its prompt.

## Known Blockers
None.

## Next Recommended Action
Builder: switch to `task/1.1-project-scaffolding`, implement the task prompt,
run the listed verification, and write a Builder session note with
`Outcome: READY_FOR_REVIEW` or `Outcome: BLOCKED`.

## Next Agent Read Order
1. `.ai/tasks/prompts/1.1.md`
2. `.ai/plans/01-foundation.md`
3. `.ai/plan.md`
4. `.ai/git-rules.md`
