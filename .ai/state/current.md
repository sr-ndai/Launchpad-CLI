# Current State

> This is the **routing artifact**. Every agent reads this first on the active
> phase branch, then follows the branch and file pointers below.
> If this file disagrees with a canonical file, trust the canonical file and
> repair this snapshot before ending the session.

## Last Updated
_Not yet initialized._

## Active Phase
_None — awaiting initial planning._

## Active Task
_None._

## Queue Snapshot
- pending: —
- ready: —
- in-progress: —
- needs-review: —
- revision-needed: —
- blocked: —

## Repo State
- default branch: `main`
- coordination branch: _none_
- active task branch: _none_
- last processed builder session: _none_

## What Changed Recently
- `.ai` system installed.

## Known Blockers
_None._

## Next Recommended Action
_Coordinator: read `plan.md`, create the first phase branch, and break the
work into the first set of tasks._

## Next Agent Read Order
1. `.ai/plan.md`
2. `.ai/tasks/queue.md`
3. `.ai/roles/coordinator.md`
