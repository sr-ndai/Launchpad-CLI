# `launchpad ssh`

Use `ssh` to open an interactive shell on the configured cluster head node.

## Syntax

```text
launchpad ssh
```

## Common Uses

Open a shell:

```powershell
launchpad ssh
```

## Behavior Notes

- this command requires an interactive terminal
- it uses the same resolved SSH settings as the other Launchpad commands
- on Windows, Launchpad shells out through the local OpenSSH client instead of
  AsyncSSH stdio redirection
- the Windows path maps `host`, `port`, `username`, `key_path`, and optional
  `known_hosts_path` onto the local `ssh` command
- if `ssh` is not installed or not on PATH on Windows, the command fails
  clearly before opening a session
- root `--json` does not apply here; this is an interactive command
- use `launchpad doctor` first if you are not sure your SSH settings are valid
