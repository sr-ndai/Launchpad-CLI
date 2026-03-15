# `launchpad ls`

Use `ls` to inspect remote files and directories without opening an SSH shell.

## Syntax

```text
launchpad ls [OPTIONS] [REMOTE_PATH]
```

## Common Uses

List your default remote root:

```powershell
launchpad ls
```

Show a long listing:

```powershell
launchpad ls -l
```

List an explicit remote path or glob:

```powershell
launchpad ls /shared/sergey/project
launchpad ls "results_*"
```

## Important Options

- `-l`, `--long`

## Behavior Notes

- Launchpad shows a spinner while fetching the remote directory listing
- output prints the requested path as a header, then the matched entries in a
  borderless table
- if you omit `REMOTE_PATH`, Launchpad uses `cluster.workspace_root` when set
  and otherwise falls back to `<shared_root>/<ssh.username>`
- relative paths are resolved beneath that default root
- glob patterns are supported
- root `--json` is supported
