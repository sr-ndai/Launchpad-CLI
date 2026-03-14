# `launchpad logs`

Use `logs` to inspect SLURM logs or solver logs for a job.

## Syntax

```text
launchpad logs [OPTIONS] JOB_ID [TASK_ID]
```

## Common Uses

Show the last lines of the default log:

```powershell
launchpad logs 12345
```

Follow task `0` live:

```powershell
launchpad logs 12345 0 -f
```

Show a solver log instead of the SLURM stdout log:

```powershell
launchpad logs 12345 0 --solver-log
```

## Important Options

- `-f`, `--follow`
- `-n`, `--lines`
- `--solver-log`
- `--err`

## Behavior Notes

- human-readable mode renders a summary panel, the selected tail output, and
  suggested follow-up commands
- `--follow` starts with a live-tail banner and then streams the remote log
  until you interrupt it
- `TASK_ID` is optional
- `--solver-log` and `--err` cannot be used together
- root `--json` is supported for non-follow usage
- `launchpad logs --follow` does not support `--json`
