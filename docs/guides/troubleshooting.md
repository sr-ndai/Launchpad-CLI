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

## `download` warns about local disk space

Launchpad checks free space before download.

Safer fixes:

- choose a different output location
- free space locally
- download only selected tasks with `--tasks`

If you really want to continue anyway, use `--force`.

## `ls` or `cleanup` cannot resolve a default remote path

Those commands need `ssh.username` when you do not pass an absolute remote
path.

Fix the username in your config, or pass an explicit absolute remote path.
