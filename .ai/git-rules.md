# Git Rules

These rules are mandatory for all agents. Violating them corrupts the project
history and makes recovery harder.

## Branching Model

```text
main
└── phase/<NN>-<short-name>
    └── task/<NN.N>-<short-name>
```

- `main` is human-approved history only.
- The active **phase branch** is the shared coordination branch.
- The active **task branch** is the task-local working branch.

## Branch Lifecycle

### 1. Create a Phase Branch

The Coordinator creates a phase branch from `main` when a phase starts.

```bash
git switch main
git pull --ff-only origin main
git switch -c phase/<NN>-<short-name>
git push -u origin phase/<NN>-<short-name>
```

### 2. Create a Task Branch

The Coordinator or Builder creates a task branch from the active phase branch
when a task is assigned.

```bash
git switch phase/<NN>-<short-name>
git pull --ff-only origin phase/<NN>-<short-name>
git switch -c task/<NN.N>-<short-name>
git push -u origin task/<NN.N>-<short-name>
```

### 3. Review and Merge a Task Branch

After the Coordinator accepts the task:

```bash
git switch phase/<NN>-<short-name>
git pull --ff-only origin phase/<NN>-<short-name>
git merge --no-ff task/<NN.N>-<short-name>
git push origin phase/<NN>-<short-name>
git branch -d task/<NN.N>-<short-name>
git push origin --delete task/<NN.N>-<short-name>
```

### 4. Complete a Phase

When all phase tasks are `done`, the Coordinator opens a PR from the phase
branch to `main`. The human owner reviews and merges it.

## Naming Conventions

| Type | Pattern | Example |
|------|---------|---------|
| Phase branch | `phase/<NN>-<kebab-case>` | `phase/01-auth-system` |
| Task branch | `task/<phase>.<seq>-<kebab-case>` | `task/1.1-login-page` |

- Phase numbers are zero-padded: `01`, `02`, and so on.
- Keep branch names short and readable.

## Pre-Work Branch Verification

Before editing code or `.ai/` files, always run:

```bash
git branch --show-current
```

Match the result to the branch you intend to edit:

- shared coordination state -> phase branch
- task implementation, task prompt, review file, Builder session note ->
  task branch

If the branch is wrong, switch before continuing.

## Commit Messages

Use conventional commits:

```text
<type>(<scope>): <short description>
```

Types:

- `feat`
- `fix`
- `refactor`
- `test`
- `docs`
- `chore`

Scope guidance:

- task code changes -> task ID, for example `feat(1.2): add retry logic`
- queue or state changes -> descriptive scope, for example
  `chore(queue): move task 1.2 to needs-review`
- reviews or sessions -> `review`, `session`, or a similarly clear scope

## Commit Rules

- Keep commits atomic.
- No WIP commits.
- No unrelated changes.
- Keep shared phase-branch `.ai/` updates separate from task code when
  practical.
- Builder evidence on the task branch may be committed separately or in the
  final handoff commit, as long as the history stays clear.

## Sync Rules

- Builders do not rebase or merge task branches.
- If a task branch needs syncing with the phase branch, the Coordinator handles
  it.
- If sync work produces conflicts, stop and document the blocker or conflict in
  the relevant session note.

## Merge Rules

- Only the Coordinator merges task branches into phase branches.
- Only the human owner merges phase branches into `main`.
- Always use `--no-ff` for task-to-phase merges.
- Never force-push `main` or a phase branch.

## Conflict Resolution

- **Builder:** do not resolve merge or rebase conflicts. Record the blocker in a
  Builder session note and stop.
- **Coordinator:** if you resolve a merge conflict during review or merge,
  document it in the Coordinator session note.
