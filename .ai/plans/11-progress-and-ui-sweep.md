# Phase Plan: Phase 11 — Progress Indicators & UI Consistency Sweep

## Goal

Two related improvements to the CLI's live feedback and visual consistency:

1. **Progress indicators (Task 11.1):** Surface spinners and progress bars at
   every long-running I/O step in `lp submit` and `lp download`. Today, local
   compression, upload, and remote extraction are all silent in submit; local
   decompression is silent in download.

2. **UI consistency sweep (Task 11.2):** Audit and fix every place the CLI
   bypasses the design system — raw `click.ClickException` messages without
   actionable suggestions, missing spinners in `ls`/`logs`/`cleanup`, and
   `click.echo("Interrupted.")` calls that ignore `--quiet`.

`display.py` and the rich-click configuration are already fully compliant with
the Phase 9 design system. Only the command files need updating.

## Scope

### Task 11.1 — Transfer progress indicators

- Add `progress_callback` to `upload_many()` and `striped_upload()` in
  `core/transfer.py`, mirroring the existing download callback pattern.
- Wire spinner for local compression in `lp submit` via `asyncio.to_thread()`.
- Wire determinate progress bar for the upload transfer in `lp submit` (both
  single-file and multi-file modes).
- Wire spinner for remote extraction in `lp submit`.
- Wire spinner for local decompression in `lp download` via `asyncio.to_thread()`.

### Task 11.2 — UI consistency sweep

- **Error messages:** Replace raw `click.ClickException(bare_string)` calls with
  messages that include an actionable suggestion where one is warranted. The
  ClickException mechanism itself stays — only the message content is improved.
- **Missing spinners:** Add spinners to non-transfer long-running operations that
  currently have none: `ls` recursive listing, `cleanup` remote discovery and
  size measurement, `logs` initial remote read before content appears.
- **Interrupted messages:** Fix `click.echo("Interrupted.")` in `status.py`,
  `logs.py`, and `download.py` — replace with `console.print(...)` so output
  respects `--no-color` and can be suppressed in `--quiet` mode.
- **Help text:** Ensure every command's `--help` docstring ends with a concrete
  example line and that no option is missing a `help=` string.

## Out of Scope

- Changes to `display.py` primitives (already fully compliant).
- Changes to `rich-click` theming in `__init__.py` (already correct).
- JSON output path changes.
- Redesigning any command's visual layout (Phase 9 completed that work).
- Per-stream or per-file progress breakdown views.
- Checksum verification progress.

## Entry Criteria

- `main` is clean after Phase 10 merge.
- No open task branches.

## Exit Criteria

- `lp submit` shows: spinner → progress bar → spinner (no silent steps).
- `lp download` shows: existing spinner → existing progress bar → new spinner.
- All `click.ClickException` messages in all commands include an actionable
  suggestion (where one exists and isn't obvious from the message alone).
- All `click.echo("Interrupted.")` replaced with `console.print(...)`.
- `ls`, `cleanup`, and `logs` show spinners during slow remote operations.
- All existing tests pass.

## Task Breakdown

| Task ID | Title | Why It Exists | Depends On |
|---------|-------|---------------|------------|
| 11.1 | Transfer progress indicators | Close all silent I/O gaps in submit and download | — |
| 11.2 | UI consistency sweep | Fix error messages, missing spinners, and quiet-mode leaks | 11.1 |

## Risks

- `asyncio.to_thread()` requires Python 3.9+. Project already targets this.
- 11.2 touches many files; Builder should make small, targeted changes rather
  than refactoring whole commands.
- Error message improvements are subjective — Builder should follow existing
  patterns in doctor.py where suggestions are most mature.

## Notes

- Phase branch was originally named `phase/11-transfer-progress-indicators`
  before 11.2 was added. Renamed to `phase/11-progress-and-ui-sweep` before
  first push.
- Task 11.2 depends on 11.1 to avoid merge conflicts in the same files
  (`submit.py`, `download.py`).
