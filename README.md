# Launchpad CLI

Launchpad is a Windows-first command-line tool for packaging solver inputs,
transferring them to a shared SLURM cluster, submitting runs, monitoring job
state, and downloading results. The repository now includes the Phase 1 package
scaffold, config and logging foundation, transport primitives, and the first
operator-facing cluster access commands.

## Status

The CLI boots, exposes the planned top-level commands, registers both
`launchpad` and `lp` entry points, and now supports:

- `launchpad config init`
- `launchpad config show`
- `launchpad ssh`
- `launchpad doctor`
- `launchpad submit`
- `launchpad status`

Core SSH, single-stream transfer, local compression primitives, the Phase 2
solver-adapter layer for Nastran discovery, the reusable remote-submit helpers,
the first functional `launchpad submit` command, and the reusable Phase 3
SLURM status/accounting query layer are present. `launchpad status` now
supports current-user and specific-job queries plus `--watch` polling. Logs,
download, and cleanup workflows remain future work.

## Quickstart

```powershell
uv sync
uv run launchpad --help
uv run lp --help
uv run launchpad config init --non-interactive --host headnode.example.com --username sergey --key-path C:\Users\sergey\.ssh\id_ed25519 --force
uv run launchpad config show
uv run launchpad submit --dry-run .
uv run launchpad doctor
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

## Operator Commands

Use `launchpad ssh` to open an interactive shell on the configured cluster head
node using the resolved SSH settings.

Use `launchpad doctor` to validate the local config, SSH key path, shared
cluster config access, SSH reachability, configured remote binaries, and the
remote writable root path when a cluster connection is available.

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

## Solver Layer

The Phase 2 solver layer now exposes a concrete Nastran adapter for deterministic
top-level `.dat` discovery, validation-friendly file metadata, run-command
construction, and shared-filesystem scratch environment setup.

The ANSYS adapter remains an explicit stub. It keeps the shared solver contract
stable but raises a clear `NotImplementedError` until the team defines the real
ANSYS workflow.

## Submit Primitives

Phase 2 now includes reusable remote submission helpers beneath the future
`launchpad submit` command:

- remote job-directory layout and setup helpers
- remote archive extraction using configured `tar` and `zstd` binaries
- SLURM submit-script generation with manifest freezing, shared-filesystem
  scratch handling, and remote-directory tracking via the SLURM job comment
- a remote `sbatch --parsable` wrapper that returns the submitted job ID

The `launchpad submit` command now orchestrates solver discovery, local
archive creation, upload, remote extraction, SLURM script generation, and
remote submission. `--dry-run` shows the resolved manifest, remote paths, and
generated submit script without making remote changes.

## Monitoring Primitives

Phase 3 now extends the SLURM core layer with:

- typed `squeue --json` status parsing
- typed `sacct --json` accounting parsing
- reusable remote query wrappers for scheduler metadata over SSH

The command-facing `launchpad status`, `launchpad logs`, and `launchpad cancel`
workflows still land in later tasks, but they now have a stable scheduler data
contract to build on.

## Status Command

`launchpad status` now provides the first monitoring workflow:

- no arguments: query the configured user's active jobs
- `launchpad status <JOB_ID>`: show per-task detail for a specific job
- `--all`: include recent accounting rows for completed or failed work
- `--watch --interval N`: refresh the Rich status view every `N` seconds
