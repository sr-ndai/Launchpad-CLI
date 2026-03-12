# System Overview

## What This Is

A file-based, stateless AI agent orchestration system for building software
products. Two agent roles, Coordinator and Builder, collaborate through
structured markdown files committed to the repository. There is no shared
memory, no database, and no dependency on chat history.

This template is installed into a product repo as `.ai/`.

## Design Goals

- Agents can spin up cold and orient from files alone.
- Git history is the permanent record of both product work and orchestration.
- File ownership is explicit.
- Token economy matters. Agents read the minimum files needed to act safely.
- The system is recoverable from repository state at any point.
- The default workflow should stay simple enough for one active Builder.

## Non-Goals

- No hidden memory between sessions.
- No automatic merge authority. Humans still gate merges to `main`.
- No automatic agent loop. Agents are invoked manually.
- No broad repo scanning by default.
- No requirement for parallel execution in v1.

## Roles

| Role | Authority | Forbidden |
|------|-----------|-----------|
| **Human Owner** | Final authority. Seeds the plan. Approves and merges PRs. Can pause, reorder, or override anything. Owns installation docs, role docs, system docs, git rules, and starter prompts. | — |
| **Coordinator** | Plans work, maintains the queue and current state, writes task prompts, reviews completed tasks, manages task branches, and opens PRs. | Must not write production application code. |
| **Builder** | Executes a single assigned task, writes code, runs verification, and records task-local evidence. | Must not choose priority, modify the shared plan, or edit shared coordination state on the phase branch. |

## Core Principles

1. **Files are the interface.** Plans, queue state, prompts, reviews, and
   session evidence live in committed files.
2. **Git is sacred.** Branch hygiene and correct merge targets are
   non-negotiable.
3. **Ownership is explicit.** Shared coordination files and task-local files
   have different owners and different authoritative branches.
4. **`state/current.md` is the routing artifact.** It tells the next agent
   where to look next. It is not a substitute for canonical files.
5. **Single active workstream by default.** One active Builder task keeps the
   system understandable and reduces drift.
6. **Recovery beats perfect automation.** If a summary goes stale, the system
   must still be recoverable from canonical files and git history.

## Branch Model

```text
main
└── phase/<NN>-<short-name>
    └── task/<NN.N>-<short-name>
```

### Branch Responsibilities

- **`main`** holds human-approved work only.
- **Active phase branch** is the shared coordination branch. It is the
  authoritative location for `plan.md`, `plans/`, `tasks/queue.md`,
  `state/current.md`, `state/decisions.md`, and Coordinator session notes.
- **Active task branch** is the task-local working branch. It is the
  authoritative location for the task's code changes, active task prompt,
  review file, and Builder session notes while the task is in progress.

When a task is accepted, the task branch is merged back into the phase branch
with `--no-ff`, bringing task-local evidence with it.

## Sources of Truth

| Kind | Meaning |
|------|---------|
| **Canonical** | The authoritative record for a decision or state transition. |
| **Summary** | A compressed view derived from canonical sources. Useful for orientation, but repair it if stale. |
| **Evidence** | A factual record of what happened in a session. |
| **Instruction** | Human-owned rules that tell agents how to behave. |

See `file-ownership.md` for the full mapping.

## High-Level Workflow

```text
Human installs `.ai/` and seeds plan.md on main
  -> Coordinator creates the first phase branch
    -> Coordinator creates queue rows and task prompts
      -> Builder works on the assigned task branch
        -> Builder writes a session note with READY_FOR_REVIEW or BLOCKED
          -> Coordinator records the queue transition on the phase branch
            -> Coordinator reviews the task branch
              -> revision-needed: Coordinator writes review on task branch
              -> accepted: Coordinator merges task branch into phase branch
                -> Coordinator opens PR from phase branch to main
                  -> Human reviews and merges
```
