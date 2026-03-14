# `launchpad download`

Use `download` to collect results from a submitted job and copy them locally.

## Syntax

```text
launchpad download [OPTIONS] JOB_ID [LOCAL_DIR]
```

## Common Uses

Download into a specific folder:

```powershell
launchpad download 12345 .\results
```

Download only selected tasks:

```powershell
launchpad download 12345 --tasks 0,2
```

Include scratch directories:

```powershell
launchpad download 12345 --include-scratch
```

Download and remove the remote job directory after success:

```powershell
launchpad download 12345 --cleanup
```

## Important Options

- `-o`, `--output`
- `--cleanup`
- `--force`
- `--exclude`
- `--include-scratch`
- `--transfer-mode [auto|single-file|multi-file]`
- `--remote-compress [auto|always|never]`
- `--tasks`
- `--streams`
- `--compression-level`

## Behavior Notes

- use either `LOCAL_DIR` or `--output`, not both
- Launchpad checks local disk space before download
- root `--json` is supported
- `--remote-compress` is deprecated; prefer `--transfer-mode`
- `--tasks` accepts a comma-separated task list
