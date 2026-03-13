# Launchpad CLI

Launchpad is a Windows-first command-line tool for packaging solver inputs,
transferring them to a shared SLURM cluster, submitting runs, monitoring job
state, and downloading results. The repository now includes the Phase 1 package
scaffold plus the initial config and logging foundation used by later commands.

## Status

The CLI boots, exposes the planned top-level commands, registers both
`launchpad` and `lp` entry points, and now supports `launchpad config init` and
`launchpad config show`. Transfers, compression, SLURM interaction, and
diagnostics are still deferred to later Phase 1 tasks.

## Quickstart

```powershell
uv sync
uv run launchpad --help
uv run lp --help
uv run launchpad config init --non-interactive --host headnode.example.com --username sergey --key-path C:\Users\sergey\.ssh\id_ed25519 --force
uv run launchpad config show
uv run pytest
```

## Configuration Layers

Launchpad resolves configuration in this order, highest priority first:

1. CLI flag overrides
2. `LAUNCHPAD_*` environment variables
3. Project-local `.launchpad.toml`
4. User config at `~/.launchpad/config.toml`
5. Cluster config at `/shared/config/launchpad.toml`

Use `launchpad config init` to create the user config file and `launchpad config show`
to inspect the resolved result. `launchpad config show --docs` prints the
annotated schema for all currently supported settings.

## Planned Commands

- `launchpad submit`
- `launchpad status`
- `launchpad logs`
- `launchpad download`
- `launchpad cancel`
- `launchpad ls`
- `launchpad config`
- `launchpad ssh`
- `launchpad cleanup`
- `launchpad doctor`

## Development Workflow

- Python 3.12+
- `uv` for environment and dependency management
- `pytest` for test execution
- `ruff` for future linting and formatting work

## Repository Layout

```text
src/launchpad_cli/
  cli/        Root Click application and command modules
  core/       Config, logging, SSH, transfer, compression, and SLURM services
  solvers/    Solver adapters and shared protocol definitions
tests/        CLI smoke tests and scaffold verification
```

See `ARCHITECTURE.md` for the module map and extension guidance.
