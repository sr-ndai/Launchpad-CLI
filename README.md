# Launchpad CLI

Launchpad is a Windows-first command-line tool for packaging solver inputs,
transferring them to a shared SLURM cluster, submitting runs, monitoring job
state, and downloading results. This repository currently contains the Phase 1
scaffold: package layout, command surface, documentation skeleton, and test
baseline.

## Status

The CLI boots, exposes the planned top-level commands, and registers both
`launchpad` and `lp` entry points. Functional implementations for config,
transfers, compression, SLURM interaction, and diagnostics are intentionally
deferred to later Phase 1 tasks.

## Quickstart

```powershell
uv sync
uv run launchpad --help
uv run lp --help
uv run pytest
```

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
