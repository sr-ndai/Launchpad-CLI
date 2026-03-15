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
- Launchpad runs SLURM scheduler commands through the cluster login shell
  because some head nodes expose `squeue`, `sacct`, and `sstat` only through
  login-shell initialization
- running jobs use `sstat` for live CPU, memory, and disk I/O metrics when the
  cluster exposes it
- completed and historical jobs use `sacct` when accounting is available
- clusters without SLURM accounting are still supported; `status --all` and
  completed-job resource totals degrade to limited or `—` output instead of
  failing outright
- `--watch` refreshes until you stop it and keeps a live status header instead
  of redrawing extra branding
- root `--json` is supported for non-watch usage only
- `launchpad status --watch` does not support `--json`
- empty states now point you toward `--all` or `doctor` instead of stopping at
  "no jobs found"
