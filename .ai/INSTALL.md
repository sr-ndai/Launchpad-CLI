# Installation Guide

Use this repository to bootstrap `.ai/` inside a product repository.

## 1. Copy the Template

Create `.ai/` at the root of the target repository and copy the contents of
this repository into it.

Example shell install:

```bash
mkdir -p .ai
rsync -a --exclude '.git' /path/to/ai-orchestration/ .ai/
```

The installed layout should be:

```text
.ai/
  README.md
  INSTALL.md
  git-rules.md
  plan.md
  plans/
  reviews/
  roles/
  sessions/
  starter-prompts/
  state/
  system/
  tasks/
    prompts/
    queue.md
```

Do not copy the template repository's `.git` directory into the target repo.

## 2. Commit the Scaffold

On `main`, commit the `.ai/` scaffold before any planning or implementation
work starts.

This gives every future phase and task branch the same starting control plane.

## 3. Seed the Project Plan

Open `.ai/plan.md` and replace the placeholders with:

- the product vision
- any constraints or non-negotiables
- the initial phase outline
- open questions that could affect sequencing

Keep this file high-level. Detailed breakdown happens later in the queue and
task prompts.

## 4. Start the Coordinator

Use `.ai/starter-prompts/coordinator-start.md` as the first Coordinator prompt.

The Coordinator should:

1. read `.ai/state/current.md`
2. read `.ai/tasks/queue.md`
3. inspect `.ai/plan.md`
4. create the first phase branch
5. populate the queue and task prompts
6. update `.ai/state/current.md`

## 5. Start the Builder

Once a task is marked `in-progress`, use `.ai/starter-prompts/builder-start.md`
to start the Builder.

The Builder should:

1. orient from `.ai/state/current.md` and `.ai/tasks/queue.md`
2. switch to the assigned task branch
3. read the task prompt
4. implement and verify
5. write a Builder session note with `READY_FOR_REVIEW` or `BLOCKED`

The Builder does not update shared coordination files on the phase branch.

## Normal Operating Cadence

For a single active task, the normal rhythm is:

1. run the Coordinator
2. let the Coordinator assign or review work
3. run the Builder for the active task
4. run the Coordinator again to ingest the Builder handoff and continue

This keeps `queue.md` and `state/current.md` authoritative on the phase branch.

## Operating Assumption

This system is optimized for one active Builder task at a time.

The active phase branch is the shared coordination branch for:

- `.ai/tasks/queue.md`
- `.ai/state/current.md`
- `.ai/plan.md`
- `.ai/plans/`
- `.ai/state/decisions.md`
- Coordinator session notes

The active task branch is the task-local branch for:

- application code under construction
- `.ai/tasks/prompts/<task-id>.md`
- `.ai/reviews/<task-id>.md`
- Builder session notes

When a task is accepted, the task branch is merged back into the phase branch
with `--no-ff`.
