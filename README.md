# Launchpad CLI

Launchpad is a Windows-first command-line tool for sending solver jobs to a
shared SLURM cluster, checking their progress, reading logs, and pulling the
results back down when they finish.

This repository now documents Launchpad for two audiences:

- people who want the shortest path from "installed" to "first successful run"
- people who want to tune configuration, transfer behavior, and command usage

## What Works Today

Launchpad currently supports:

- SSH-based cluster access with layered configuration
- diagnostics with `launchpad doctor`
- job submission with `launchpad submit`
- job status with `launchpad status`
- log inspection with `launchpad logs`
- result download with `launchpad download`
- job cancellation with `launchpad cancel`
- remote listing with `launchpad ls`
- remote cleanup with `launchpad cleanup`

Current limits:

- Nastran is the only implemented solver workflow
- ANSYS submit support is intentionally not implemented yet
- `launchpad config edit` and `launchpad config validate` are scaffolded but
  not implemented yet

## Install

Recommended install:

```powershell
uv tool install git+https://github.com/sr-ndai/Launchpad-CLI.git
launchpad
```

If you prefer the short alias, `lp` works everywhere that `launchpad` works.

Launchpad now has three help surfaces:

- `launchpad` shows the human-facing welcome screen.
- `launchpad --help` shows the compact root command reference.
- `launchpad <command> --help` shows command-specific flags and examples.

Use `--no-color` or `NO_COLOR=1` when you want plain output.

Developer install from a source checkout:

```powershell
uv sync
uv run launchpad --help
uv run pytest
```

## Quickstart

If you already have cluster access and an SSH key, this is the shortest path:

```powershell
launchpad config init
launchpad doctor
launchpad submit --dry-run .
launchpad submit .
launchpad status <JOB_ID>
```

When the job finishes:

```powershell
launchpad download <JOB_ID> .\results
```

## Documentation

Start here:

- [Documentation Home](docs/README.md)
- [Getting Started](docs/guides/getting-started.md)
- [Submit Your First Job](docs/guides/first-job.md)
- [Common Tasks](docs/guides/common-tasks.md)
- [Troubleshooting](docs/guides/troubleshooting.md)

Reference:

- [Configuration Reference](docs/reference/configuration.md)
- [Command Reference](docs/reference/commands/README.md)

Technical and contributor docs:

- [Architecture](ARCHITECTURE.md)
- [Transfer Architecture Decision](docs/transfer-benchmark.md)

## A Few Important Notes

- Examples in these docs assume Windows PowerShell.
- The primary command spelling in the docs is `launchpad`; `lp` is just a
  shorter alias.
- The Launchpad wordmark only appears on the bare `launchpad` welcome screen.
  It is suppressed for `--json`, `--quiet`, `--no-color`, and non-TTY output.
- The code is the source of truth. Where older plan text and current behavior
  disagree, these docs follow the current CLI.
