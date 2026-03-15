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

- Launchpad shows a spinner while listing candidate remote directories and
  another while measuring their sizes
- numbered cleanup candidates are shown for root scans; one final confirmation
  is required before deletion
- output uses restrained warning and success lines with aligned metadata
- with `JOB_IDS`, Launchpad resolves the remote job directory from scheduler
  metadata
- without `JOB_IDS`, Launchpad discovers cleanup candidates under
  `cluster.workspace_root` when set and otherwise under the legacy remote user
  root fallback
- cleanup only supports terminal jobs (finished or cancelled)
- root `--json` is supported
