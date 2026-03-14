# `launchpad doctor`

Use `doctor` when setup or connectivity is not behaving the way you expect.

## Syntax

```text
launchpad doctor
```

## What It Checks

- Python version
- config resolution
- SSH key presence
- shared cluster config visibility
- SSH connectivity
- required remote binaries
- remote writable path

Human-readable output groups those checks into `Local Setup` and
`Cluster Access`, then ends with the next useful command or fix.

## Common Uses

Run the human-readable version:

```powershell
launchpad doctor
```

Run the machine-readable version:

```powershell
launchpad --json doctor
```

## Behavior Notes

- a failing check exits non-zero
- if local SSH config is incomplete, the remote checks are skipped
- branding is reserved for the all-pass success path
- this is the first command to run on a new machine and the first command to
  run when something breaks
