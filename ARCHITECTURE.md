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
  groups. `submit.py` now orchestrates the functional Phase 2 Nastran submit
  path and dry-run preview, while `status.py` now provides the first Phase 3
  monitoring flow for current-user, specific-job, and watch-mode status
  queries. `logs.py` and `cancel.py` now cover the remaining Phase 3 operator
  workflows for remote log access and SLURM cancellation. `download.py` now
  owns the Phase 4 result-retrieval orchestration on top of the shared
  download primitives.
- `src/launchpad_cli/display.py` centralizes Rich console creation plus the
  submit-focused dry-run/confirmation formatting and the status overview/detail
  renderables used by watch mode.

### Core Layer

- `src/launchpad_cli/core/config.py` will hold the layered configuration models
  and file/env loading entry points.
- `src/launchpad_cli/core/logging.py` will configure structured application
  logging.
- `src/launchpad_cli/core/ssh.py`, `transfer.py`, and `compress.py` define the
  transport and archive contracts used by submit/download flows. `compress.py`
  now also exposes archive inspection, local checksum helpers, and remote
  archive creation for Phase 4 retrieval workflows.
- `src/launchpad_cli/core/slurm.py` now builds submit scripts, wraps remote
  `sbatch` submission, parses `squeue --json` / `sacct --json` payloads into
  typed records, and exposes reusable remote scheduler query wrappers for later
  monitoring commands.
- `src/launchpad_cli/core/remote_ops.py` and `local_ops.py` hold filesystem
  helpers that should stay outside command modules. `remote_ops.py` now covers
  remote job-directory setup, remote text writes, archive extraction, size
  queries, listings, checksums, and deletions. `local_ops.py` now handles
  download-destination resolution plus disk-space checks for Windows-first
  retrieval flows.

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
  remote-submit, download-groundwork, and scheduler-query primitives with fakes
  instead of a live cluster.
- `tests/test_compress.py` and `tests/test_local_ops.py` cover archive
  inspection, checksums, remote archive creation, and local download path/disk
  semantics.
- `tests/test_submit.py` covers the submit command’s dry-run preview and mocked
  execution wiring.
- `tests/test_status.py` covers the status command's overview/json/watch
  wiring plus the polling helper.
- `tests/test_logs.py` and `tests/test_cancel.py` cover the remote log and
  cancellation command wiring with fake remote effects.
- `tests/conftest.py` adds the `src/` tree to `sys.path` so local test runs can
  import the package without extra setup.

## Execution Flow

The intended steady-state data flow is:

1. Click parses the user command and global flags in the root CLI group.
2. Command modules resolve configuration and hand work to `launchpad_cli.core`.
3. Core services call solver adapters for solver-specific behavior.
4. Display helpers render human-facing output while JSON output stays
   script-friendly.

The repository now implements the solver layer, reusable remote-submit
primitives, the first functional `launchpad submit` orchestration path with
Rich dry-run and confirmation output, and the reusable SLURM status/accounting
query layer needed by the Phase 3 monitoring commands. `launchpad status`,
`launchpad logs`, and `launchpad cancel` now build on that layer with the full
Phase 3 operator command surface. Phase 4 now includes the reusable download
and remote-filesystem groundwork plus the command-level `launchpad download`
flow for job lookup, disk checks, transfer orchestration, verification, and
optional remote cleanup. Remote listing and cleanup command wiring are still
pending.

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

- Remote listing and cleanup command orchestration are not active yet.
- The ANSYS adapter remains intentionally unimplemented until the team defines
  the supported runtime contract.
