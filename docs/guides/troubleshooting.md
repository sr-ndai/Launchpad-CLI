# Troubleshooting

Start with:

```powershell
launchpad doctor
```

That is the fastest way to separate a local setup problem from a remote cluster
problem.

## `launchpad config init` says a required value is missing

You are in non-interactive mode and did not provide all required SSH values.

Fix:

- supply `--host`, `--username`, and `--key-path`
- or run `launchpad config init` without `--non-interactive`

## `doctor` fails on config or SSH values

Launchpad needs at least:

- `ssh.host`
- `ssh.username`
- `ssh.key_path`

Check:

```powershell
launchpad config show
```

Then fix the user config or your `LAUNCHPAD_*` environment variables.

## `doctor` says the SSH key is missing

The configured key path does not point to a file on your machine.

Fix the path in `~/.launchpad/config.toml` or rerun:

```powershell
launchpad config init --force
```

## `doctor` says scheduler binaries are missing but manual SSH works

Launchpad checks `sbatch`, `squeue`, `sacct`, and `sstat` through the same
login-shell environment it uses for scheduler commands. If those commands work
in a manual SSH session but fail in Launchpad, the head node is probably
loading SLURM only during login-shell initialization.

Fixes:

- update the cluster's login-shell initialization so SLURM is on PATH
- or set `remote_binaries.sbatch`, `remote_binaries.squeue`, and
  `remote_binaries.sacct` / `remote_binaries.sstat` to absolute paths in config

Then rerun:

```powershell
launchpad doctor
```

## `status --all` warns that accounting is unavailable

That cluster can still run Launchpad jobs, but `sacct` is missing or SLURM
accounting is disabled.

What still works:

- `launchpad submit`
- `launchpad status` for active jobs
- live running-job metrics when `sstat` is available

What is limited:

- `launchpad status --all`
- completed-job history
- completed-job CPU, memory, and disk totals

Fixes:

- enable SLURM accounting on the cluster
- or configure `remote_binaries.sacct` to the correct absolute path if the
  binary exists but is not on the login-shell PATH

## `doctor` says `tar` or `zstd` is missing but manual SSH works

Launchpad still checks non-scheduler remote tools through its normal
non-interactive SSH exec environment. That PATH can differ from a manual login
shell.

Fixes:

- set `remote_binaries.tar` or `remote_binaries.zstd` to absolute paths
- or update the non-interactive SSH exec PATH on the cluster

Then rerun:

```powershell
launchpad doctor
```

## `doctor` says the remote workspace root is missing or not writable

Launchpad checks `cluster.workspace_root` when you set it. If that value is
unset, Launchpad falls back to `<cluster.shared_root>/<ssh.username>`.

Fixes:

- set `cluster.workspace_root` to the writable shared Launchpad directory,
  such as `/shared/launchpad`
- or create and grant access to the legacy fallback path

Then rerun:

```powershell
launchpad doctor
```
## `status`, `logs`, or `cancel` says a SLURM command was not found

Launchpad runs `squeue`, `sacct`, `sstat`, and `scancel` through the cluster
login shell. If those commands are missing there, operator commands fail even
when raw SSH connectivity works.

Fixes:

- update the head-node login-shell initialization so SLURM is loaded
- or set `remote_binaries.squeue`, `remote_binaries.sacct`,
  `remote_binaries.sstat`, and `remote_binaries.sbatch` to absolute paths
  where applicable

## `submit` says no supported solver inputs were found

Launchpad did not find a supported input file in the directory you submitted.

Check:

- you are in the correct folder
- the Nastran input file extension matches the configured value
- you are not trying to use the ANSYS workflow yet

## ANSYS does not work

That is expected right now. The ANSYS adapter is intentionally a stub and
submit support is not implemented yet.

## `status --watch` with `--json` fails

That combination is not supported. Watch mode is terminal-oriented.

Use either:

- `launchpad status --watch`
- `launchpad --json status <JOB_ID>`

## `logs --follow` with `--json` fails

That combination is not supported. Follow mode streams live terminal output.

Use either:

- `launchpad logs <JOB_ID> -f`
- `launchpad --json logs <JOB_ID>`

## `logs` asks for a task ref or opens a picker

Multi-task jobs need one task to be selected before Launchpad can read a
specific log file.

Use either:

- an explicit task ref such as `launchpad logs <JOB_ID> 001`
- a filename or path ref such as `launchpad logs <JOB_ID> wing.dat`
- the human TTY picker via `launchpad logs <JOB_ID>` or `launchpad logs <JOB_ID> -f`

If the job predates `launchpad-manifest.json`, only raw numeric task IDs are
available for selector fallback.

## `download` warns about local disk space

Launchpad checks free space before download.

Safer fixes:

- choose a different output location
- free space locally
- download only selected tasks with `--tasks`

If you really want to continue anyway, use `--force`.

## `launchpad ssh` fails on Windows before opening a shell

On Windows, Launchpad uses the local OpenSSH client for interactive shell
access instead of AsyncSSH stdio redirection.

Check:

- `ssh.exe` is installed
- `ssh.exe` is on PATH
- the resolved `ssh.host`, `ssh.username`, `ssh.key_path`, and optional
  `ssh.known_hosts_path` values are correct

If you are unsure about the config first, run:

```powershell
launchpad doctor
launchpad config show
```

## `ls` or `cleanup` cannot resolve a default remote path

Those commands use `cluster.workspace_root` when it is configured. Otherwise
they fall back to `<cluster.shared_root>/<ssh.username>`, which still requires
`ssh.username`.

Fix `cluster.workspace_root` or the username in your config, or pass an
explicit absolute remote path.
