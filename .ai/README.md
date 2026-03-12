# AI Orchestration System Template

This repository is the source-of-truth template for the `.ai/` folder that
gets installed into a product repository.

After installation, this file lives at `.ai/README.md` and every path in the
docs is literal from the product repo root, for example `.ai/state/current.md`
or `.ai/tasks/queue.md`.

## What You Install

Copy the contents of this repository into `<product-repo>/.ai/` so the target
tree looks like this:

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

Files prefixed with `_` are templates or examples. They are scaffolding for the
human owner and should be ignored by agents unless explicitly referenced.

## Install

1. Create `.ai/` at the root of the product repository.
2. Copy every file and folder from this repository into `.ai/`.
3. Commit the scaffold on `main`.
4. Replace placeholders in `.ai/plan.md`.
5. Start the Coordinator with `.ai/starter-prompts/coordinator-start.md`.
6. After each Builder run, run the Coordinator again.

Full setup instructions live in `INSTALL.md`.

## Runtime Entry Points

- **Coordinator:** start with `.ai/state/current.md`, then `.ai/tasks/queue.md`,
  then `.ai/roles/coordinator.md`.
- **Builder:** start with `.ai/state/current.md`, `.ai/tasks/queue.md`, and the
  active task prompt on the task branch, then `.ai/roles/builder.md`.

## System Documentation

| Document | Purpose |
|----------|---------|
| `system/system-overview.md` | What this system is, branch model, roles, principles |
| `system/operating-model.md` | How the Coordinator and Builder behave at runtime |
| `system/file-ownership.md` | Ownership, authoritative branches, schemas, edit permissions |

## Core Rules

- **Files are the interface.** Never rely on chat history as memory.
- **Shared coordination state lives on the active phase branch.**
- **Task-local work lives on the active task branch.**
- **Git is sacred.** Verify your branch before editing anything.
- **Ownership is explicit.** Check `system/file-ownership.md` before editing.
- **`state/current.md` is the routing artifact.** If it conflicts with a
  canonical file, trust the canonical file and repair `current.md`.
