# File Ownership and Schemas

Every orchestration artifact has one primary owner and one authoritative branch
at any given time. Cross-role editing is the exception, not the default.

Files prefixed with `_` are templates or examples. Agents should ignore them
unless a human explicitly points to them.

## Ownership Table

| Artifact | Purpose | Type | Owner | Authoritative Branch | Builder May Edit | Coordinator May Edit |
|----------|---------|------|-------|----------------------|------------------|----------------------|
| `.ai/README.md` | Entry point and installation context | Instruction | Human | All branches | No | No |
| `.ai/INSTALL.md` | Bootstrap instructions | Instruction | Human | All branches | No | No |
| `.ai/git-rules.md` | Git workflow policy | Instruction | Human | All branches | No | No |
| `.ai/roles/*.md` | Role behavior rules | Instruction | Human | All branches | No | No |
| `.ai/system/*.md` | System documentation | Instruction | Human | All branches | No | No |
| `.ai/starter-prompts/*.md` | Copyable launch prompts | Instruction | Human | All branches | No | No |
| `.ai/plan.md` | High-level roadmap | Canonical | Coordinator | Active phase branch | No | Yes |
| `.ai/plans/*.md` | Detailed phase plans | Canonical | Coordinator | Active phase branch | No | Yes |
| `.ai/tasks/queue.md` | Shared task dashboard | Summary | Coordinator | Active phase branch | No | Yes |
| `.ai/state/current.md` | Routing snapshot | Summary | Coordinator | Active phase branch | No | Yes |
| `.ai/state/decisions.md` | Decision history | Canonical | Coordinator | Active phase branch | No | Yes (append-only) |
| `.ai/sessions/*-coordinator-*` | Coordinator evidence | Evidence | Coordinator | Active phase branch | No | Yes |
| `.ai/tasks/prompts/<task-id>.md` | Task execution contract | Canonical | Coordinator | Phase branch before assignment; active task branch once in progress | No | Yes |
| `.ai/reviews/<task-id>.md` | Task review verdict | Canonical | Coordinator | Active task branch while task is active; phase branch after merge | No | Yes |
| `.ai/sessions/*-builder-*` | Builder evidence | Evidence | Builder | Active task branch | Yes | No |

## Artifact Types

| Type | Meaning | Mutability |
|------|---------|------------|
| **Canonical** | Authoritative record. If it conflicts with a summary, it wins. | Owner may update per rules. |
| **Summary** | Compressed view for fast orientation. | Owner repairs from canonical files. |
| **Evidence** | Factual record of what happened. | Create a new file; do not rewrite history. |
| **Instruction** | Human-owned rules and helper materials. | Human updates only. |

## Branch Rules

- Shared coordination state lives on the active phase branch.
- Task-local execution artifacts live on the active task branch.
- `state/current.md` is always read first on the active phase branch.
- If `state/current.md` points to an active task branch, switch to that branch
  for the task prompt, review file, and Builder evidence.
- If a summary file conflicts with a canonical file, trust the canonical file
  and repair the summary before the Coordinator ends the session.

## Read Triggers

| File | Read When |
|------|-----------|
| `state/current.md` | Every session, first, on the active phase branch. |
| `tasks/queue.md` | Every session, after `state/current.md`, on the active phase branch. |
| `plan.md` | When creating tasks, reprioritizing, or recovering from drift. |
| `plans/*.md` | When a phase needs more detail than `plan.md` holds. |
| `tasks/prompts/<id>.md` | Builder: starting or resuming a task. Coordinator: assigning or reviewing a task. |
| `reviews/<id>.md` | Builder: when revising a task. Coordinator: follow-up review work. |
| `state/decisions.md` | When a past decision affects current work. |
| `sessions/*-builder-*` | Coordinator: during review or blocker handling. |
| `sessions/*-coordinator-*` | Human or future Coordinator: reconstructing prior coordination work. |
| `git-rules.md` | Before any git operation. |
| `roles/*.md` | At the start of each agent session. |
| `starter-prompts/*.md` | Human only, when launching a fresh Coordinator or Builder. |

## File Schemas

### `queue.md` Row Format

```text
| Task ID | Phase | Title | Status | Depends On | Branch | Assigned |
```

- **Task ID:** `<phase>.<sequence>` such as `1.1`
- **Phase:** Phase number
- **Title:** Short descriptive title
- **Status:** `pending`, `ready`, `in-progress`, `needs-review`,
  `revision-needed`, `done`, or `blocked`
- **Depends On:** Comma-separated task IDs, or `—`
- **Branch:** Full task branch name such as `task/1.1-login-page`
- **Assigned:** Agent or human identifier, or `—`

### Task Prompt Required Sections

Every task prompt must contain:

- **Objective** — The outcome the Builder must produce.
- **Context** — Background, references, and constraints.
- **In Scope** — What the Builder is expected to do.
- **Out of Scope** — What the Builder must not do.
- **Deliverables** — Concrete outputs or files that should exist at the end.
- **Branch** — Exact task branch name.
- **Verification** — Commands or checks required before handoff.

If scope changes after the task starts, the Coordinator adds a dated
`## Revision YYYY-MM-DD` section on the task branch.

### Review File Required Sections

- **Verdict line** — `**Verdict:** ACCEPTED` or `**Verdict:** REVISION_NEEDED`
- **Summary** — Whether the work meets the prompt
- **Issues** — Specific problems with file and line references
- **Required Changes** — Exact changes needed when revisions are required

### `current.md` Structure

```text
# Current State

## Last Updated
YYYY-MM-DD

## Active Phase
Phase N — Name

## Active Task
N.N — Description

## Queue Snapshot
- pending: task IDs or —
- ready: task IDs or —
- in-progress: task IDs or —
- needs-review: task IDs or —
- revision-needed: task IDs or —
- blocked: task IDs or —

## Repo State
- default branch: `main`
- coordination branch: `phase/NN-name`
- active task branch: `task/N.N-name`
- last processed builder session: `YYYY-MM-DD-HHMM-builder-N.N.md` or `none`

## What Changed Recently
- Brief list of recent events.

## Known Blockers
None or list.

## Next Recommended Action
What the next agent invocation should do.

## Next Agent Read Order
1. file path
2. file path
```

### `decisions.md` Format

Append-only table:

```text
| Date | Decision | Rationale | Impact |
```

### Session Note Requirements

- Coordinator session notes follow the template in `operating-model.md` and are
  written on the active phase branch.
- Builder session notes follow the template in `operating-model.md`, include an
  exact `Outcome` value of `READY_FOR_REVIEW` or `BLOCKED`, and are written on
  the active task branch.
- Session note filenames should include `YYYY-MM-DD-HHMM` so they can be
  ordered and processed reliably.
