# Phase Plan: Phase 11 — Transfer Progress Indicators

## Goal

Surface progress feedback at every long-running I/O step in `lp submit` and
`lp download`. Today, local compression and remote extraction are silent in
submit, and local decompression is silent in download. The download transfer
path already has a Rich progress bar; the submit upload path has none. Phase 11
closes all gaps using infrastructure that already exists in `display.py`.

## Scope

- Add `progress_callback` support to `upload_many()` and `striped_upload()` in
  `core/transfer.py` (mirroring the existing download pattern).
- Wire a spinner for local compression and remote extraction in `cli/submit.py`.
- Wire a determinate progress bar for the upload transfer in `cli/submit.py`.
- Wire a spinner for local decompression in `cli/download.py`.
- Use `asyncio.to_thread()` for blocking compression/decompression so spinners
  animate without blocking the event loop.

## Out of Scope

- Changes to the download transfer progress bar (already done).
- Changes to the download remote-compression spinner (already done).
- Per-stream or per-file breakdown views.
- Checksum verification progress feedback.
- New display primitives (reuse `build_progress` and `build_spinner` only).

## Entry Criteria

- `main` is clean after Phase 10 merge.
- No open task branches.

## Exit Criteria

- `lp submit` shows: spinner (compressing) → progress bar (uploading) → spinner
  (extracting on cluster).
- `lp download` shows: existing spinner (remote compress) → existing progress
  bar (download) → new spinner (extracting locally).
- All existing tests pass.
- No regressions to `upload_many` / `striped_upload` callers that omit the
  callback (backward-compatible optional parameter).

## Task Breakdown

| Task ID | Title | Why It Exists | Depends On |
|---------|-------|---------------|------------|
| 11.1 | Transfer progress indicators | Close all silent I/O gaps in submit and download | — |

## Risks

- `asyncio.to_thread()` requires Python 3.9+. The project already targets this
  baseline; no mitigation needed.
- `striped_upload` currently holds a `TemporaryDirectory` context over the
  `upload_many` call. Adding a progress callback through this path is purely
  additive; no structural change required.

## Notes

- Keep the single-task structure; the scope is narrow and well-understood.
- Builder should follow the `download_many` / `_run_with_download_progress`
  patterns exactly rather than inventing new abstractions.
