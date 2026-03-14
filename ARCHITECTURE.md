# Launchpad Architecture

This document is for contributors and reviewers. If you are trying to use the
tool, start with [README.md](README.md) or [docs/README.md](docs/README.md)
instead.

## Purpose

Launchpad is a Windows-first CLI for packaging solver inputs, transferring them
to a shared SLURM cluster, submitting jobs, monitoring execution, and
retrieving results.

The current product surface is organized around one normal workflow:

1. resolve configuration
2. submit work
3. inspect status and logs
4. download results
5. optionally clean up remote job directories

## Code Map

### CLI Layer

`src/launchpad_cli/cli/` contains the user-facing command modules:

- `__init__.py`: root Click group, global options, and command registration
- `config_cmd.py`: config initialization and inspection
- `doctor.py`: local and remote diagnostics
- `ssh_cmd.py`: interactive cluster shell
- `submit.py`: input discovery, packaging, transfer, script generation, submit
- `status.py`: SLURM status and accounting queries
- `logs.py`: SLURM and solver log access
- `download.py`: result selection, transfer, verification, and extraction
- `cancel.py`: SLURM cancellation
- `ls.py`: remote listing
- `cleanup.py`: remote job-directory removal

### Core Layer

`src/launchpad_cli/core/` contains reusable services kept out of the Click
callbacks:

- `config.py`: layered configuration models and resolution
- `logging.py`: application logging setup
- `ssh.py`: SSH session helpers
- `transfer.py`: upload and download primitives
- `compress.py`: archive creation, inspection, extraction, and checksums
- `remote_ops.py`: remote filesystem helpers
- `local_ops.py`: local filesystem and disk-space helpers
- `slurm.py`: submit-script generation plus `squeue` and `sacct` query helpers

### Solver Layer

`src/launchpad_cli/solvers/` isolates solver-specific behavior:

- `base.py`: shared solver protocol and types
- `nastran.py`: implemented Nastran adapter
- `ansys.py`: protocol-compliant stub with explicit runtime failure

### Display Layer

`src/launchpad_cli/display.py` centralizes Rich console and table rendering so
command modules do not hand-build terminal UI in multiple places.

## Execution Flow

Most commands follow the same pattern:

1. Click parses the root flags and subcommand arguments.
2. The command resolves the layered config from files, environment, and CLI
   overrides.
3. The command hands the actual work to `launchpad_cli.core`.
4. Solver-specific branches go through the adapter layer.
5. Rich renders human output; root `--json` produces machine-readable output
   where the command supports it.

## Current Extension Points

- add a new root command by adding a module in `src/launchpad_cli/cli/` and
  registering it in `cli/__init__.py`
- add a new solver by implementing the protocol in `solvers/` and wiring it
  into the submit path
- change transfer behavior in `core/transfer.py`
- change config behavior in `core/config.py`

## Current Limits

- ANSYS submit support is not implemented yet
- `launchpad config edit` and `launchpad config validate` are not implemented
- some command combinations are intentionally terminal-only, such as
  `status --watch` and `logs --follow`
