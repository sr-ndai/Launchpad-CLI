# Transfer Architecture Decision

## Status

Phase 5 no longer treats missing real-cluster benchmarks as the gate for
transfer design. Real-cluster validation is still required before Launchpad
calls the new transport "proven", but task `5.1` must choose the architecture
now so task `5.2` can implement it without open product questions.

## Current Repository Baseline

- `src/launchpad_cli/core/transfer.py` implements resumable single-stream SFTP
  upload and download for one file at a time.
- `launchpad submit` always materializes one local `.tar.zst` archive, uploads
  that archive, and extracts it remotely.
- `launchpad download` already has two internal shapes:
  - `archive`: create one remote `.tar.zst`, download it, verify checksum, and
    extract locally
  - `raw`: walk the remote tree and download files directly
- `src/launchpad_cli/core/config.py` already exposes transfer defaults which
  Phase 5 should keep using:
  - `transfer.parallel_streams` (default `8`)
  - `transfer.chunk_size_mb` (default `64`)
  - `transfer.verify_checksums`
  - `transfer.resume_enabled`

The design therefore should extend the current archive-first baseline instead
of replacing it with an entirely different transport stack.

## Precedent Review

### 1. Large single-file transfer uses a different control from many-file transfer

- Rclone documents `--transfers` as "the number of file transfers to run in
  parallel" and points operators to `--multi-thread-streams` for single-file
  control instead.
- Rclone documents `--multi-thread-streams` separately for one large file above
  a cutoff, with a distinct chunk size and stream count.

Why it matters for Launchpad:

- "parallel transfer" is not one thing. A large archive and a directory tree
  need different execution models.
- Launchpad should expose a transfer mode, not pretend that one `--streams`
  value means the same thing in every path.

Sources:

- Rclone docs: <https://rclone.org/docs/#transfers>
- Rclone docs: <https://rclone.org/docs/#multi-thread-streams>

### 2. SFTP implementations separate per-file request pipelining from whole-transfer concurrency

- Rclone's SFTP backend has a separate `--sftp-concurrency` control for "the
  maximum number of outstanding requests for one file", independent from the
  number of parallel file transfers.
- The same backend documents `--sftp-disable-concurrent-reads` and
  `--sftp-disable-concurrent-writes`, which is a strong signal that some SFTP
  servers behave differently under aggressive concurrency.
- Rclone also documents `--sftp-connections` separately from file-transfer
  concurrency, and warns that connection limits need care.

Why it matters for Launchpad:

- `--streams` should be the operator-facing concurrency budget.
- Request pipelining inside one file should stay an internal implementation
  detail with conservative defaults.
- Launchpad should assume server compatibility varies and must degrade
  gracefully instead of treating high concurrency as guaranteed.

Source:

- Rclone SFTP backend docs: <https://rclone.org/sftp/>

### 3. Single-handle SFTP pipelining is real, but it is not the same as safe striped assembly

- Paramiko documents that SFTP `put`/`putfo` use pipelining for speed.
- Paramiko exposes `set_pipelined()` for write operations and `readv()` plus
  `max_concurrent_prefetch_requests` for concurrent ranged reads.
- Paramiko also notes that OpenSSH's SFTP implementation imposes a limit of 64
  concurrent requests, while Paramiko itself does not cap that by default.

Why it matters for Launchpad:

- Request pipelining inside one open file handle is valid precedent and should
  inform the internal tuning of Launchpad's per-file workers.
- It is not enough to justify speculative concurrent remote writes into a
  single destination file as Launchpad's primary correctness model.
- The safer design is to stripe through temporary part files and perform final
  assembly on the side Launchpad controls directly.

Source:

- Paramiko SFTP API docs: <https://docs.paramiko.org/en/stable/api/sftp.html>

## Decision

Phase 5 should implement three public transfer modes on both `launchpad submit`
and `launchpad download`:

- `auto`
- `single-file`
- `multi-file`

`auto` stays the default. `single-file` and `multi-file` are explicit operator
overrides.

### Public CLI Shape

`launchpad submit` should gain:

```text
--transfer-mode [auto|single-file|multi-file]
--streams INTEGER
```

`launchpad download` should standardize on:

```text
--transfer-mode [auto|single-file|multi-file]
--streams INTEGER
```

Default stream rule:

- On both commands, `--streams` should default to the resolved
  `transfer.parallel_streams` config value rather than a hard-coded command
  default.

Decision on `download --remote-compress`:

- It should be superseded by `--transfer-mode`.
- Task `5.2` should keep `--remote-compress` only as a deprecated compatibility
  alias:
  - `always` -> `single-file`
  - `never` -> `multi-file`
  - `auto` -> `auto`
- Help text and docs should move users to `--transfer-mode`.

### Meaning of `--streams`

`--streams` is the top-level concurrency budget. It does not expose SFTP packet
or prefetch tuning directly.

- In `single-file` mode:
  - `--streams` = number of stripes/parts processed concurrently
  - each active stripe gets its own SSH/SFTP worker
  - effective streams = `min(requested_streams, number_of_parts)`
- In `multi-file` mode:
  - `--streams` = number of concurrent whole-file workers
  - each worker transfers one file at a time and reuses the existing resume and
    checksum flow
  - effective streams = `min(requested_streams, number_of_files)`

Internal rule for `5.2`:

- Keep per-file SFTP request pipelining internal.
- Start with a conservative cap of 64 outstanding requests per file when the
  underlying library path supports it, matching the OpenSSH/Paramiko precedent.
- Do not add a second public flag for request-window tuning in Phase 5.

## Command Decisions

### Submit

`submit auto` should behave like this:

- If compression is enabled, choose `single-file`.
- If `--no-compress` is set, choose `multi-file`.

Rationale:

- The normal submit path already builds one `.tar.zst` payload, so `single-file`
  is the natural and lowest-risk acceleration target.
- When the operator explicitly disables compression, Launchpad no longer has a
  single payload, so `multi-file` is the correct automatic behavior.

Rules for explicit overrides:

- `submit --transfer-mode single-file` requires the archive-producing path.
- `submit --transfer-mode multi-file` requires `--no-compress`.
- If the operator requests `multi-file` without `--no-compress`, task `5.2`
  should fail fast with a clear validation error instead of silently changing
  packaging semantics.

### Download

`download auto` should behave like this:

- If remote `tar` and `zstd` are available, choose `single-file`.
- Otherwise choose `multi-file`.

Rationale:

- Download already has an archive path and a raw-tree path.
- The archive path is the closest match to the existing correctness model:
  one payload, one checksum, one extraction step.
- Falling back to `multi-file` when remote compression is unavailable preserves
  current functionality without blocking the operator.

Rules for explicit overrides:

- `download --transfer-mode single-file` forces remote archive creation and
  striped download of that archive.
- `download --transfer-mode multi-file` skips remote archive creation and
  downloads the selected remote files directly with a worker pool.

## Safe Implementation Strategy For `single-file`

The design requirement for `5.2` is explicit: deliver striped transfer without
depending on concurrent remote writes into one SFTP destination file.

### Submit `single-file`

1. Keep the current local archive creation step.
2. Split the local archive into deterministic temporary part files sized from
   `transfer.chunk_size_mb`.
3. Upload parts concurrently to a hidden remote staging directory such as:
   `.launchpad-transfer/<archive-name>/part-00000`
4. Resume per part:
   - matching remote size -> keep the part
   - missing or mismatched size -> re-upload that part only
5. After all parts are present, run one remote assembly step:
   - concatenate parts in order into `<archive>.partial`
   - verify final byte count
   - atomically rename to the final archive path
6. Only then run remote extraction.
7. Remove remote part files after the final archive is verified.

Why this is the chosen model:

- It avoids concurrent writes into one remote SFTP file handle.
- It keeps resume semantics deterministic.
- It lets Launchpad verify the final assembled archive before extraction.

### Download `single-file`

1. Create the remote archive as the current code already does.
2. Read the final archive size and divide it into deterministic byte ranges.
3. Download each range concurrently into local temporary part files.
4. Resume per part by size.
5. Concatenate parts locally into the final archive.
6. Verify checksum and extracted file count using the current archive path.
7. Remove temporary part files after verification succeeds.

Why this is the chosen model:

- The remote side only performs normal archive creation, not speculative
  multi-writer file mutation.
- Local assembly is easier to reason about and recover if interrupted.
- It keeps the existing archive verification flow largely intact.

## Safe Implementation Strategy For `multi-file`

`multi-file` is the worker-pool path for many discrete files.

Task `5.2` should:

- build a file manifest first
- enqueue only real files, not directories
- preserve directory layout exactly
- transfer whole files with `--streams` worker concurrency
- reuse current per-file resume logic
- keep checksum verification per file when enabled
- treat the transfer as failed if any file is missing, mismatched, or cannot be
  retried successfully

Mode-specific command behavior:

- `submit multi-file`
  - skip archive creation
  - create the remote job directory first
  - upload staged files directly into their final remote layout
  - skip remote extraction because there is no archive
- `download multi-file`
  - keep the current raw-tree path
  - parallelize the per-file downloads instead of forcing `--streams 1`

## Fallback And Server-Limit Rules

Task `5.2` should implement these rules exactly:

1. Treat the requested stream count as an upper bound, not a promise.
2. Never use more streams than there are parts/files to process.
3. Open stream workers lazily.
4. If the SSH server rejects additional sessions, channels, or SFTP operations:
   - log a warning
   - reduce concurrency
   - retry at the highest confirmed-good stream count
5. If concurrency has to fall all the way to `1`, continue in single-stream
   mode rather than failing, unless even the single-stream path fails.
6. Only fail the command immediately when:
   - the operator requested a logically invalid combination
   - the single-stream fallback also fails
   - checksum or size verification fails

This is the correct conservative behavior for Phase 5. Operators care more
about successful completion and safe resume than about strictly honoring the
requested parallelism number.

## Deferred Real-Cluster Validation Matrix

Real-cluster validation is deferred, not canceled. Once workstation cluster
access exists, the follow-up benchmark should measure:

1. `single-file` submit/download at `--streams 1`, `2`, `4`, and `8`
2. `multi-file` submit/download for a tree of many small and medium files
3. fallback behavior when the requested stream count exceeds the server limit
4. resume behavior after interrupted transfer in both modes
5. checksum and assembly correctness for striped archive paths

That validation should confirm throughput, failure modes, and the best default
stream counts, but it should not block task `5.2`.

## Task `5.2` Implementation Brief

Task `5.2` should leave the repository with:

- a shared transfer-mode abstraction used by submit and download
- public `--transfer-mode` and `--streams` support on both commands
- deprecated `download --remote-compress` compatibility mapping
- striped `single-file` upload/download using temporary part files plus final
  assembly
- worker-pool `multi-file` upload/download for loose file trees
- clear warnings and safe degradation when server limits reduce actual streams
- retained checksum, resume, and extraction verification behavior

## Implementation-Ready Recommendation

Phase 5 should keep the current resumable archive-first workflow as the
baseline, then extend it with a hybrid transport model:

- `single-file` for one logical payload, implemented via concurrent temporary
  parts plus verified final assembly
- `multi-file` for many discrete files, implemented via a worker pool
- `auto` as the default on both commands, resolving to `single-file` for the
  normal archive path and `multi-file` only when the workflow genuinely has no
  single payload or remote archive support is unavailable

That is the design task `5.2` should implement.
