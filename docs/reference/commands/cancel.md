# `launchpad cancel`

Use `cancel` to stop a whole SLURM job or selected array tasks.

## Syntax

```text
launchpad cancel [OPTIONS] JOB_ID [TASK_IDS]...
```

## Common Uses

Cancel a whole job:

```powershell
launchpad cancel 12345
```

Cancel selected tasks:

```powershell
launchpad cancel 12345 0 2
```

Skip the confirmation prompt:

```powershell
launchpad cancel 12345 --yes
```

## Important Options

- `--yes`

## Behavior Notes

- without `--yes`, Launchpad shows a cancellation preview before the final
  confirmation prompt
- human-readable mode finishes with a cancellation summary and next-step hints
- if you pass no task IDs, Launchpad cancels the whole job
- if you pass task IDs, they must be numeric
- root `--json` is supported
