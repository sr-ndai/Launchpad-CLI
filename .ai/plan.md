# Launchpad: Software Development Plan

## 1. Project Overview

**Launchpad** (`launchpad-cli`) is a trusted submission and retrieval layer for solver jobs on a shared SLURM cluster. It replaces the current manual workflow of WinSCP + SSH + hand-written bash scripts with a single CLI that engineers run from their local Windows terminal: compress → upload → submit → monitor → download.

**Naming convention:**

- **Package name:** `launchpad-cli` (what you install)
- **CLI commands:** `launchpad` (full) and `lp` (short alias) — both are registered as entry points and are fully interchangeable
- **Python import path:** `launchpad_cli.*`
- **Repository:** `gitlab.example.com/team/launchpad-cli`
- **Config directory:** `~/.launchpad/`
- **Cluster shared config:** `/shared/config/launchpad.toml` (on mounted FSx, read as a local file)

### Design Principles

This CLI follows the [Command Line Interface Guidelines](https://clig.dev/) as a design reference. Key principles:

- **Zero-friction by default, full control on demand.** `launchpad submit` with no arguments must work. The least technical team member should be able to navigate to their input folder, type `lp submit`, and have a job running on the cluster. Every option has a sensible default. Power users get granular control over solver settings, compression levels, transfer parallelism, SLURM parameters, and more — but none of it is required.
- **SLURM is authoritative.** No durable job state lives locally. SLURM owns job truth via `squeue` and `sacct`. Local cache (cluster config) and logs (`~/.launchpad/logs/`) are advisory — they improve UX but are never the source of truth. If your machine reboots mid-run, nothing is lost — you just call `lp status` when you're back.
- **Convention over configuration.** Sensible defaults live in a shared cluster config file on the mounted FSx drive. Engineers override only what they need, either via local config or CLI flags.
- **Human-first, machine-friendly.** Primary output is human-readable with color and formatting. `--json` provides structured output for scripting. `--quiet` suppresses non-essential output. The CLI detects TTY vs pipe and adapts automatically.
- **Composable.** Commands return proper exit codes, write primary output to `stdout`, messaging/progress to `stderr`, and support `--json` for piping to `jq` or other tools. Each command does one thing well.
- **Conversational.** When something goes wrong, the CLI explains what happened and suggests what to do next. After a successful submit, it tells you the next command to run. After an error, it tells you how to fix it.
- **Solver-aware, not solver-specific.** The core engine handles compression, transfer, SLURM interaction, and folder structure. Solver-specific logic (input file extensions, output file extensions, executable paths, SLURM resource templates) is encapsulated in solver adapters. V1 ships with Nastran fully implemented. ANSYS ships as a Protocol-compliant stub — the adapter skeleton exists (so the abstraction is proven) but is not functionally implemented until an ANSYS user on the team defines the workflow.
- **Reliable transfers first, fast transfers second.** V1 uses single-stream SFTP with resume support, integrity verification, and great progress UX. Parallel multi-stream transfer is a Phase 5 optimization that will be benchmarked against alternatives before committing to a design. Engineers will forgive a slower transfer. They will not forgive a corrupted archive.
- **Beautiful terminal UI.** The CLI should be visually polished and colorful — progress bars, status tables, clear color-coded states, styled headers, and helpful formatting. Even engineers who don't care about CLIs should find it pleasant to use. Use Rich extensively for all output. Respect `NO_COLOR` and `--no-color` for environments that don't support color.
- **Windows-first.** The entire team is on Windows. All path handling, terminal output, and installation instructions assume Windows. Cross-platform correctness is maintained but not the priority.
- **Documentation is a first-class deliverable.** Every module, function, and CLI command must have clear, concise documentation. The README must cover installation, quickstart, full command reference, and configuration. Docstrings follow a succinct style (one-liner summary + args if non-obvious). Documentation is maintained alongside code — not as an afterthought. This project will be developed and maintained with AI coding agents (Coordinator/Builder loop), so code clarity and documentation quality directly affect development velocity.

---

## 2. Requirements Summary

| Dimension            | Decision                                                  |
|----------------------|-----------------------------------------------------------|
| Runtime behavior     | Stateless commands, no daemon                             |
| Target audience      | 3–10 structural engineers (not Python experts)            |
| Solvers              | Nastran (fully implemented), ANSYS (stub/placeholder for V1) |
| Transfer size        | 10+ GB compressed (single-stream SFTP with resume in V1, parallel as Phase 5 optimization) |
| Compression          | zstd (already team standard)                              |
| SSH access           | Direct to head node, key-based auth                       |
| Cluster filesystem   | FSx for Lustre (mounted at `/shared`)                     |
| Job scheduler        | SLURM (array jobs for multi-file submits)                 |
| Job completion       | SLURM status only (no output file parsing)                |
| Local OS             | Windows (all team members)                                |
| Python               | 3.12+                                                     |
| Package manager      | `uv` (development), `pip`/`uv tool` (team installation)   |
| Distribution         | `pip install` / `uv tool install` from GitLab repo        |

---

## 3. CLI Command Surface

The CLI is organized as a Click group with subcommands. The root command is `launchpad` with a short alias `lp`. All examples below use `launchpad` but `lp` is interchangeable everywhere.

### 3.0 Global Behavior (clig.dev conformance)

**Global flags available on all commands:**

| Flag | Description |
|------|-------------|
| `--help` / `-h` | Show help text for the command. Appending `-h` to any command always shows help. |
| `--version` | Print version and exit. |
| `--quiet` / `-q` | Suppress non-essential output (progress bars, informational messages). Errors still go to stderr. |
| `--no-color` | Disable all color and formatting. Also triggered by `NO_COLOR` env var or non-TTY stdout. |
| `--json` | Output structured JSON to stdout (where applicable). Disables human formatting. |
| `--verbose` / `-v` | Increase output verbosity (SSH debug info, transfer details). |

**Exit codes:**

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | General error (bad input, validation failure, remote command failed) |
| `2` | Connection error (SSH connection refused, timeout, auth failure) |
| `3` | Transfer error (upload/download failed, checksum mismatch) |
| `4` | SLURM error (submission rejected, invalid partition, quota exceeded) |
| `130` | Interrupted by Ctrl-C (SIGINT) |

**Output streams (per clig.dev):**

- **stdout:** Primary command output (job IDs, status tables, file listings, JSON output). This is what gets piped.
- **stderr:** Progress bars, spinners, informational messages, warnings, errors. This is what the human sees when piping stdout elsewhere.

**Signal handling:**

- `Ctrl-C` (SIGINT): Immediately prints a message and begins clean shutdown. If pressed during a transfer, the partial file is preserved for resume. If pressed during a long cleanup, a second `Ctrl-C` skips cleanup and exits.

**Typo suggestions:**

If the user types an invalid subcommand (e.g., `lp stauts`), the CLI suggests the closest match: `Did you mean 'status'?`. Note: Click does not provide this natively. This requires a custom implementation using `difflib.get_close_matches` in the Click group's `resolve_command` override. This is a nice-to-have for Phase 5 polish, not a launch blocker.

### 3.1 `launchpad submit`

The primary command. Orchestrates the full submission pipeline from the local working directory.

```
launchpad submit [OPTIONS] [INPUT_DIR]
```

**The zero-argument case must work.** An engineer navigates to a folder with `.dat` files, types `launchpad submit`, and the job is running on the cluster. The solver is auto-detected from input file extensions, the name is auto-generated, and all SLURM parameters come from the shared cluster config. This is the golden path.

**What it does, in order:**

1. Discovers input files in `INPUT_DIR` (defaults to `.`) based on solver type (auto-detected or specified).
2. Validates inputs (file count, naming, extensions).
3. Compresses inputs into a `.tar.zst` archive.
4. Creates the remote job directory on FSx: `/shared/<user>/<run_name>/`.
5. Uploads the archive via parallel SFTP.
6. Decompresses on the remote side.
7. Generates the SLURM submit script from solver template + user overrides.
8. Submits via `sbatch` (executed over SSH).
9. Prints a rich summary: job ID, run name, directory paths, and monitoring commands.

**Auto-detection and naming:**

- **Solver auto-detection:** If `--solver` is not specified, the CLI scans `INPUT_DIR` for known input extensions. If it finds `.dat` files and no ANSYS-specific files, it defaults to Nastran. If ambiguous, it prompts the user (Rich selection prompt, not a crash).
- **Run name generation:** Defaults to a human-readable name combining solver, date, and short random suffix: `nastran-20260311-1422-a7f3`. This is interpretable in `squeue` output, log directories, and shared folders without needing to look up what `run-a7f3b2c1` was. The `--name` flag overrides this entirely for engineers who want fully custom names.

**Key options (all optional):**

| Flag | Default | Description |
|------|---------|-------------|
| `--solver` / `-s` | Auto-detect from file extensions | Solver type (`nastran`, `ansys`) |
| `--name` / `-n` | `<solver>-<YYYYMMDD>-<HHMM>-<4hex>` | Run name / SLURM job name |
| `--cpus` / `-c` | From cluster config | CPUs per task |
| `--max-concurrent` / `-m` | Number of input files | Max simultaneous array tasks |
| `--partition` / `-p` | From cluster config | SLURM partition |
| `--time` | `99:00:00` | Wall time limit |
| `--begin` | Immediate | Deferred start time (SLURM format) |
| `--memory` | From solver defaults | Solver memory allocation |
| `--compression-level` | `3` | zstd compression level (1–19) |
| `--streams` | `1` (Phase 5: configurable for parallel transfer) | Number of SFTP streams |
| `--dry-run` | `False` | Show full manifest preview without executing: discovered inputs, extra files, resolved solver, remote directory, SLURM settings, and generated submit script |
| `--no-compress` | `False` | Skip compression (if files are already compressed) |
| `--extra-files` | `[]` | Additional files to include (e.g., INCLUDE references, material libraries) |
| `--include-all` | `False` | Package the entire `INPUT_DIR` directory, not just discovered solver input files |

**File discovery and INCLUDE dependencies (V1 policy):**

V1 discovers solver input files by extension only (e.g., `.dat` for Nastran). It does **not** parse Nastran INCLUDE statements or resolve dependency trees. If a `.dat` file references other files via INCLUDE, the engineer must either: (a) use `--extra-files` to specify them, (b) use `--include-all` to package the entire directory, or (c) keep referenced files alongside the inputs. This is an explicit simplification — automatic INCLUDE resolution is tracked as a future enhancement. The `--dry-run` manifest preview shows exactly which files will be packaged, making it easy to verify nothing is missing before submitting.

**Example usage:**

```bash
# Simplest possible — just works
cd C:\Projects\tank_analysis\model_v3
lp submit

# Power user: named run with custom resources
launchpad submit --name tank_v3 --cpus 16 --compression-level 6

# ANSYS with deferred start (requires ANSYS adapter implementation — stub in V1)
lp submit -s ansys --begin "2025-07-01T22:00:00"

# Dry run to verify before submitting
lp submit --dry-run
```

### 3.2 `launchpad status`

Query SLURM for job status. Wraps `squeue` and `sacct` with better formatting.

```
launchpad status [OPTIONS] [JOB_ID]
```

**Behavior:**

- With no arguments: shows all of the current user's active/recent jobs.
- With a job ID: shows detailed status for that specific job (including array task breakdown).
- Includes: job state, node assignment, elapsed time. CPU/memory utilization shown when available (depends on cluster accounting configuration — `sstat` for running jobs, `sacct` for completed). If accounting data is unavailable, columns are omitted rather than showing misleading blanks.

**Key options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--all` / `-a` | `False` | Show completed/failed jobs too (via `sacct`) |
| `--watch` / `-w` | `False` | Refresh every N seconds (like `watch squeue`) |
| `--interval` | `30` | Refresh interval in seconds (with `--watch`) |
| `--json` | `False` | Output as JSON (for scripting) |

**Example output:**

```
Job: 12345 (nastran-20260311-1422-a7f3)  |  Array: 0-11  |  Partition: simulation-r6i-8x

 Task  State      Node           Elapsed    CPU%   Mem (GB)
 ────  ─────      ────           ───────    ────   ────────
    0  RUNNING    compute-dy-1   02:14:33    98%    187/236
    1  RUNNING    compute-dy-2   02:14:33    95%    203/236
    2  COMPLETED  compute-dy-3   01:45:12    97%    178/236
    3  PENDING    —              —           —      —
   ...

Summary: 2 running, 1 completed, 9 pending
```

### 3.3 `launchpad logs`

Stream or view remote log files for a running/completed job.

```
launchpad logs [OPTIONS] <JOB_ID> [TASK_ID]
```

**Behavior:**

- Tails the SLURM log file (`logs/<run_name>_<jobid>_<taskid>.log`) over SSH.
- With `--solver-log`: tails the solver-specific output file instead (e.g., `.f06` for Nastran).
- With `--err`: tails the SLURM `.err` file.

**Key options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--follow` / `-f` | `False` | Continuous tail (like `tail -f`) |
| `--lines` / `-n` | `50` | Number of lines to show |
| `--solver-log` | `False` | View solver output file instead of SLURM log |
| `--err` | `False` | View stderr log |

**Example:**

```bash
# Tail the SLURM log for task 0 of job 12345
lp logs 12345 0 -f

# View last 100 lines of the .f06 file for task 2
lp logs 12345 2 --solver-log -n 100
```

### 3.4 `launchpad download`

Compress and download results from a completed job.

```
launchpad download [OPTIONS] <JOB_ID> [LOCAL_DIR]
```

**What it does, in order:**

1. Queries SLURM for the job's working directory and completion status.
2. Warns if any tasks are still running (option to download partial results).
3. Checks remote result sizes via `du`.
4. Checks local disk space availability. Aborts if insufficient (with override flag).
5. Compresses results on the remote side into `.tar.zst`.
6. Downloads via parallel SFTP to `LOCAL_DIR` (defaults to `./results_<run_name>/`).
7. Decompresses locally.
8. Verifies integrity (file count, checksum comparison).
9. Optionally cleans up the remote directory (`--cleanup`).

**Key options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--output` / `-o` | `./results_<run_name>/` | Local destination |
| `--cleanup` | `False` | Delete remote directory after successful download |
| `--force` | `False` | Download even if local space is tight |
| `--exclude` | `[]` | Glob patterns to exclude from download |
| `--include-scratch` | `False` | Include scratch files (normally excluded) |
| `--remote-compress` | `auto` | Remote compression policy: `auto` (compress if `tar`+`zstd` available on head node), `always` (fail if unavailable), `never` (raw transfer). Head node CPU impact is a consideration — `never` avoids head node load at cost of transfer speed. |
| `--tasks` | All | Download specific task results only (e.g., `0,1,5`) |
| `--streams` | `1` (Phase 5: configurable for parallel transfer) | Number of SFTP streams |
| `--compression-level` | `3` | zstd compression level for remote compression |

**Pre-download output:**

```
Job 12345 (tank_v3): 12/12 tasks COMPLETED

Remote results: 47.3 GB (12 task directories)
Compressed estimate: ~11.8 GB (zstd)
Local free space: 234.1 GB (C:\Projects\tank_analysis\results_tank_v3)

Proceed with download? [Y/n]
```

### 3.5 `launchpad cancel`

Cancel running or pending jobs.

```
launchpad cancel <JOB_ID> [TASK_IDS...]
```

- With just a job ID: cancels the entire array job.
- With task IDs: cancels specific array tasks only.
- Always prompts for confirmation unless `--yes` is passed.

### 3.6 `launchpad ls`

List files and directories on the remote cluster.

```
launchpad ls [OPTIONS] [REMOTE_PATH]
```

- Defaults to the user's job directory on `/shared`.
- Supports `--long` for detailed listing (sizes, dates).
- Supports glob patterns.

### 3.7 `launchpad config`

View and manage configuration.

```
launchpad config show          # Print resolved config (all layers merged)
launchpad config edit          # Open local config in editor
launchpad config init          # Create a default local config file
launchpad config validate      # Validate all config files
```

### 3.8 `launchpad ssh`

Drop into an interactive SSH session on the head node. Convenience wrapper so engineers don't need a separate terminal/PuTTY.

```
launchpad ssh
```

### 3.9 `launchpad cleanup`

Remove remote job directories for completed jobs.

```
launchpad cleanup [OPTIONS] [JOB_IDS...]
```

- With no arguments: lists all directories in the user's space with sizes, asks which to delete.
- With job IDs: removes those specific job directories.
- `--older-than 30d`: remove directories older than a duration.

### 3.10 `launchpad doctor`

Diagnostics command. Checks everything needed for Launchpad to work correctly. This is the first tool to run when something goes wrong, and the first thing to run on a fresh machine after installation.

```
launchpad doctor
```

**What it checks, in order:**

1. Python version meets minimum (3.12+).
2. Config resolution: which config files were found, merged values for key settings.
3. SSH key file exists at configured path and has correct permissions.
4. SSH connection to head node succeeds (host reachable, auth works).
5. Remote binaries exist and are executable: `sbatch`, `squeue`, `sacct`, `tar`, `zstd`.
6. Shared config file is readable at `/shared/config/launchpad.toml`.
7. User's remote root directory exists and is writable (`/shared/<user>/`).
8. Solver executables exist at configured paths (e.g., Nastran binary).
9. Basic transfer test: upload a small test file, verify, delete.

**Output:** Color-coded pass/fail for each check with actionable fix suggestions for failures.

```
launchpad doctor

  ✓ Python 3.12.4
  ✓ Config loaded (cluster + user)
  ✓ SSH key found: C:\Users\sergey\.ssh\id_ed25519
  ✓ SSH connection to 10.0.1.50
  ✓ Remote binaries: sbatch squeue sacct tar zstd
  ✓ Shared config: /shared/config/launchpad.toml
  ✓ Remote root writable: /shared/sergey/
  ✓ Nastran binary: /shared/siemens/nastran2312/bin/nastran
  ✓ Transfer test: 1.2 MB/s

  All checks passed.
```

---

## 4. Architecture

### 4.1 Package Structure

```
launchpad-cli/
├── pyproject.toml
├── README.md
├── tests/
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_compress.py
│   ├── test_transfer.py
│   ├── test_slurm.py
│   ├── test_submit.py
│   └── test_solvers/
│       ├── test_nastran.py
│       └── test_ansys.py            # Tests that stub raises NotImplementedError
├── src/
│   └── launchpad_cli/
│       ├── __init__.py
│       ├── cli/
│       │   ├── __init__.py          # Click group definition (rich-click integration)
│       │   ├── submit.py            # launchpad submit
│       │   ├── status.py            # launchpad status
│       │   ├── logs.py              # launchpad logs
│       │   ├── download.py          # launchpad download
│       │   ├── cancel.py            # launchpad cancel
│       │   ├── ls.py                # launchpad ls
│       │   ├── config_cmd.py        # launchpad config
│       │   ├── ssh_cmd.py           # launchpad ssh
│       │   ├── cleanup.py           # launchpad cleanup
│       │   └── doctor.py            # launchpad doctor (diagnostics)
│       ├── core/
│       │   ├── __init__.py
│       │   ├── config.py            # Pydantic config models, layered loading
│       │   ├── logging.py           # loguru setup: console + file sinks, rotation
│       │   ├── ssh.py               # asyncssh connection management
│       │   ├── transfer.py          # SFTP upload/download engine (single-stream V1, parallel Phase 5)
│       │   ├── compress.py          # zstd compress/decompress (local + remote)
│       │   ├── slurm.py             # SLURM command builders + output parsers
│       │   ├── remote_ops.py        # Remote filesystem operations (mkdir, du, rm, etc.)
│       │   └── local_ops.py         # Local filesystem operations (disk space, paths)
│       ├── solvers/
│       │   ├── __init__.py
│       │   ├── base.py              # SolverAdapter Protocol
│       │   ├── nastran.py           # Nastran adapter (fully implemented)
│       │   └── ansys.py             # ANSYS adapter (stub — Protocol-compliant skeleton, not implemented in V1)
│       └── display.py               # Rich console output formatting
```

### 4.2 Module Responsibilities

**`core/config.py`** — The configuration system. Five layers merge bottom-up, following clig.dev's recommended precedence. **All config loading is a local filesystem operation** — no SSH or network I/O. The cluster config lives on the mounted FSx drive (`/shared/`), which is accessible as a local path. This means `lp --help`, `lp config show`, and validation never depend on cluster reachability.

```
Priority (highest to lowest):
  1. CLI flags                                  (per-invocation)
  2. Environment variables (LAUNCHPAD_*)         (per-session / per-machine)
  3. Project-local .launchpad.toml               (per-project, in CWD)
  4. User config  ~/.launchpad/config.toml       (per-user, personal defaults)
  5. Cluster config /shared/config/launchpad.toml  (team-wide, on mounted FSx, optional — gracefully skipped if not mounted)
```

**Environment variable convention:** All environment variables are prefixed with `LAUNCHPAD_` and use uppercase with underscores. Nested config uses double underscores as separators.

| Environment Variable | Config Equivalent | Description |
|---------------------|-------------------|-------------|
| `LAUNCHPAD_HOST` | `ssh.host` | Cluster head node IP/hostname |
| `LAUNCHPAD_USER` | `ssh.username` | SSH username |
| `LAUNCHPAD_KEY` | `ssh.key_path` | Path to SSH private key |
| `LAUNCHPAD_PORT` | `ssh.port` | SSH port (default: 22) |
| `LAUNCHPAD_SOLVER` | `submit.solver` | Default solver |
| `LAUNCHPAD_PARTITION` | `cluster.default_partition` | Default SLURM partition |
| `LAUNCHPAD_STREAMS` | `transfer.parallel_streams` | Parallel SFTP streams |
| `LAUNCHPAD_COMPRESSION` | `transfer.compression_level` | zstd compression level |
| `NO_COLOR` | — | Standard env var: disables color output |

This supports the existing team workflow where SSH credentials are set as environment variables, while also allowing engineers to "lock in" their settings via `~/.launchpad/config.toml` for convenience. The user config file is the place for personal overrides — an engineer who always wants 16 streams or always uses a specific partition sets it once in their user config and never thinks about it again.

The config is modeled with Pydantic:

```python
from pydantic import BaseModel


class SSHConfig(BaseModel):
    """SSH connection settings. Resolved from env vars, config files, or CLI flags."""
    host: str
    port: int = 22
    username: str
    key_path: str  # Path to SSH private key file (not the key itself — per clig.dev, never secrets in flags/env)
    known_hosts_path: str | None = None


class TransferConfig(BaseModel):
    """File transfer tuning parameters."""
    parallel_streams: int = 8
    chunk_size_mb: int = 64
    compression_level: int = 3  # zstd level (1-19, 3 is good default)
    compression_threads: int = 0  # 0 = auto-detect
    verify_checksums: bool = True
    resume_enabled: bool = True


class ClusterConfig(BaseModel):
    """Cluster-wide defaults."""
    shared_root: str = "/shared"
    default_partition: str = "simulation-r6i-8x"
    default_wall_time: str = "99:00:00"
    scratch_root: str = "{job_dir}/scratch"
    logs_subdir: str = "logs"


class NastranDefaults(BaseModel):
    """Nastran solver defaults."""
    executable_path: str = "/shared/siemens/nastran2312/bin/nastran"
    input_extension: str = ".dat"
    memory: str = "236Gb"
    buffpool: str = "5Gb"
    buffsize: int = 65537
    smemory: str = "150Gb"
    memorymaximum: str = "236Gb"
    default_cpus: int = 12


class AnsysDefaults(BaseModel):
    """ANSYS solver defaults."""
    executable_path: str = "/shared/ansys/v241/bin/ansys241"
    input_extension: str = ".dat"
    default_cpus: int = 12
    # ANSYS-specific flags go here


class SolverConfig(BaseModel):
    """All solver configurations."""
    nastran: NastranDefaults = NastranDefaults()
    ansys: AnsysDefaults = AnsysDefaults()


class LaunchpadConfig(BaseModel):
    """Root configuration model."""
    ssh: SSHConfig
    transfer: TransferConfig = TransferConfig()
    cluster: ClusterConfig = ClusterConfig()
    solvers: SolverConfig = SolverConfig()
```

**`core/ssh.py`** — Manages the SSH connection lifecycle. Provides a context manager that Click commands use:

```python
import asyncssh
from contextlib import asynccontextmanager
from typing import AsyncGenerator


@asynccontextmanager
async def ssh_session(config: SSHConfig) -> AsyncGenerator[asyncssh.SSHClientConnection, None]:
    """Open an SSH connection to the cluster head node."""
    conn = await asyncssh.connect(
        host=config.host,
        port=config.port,
        username=config.username,
        client_keys=[config.key_path],
        known_hosts=config.known_hosts_path,
    )
    try:
        yield conn
    finally:
        conn.close()
```

**`core/transfer.py`** — The SFTP transfer engine. V1 uses single-stream transfers with resume support. Parallel multi-stream is a Phase 5 optimization, benchmarked before implementation.

- Opens one SFTP channel over the SSH connection.
- Uploads/downloads with progress reporting via Rich.
- Supports resume: checks remote/local file size and resumes from last complete offset.
- Integrity verification: file size match post-transfer, optional checksum.

```python
async def upload(
    conn: asyncssh.SSHClientConnection,
    local_path: Path,
    remote_path: str,
    *,
    resume: bool = True,
    progress_callback: Callable[[int], None] | None = None,
) -> None:
    """Upload a file via SFTP with resume support and progress reporting."""
    ...


async def download(
    conn: asyncssh.SSHClientConnection,
    remote_path: str,
    local_path: Path,
    *,
    resume: bool = True,
    progress_callback: Callable[[int], None] | None = None,
) -> None:
    """Download a file via SFTP with resume support and progress reporting."""
    ...
```

**`core/compress.py`** — Handles zstd compression locally (before upload) and remotely (before download). Uses the `zstandard` library locally and invokes `zstd` or `tar --zstd` over SSH for remote operations.

**`core/slurm.py`** — Builds and parses SLURM commands. No shell scripts are generated locally — the submit script is generated on the remote side by this module issuing commands over SSH. Key functions:

```python
def build_submit_script(
    solver: SolverAdapter,
    input_files: list[str],
    config: LaunchpadConfig,
    overrides: SubmitOverrides,
) -> str:
    """Generate the SLURM batch script content."""
    ...


def parse_squeue_output(raw: str) -> list[JobStatus]:
    """Parse squeue --json output into structured data."""
    ...


def parse_sacct_output(raw: str) -> list[JobAccounting]:
    """Parse sacct --json output into structured data."""
    ...
```

**`solvers/base.py`** — Defines the solver adapter protocol:

```python
from typing import Protocol


class SolverAdapter(Protocol):
    """Interface that each solver must implement."""

    @property
    def name(self) -> str:
        """Solver display name (e.g., 'Nastran')."""
        ...

    @property
    def input_extensions(self) -> list[str]:
        """File extensions to discover as input files (e.g., ['.dat'])."""
        ...

    @property
    def output_extensions(self) -> list[str]:
        """Key output file extensions for log viewing (e.g., ['.f06', '.op2'])."""
        ...

    def build_run_command(
        self,
        input_file: str,
        config: LaunchpadConfig,
        overrides: SubmitOverrides,
    ) -> str:
        """Build the shell command that runs the solver for one input file."""
        ...

    def build_scratch_env(self, scratch_dir: str) -> dict[str, str]:
        """Return environment variables needed for scratch directory setup."""
        ...
```

**`display.py`** — All Rich formatting. This is what makes the CLI feel polished rather than utilitarian. Responsibilities:

- **Progress bars:** Multi-bar display during parallel transfers showing per-stream and total progress, transfer speed, ETA.
- **Status tables:** Color-coded job state (`RUNNING` → green, `PENDING` → yellow, `FAILED` → red, `COMPLETED` → blue). Uses Rich's `Table` with clean column alignment.
- **Panels and headers:** Styled section headers for submit confirmations, download summaries. Uses Rich `Panel` and `Rule` for visual structure.
- **Spinners:** Animated spinners for SSH connection, remote compression, and other latent operations.
- **Confirmation prompts:** Rich-styled prompts for destructive actions (cleanup, overwrite) with clear default highlighting.
- **Disk space warnings:** Color-coded bar showing local free space vs. download size.
- **Error display:** Errors in red panels with actionable suggestions, not raw tracebacks.
- **Help text:** `rich-click` integration for colorized `--help` output across all commands.

The goal: even the least technical team member should find the output clear, informative, and easy to scan.

### 4.3 Data Flow: `launchpad submit`

```
┌─────────────────────────────────────────────────────────┐
│  LOCAL (Windows)                                        │
│                                                         │
│  1. Discover .dat files in CWD                          │
│  2. Validate file count + naming                        │
│  3. Compress → .tar.zst (local zstd, multi-threaded)    │
│  4. Upload .tar.zst via parallel SFTP ──────────────┐   │
│                                                     │   │
└─────────────────────────────────────────────────────│───┘
                                                      │
┌─────────────────────────────────────────────────────│───┐
│  REMOTE (Head Node, FSx for Lustre)                 ▼   │
│                                                         │
│  5. mkdir /shared/<user>/<run_name>/                         │
│  6. Decompress .tar.zst into job directory               │
│  7. Write SLURM submit script (generated, not uploaded)  │
│  8. Write file manifest                                  │
│  9. mkdir logs/ scratch/                                 │
│  10. sbatch submit → returns Job ID                      │
│                                                         │
└─────────────────────────────────────────────────────────┘
                      │
                      ▼
              Print job ID + paths
              "Monitor with: lp status 12345"
```

### 4.4 Data Flow: `launchpad download`

```
┌────────────────────────────────────────────────────────────┐
│  LOCAL (Windows)                                           │
│                                                            │
│  1. lp download 12345                                      │
│  2. SSH query: job status, remote dir, result sizes        │
│  3. Check local disk space vs. estimated download size     │
│  4. Confirm with user ──────────────────────────────┐      │
│                                                     │      │
│  8. Parallel SFTP download .tar.zst ◄───────────────│──┐   │
│  9. Decompress locally                              │  │   │
│  10. Verify (file count, optional checksums)        │  │   │
│                                                     │  │   │
└─────────────────────────────────────────────────────│──│───┘
                                                      │  │
┌─────────────────────────────────────────────────────│──│───┐
│  REMOTE                                             ▼  │   │
│                                                        │   │
│  5. tar --zstd results_*/ → results.tar.zst            │   │
│  6. Compute checksums                                  │   │
│  7. Serve download ────────────────────────────────────┘   │
│  (optional) 11. rm -rf job directory if --cleanup          │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

---

## 5. Transfer Strategy

With 10+ GB payloads, transfer speed matters — but reliability and correctness matter more. The strategy is deliberately phased: get it right first, then get it fast.

### 5.1 V1 Transfer Design (Phases 1–4): Single-Stream, Reliable

V1 uses a single SFTP stream per transfer. This is intentionally conservative:

- **Upload:** One `asyncssh` SFTP channel uploads the `.tar.zst` archive with progress reporting via Rich.
- **Download:** Same in reverse.
- **Resume:** If interrupted (network drop, Ctrl+C), the next attempt checks the remote/local file size and resumes from the last complete offset. This is critical for multi-GB transfers and is the single most important transfer feature.
- **Integrity:** After transfer, verify file size match and optional checksum comparison.
- **Progress:** Rich progress bar showing bytes transferred, speed, ETA, and percentage.

A single SFTP stream over SSH typically achieves 100–150 MB/s on a good network. For a 3 GB compressed archive, that's ~20–30 seconds. This is slower than WinSCP's multi-connection approach but is correct, resumable, and simple to debug.

### 5.2 Phase 5: Benchmark Before Committing to Parallel Design

The plan originally specified a custom multipart transfer system (N SFTP channels, chunk splitting, offset-based parallel writes). This is **not trivial** — it is a custom protocol on top of SFTP with correctness, resume, buffering, and integrity implications. Before committing to a design, Phase 5 benchmarks these candidates on the actual cluster and network:

1. **Multiple SSH connections** (not channels) — open N separate SSH connections, each uploading/downloading a different part. Simpler than multiplexed channels.
2. **Multiple SFTP channels on one connection** — the original plan. AsyncSSH supports this, but correctness of concurrent offset writes to one file needs validation.
3. **Split archive into N parts** — compress into multiple `.tar.zst.NNN` parts, transfer each on its own stream, reassemble remotely. Simpler resume semantics.
4. **Parallel transfer of many files** — skip archiving entirely, transfer individual files in parallel. Trades compression ratio for simplicity.
5. **Remote `tar | zstd` streaming over SSH** — pipe directly over the SSH connection, bypassing SFTP. Potentially fastest, but no resume.

The winner depends on: head node SSH config (MaxSessions, MaxStartups), FSx I/O characteristics, actual network bandwidth, and Windows asyncssh behavior. Do not assume any approach is optimal without benchmarking.

### 5.3 Compression Tuning

zstd level 3 (the default) gives ~3:1 compression on FEA input files at ~500 MB/s compression speed. The compression level is configurable via `--compression-level` for teams that prefer stronger compression on slower networks.

### 5.4 Resume Support

If a transfer is interrupted (network drop, user Ctrl+C), the next attempt checks the remote file size and resumes from the last complete offset. This works for both upload and download, and is available from V1. Resume is the most important transfer feature for a team dealing with 10+ GB payloads.

---

## 6. Configuration System Detail

### 6.1 Cluster Shared Config

Lives at `/shared/config/launchpad.toml` on the FSx for Lustre drive, which is mounted locally on team workstations. This file is read as a local file — no SSH or network I/O. Managed by the team lead or cluster admin. If the drive is not mounted (e.g., working remotely without VPN), the CLI gracefully falls back to user config + env vars. Example:

```toml
[ssh]
host = "headnode.example.com"
port = 22

[cluster]
shared_root = "/shared"
default_partition = "simulation-r6i-8x"
default_wall_time = "99:00:00"

[transfer]
parallel_streams = 8
compression_level = 3

[solvers.nastran]
executable_path = "/shared/siemens/nastran2312/bin/nastran"
memory = "236Gb"
buffpool = "5Gb"
buffsize = 65537
smemory = "150Gb"
memorymaximum = "236Gb"
default_cpus = 12

[solvers.ansys]
executable_path = "/shared/ansys/v241/bin/ansys241"
default_cpus = 12

# Remote binary paths (validated by `lp doctor`)
[remote_binaries]
sbatch = "sbatch"      # Must be on PATH
squeue = "squeue"
sacct = "sacct"
tar = "tar"
zstd = "zstd"

# Profile schema placeholder (multi-cluster support is out of scope for V1,
# but the config shape is here so we don't break compatibility later).
# Uncomment and add profiles when needed:
# [profiles.production]
# ssh.host = "prod-headnode.example.com"
# cluster.shared_root = "/shared"
# cluster.default_partition = "simulation-r6i-8x"
#
# [profiles.dev]
# ssh.host = "dev-headnode.example.com"
# cluster.default_partition = "debug"
```

**Assumed remote environment:**

- SLURM 22.05+ (required for `squeue --json` and `sacct --json` output format).
- `tar` with `--zstd` support (GNU tar 1.31+, or `zstd` available separately for piped compression).
- `zstd` CLI available on head node for remote compression/decompression.
- These assumptions are validated by `lp doctor` — if any binary is missing or too old, the doctor reports it with a fix suggestion.

### 6.2 User Local Config

Lives at `~/.launchpad/config.toml`. Created by `launchpad config init`. This is the engineer's personal configuration — it stores SSH credentials and any personal overrides to the team-wide cluster config that the engineer cannot edit directly.

**This is the migration path from environment variables.** If an engineer currently has `LAUNCHPAD_HOST`, `LAUNCHPAD_USER`, and `LAUNCHPAD_KEY` set as environment variables, those will work immediately. Running `launchpad config init` writes them to the config file so they don't need to maintain env vars.

Example:

```toml
[ssh]
username = "sergey"
key_path = "C:\\Users\\sergey\\.ssh\\id_ed25519"

[transfer]
parallel_streams = 12  # Personal override: faster connection from my workstation

[submit]
default_cpus = 16      # I always want 16 CPUs, team default is 12
```

**What can be overridden:** Any setting from the cluster config can be overridden here. The engineer cannot break things for others — their user config only affects their own invocations. Common personal overrides include: parallel_streams (varies by workstation network), default_cpus, default partition, and solver defaults.

### 6.3 Environment Variables

Environment variables follow the `LAUNCHPAD_*` convention and sit between CLI flags and config files in precedence. They are most useful for:

- **CI/CD pipelines** where config files aren't available.
- **Temporary overrides** for a single terminal session.
- **Migration** from the current workflow where SSH credentials are already set as env vars.

Example (PowerShell):

```powershell
$env:LAUNCHPAD_HOST = "10.0.1.50"
$env:LAUNCHPAD_USER = "sergey"
$env:LAUNCHPAD_KEY = "C:\Users\sergey\.ssh\id_ed25519"

# Now lp submit will use these credentials
lp submit
```

### 6.4 Project Local Config

Lives at `.launchpad.toml` in the project directory. Example:

```toml
[submit]
solver = "nastran"
cpus = 16
name_prefix = "tank_v3"
partition = "simulation-r6i-16x"
```

### 6.5 Config Resolution

When any command runs, the config loader:

1. Reads `/shared/config/launchpad.toml` from the mounted FSx drive (optional — skipped gracefully if path doesn't exist, e.g., when not on the network).
2. Reads `~/.launchpad/config.toml`.
3. Reads `./.launchpad.toml` (if present).
4. Reads `LAUNCHPAD_*` environment variables.
5. Merges them in priority order (higher overrides lower).
6. Applies CLI flag overrides on top.

Config loading is always a local filesystem operation. There is no SSH, no network I/O, no caching, and no TTL. If the shared drive is not mounted (e.g., working from home without VPN), the CLI still works — it just uses user config + env vars + CLI flags. The `lp doctor` command verifies shared config accessibility.

---

## 7. SLURM Integration Detail

### 7.1 Submit Script Generation

The CLI generates the SLURM submit script **on the remote machine** (not uploaded). The script follows the same pattern as your existing `nastran_array_job.sh` but is templated from the solver adapter. Key decisions preserved from your current script:

- Array job with `%max_concurrent` throttle.
- File manifest written at submission time (frozen file list).
- Per-task result directories: `results_<basename>_<taskid>/`.
- Scratch on shared filesystem (not `/tmp`), cleaned on success.
- `set -euo pipefail` after SBATCH directives.

### 7.2 Status Queries

`launchpad status` uses `squeue --json` and `sacct --json` for structured parsing (no brittle column-position parsing). SLURM's JSON output is available in modern versions and gives us clean access to all fields.

Resource utilization comes from `sstat` (for running jobs) and `sacct` (for completed jobs), both with `--json` output.

### 7.3 Job Tracking

Since the CLI is stateless, it needs a way to map Job IDs to remote directories. Two options:

**Option A: SLURM job comment.** When submitting, write the remote directory path into the SLURM job comment field (`--comment="/shared/sergey/nastran-20260311-1422-a7f3"`). This lets `launchpad status` and `launchpad download` resolve the directory from just a job ID.

**Option B: Local breadcrumb file.** Write a `.launchpad-job` file in the local project directory after submission containing the job ID, remote path, and timestamp. This is simpler but breaks statelessness slightly.

**Recommendation: Option A.** The SLURM comment field is the correct place for this metadata. It survives machine reboots, works from any workstation, and requires no local state.

---

## 8. Error Handling Strategy

Per clig.dev: catch errors and rewrite them for humans. Signal-to-noise ratio is critical. Put the most important information last (where the eye lands). Suggest next steps.

| Scenario | Handling | Exit Code |
|----------|----------|-----------|
| SSH connection refused | Retry 3 times with backoff, then clear error message with troubleshooting steps | `2` |
| SSH auth failure | Explain which key was tried, suggest checking `LAUNCHPAD_KEY` or `~/.launchpad/config.toml` | `2` |
| Transfer interrupted | Resume from last chunk boundary on retry. Print: "Transfer interrupted. Run the same command again to resume." | `3` |
| Checksum mismatch | Print expected vs actual, suggest re-download | `3` |
| SLURM submission fails | Display sbatch stderr, suggest common fixes (wrong partition, quota exceeded) | `4` |
| Insufficient local disk space | Abort with clear size comparison, suggest `--exclude` patterns or `--tasks` | `1` |
| Input file validation fails | List problems, suggest fixes, abort before any upload | `1` |
| Remote directory already exists | Prompt: overwrite, rename with suffix, or abort | `1` |
| Job cancelled during download | Warn and offer partial download | `1` |
| Solver fails (SLURM COMPLETED but solver errored) | Surface in `launchpad status` via exit code if available, but no output parsing | — |
| User hits Ctrl-C | Immediately print "Interrupted.", clean up gracefully, exit | `130` |
| Unknown/unexpected error | Print a concise error (not a traceback), suggest `--verbose` for details, suggest filing an issue | `1` |

### 8.1 Logging Strategy

Logging is a development-time and operational requirement, not an afterthought. Every module must use structured logging from day one. `loguru` is the logging library — it replaces the stdlib `logging` module entirely with a simpler API, automatic formatting, and built-in rotation.

**Log levels and where they appear:**

| Level | Purpose | Visible to user? |
|-------|---------|-------------------|
| `TRACE` | Low-level debugging (SSH channel ops, byte-level transfer details) | Only with `-vv` |
| `DEBUG` | Operational detail (config resolution, file discovery, SLURM commands issued) | Only with `--verbose` / `-v` |
| `INFO` | Key milestones (upload started, job submitted, download complete) | Default on stderr via Rich |
| `WARNING` | Non-fatal issues (low disk space, slow transfer, deprecated config key) | Always on stderr |
| `ERROR` | Failures that abort the operation | Always on stderr |

**Log file:**

All log output (DEBUG and above) is always written to a log file, regardless of terminal verbosity. This is critical for diagnosing issues after the fact ("my submit failed last night, what happened?").

- **Location:** `~/.launchpad/logs/launchpad.log`
- **Rotation:** 10 MB per file, keep 5 rotated files (configurable in user config)
- **Format:** Structured with timestamp, level, module, and message. Example:
  ```
  2025-07-15 14:32:01.234 | DEBUG | core.config | Resolved config: cluster=/shared/config/launchpad.toml, user=~/.launchpad/config.toml
  2025-07-15 14:32:02.891 | INFO  | core.transfer | Uploading tank_v3.tar.zst (3.2 GB) via 8 SFTP streams
  2025-07-15 14:32:45.102 | INFO  | core.slurm | Submitted job 12345 (array 0-11) to partition simulation-r6i-8x
  ```

**Setup pattern (in `core/logging.py`):**

```python
from loguru import logger
import sys
from pathlib import Path


def setup_logging(verbosity: int = 0, log_dir: Path | None = None) -> None:
    """Configure loguru sinks for console and file output.

    Args:
        verbosity: 0 = default (WARNING+), 1 = DEBUG, 2 = TRACE.
        log_dir: Directory for log files. Defaults to ~/.launchpad/logs/.
    """
    logger.remove()  # Remove default stderr sink

    # Console sink: level depends on verbosity, formatted for humans
    console_level = {0: "WARNING", 1: "DEBUG", 2: "TRACE"}.get(verbosity, "WARNING")
    logger.add(
        sys.stderr,
        level=console_level,
        format="<level>{message}</level>",
        colorize=True,
    )

    # File sink: always DEBUG+, structured format, rotation
    if log_dir is None:
        log_dir = Path.home() / ".launchpad" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_dir / "launchpad.log",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <7} | {name}:{function} | {message}",
        rotation="10 MB",
        retention=5,
    )
```

**Development requirement:** Every module must `from loguru import logger` and use `logger.debug()`, `logger.info()`, etc. for all significant operations. This is not optional — it is part of code review. Specifically:

- **config.py**: Log which config files were found, merged, and which keys came from which source.
- **ssh.py**: Log connection attempts, retries, and connection parameters (never log key contents).
- **transfer.py**: Log transfer start/end, speeds, chunk assignments, resume decisions.
- **slurm.py**: Log every SLURM command issued and its raw output at DEBUG level.
- **compress.py**: Log compression ratio, speed, and file sizes.
- **CLI commands**: Log the resolved options before executing (at DEBUG), and the outcome after.

---

## 9. Dependencies

| Package | Purpose | Version Constraint |
|---------|---------|-------------------|
| `click` | CLI framework | `>=8.1` |
| `rich-click` | Rich-formatted help text and error output for Click | `>=1.7` |
| `asyncssh` | SSH/SFTP transport | `>=2.14` |
| `pydantic` | Config validation | `>=2.0` |
| `zstandard` | Local zstd compression | `>=0.22` |
| `rich` | Terminal UI (progress bars, tables, panels, spinners) | `>=13.0` |
| `loguru` | Structured logging with rotation, retention, and pretty formatting | `>=0.7` |

**Notable exclusions:**

- No `paramiko`. `asyncssh` is async-native, supports multiplexed channels on a single connection (critical for parallel SFTP), and handles SSH key auth cleanly on Windows.
- No `tomli`. Python 3.12 includes `tomllib` in the stdlib.
- No `aiorun` / `uvloop`. The team is all-Windows where uvloop is unsupported, and `asyncio.run()` with a simple wrapper handles our CLI use case cleanly without extra dependencies.

**Runtime requirement:** Python 3.12+ (for `tomllib` stdlib, `StrEnum`, modern typing features including `type` statement). The team installs Python once; this is not a burden.

---

## 10. Distribution & Installation

### 10.1 Package Build

Standard `pyproject.toml` with entry point, managed by `uv`:

```toml
[project]
name = "launchpad-cli"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "click>=8.1",
    "rich-click>=1.7",
    "asyncssh>=2.14",
    "pydantic>=2.0",
    "zstandard>=0.22",
    "rich>=13.0",
    "loguru>=0.7",
]

[project.scripts]
launchpad = "launchpad_cli.cli:main"
lp = "launchpad_cli.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.uv]
dev-dependencies = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.4",
]
```

### 10.2 Development Setup (uv)

```powershell
git clone https://gitlab.example.com/team/launchpad-cli.git
cd launchpad-cli
uv sync
uv run launchpad --help       # Verify it works
uv run pytest            # Run tests
```

### 10.3 Installation for Team Members

The simplest reliable path for non-Python-expert engineers on Windows:

**Option A: uv tool (recommended, cleanest isolation):**

```powershell
# 1. Install uv (one-time)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 2. Install launchpad-cli (uv handles Python automatically)
uv tool install git+https://gitlab.example.com/team/launchpad-cli.git
```

This is the best option because `uv tool` installs the CLI in an isolated environment and `uv` can even install Python automatically if not present. No `pip`, no virtual environment management, no PATH issues.

**Option B: pip (if uv is not available):**

```powershell
# 1. Install Python 3.12+ from python.org (or winget)
winget install Python.Python.3.12

# 2. Install launchpad-cli from GitLab
pip install git+https://gitlab.example.com/team/launchpad-cli.git
```

After either option, `launchpad` and `lp` are available in any terminal.

**Upgrades:**

```powershell
# uv
uv tool upgrade launchpad-cli

# pip
pip install --upgrade git+https://gitlab.example.com/team/launchpad-cli.git
```

**First-run setup:**

```powershell
launchpad config init
# Prompts for: username, SSH key path, host (if not in shared config)
# Creates ~/.launchpad/config.toml
# Uses Rich prompts with clear defaults and validation
```

---

## 11. Development Phases

### Phase 1: Foundation (Weeks 1–2)

**Goal:** SSH connection, config system, and basic file transfer working end-to-end.

- [x] Project scaffolding (`pyproject.toml`, `src/` layout, `uv` for dependency management and dev workflow)
- [x] `core/config.py` — Pydantic models, TOML loading, layered merge logic with env var support
- [x] `core/logging.py` — loguru setup: console sink (verbosity-dependent), file sink (rotation, retention)
- [x] `core/ssh.py` — asyncssh connection manager with retry logic
- [x] `core/transfer.py` — Single-stream SFTP upload/download with Rich progress bar
- [x] `core/compress.py` — Local zstd compress/decompress using `zstandard`
- [x] `launchpad config init` / `launchpad config show` commands
- [x] `launchpad ssh` command (interactive session passthrough)
- [x] `launchpad doctor` command — full diagnostics (config, SSH, remote binaries, writable paths)
- [x] Basic test infrastructure with pytest
- [x] `ARCHITECTURE.md` — Codebase map for human and AI agent contributors
- [x] README skeleton with installation instructions

**Milestone:** Can SSH into cluster and upload/download a file from the command line.

### Phase 2: Submission Pipeline (Weeks 3–4)

**Goal:** Full submit workflow for Nastran.

- [x] `solvers/base.py` — SolverAdapter Protocol definition
- [x] `solvers/nastran.py` — Nastran adapter (input discovery, run command, scratch setup)
- [x] `solvers/ansys.py` — ANSYS stub (Protocol-compliant skeleton with `NotImplementedError`)
- [x] `core/slurm.py` — Submit script generation, `sbatch` execution over SSH
- [x] `core/remote_ops.py` — Remote mkdir, tar, file listing, du
- [x] `cli/submit.py` — Full orchestration: discover → compress → upload → decompress → generate script → submit
- [x] `--dry-run` support
- [x] `display.py` — Rich output formatting for submit confirmation

**Milestone:** `launchpad submit` works end-to-end for Nastran jobs from a Windows terminal.

### Phase 3: Monitoring & Logs (Weeks 5–6)

**Goal:** Status tracking and log access.

- [x] `core/slurm.py` — `squeue --json` and `sacct --json` parsing
- [x] `cli/status.py` — Status table with resource utilization
- [x] `cli/logs.py` — Remote log tailing (SLURM logs + solver output files)
- [x] `--watch` mode for status (polling loop with Rich live display)
- [x] `launchpad cancel` command

**Milestone:** Can monitor and manage jobs entirely from local terminal.

### Phase 4: Download & Cleanup (Weeks 7–8)

**Goal:** Results retrieval with safety checks.

- [ ] `core/local_ops.py` — Disk space checking, path handling (Windows-aware)
- [ ] `core/compress.py` — Remote-side compression (tar + zstd over SSH)
- [ ] `cli/download.py` — Full orchestration: check status → size check → space check → compress remote → download → decompress local → verify
- [ ] `cli/cleanup.py` — Remote directory management
- [ ] `cli/ls.py` — Remote file listing
- [ ] Integrity verification (file counts, optional checksums)

**Milestone:** Full job lifecycle works: submit → monitor → download → cleanup.

### Phase 5: Performance & Polish (Weeks 9–10)

**Goal:** Transfer optimization, edge cases, logging audit.

- [ ] **Transfer benchmark:** Test 3+ parallel transfer strategies (see Section 5.2) against the actual cluster. Measure throughput, resume correctness, and stability. Select winner based on data, not assumptions.
- [ ] Implement the winning parallel transfer strategy (or keep single-stream if overhead isn't justified)
- [ ] Resume support hardened for interrupted transfers
- [ ] Comprehensive error handling and user-friendly error messages
- [ ] `--json` output mode for all commands (scriptability)
- [ ] Typo suggestions for invalid subcommands (custom `difflib.get_close_matches` in Click group)
- [ ] Edge case handling: existing directories, partial results, cancelled jobs
- [ ] Logging audit: verify every module has appropriate DEBUG/INFO/WARNING log calls, log file rotation works correctly, `--verbose` output is useful without being noisy

**Not in Phase 5 (deferred):** `solvers/ansys.py` implementation. The stub exists and conforms to the `SolverAdapter` Protocol, but functional implementation requires an ANSYS user to define the workflow (input format, executable invocation, scratch requirements). This is tracked as a future task.

**Milestone:** Production-ready for team rollout (Nastran). Transfer speed validated against WinSCP baseline.

### Phase 6: Team Rollout (Week 11)

- [ ] Write the shared cluster config (`/shared/config/launchpad.toml`)
- [ ] Finalize README: installation, quickstart, full command reference, config reference
- [ ] Finalize ARCHITECTURE.md with all modules documented
- [ ] Verify `--help` output is clear and complete for every command
- [ ] `launchpad config init` wizard tested on a fresh Windows machine
- [ ] `lp doctor` passes on a fresh Windows machine after install + config init
- [ ] Walk each team member through first submit + download cycle
- [ ] Collect feedback, file issues

**Rollout success metrics (measure after 2 weeks of team use):**

| Metric | Target |
|--------|--------|
| First successful submit from a fresh machine | Under 10 minutes (install + config + first job) |
| Manual SSH / WinSCP sessions per analysis cycle | Reduced to near zero for standard workflows |
| Failed submissions due to wrong paths, bad scripts, or missing files | Significantly reduced vs. manual workflow |
| Transfer throughput | At least comparable to current WinSCP workflow |
| One-command download for completed jobs | Works reliably for all team members |

---

## 12. Testing Strategy

| Layer | Approach |
|-------|----------|
| Config loading & merging | Unit tests with fixture TOML files and mock env vars (`LAUNCHPAD_*`) |
| Environment variable precedence | Unit tests verifying env vars override config files, CLI flags override env vars |
| Logging setup | Unit tests verifying log file creation, rotation, verbosity levels |
| SLURM command building | Unit tests (string comparison of generated scripts) |
| SLURM output parsing | Unit tests with captured `squeue --json` / `sacct --json` samples |
| Solver adapters | Unit tests (input discovery, command building). ANSYS stub test: verify `NotImplementedError`. |
| Compression | Integration tests with real files (small) |
| SSH + Transfer | Integration tests against a local SSH server (or skip in CI, test manually) |
| Full submit pipeline | Manual integration tests against the real cluster |
| CLI surface | Click's `CliRunner` for argument parsing and help text |

**Pragmatic note:** This is an internal team tool, not a public library. Unit tests on the parsers and generators are high-value. End-to-end tests against the real cluster are done manually during development. Don't over-invest in mocking SSH.

---

## 13. Future Considerations (Not in Scope for V1)

These are deliberate omissions to keep V1 focused:

- **ANSYS adapter implementation.** The `SolverAdapter` Protocol and a stub `ansys.py` exist in V1 to prove the abstraction. Full implementation requires an ANSYS user to define the workflow (input format, executable, scratch requirements). The stub raises `NotImplementedError` with a helpful message.
- **Nastran INCLUDE resolution.** V1 discovers input files by extension only. Automatic parsing of Nastran INCLUDE statements to build a dependency tree and auto-include referenced files is a valuable future enhancement. For now, engineers use `--extra-files` or `--include-all`.
- **Compute-node compression.** Remote compression currently runs on the head node. For clusters where head node CPU is contentious, a future option could submit a short SLURM job to compress results on a compute node before download.
- **Cloud provider abstraction.** You mentioned possibly switching from AWS. If that happens, the SSH + SLURM layer is provider-agnostic already. The only AWS-specific piece is FSx path conventions, which is a config change.
- **Web dashboard.** A NiceGUI or similar web UI on top of the same core library. The `core/` package is designed to be importable without Click, making this straightforward later.
- **Job dependency chains.** SLURM supports `--dependency=afterok:JOBID`. The architecture supports this but V1 doesn't expose it.
- **Notifications.** Slack/email/desktop notifications on job completion. Could be added as a `launchpad notify` command or post-submit hook.
- **Multi-cluster support.** Config profiles for different clusters (e.g., `launchpad --cluster prod submit`). The profile schema placeholder exists in the cluster config already.

---

## 14. Open Design Questions

These should be resolved before or during Phase 1:

1. **CLI command name (resolved):** `launchpad` (full) and `lp` (short alias). Package name: `launchpad-cli`. Both entry points are registered in `pyproject.toml`.
2. **Async architecture (resolved):** Click is synchronous; `asyncssh` is async. Each Click command is a thin synchronous shell that calls `asyncio.run()` on an async implementation function. This is a standard, well-established pattern that works cleanly on Python 3.12+ on Windows. Do not call `asyncio.run()` more than once per command invocation — all async work for a single command (upload, SSH exec, download) lives in one async function. For long-running commands (`lp logs -f`, `lp status --watch`), the async function runs a polling loop that checks for `KeyboardInterrupt` / `asyncio.CancelledError` to handle Ctrl-C gracefully.
3. **Cluster config bootstrap (resolved):** The shared config lives on the mounted FSx drive at `/shared/config/launchpad.toml` — it's a local file read, not a remote fetch. `launchpad config init` prompts for SSH credentials (host, username, key path), writes them to `~/.launchpad/config.toml`, and validates that `/shared/config/launchpad.toml` is readable. If `LAUNCHPAD_HOST`, `LAUNCHPAD_USER`, and `LAUNCHPAD_KEY` environment variables are already set (which they are for the current team), the init wizard detects them and offers to write them to the config file — making migration seamless.
4. **ANSYS adapter (deferred):** The `SolverAdapter` Protocol and a stub `ansys.py` ship in V1, but functional implementation is deferred until an ANSYS user on the team defines the exact workflow (input format, executable invocation, scratch requirements). The stub should raise a clear `NotImplementedError` with a helpful message if someone tries `lp submit -s ansys`.

---

## 15. Documentation Requirements

Documentation is a first-class deliverable, maintained alongside code at all times.

### 15.1 Code Documentation

- **Every public function and class** has a docstring. Docstrings are succinct: one-line summary, then parameters/returns only if non-obvious from type hints.
- **Module-level docstrings** at the top of every `.py` file explaining the module's purpose and key design decisions.
- **Type hints everywhere.** All function signatures are fully typed. Pydantic models serve as self-documenting config schemas.
- **Inline comments** for non-obvious logic — especially SSH channel management, SLURM script generation, and parallel transfer coordination.

### 15.2 User-Facing Documentation

- **README.md** — Installation, quickstart (submit your first job in 3 commands), full command reference.
- **`launchpad --help` and `launchpad <command> --help`** — Rich-formatted help text via `rich-click`. Every command and every flag has a help string. Examples are included in help text for complex commands.
- **`launchpad config show --docs`** — Prints annotated config schema showing all available settings, their types, defaults, and descriptions.

### 15.3 AI-Agent Readability

This project is developed using AI coding agents in a Coordinator/Builder loop. To maximize agent effectiveness:

- **Clear module boundaries.** Each module has a single, well-defined responsibility stated in its module docstring. An AI agent reading the docstring can understand the module's contract without reading implementation.
- **Protocol-driven interfaces.** `SolverAdapter` is a Protocol, not an ABC. The interface is explicit in code, not implicit in usage patterns.
- **No implicit state.** Functions take their dependencies as arguments. No module-level singletons, no hidden caches, no import-time side effects. An AI agent can reason about any function by reading its signature.
- **Test fixtures as documentation.** Test fixtures (sample TOML configs, captured SLURM JSON output, sample `.dat` file trees) serve double duty as documentation of expected data formats.
- **ARCHITECTURE.md** — A high-level map of the codebase: which module does what, how data flows through the system, and where to make changes for common tasks (add a new solver, add a new CLI command, change transfer behavior). This is the first file an AI agent (or new human contributor) should read.
