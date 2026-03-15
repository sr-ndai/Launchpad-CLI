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
- scheduler binary checks for `sbatch`, `squeue`, and `sacct` run through the
  same login-shell environment Launchpad uses for scheduler commands
- non-scheduler remote checks such as `tar`, `zstd`, and the writable-root
  probe still run through Launchpad's normal non-interactive SSH exec path
- the writable-root probe checks `cluster.workspace_root` when configured and
  otherwise falls back to `<cluster.shared_root>/<ssh.username>`
- if scheduler binaries fail, Launchpad points you toward head-node
  login-shell initialization or `remote_binaries.sbatch` /
  `remote_binaries.squeue` / `remote_binaries.sacct` absolute paths
- if non-scheduler binaries fail, Launchpad points you toward `remote_binaries.*`
  absolute paths or fixing the PATH seen by non-interactive SSH exec sessions
- branding is reserved for the all-pass success path
- this is the first command to run on a new machine and the first command to
  run when something breaks
