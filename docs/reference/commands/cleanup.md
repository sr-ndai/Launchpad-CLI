# `launchpad cleanup`

Use `cleanup` to delete remote job directories after you have collected the
results you need.

## Syntax

```text
launchpad cleanup [OPTIONS] [JOB_IDS]...
```

## Common Uses

Clean up one finished job:

```powershell
launchpad cleanup 12345
```

Clean up old job directories:

```powershell
launchpad cleanup --older-than 30d
```

Skip confirmations:

```powershell
launchpad cleanup --older-than 30d --yes
```

## Important Options

- `--older-than`
- `--yes`

## Behavior Notes

- with `JOB_IDS`, Launchpad resolves the remote job directory from scheduler
  metadata
- without `JOB_IDS`, Launchpad discovers cleanup candidates under your remote
  user root
- cleanup only supports terminal jobs
- root `--json` is supported
