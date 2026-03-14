# `launchpad status`

Use `status` to inspect current jobs or a specific job.

## Syntax

```text
launchpad status [OPTIONS] [JOB_ID]
```

## Common Uses

Show current jobs:

```powershell
launchpad status
```

Show one job:

```powershell
launchpad status 12345
```

Watch live updates:

```powershell
launchpad status --watch
```

Include recent completed jobs:

```powershell
launchpad status --all
```

## Important Options

- `--all`
- `--watch`
- `--interval`

## Behavior Notes

- with no `JOB_ID`, Launchpad shows the current user's jobs
- with a `JOB_ID`, Launchpad shows detail for that job
- `--watch` refreshes until you stop it
- root `--json` is supported for non-watch usage only
- `launchpad status --watch` does not support `--json`
