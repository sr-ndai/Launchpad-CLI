# Transfer Benchmark

## Status

Blocked on missing cluster prerequisites as of 2026-03-13 19:55 PDT.

## Task Scope

Task `5.1` requires benchmarking at least three Phase 5 transfer candidates on
the real cluster/head-node workflow before recommending whether Launchpad
should move beyond the current resumable single-stream SFTP path.

## Planned Benchmark Matrix

The Phase 5 plan identifies these candidate strategies:

1. Current baseline: single-stream SFTP with resume.
2. Multiple SSH connections, one part per connection.
3. Multiple SFTP channels on one SSH connection.
4. Split archive into multiple parts and transfer parts in parallel.
5. Parallel transfer of many files without a single archive.
6. Remote `tar | zstd` streaming over SSH.

The intended benchmark set for this task was the baseline plus at least three
alternative strategies from that list, measuring throughput, resume behavior,
and failure modes on the real cluster.

## Blocking Evidence

The benchmark matrix was not executed because the repository environment does
not currently resolve any usable cluster connection settings.

### Commands Run

```bash
uv run launchpad doctor
uv run python - <<'PY'
from pathlib import Path
from launchpad_cli.core.config import resolve_config

cfg = resolve_config(cwd=Path.cwd(), env={})
print(cfg.config.model_dump())
print([(layer.name, str(layer.path) if layer.path else None, layer.loaded) for layer in cfg.layers])
PY
```

### Observed Prerequisite Gaps

- `/shared/config/launchpad.toml` is not present.
- `~/.launchpad/config.toml` is not present.
- `./.launchpad.toml` is not present.
- `LAUNCHPAD_HOST`, `LAUNCHPAD_USER`, and `LAUNCHPAD_KEY` are unset.
- `launchpad doctor` therefore reports missing `ssh.host`, `ssh.username`, and
  SSH key configuration, then skips all remote checks.

### Doctor Output Summary

- `PASS` Python 3.12.13
- `FAIL` missing `ssh.host` and `ssh.username`
- `FAIL` no SSH private key configured through Launchpad config
- `FAIL` shared config missing at `/shared/config/launchpad.toml`
- `SKIP` remote SSH, remote binary, and remote writable-path checks

## Why The Task Is Blocked

This task explicitly requires the actual cluster/head-node environment. With no
resolved cluster host, username, or Launchpad SSH key configuration, there is
no defensible way to run the benchmark matrix or record real transfer results.

## Unblock Conditions

The benchmark can proceed once this workstation has enough Launchpad
configuration to reach the real cluster, at minimum:

- a reachable cluster host and username
- a valid SSH private key configured for Launchpad
- either `/shared/config/launchpad.toml` mounted locally or equivalent
  user/project/environment overrides

After that, rerun `uv run launchpad doctor` until remote checks pass, then
execute the benchmark matrix and append raw measurements, resume observations,
failure modes, and the final recommendation to this document.
