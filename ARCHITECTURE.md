# Launchpad Architecture

## Purpose

Launchpad is a Windows-first CLI for packaging solver inputs, transferring them
to a shared SLURM cluster, submitting jobs, monitoring execution, and
retrieving results. Phase 1 establishes the package boundaries and command
surface so later tasks can add real config, transport, compression, and
diagnostic behavior without reshaping the repository.

## Code Map

### CLI Layer

- `src/launchpad_cli/cli/__init__.py` defines the root Click group, global
  options, and command registration.
- `src/launchpad_cli/cli/*.py` modules own individual commands or command
  groups. In this scaffold they expose placeholder callbacks and help text only.
- `src/launchpad_cli/display.py` centralizes Rich console creation for later
  user-facing output work.

### Core Layer

- `src/launchpad_cli/core/config.py` will hold the layered configuration models
  and file/env loading entry points.
- `src/launchpad_cli/core/logging.py` will configure structured application
  logging.
- `src/launchpad_cli/core/ssh.py`, `transfer.py`, and `compress.py` define the
  transport and archive contracts used by submit/download flows.
- `src/launchpad_cli/core/slurm.py` will build scheduler commands and parse job
  status output.
- `src/launchpad_cli/core/remote_ops.py` and `local_ops.py` are reserved for
  filesystem helpers that should stay outside command modules.

### Solver Layer

- `src/launchpad_cli/solvers/base.py` defines the solver adapter protocol.
- `src/launchpad_cli/solvers/nastran.py` contains the initial implemented solver
  stub.
- `src/launchpad_cli/solvers/ansys.py` preserves the planned ANSYS adapter slot
  while remaining explicitly unimplemented for Phase 1.

### Tests

- `tests/test_cli.py` provides CLI smoke coverage for the root command.
- `tests/test_project_scaffold.py` verifies packaging entry points and the
  expected module skeleton.
- `tests/conftest.py` adds the `src/` tree to `sys.path` so local test runs can
  import the package without extra setup.

## Execution Flow

The intended steady-state data flow is:

1. Click parses the user command and global flags in the root CLI group.
2. Command modules resolve configuration and hand work to `launchpad_cli.core`.
3. Core services call solver adapters for solver-specific behavior.
4. Display helpers render human-facing output while JSON output stays
   script-friendly.

This task implements only step 1 and the package placeholders needed for later
steps.

## Common Changes

- Add a new command: create a module in `src/launchpad_cli/cli/`, register it
  in `src/launchpad_cli/cli/__init__.py`, and add CLI smoke coverage.
- Add a new solver: implement the `SolverAdapter` protocol in
  `src/launchpad_cli/solvers/` and extend the solver registry.
- Change transfer behavior: work in `src/launchpad_cli/core/transfer.py` and
  keep transport details out of CLI callbacks.
- Change configuration behavior: update `src/launchpad_cli/core/config.py` and
  cover precedence rules in tests.

## Current Limits

- Command implementations are placeholders only.
- No cluster connectivity, compression, SLURM integration, or config loading is
  active yet.
- The scaffold is intentionally narrow so later Phase 1 tasks can fill in real
  behavior incrementally.
