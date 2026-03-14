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
- root `--json` does not apply here; this is an interactive command
- use `launchpad doctor` first if you are not sure your SSH settings are valid
