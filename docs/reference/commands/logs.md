# `launchpad logs`

Use `logs` to inspect SLURM logs or solver logs for a job.

## Syntax

```text
launchpad logs [OPTIONS] JOB_ID [TASK_REF]
```

## Common Uses

Show the last lines of the default log:

```powershell
launchpad logs 12345
```

Follow the selected task live. For multi-task jobs in a human TTY, Launchpad
opens an arrow-key picker if you omit `TASK_REF`:

```powershell
launchpad logs 12345 -f
```

Follow task `0` live explicitly:

```powershell
launchpad logs 12345 0 -f
```

Show the primary solver log instead of the SLURM stdout log:

```powershell
launchpad logs 12345 0 --solver-log
```

Show a non-primary solver log kind by alias:

```powershell
launchpad logs 12345 001 --log-kind telemetry
```

## Important Options

- `-f`, `--follow`
- `-n`, `--lines`
- `--solver-log`
- `--log-kind`
- `--err`

## Behavior Notes

- human-readable mode prints a minimal job/task/log header and path line, then
  shows raw log content with almost no wrapper chrome
- Launchpad resolves the scheduler metadata behind `logs` through the cluster
  login shell because some head nodes expose `squeue` and `sacct` only there
- `--follow` prints that header once and then streams the remote log until you
  interrupt it; follow mode uses retry-by-name semantics so a newly created log
  file can appear shortly after you start following
- `TASK_REF` is optional
- new manifest-backed jobs accept raw task IDs, aliases, exact filenames,
  exact relative paths, and exact input stems as task references
- when a human TTY targets a multi-task job without `TASK_REF`, Launchpad opens
  an interactive picker instead of failing immediately
- `--solver-log`, `--log-kind`, and `--err` are mutually exclusive
- `--solver-log` maps to the manifest's primary solver log kind `solver`
- legacy jobs without `launchpad-manifest.json` only support best-effort
  primary solver-log fallback; non-primary `--log-kind` values fail clearly
- root `--json` is supported for non-follow usage
- `launchpad logs --follow` does not support `--json`
