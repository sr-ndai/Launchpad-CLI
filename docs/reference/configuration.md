# Configuration Reference

This page explains how Launchpad resolves settings and where to change them.
For the full live schema with defaults and descriptions, run:

```powershell
launchpad config show --docs
```

## Precedence

Launchpad resolves configuration in this order, highest priority first:

1. CLI flags
2. `LAUNCHPAD_*` environment variables
3. project-local `.launchpad.toml`
4. user config at `~/.launchpad/config.toml`
5. cluster config at `/shared/config/launchpad.toml`

Use the smallest override that solves your problem. Most users only need the
user config and occasional command flags.

## File Locations

- user config: `~/.launchpad/config.toml`
- user logs: `~/.launchpad/logs`
- project config: `.launchpad.toml` in the working directory
- shared cluster config: `/shared/config/launchpad.toml`

## Common Commands

```powershell
launchpad config init
launchpad config show
launchpad config show --docs
launchpad --json config show
```

Notes:

- `config init` now guides you through the required SSH values and ends with a
  config summary plus next steps
- `config show` prints the resolved result
- `config show --docs` prints the documented schema
- `config edit` and `config validate` are scaffolded but not implemented yet

## Environment Variables

Launchpad supports both short aliases and nested config keys.

Short aliases:

- `LAUNCHPAD_HOST`
- `LAUNCHPAD_USER`
- `LAUNCHPAD_KEY`
- `LAUNCHPAD_PORT`
- `LAUNCHPAD_SOLVER`
- `LAUNCHPAD_PARTITION`
- `LAUNCHPAD_STREAMS`
- `LAUNCHPAD_COMPRESSION`

Nested keys use double underscores:

```powershell
$env:LAUNCHPAD_SOLVERS__NASTRAN__DEFAULT_CPUS = "20"
$env:LAUNCHPAD_TRANSFER__VERIFY_CHECKSUMS = "false"
```

## Example User Config

```toml
[ssh]
host = "headnode.example.com"
username = "sergey"
key_path = "C:\\Users\\sergey\\.ssh\\id_ed25519"

[transfer]
parallel_streams = 8
compression_level = 3

[submit]
name_prefix = "wing"

[cluster]
default_partition = "simulation-r6i-8x"
```

## Key Settings To Know

### `ssh`

Controls how Launchpad connects to the cluster:

- `host`
- `port`
- `username`
- `key_path`
- `known_hosts_path`

Notes:

- `launchpad doctor` checks remote binaries and the writable shared root
  through Launchpad's non-interactive SSH exec environment, so PATH differences
  between interactive login shells and command exec sessions matter
- on Windows, `launchpad ssh` maps these same values onto the local OpenSSH
  client instead of using AsyncSSH stdio passthrough

### `transfer`

Controls packaging and transfer behavior:

- `parallel_streams`
- `chunk_size_mb`
- `compression_level`
- `compression_threads`
- `verify_checksums`
- `resume_enabled`

### `cluster`

Controls shared filesystem and scheduler defaults:

- `shared_root`
- `default_partition`
- `default_wall_time`
- `scratch_root`
- `logs_subdir`

### `submit`

Controls default submit behavior:

- `solver`
- `cpus`
- `partition`
- `name_prefix`

### `solvers`

Holds solver-specific defaults. Nastran is implemented. ANSYS settings exist in
the schema, but the submit workflow is not implemented yet.

## Project-Local Overrides

Use `.launchpad.toml` when one project needs different defaults than your
normal user config.

Example:

```toml
[submit]
solver = "nastran"

[cluster]
default_partition = "nightly"
```

That file only affects commands run from that project directory.
