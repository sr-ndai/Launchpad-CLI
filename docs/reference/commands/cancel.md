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

- if you pass no task IDs, Launchpad cancels the whole job
- if you pass task IDs, they must be numeric
- root `--json` is supported
