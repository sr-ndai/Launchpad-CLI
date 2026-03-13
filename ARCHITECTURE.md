# Launchpad Architecture

## Purpose

Launchpad is a Windows-first CLI for packaging solver inputs, transferring them
to a shared SLURM cluster, submitting jobs, monitoring execution, and
retrieving results. Phase 1 established the package boundaries and command
surface; Phase 2 begins filling in the submission pipeline around stable solver
contracts.

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
- `src/launchpad_cli/core/slurm.py` now builds submit scripts and wraps remote
  `sbatch` submission. Later tasks will extend it with status/accounting
  parsing.
- `src/launchpad_cli/core/remote_ops.py` and `local_ops.py` hold filesystem
  helpers that should stay outside command modules. `remote_ops.py` now covers
  remote job-directory setup, remote text writes, and archive extraction used by
  submit flows.

### Solver Layer

- `src/launchpad_cli/solvers/base.py` defines the solver adapter protocol,
  discovered-input metadata, and narrow submit override contract.
- `src/launchpad_cli/solvers/nastran.py` contains the first concrete solver:
  deterministic input discovery, command construction, and scratch environment
  setup for Nastran.
- `src/launchpad_cli/solvers/ansys.py` preserves the planned ANSYS adapter slot
  as a protocol-compliant stub with explicit runtime failure behavior.

### Tests

- `tests/test_cli.py` provides CLI smoke coverage for the root command.
- `tests/test_project_scaffold.py` verifies packaging entry points and the
  expected module skeleton.
- `tests/test_solver_adapters.py` covers solver discovery, command building,
  scratch environment setup, and the ANSYS stub behavior.
- `tests/test_remote_ops.py` and `tests/test_slurm.py` cover the reusable
  remote-submit primitives with fakes instead of a live cluster.
- `tests/conftest.py` adds the `src/` tree to `sys.path` so local test runs can
  import the package without extra setup.

## Execution Flow

The intended steady-state data flow is:

1. Click parses the user command and global flags in the root CLI group.
2. Command modules resolve configuration and hand work to `launchpad_cli.core`.
3. Core services call solver adapters for solver-specific behavior.
4. Display helpers render human-facing output while JSON output stays
   script-friendly.

The repository now implements the solver layer plus the reusable remote-submit
primitives beneath `launchpad submit`, while CLI orchestration and Rich-facing
presentation remain future work.

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
- No submit orchestration, remote SLURM integration, or result workflows are
  active yet.
- The ANSYS adapter remains intentionally unimplemented until the team defines
  the supported runtime contract.
