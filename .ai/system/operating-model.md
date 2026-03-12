# Operating Model

This document defines how the Coordinator and Builder behave during normal
operation. For ownership and schemas, see `file-ownership.md`.

## Branch Authority

Before doing anything else, identify which branch owns the state you are about
to touch.

- **Active phase branch:** shared coordination branch. This is where the
  Coordinator maintains `plan.md`, `plans/`, `tasks/queue.md`,
  `state/current.md`, `state/decisions.md`, and Coordinator session notes.
- **Active task branch:** task-local working branch. This is where the Builder
  works, where the active task prompt is read, where review files live while
  the task is active, and where Builder session notes are written.
- **`state/current.md` is the router.** Read it first on the phase branch, then
  follow its `active task branch` and `next agent read order` fields.

If a summary conflicts with a canonical file, trust the canonical file and
repair the summary before the Coordinator ends the session.

## Coordinator Operating Loop

Every time the Coordinator is invoked, follow this sequence.

### 1. Orient on the Phase Branch

1. Start on the active phase branch. If the system is not initialized yet,
   start on `main`.
2. Read `.ai/state/current.md`.
3. Read `.ai/tasks/queue.md`.
4. Read `.ai/git-rules.md` before any git operations.

### 2. Inspect Active Task Branch When Present

5. If `state/current.md` names an active task branch, inspect the task-local
   files on that branch before planning new work:
   - `.ai/tasks/prompts/<task-id>.md`
   - `.ai/reviews/<task-id>.md` if it exists
   - latest `.ai/sessions/*-builder-*` note for the task
6. Compare that latest Builder session note to
   `last processed builder session` in `.ai/state/current.md`.
7. Only if the Builder session note is newer and unprocessed:
   - `READY_FOR_REVIEW` -> update the queue row on the phase branch from
     `in-progress` or `revision-needed` to `needs-review`
   - `BLOCKED` -> update the queue row on the phase branch to `blocked` and
     record the blocker in `.ai/state/current.md`
8. After recording the handoff, update `last processed builder session` in
   `.ai/state/current.md`.

### 3. Act on Highest Priority Work

9. **If a task is `needs-review`**: review it first.
10. **If a task is `revision-needed`**: confirm that the review file on the task
   branch is actionable and the task is still assigned correctly.
11. **If no review work exists**:
   - promote a `pending` task to `ready` when dependencies are done
   - assign a `ready` task by setting it to `in-progress`
   - create new tasks and prompts from the plan when the queue is too thin

### 4. Plan Only When Needed

12. Read `.ai/plan.md` and `.ai/plans/` only when you need to create tasks,
    reprioritize, or repair drift between plan and reality.
13. If reality diverges from the plan, update `.ai/plan.md` and append the
    decision to `.ai/state/decisions.md`.

### 5. Close on the Phase Branch

14. Update `.ai/state/current.md` with:
    - current queue snapshot
    - coordination branch
    - active task branch
    - last processed builder session
    - next recommended action
    - next agent read order
15. Write a Coordinator session note in `.ai/sessions/`.
16. Commit phase-branch `.ai/` updates.

## Builder Operating Loop

Every time the Builder is invoked, follow this sequence.

### 1. Orient

1. Read `.ai/state/current.md` on the phase branch.
2. Read `.ai/tasks/queue.md` on the phase branch.
3. Identify the assigned task:
   - use the task ID provided by the human, or
   - infer the single active task from `state/current.md` and `queue.md`
4. Switch to the task branch named in the queue row or prompt.
5. Read `.ai/tasks/prompts/<task-id>.md` on the task branch.
6. Read `.ai/git-rules.md`.
7. If the task is `revision-needed`, read `.ai/reviews/<task-id>.md` on the
   task branch.

### 2. Prepare

8. Run `git branch --show-current` and confirm it matches the branch named in
   the prompt.
9. Stay in scope. If you discover something outside scope, note it. Do not fix
   it unless the prompt says to.

### 3. Execute

10. Implement the task requirements.
11. Make clean commits on the task branch.
12. Do not edit shared coordination files on the phase branch:
    - `.ai/tasks/queue.md`
    - `.ai/state/current.md`
    - `.ai/plan.md`
    - `.ai/plans/`
    - `.ai/state/decisions.md`

### 4. Verify

13. Run every verification step listed in the prompt.
14. Record the results in a new Builder session note.

### 5. Close on the Task Branch

15. Write a Builder session note in `.ai/sessions/` with an exact
    `Outcome: READY_FOR_REVIEW` or `Outcome: BLOCKED`.
16. Commit task-local `.ai/` evidence on the task branch.
17. Stop. The Coordinator records queue transitions on the phase branch.

## Task Lifecycle

### Queue States

| Status | Meaning |
|--------|---------|
| `pending` | Not yet actionable |
| `ready` | Dependencies met and available for assignment |
| `in-progress` | Builder is actively working on the task branch |
| `needs-review` | Builder reported `READY_FOR_REVIEW`; Coordinator review is pending |
| `revision-needed` | Coordinator reviewed the task and requested changes |
| `done` | Accepted and merged into the phase branch |
| `blocked` | Cannot proceed due to blocker |

### Queue Transitions

All queue transitions are recorded by the Coordinator on the active phase
branch.

```text
pending -> ready
ready -> in-progress
in-progress -> needs-review
revision-needed -> needs-review
needs-review -> done
needs-review -> revision-needed
in-progress -> blocked
revision-needed -> blocked
blocked -> ready
```

### Builder Outcome Signals

The Builder does not edit `queue.md`. Instead, the Builder reports one of these
exact outcomes in the session note:

- `READY_FOR_REVIEW`
- `BLOCKED`

The Coordinator translates that signal into the queue transition on the phase
branch.

## Review Lifecycle

### Coordinator Review Procedure

1. Start from the active phase branch and identify the task row in
   `.ai/tasks/queue.md`.
2. Switch to the task branch named in that row.
3. Read the latest Builder session note for the task.
4. Inspect the diff against the phase branch named in `.ai/state/current.md`:
   `git diff <phase-branch>...<task-branch>`
5. Run the prompt's verification steps if they are still relevant.
6. Write or update `.ai/reviews/<task-id>.md` on the task branch.

### Review File Format

```text
# Review: <task-id>

**Verdict:** ACCEPTED | REVISION_NEEDED

## Summary
_What was done and whether it meets the prompt requirements._

## Issues
1. _Specific issue with file and line references._

## Required Changes
1. _Exact change needed._
```

The verdict line must be exactly `ACCEPTED` or `REVISION_NEEDED`.

### After Review

- **If accepted:**
  1. commit the review file on the task branch
  2. switch to the phase branch
  3. merge the task branch with `--no-ff`
  4. set the queue row to `done`
  5. update `.ai/state/current.md`
  6. write a Coordinator session note
  7. delete the task branch

- **If revision is needed:**
  1. commit the review file on the task branch
  2. switch to the phase branch
  3. set the queue row to `revision-needed`
  4. update `.ai/state/current.md`
  5. write a Coordinator session note

## Prompt Immutability

- The Coordinator may edit a task prompt freely before the task enters
  `in-progress`.
- Once a task is `in-progress`, the task prompt becomes task-local.
- Any later change must be a clearly dated `## Revision YYYY-MM-DD` section
  added by the Coordinator on the task branch.

This prevents silent scope creep.

## Pull Requests

When all tasks in a phase are `done` and merged into the phase branch:

1. Verify the phase branch is clean.
2. Confirm phase-level verification is green.
3. Update `.ai/state/current.md` with the completed phase summary.
4. Open a PR from the phase branch to `main`.
5. The human owner reviews and merges.

## Session Notes

Session notes are evidence. They should be concise, factual, and useful for
recovery.

### Coordinator Session Note

File: `.ai/sessions/<YYYY-MM-DD>-<HHMM>-coordinator-<short-summary>.md`

```text
# Coordinator Session - <YYYY-MM-DD>

## Actions Taken
- _Action 1_
- _Action 2_

## Branches Touched
- coordination: `phase/<NN>-<name>`
- task: `task/<NN.N>-<name>` or `none`

## Decisions Made
- _Decision_

## Tasks Updated
| Task ID | Old Status | New Status |
|---------|------------|------------|
| _1.3_ | _needs-review_ | _done_ |

## Next Recommended Action
_What the next invocation should do._
```

### Builder Session Note

File: `.ai/sessions/<YYYY-MM-DD>-<HHMM>-builder-<task-id>.md`

```text
# Builder Session - <task-id> - <YYYY-MM-DD>

## Objective
_One-line task objective from prompt._

## Outcome
READY_FOR_REVIEW | BLOCKED

## What Was Done
_Brief summary of implementation._

## Files Changed
- _path/to/file_

## Verification Results
_Command-by-command results._

## Observations
_Blockers, ambiguities, or out-of-scope issues._
```

## Escalation and Blockers

- **Builder hits ambiguity:** use the most conservative interpretation, note it
  in the session note, and stop if the ambiguity would change behavior.
- **Builder hits a blocker:** write `Outcome: BLOCKED`, explain the blocker,
  and stop.
- **Builder discovers out-of-scope work:** note it, do not fix it.
- **Coordinator encounters plan-breaking reality:** update `.ai/plan.md`, log
  the decision in `.ai/state/decisions.md`, and adjust the queue.
