# `launchpad config`

Use `config` to create and inspect Launchpad configuration.

## Commands

- `launchpad config init`
- `launchpad config show`
- `launchpad config show --docs`
- `launchpad config edit`
- `launchpad config validate`

## What Works Today

Implemented:

- `config init`
- `config show`
- `config show --docs`

Not implemented yet:

- `config edit`
- `config validate`

## Common Uses

Create a starter config:

```powershell
launchpad config init
```

Create a starter config without prompts:

```powershell
launchpad config init --non-interactive --host headnode.example.com --username sergey --key-path C:\Users\sergey\.ssh\id_ed25519
```

Show the resolved result:

```powershell
launchpad config show
launchpad --json config show
```

Show the live schema docs:

```powershell
launchpad config show --docs
```

## Important Options

`config init`:

- `--host`
- `--username`
- `--key-path`
- `--port`
- `--known-hosts-path`
- `--force`
- `--non-interactive`

`config show`:

- `--docs`

## Notes

- `config init` writes `~/.launchpad/config.toml`
- `config show` reflects all config layers together
- the exhaustive schema lives in `launchpad config show --docs`, not only in
  this page
