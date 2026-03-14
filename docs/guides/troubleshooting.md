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

## `doctor` says remote binaries are missing but manual SSH works

Launchpad checks remote binaries through the same non-interactive SSH exec
environment it uses for submit, status, download, and other command execution.
That environment can have a different PATH than an interactive login shell.

Fixes:

- set `remote_binaries.*` to absolute paths in config
- or update the cluster's non-interactive shell startup so those tools are on
  PATH for SSH exec sessions

Then rerun:

```powershell
launchpad doctor
```

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

Those commands need `ssh.username` when you do not pass an absolute remote
path.

Fix the username in your config, or pass an explicit absolute remote path.
