# Launchpad CLI — Terminal UI Redesign Plan

> **Purpose:** Guide an AI coding agent (Codex) through a complete visual and
> interaction overhaul of Launchpad's Rich-based terminal output. The goal is a
> cohesive, modern, beautiful CLI that stands alongside Claude Code, Gemini CLI,
> Codex CLI, GitHub CLI (`gh`), and `uv` in polish and personality.
>
> **Stack constraint:** Python + Rich + rich-click. No TUI framework swap. All
> changes are to the `display.py` module and individual `cli/*.py` command files.

---

## 1. Design Philosophy

### 1.1 The Problem with the Current UI

The current Launchpad output relies heavily on Rich `Panel` and `Box` for every
piece of information. The result is:

- **Box fatigue.** Nearly every output is wrapped in a bordered box. Boxes stop
  being visual anchors when everything is a box — they become noise.
- **Dense, uniform hierarchy.** Doctor summary, check results, task references,
  and next steps all look the same. There is no breathing room and no
  typographic hierarchy to guide the eye.
- **Clunky proportions.** Box titles sit awkwardly. Tables inside panels create
  double-border nesting. The overall impression is "functional but homemade."

### 1.2 Design Principles for the New UI

These principles are ordered by priority:

1. **Breathe.** Use whitespace as a structural element. Not every group needs
   a border. A blank line and a subtle indent often communicate hierarchy better
   than a box.

2. **Hierarchy through typography, not containers.** Use bold, dim, color, and
   indentation to create visual levels. Reserve bordered panels for the single
   most important block in a command's output (the "hero card").

3. **Color is information, not decoration.** Every color must encode meaning:
   green = success/pass, red = failure/error, yellow = warning/pending,
   blue/cyan = informational emphasis, dim/grey = secondary metadata. No
   gratuitous color.

4. **Terse by default, verbose on demand.** Follow the `uv` model: the happy
   path should feel effortless and fast — a few tight lines of confirmation,
   not a wall of panels. Detail lives behind `--verbose`.

5. **Consistent visual grammar.** Every command should feel like it comes from
   the same tool. Shared prefix symbols, shared section spacing, shared color
   semantics. Define the grammar once in `display.py` and never deviate.

6. **Personality in restraint.** The CLI's personality comes from its
   confidence, conciseness, and conversational next-step suggestions — not from
   ASCII art or emoji overload. The Launchpad wordmark appears on the welcome
   screen and nowhere else.

---

## 2. Visual Grammar — The Design System

This section defines every reusable visual primitive. Codex should implement
these as functions/constants in `display.py` and use them across all commands.

### 2.1 Status Prefix Symbols

Replace the current `PASS`/`FAIL` badges inside boxes with inline prefix
symbols. These are the only symbols used across the entire CLI:

```
Symbol    Meaning              Rich markup
──────    ───────              ──────────
  ✓       Pass / Success       [bold green]✓[/]
  ✗       Fail / Error         [bold red]✗[/]
  ●       Running / Active     [bold green]●[/]
  ○       Pending / Waiting    [dim]○[/]
  ▲       Warning              [bold yellow]▲[/]
  —       Skipped / N/A        [dim]—[/]
  →       Next step / Action   [bold cyan]→[/]
```

These symbols are always followed by exactly two spaces, then the label. Labels
are **never** bold unless they are the primary identifier (e.g., a check name
or a job ID).

### 2.2 Color Palette

Define named color constants. All colors are semantic, never arbitrary:

```python
# display.py — top-level constants
C_SUCCESS  = "green"
C_ERROR    = "red"
C_WARN     = "yellow"
C_INFO     = "cyan"
C_ACCENT   = "blue"
C_DIM      = "dim"
C_MUTED    = "grey70"
C_LABEL    = "bold"
C_VALUE    = "white"
```

Rules:
- **Primary text:** default terminal foreground (no explicit color).
- **Labels / keys** in key-value pairs: `C_DIM` or `C_MUTED`.
- **Values:** default or `C_VALUE`.
- **Emphasis / identifiers:** `C_ACCENT` or `C_INFO`.
- **State colors:** Only `C_SUCCESS`, `C_ERROR`, `C_WARN` — never mixed.

### 2.3 Section Headers

Replace Rich `Panel(title=...)` for section grouping with lightweight headers:

```
  Local Setup
  ───────────────────────────────────────
```

Implementation: A Rich `Rule` with left-aligned text, styled `bold`, with the
rule line in `C_DIM`. One blank line before, no blank line after (content
starts on the next line).

```python
def section_header(title: str) -> None:
    """Print a thin ruled section header."""
    console.print()
    console.print(Rule(title, style=C_DIM, align="left"))
```

### 2.4 Key-Value Pairs

The most common pattern across all commands. Two styles:

**Inline (for compact metadata):**
```
  Run name        nastran-20260314-1749-fbc2
  Job ID          923
  Remote dir      /shared/launchpad/nastran-20260314-1749-fbc2
```

Implementation: Label right-padded to a fixed column width (16 chars), styled
`C_DIM`. Value is default color. Two-space left indent on every line.

```python
def kv(label: str, value: str, label_width: int = 16) -> None:
    """Print a key-value pair with aligned columns."""
    console.print(f"  [dim]{label:<{label_width}}[/] {value}")
```

**Stacked (for longer values or grouped metadata):**
```
  Transfer
    Mode            single-file
    Streams         requested 8, effective 1
    Payload         nastran-20260314-1749-fbc2.tar.zst
```

Implementation: Group label is printed as a `section_header` or bold line,
children are `kv()` calls with additional 2-space indent.

### 2.5 The Hero Card

One Rich `Panel` per command output — the **hero card**. This is the single
most important piece of information from the command. It should be visually
distinct because it's the only bordered element.

Rules:
- Border style: `ROUNDED` (the default Rich panel border).
- Border color: `C_ACCENT` (blue) for success, `C_ERROR` for failure.
- Title: short, descriptive, left-aligned.
- Padding: `(1, 2)` — one line top/bottom, two spaces left/right.
- Width: full terminal width minus 2 (Rich default).
- The hero card contains **only** the essential summary — not tables, not
  check lists, not next steps.

Example — `submit` hero card:
```
╭─ Submission Complete ─────────────────────────────────────────────────────╮
│                                                                           │
│  Run name        nastran-20260314-1749-fbc2                               │
│  Job ID          923                                                      │
│  Remote dir      /shared/launchpad/nastran-20260314-1749-fbc2             │
│                                                                           │
╰───────────────────────────────────────────────────────────────────────────╯
```

### 2.6 Tables

Tables should be **borderless** by default. Use column alignment and subtle
color to differentiate rows. Reserve bordered tables only for data-dense
displays where visual gridlines genuinely help scanning (e.g., multi-column
task references with 10+ rows).

**Default table style:**
```python
table = Table(
    show_header=True,
    header_style="bold",
    show_edge=False,
    show_lines=False,
    pad_edge=False,
    padding=(0, 2),
    box=None,
)
```

**Header row:** Bold text, no background color, no border. Use thin
`Rule`-style separator only if the table is visually ambiguous without it.

**Row alternation:** Not needed for short tables (<8 rows). For longer tables,
use `C_DIM` on even rows or a `dim` background.

### 2.7 Next Steps Block

Every command ends with actionable next steps. This replaces the current boxed
"Next Steps" panel with a lightweight list:

```
  Next
  → launchpad status 923
  → launchpad status 923 --watch
  → launchpad download 923
```

Implementation: `section_header("Next")` followed by lines prefixed with
`[bold cyan]→[/]`. Each suggestion is a copyable command.

### 2.8 Progress Bars

Use Rich's `Progress` with a custom minimal column set. The bar itself should
be short (30-40 chars), with speed and ETA on the right:

```
  Uploading   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  78%  142 MB/s  ETA 0:12
```

Bar color: `C_ACCENT` (blue). Completed bar: `C_SUCCESS` (green).
Do not wrap progress bars in panels or boxes.

### 2.9 Spinners

Use Rich's `Status` spinner for short indeterminate operations (SSH connect,
remote compress). Keep the message terse:

```
  ⠋ Connecting to cluster...
  ⠋ Compressing on remote...
```

After completion, replace the spinner line with a `✓` status line:
```
  ✓  Connected to 10.98.72.105
```

### 2.10 Error Display

Errors get a single-line red prefix followed by the message. Suggestions follow
as dim text. Never use a panel for errors — panels make errors feel
heavyweight and alarming when they might be simple fixes.

```
  ✗  Invalid literal for int(): 'simulation-r6i-8x-dy-r6i-8xlarger7-1'

     This looks like a SLURM node name, not a job ID.
     Launchpad expected a numeric job ID but received a node name
     from squeue output.

     Try: launchpad status 923
```

For fatal errors, use a single `Panel` with `C_ERROR` border — but this should
be rare (unhandled exceptions, crash reports).

---

## 3. Command-by-Command Redesign

### 3.1 `launchpad` (no arguments) — Welcome Screen

**Current:** Not shown in samples but likely a help dump.

**New:** A branded, minimal welcome screen. This is the one place the
Launchpad wordmark appears. Keep it tight — 5-6 lines max:

```

  Launchpad  v0.3.0

  Submit, monitor, and retrieve solver jobs on your SLURM cluster.

  → launchpad submit           Compress, upload, and submit a job
  → launchpad status [JOB_ID]  Check job status
  → launchpad doctor           Verify your setup

  Run launchpad -h for all commands.

```

Implementation notes:
- The word "Launchpad" is `[bold cyan]Launchpad[/]`, version is `[dim]`.
- The tagline is default color, no formatting.
- Command suggestions use the `→` prefix, command name in `bold`, description
  in `C_DIM`.
- No box, no ASCII art, no emoji. Confidence through restraint.

### 3.2 `launchpad doctor` — Diagnostics

**Current:** Three nested boxes (summary box, local setup box, cluster access
box) with `PASS`/`FAIL` badges. Feels heavy.

**New:** Flat list with status prefixes, grouped by section headers:

```

  Doctor
  ───────────────────────────────────────

  Local Setup
    ✓  Python Runtime              Python 3.12.2
    ✓  Config Resolution           C:\Users\srogachev\.launchpad\config.toml
    ✓  SSH Key                     C:\Users\srogachev\.ssh\jlansang.pem
    ✗  Shared Config               Not found: \shared\config\launchpad.toml
       Mount the shared /shared filesystem or rely on local config overrides.

  Cluster Access
    ✓  SSH Connection              10.98.72.105:22 as ubuntu
    ✓  Remote Binaries             sbatch, squeue, sacct, tar, zstd
    ✗  Writable Root               /shared/launchpad not writable
       Create the directory or set cluster.workspace_root in config.

  ───────────────────────────────────────
  7 checks: 5 passed, 2 failed

  Next
  → Fix the failed checks above, then re-run:
  → launchpad doctor

```

Implementation notes:
- Top `section_header("Doctor")`.
- Sub-sections ("Local Setup", "Cluster Access") are printed as bold lines with
  2-space indent, followed by check items at 4-space indent.
- Each check: status prefix + check name (bold, fixed-width ~24 chars) + value
  (dim or default based on importance).
- Failed checks: the error detail and suggestion are printed on the next line(s)
  at 7-space indent (aligned under the check name), styled `C_DIM`.
- Summary line: plain text, no box. `"7 checks: [green]5 passed[/], [red]2
  failed[/]"`.
- Next steps block at the bottom.

### 3.3 `launchpad submit` — Job Submission

**Current:** Three boxes — Submission Complete panel, Task References table-in-
panel, Next Steps panel.

**New:** Hero card for the submission summary + flat table for tasks + next
steps:

```

╭─ Submitted ───────────────────────────────────────────────────────────────╮
│                                                                           │
│  Run name   nastran-20260314-1749-fbc2                                    │
│  Job ID     923                                                           │
│  Remote     /shared/launchpad/nastran-20260314-1749-fbc2                  │
│                                                                           │
╰───────────────────────────────────────────────────────────────────────────╯

  Tasks
    Alias  Label           Input
    001    S1_LB4_10x16    S1_LB4_10x16.dat
    002    S1_LB4_10x24    S1_LB4_10x24.dat
    003    S1_LB4_20x16    S1_LB4_20x16.dat
    004    S1_LB4_20x24    S1_LB4_20x24.dat

  Transfer
    Mode        single-file
    Streams     requested 8 → effective 1
    Payload     nastran-20260314-1749-fbc2.tar.zst

  Next
  → launchpad status 923
  → launchpad status 923 --watch
  → launchpad download 923

```

Implementation notes:
- Hero card with `C_ACCENT` border. Title: "Submitted". Only the three most
  essential KV pairs inside.
- Tasks section: borderless `Table` with 4-space left indent. Alias column is
  `C_DIM`, Label is default bold, Input is `C_DIM`.
- Transfer section: `kv()` pairs nested under a bold group label.
- Strip "Task" column from the table — the alias IS the task reference. Remove
  the column that just shows SLURM array index since it's internal.

### 3.4 `launchpad status` — Job Status

**Current:** Not shown fully, but expected to be table-heavy.

**New:** Compact header + borderless status table:

```

  Job 923  nastran-20260314-1749-fbc2
  Array 0-3  Partition simulation-r6i-8x

  Alias  Label           State       Node          Elapsed   CPU%   Mem
  001    S1_LB4_10x16    ●  RUNNING  compute-dy-1  02:14:33   98%   187/236 GB
  002    S1_LB4_10x24    ●  RUNNING  compute-dy-2  02:14:33   95%   203/236 GB
  003    S1_LB4_20x16    ✓  COMPLETED compute-dy-3  01:45:12   97%   178/236 GB
  004    S1_LB4_20x24    ○  PENDING  —              —          —     —

  Summary: 2 running, 1 completed, 1 pending

  Next
  → launchpad logs 923 001
  → launchpad download 923

```

Implementation notes:
- Job header: Job ID in `bold`, run name in `C_INFO`. Second line for array
  range and partition in `C_DIM`.
- State column uses the status prefix symbols inline (●, ✓, ○) plus the state
  word. State words are colored: RUNNING=green, COMPLETED=blue, PENDING=dim,
  FAILED=red.
- Memory column: `used/total GB` format. Used is colored green if <80%, yellow
  if 80-95%, red if >95%.
- Summary line: counts colored by state.
- `--watch` mode: Use Rich's `Live` display to refresh the table in place.
  Clear the table and reprint — no flicker thanks to Rich's alternate screen
  handling.

### 3.5 `launchpad download` — Results Download

**Current:** Not shown, but per the plan, includes a pre-download confirmation.

**New:** Clean pre-download summary, then a progress bar, then a verification
summary:

**Pre-download:**
```

  Job 923  nastran-20260314-1749-fbc2
  4/4 tasks COMPLETED

  Remote results     47.3 GB across 4 task directories
  Compressed est.    ~11.8 GB (zstd level 3)
  Local free space   234.1 GB at C:\Projects\results_nastran-20260314-1749-fbc2

  Proceed? [Y/n]

```

**During download:**
```
  Compressing on remote...   done (11.4 GB)
  Downloading   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  78%  142 MB/s  ETA 0:12
```

**Post-download:**
```

  ✓  Download complete

  Local path     C:\Projects\results_nastran-20260314-1749-fbc2
  Size           47.3 GB (4 task directories)
  Integrity      ✓ all files verified

  Next
  → launchpad cleanup 923

```

### 3.6 `launchpad logs` — Log Streaming

**Current:** Not shown.

**New:** Minimal header, then raw log content. The chrome should disappear
while reading logs:

```
  Job 923 · Task 001 (S1_LB4_10x16) · SLURM log
  ───────────────────────────────────────

  [raw log content streams here...]
```

With `--follow`, the header stays sticky at the top if using Rich Live, or
simply prints once and then streams.

### 3.7 `launchpad cancel` — Job Cancellation

```
  Cancel job 923? This will cancel 2 running and 1 pending tasks. [y/N]

  ✓  Cancelled job 923

  001  S1_LB4_10x16    was RUNNING   → CANCELLED
  002  S1_LB4_10x24    was RUNNING   → CANCELLED
  003  S1_LB4_20x16    was COMPLETED → unchanged
  004  S1_LB4_20x24    was PENDING   → CANCELLED
```

### 3.8 `launchpad ls` — Remote File Listing

Follow the `eza`/`lsd` style — clean columns, subtle color for file types:

```
  /shared/launchpad/nastran-20260314-1749-fbc2

  Type  Name                                  Size     Modified
  dir   logs/                                 —        2026-03-14 17:49
  dir   results_S1_LB4_10x16_0/              12.3 GB  2026-03-14 19:02
  dir   results_S1_LB4_10x24_1/              11.8 GB  2026-03-14 19:15
  file  nastran-20260314-1749-fbc2.tar.zst     3.2 GB  2026-03-14 17:50
  file  submit.sh                              1.2 KB  2026-03-14 17:49
```

### 3.9 `launchpad cleanup` — Remote Cleanup

```
  Remote directories in /shared/launchpad

  #  Run Name                          Size     Age
  1  nastran-20260314-1749-fbc2        47.3 GB  2 days
  2  nastran-20260312-0930-b4e1        23.1 GB  4 days
  3  nastran-20260301-1100-c8d2        55.8 GB  13 days

  Delete which? (comma-separated numbers, or 'all') [none]:
```

### 3.10 `launchpad config show` — Config Display

```
  Resolved Configuration
  ───────────────────────────────────────

  Sources (highest to lowest priority)
    1. CLI flags
    2. Environment variables           LAUNCHPAD_HOST, LAUNCHPAD_USER
    3. User config                     C:\Users\srogachev\.launchpad\config.toml
    4. Shared config                   not found

  SSH
    host              10.98.72.105
    port              22
    username          ubuntu
    key_path          C:\Users\srogachev\.ssh\jlansang.pem

  Cluster
    shared_root       /shared
    partition         simulation-r6i-8x
    wall_time         99:00:00

  Transfer
    streams           8
    compression       level 3
    checksums         enabled

  Nastran
    executable        /shared/siemens/nastran2312/bin/nastran
    memory            236Gb
    cpus              12
```

### 3.11 `launchpad --help` — Root Help

Redesign with `rich-click` for clean grouped help:

```
  Usage: launchpad [OPTIONS] COMMAND

  Submit, monitor, and retrieve solver jobs on your SLURM cluster.

  Workflow
    submit       Compress, upload, and submit a job
    status       Check job status
    download     Download results from a completed job
    logs         Stream or view remote log files
    cancel       Cancel running or pending jobs

  Utilities
    doctor       Verify setup and diagnose issues
    config       View and manage configuration
    ls           List remote files and directories
    cleanup      Remove remote job directories
    ssh          Open an interactive SSH session

  Options
    -h, --help       Show this help
    --version        Show version
    -q, --quiet      Suppress non-essential output
    -v, --verbose    Increase output detail
    --no-color       Disable colors
    --json           Output structured JSON

```

---

## 4. Implementation Plan

### Phase A: Design System Foundation (display.py rewrite)

**Goal:** Build all shared primitives before touching any command.

1. **Define constants** at the top of `display.py`:
   - Color constants (`C_SUCCESS`, `C_ERROR`, etc.)
   - Status prefix symbols as a dict/enum
   - Default indent width (2 spaces)
   - Default label column width (16 chars)

2. **Implement primitive functions:**
   - `kv(label, value, label_width=16, indent=2)` — key-value pair
   - `status_line(symbol, label, detail="", indent=2)` — status prefix line
   - `section_header(title)` — ruled section header
   - `next_steps(commands: list[str])` — next steps block
   - `hero_panel(title, content: list[tuple[str,str]], border_color=C_ACCENT)` — the one allowed panel
   - `error_block(message, suggestion="")` — error display
   - `success_line(message)` — single-line success with ✓
   - `warning_line(message)` — single-line warning with ▲
   - `make_table(**kwargs)` — factory that returns a pre-styled borderless Table
   - `confirm(message, default=False)` — styled confirmation prompt

3. **Remove or deprecate** all existing panel-heavy display functions.

4. **Add a `theme.py` or section in `display.py`** that handles `NO_COLOR` and
   `--no-color` gracefully. When color is disabled, symbols degrade to text:
   `✓` → `PASS`, `✗` → `FAIL`, etc.

### Phase B: Doctor Redesign

Apply the design system to `doctor.py`:

1. Replace the three nested panels with `section_header` + `status_line` calls.
2. Group checks under "Local Setup" and "Cluster Access" sub-headers.
3. Failed check details: indented dim text with actionable suggestion.
4. Summary line: plain text count with colored numbers.
5. Next steps block at the bottom.

**Test:** Run `launchpad doctor` on a machine with some passing and some
failing checks. Verify visual hierarchy is clear at a glance.

### Phase C: Submit Redesign

1. Replace the three panels with: hero card → tasks table → transfer metadata
   → next steps.
2. Hero card: only run name, job ID, remote dir.
3. Tasks table: borderless, indented, with alias/label/input columns.
4. Transfer metadata: `kv()` pairs under a bold "Transfer" label.
5. The progress bar during upload should use the new minimal style.

### Phase D: Status Redesign

1. Job header as inline metadata (no panel).
2. Status table: borderless, with inline status symbols and colored state words.
3. Summary line after the table.
4. `--watch` mode: use `Rich.Live` to redraw the table in-place.

### Phase E: Download, Logs, Cancel, LS, Cleanup, Config

Apply the design system to all remaining commands. Each should follow the
patterns established in Phases B-D:

- No panels except one hero card per command (and many commands need none).
- Sections via `section_header`.
- Data via `kv()` and `make_table()`.
- State via `status_line()`.
- Actions via `next_steps()`.

### Phase F: Help & Welcome Screen

1. Configure `rich-click` to produce grouped, clean help output.
2. Implement the branded welcome screen for bare `launchpad` invocation.
3. Style `--help` for each command with examples.

### Phase G: Error Handling Polish

1. Audit every `except` block and error path.
2. Replace raw tracebacks with `error_block()`.
3. Ensure every error suggests a next step.
4. The `int()` parsing error in the current `status` output is a good test
   case — it should produce a clear, helpful message, not a Python ValueError.

---

## 5. Detailed Style Rules for Codex

These rules should be followed for every line of terminal output:

### Spacing Rules

- **Between sections:** One blank line.
- **Between a section header and its content:** Zero blank lines (content starts
  on the next line).
- **Between the last content line and the next section header:** One blank line.
- **Before the first output of a command:** One blank line.
- **After the last output of a command:** One blank line.
- **Inside a hero panel:** One blank line of vertical padding top and bottom
  (achieved via `padding=(1, 2)` on the Rich Panel).

### Indentation Rules

- **Base indent:** 2 spaces for all content.
- **Nested indent:** 4 spaces for items inside a named group.
- **Table indent:** 2 spaces (use Rich Table `padding` or manually prepend).
- **Error suggestion indent:** 5 spaces (aligned under the error message text,
  past the `✗  ` prefix).

### Typography Rules

- **Never** use ALL CAPS for state words in running text. Use title case:
  `Running`, `Completed`, `Failed`, `Pending`.
- **Bold** is reserved for: the most important identifier in a line (job ID,
  run name, check name), column headers, and section header text.
- **Dim** is used for: secondary metadata, labels in KV pairs, timestamps,
  aliases, suggestions after errors.
- **Italic** is not used (terminal italic support is inconsistent on Windows).

### Color Rules

- Never combine two foreground colors in the same word.
- Never use background colors except in progress bars.
- Status prefix symbols are always colored; the text after them is default
  unless it's a state word.
- State words are always colored to match their meaning.
- In `--no-color` mode, all meaning must still be conveyed through text and
  symbols alone.

### Panel Rules

- Maximum one `Panel` per command invocation.
- Panel border: `box.ROUNDED`.
- Panel border color: `C_ACCENT` (blue) for success/info, `C_ERROR` (red) for
  failure summaries.
- Panel title: left-aligned, bold, short (1-3 words).
- Panel content: `kv()` pairs or short text. Never nest a Table inside a Panel.
- Panel width: terminal width (Rich default). No explicit width constraint.

### Table Rules

- Default: no border, no edge, no lines.
- Headers: bold, no color, no background.
- Padding: `(0, 2)` — no vertical padding, 2-char column gap.
- Column alignment: left for text, right for numbers.
- If a table has more than 10 rows, add a dim alternating row style.
- Never put a table inside a Panel.

---

## 6. Reference: What Modern CLIs Get Right

These are the patterns observed in the best modern CLIs that Launchpad should
emulate:

### From `uv` (Astral)

- **Terse completion messages.** `Resolved 1 package in 167ms` — no box, no
  celebration, just the fact. Launchpad should aspire to this for the happy
  path.
- **Prefix symbols for state.** `+` for added, `-` for removed. Simple and
  scannable.
- **Timing info is inline**, not in a separate section.

### From Claude Code (Anthropic)

- **Markdown-style output** with syntax-highlighted code blocks.
- **Inline diffs** with color — green for additions, red for removals.
- **Tool calls are visually distinct** from output text using subtle
  indentation and dim labels.
- **Minimal chrome.** The tool stays out of the way and lets the content speak.

### From Codex CLI (OpenAI)

- **Full-screen TUI** for interactive mode, but **terse line output** for
  `exec` mode. Launchpad is closer to exec mode — every command should produce
  compact output and exit.
- **Diff rendering** uses color and `+`/`-` prefixes, not boxes.
- **Theming support** — users can pick color themes. Not required for V1 but
  the color constant approach makes it easy to add later.

### From GitHub CLI (`gh`)

- **Grouped help text** with clean alignment. Commands are grouped by domain
  ("Workflow", "Utilities") not listed alphabetically.
- **Conversational error messages.** "Could not find a pull request" rather
  than a stack trace.
- **JSON output mode** for every command, not just some.

### From Gemini CLI (Google)

- **Rebuilt rendering engine** to eliminate flicker and layout jumps.
  Launchpad doesn't need a custom renderer (Rich handles this), but the
  principle applies: never print-then-clear-then-reprint. Use `Rich.Live` for
  dynamic content.
- **Sticky headers** for long output. In `--watch` mode, the job header should
  remain visible.

### From Charm (Bubble Tea / Lip Gloss)

- **Component-based design.** Each visual element is a composable piece. The
  `display.py` primitive functions serve the same purpose in Python/Rich.
- **Playful but not childish.** Charm tools feel fun because they're polished,
  not because they're colorful. The polish comes from consistent spacing,
  alignment, and restraint.

---

## 7. Migration Notes

### What Changes

| Before (current)                     | After (new)                              |
|--------------------------------------|------------------------------------------|
| Rich Panel for every section         | One hero panel max; sections use headers |
| `PASS`/`FAIL` text badges in panels  | `✓`/`✗` inline prefix symbols           |
| Tables inside Panels                 | Borderless tables, never inside Panels   |
| Multiple boxes stacked vertically    | Flat layout with section rules           |
| Box-wrapped "Next Steps"             | `→` prefixed list with section header    |
| Dense, uniform visual weight         | Clear hierarchy through typography       |
| Error as traceback or raw message    | `error_block()` with suggestion          |
| No consistent spacing                | Strict 1-blank-line section separation   |

### What Stays

- Rich as the rendering library.
- rich-click for help formatting.
- All command names and flag interfaces.
- All data that's currently shown (nothing is removed, just reformatted).
- `--json`, `--quiet`, `--no-color` behavior.
- `--verbose` flag for additional detail.

### Backward Compatibility

- `--json` output is unaffected by visual changes (it's structured data).
- `--quiet` continues to suppress non-essential output.
- `--no-color` / `NO_COLOR` disables all ANSI codes. Symbols degrade to text
  equivalents.
- Non-TTY stdout (piped output) automatically disables color and formatting.

---

## 8. Acceptance Criteria

The redesign is complete when:

1. **Every command** uses only the primitives defined in `display.py`.
2. **No command** uses more than one Rich Panel.
3. **Every error** includes an actionable suggestion.
4. **Every command** ends with a next-steps block (where applicable).
5. **`launchpad doctor`** passes visual inspection: flat, scannable, clear
   hierarchy.
6. **`launchpad submit`** output fits in ~25 terminal lines for a 4-file job.
7. **`launchpad status`** table is readable at 80-column terminal width.
8. **`--no-color`** mode is fully functional and readable.
9. **`--json`** mode is unaffected.
10. **Spacing is consistent** across all commands — verified by visual
    inspection of full output.

---

## Appendix A: display.py Skeleton

```python
"""Shared terminal output primitives for the Launchpad CLI.

All command modules import from this module to ensure visual consistency.
No command should call console.print() directly with inline styles —
use the primitives below instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.theme import Theme

if TYPE_CHECKING:
    from collections.abc import Sequence

# ── Color semantics ──────────────────────────────────────────────────────
C_SUCCESS = "green"
C_ERROR = "red"
C_WARN = "yellow"
C_INFO = "cyan"
C_ACCENT = "blue"
C_DIM = "dim"
C_MUTED = "grey70"

# ── Status symbols ───────────────────────────────────────────────────────
SYM_PASS = f"[bold {C_SUCCESS}]✓[/]"
SYM_FAIL = f"[bold {C_ERROR}]✗[/]"
SYM_RUN = f"[bold {C_SUCCESS}]●[/]"
SYM_PEND = f"[{C_DIM}]○[/]"
SYM_WARN = f"[bold {C_WARN}]▲[/]"
SYM_SKIP = f"[{C_DIM}]—[/]"
SYM_NEXT = f"[bold {C_INFO}]→[/]"

# ── Console instance ─────────────────────────────────────────────────────
console = Console()


def kv(
    label: str,
    value: str,
    *,
    label_width: int = 16,
    indent: int = 2,
) -> None:
    """Print an aligned key-value pair.

    Args:
        label: Left-hand label (styled dim).
        value: Right-hand value.
        label_width: Column width for the label.
        indent: Leading space count.
    """
    pad = " " * indent
    console.print(f"{pad}[{C_DIM}]{label:<{label_width}}[/] {value}")


def status_line(
    symbol: str,
    label: str,
    detail: str = "",
    *,
    indent: int = 2,
) -> None:
    """Print a status-prefixed line (e.g., ✓  SSH Connection  10.0.1.50).

    Args:
        symbol: One of the SYM_* constants.
        label: Check or item name.
        detail: Optional trailing detail text.
        indent: Leading space count.
    """
    pad = " " * indent
    detail_str = f"  [{C_DIM}]{detail}[/]" if detail else ""
    console.print(f"{pad}{symbol}  [bold]{label}[/]{detail_str}")


def section_header(title: str) -> None:
    """Print a thin ruled section header with a blank line above."""
    console.print()
    console.print(
        Rule(title, style=C_DIM, align="left"),
    )


def next_steps(commands: Sequence[str]) -> None:
    """Print the trailing next-steps block.

    Args:
        commands: Shell commands or instructions to suggest.
    """
    section_header("Next")
    for cmd in commands:
        console.print(f"  {SYM_NEXT} {cmd}")
    console.print()


def hero_panel(
    title: str,
    rows: Sequence[tuple[str, str]],
    *,
    border_color: str = C_ACCENT,
    label_width: int = 14,
) -> None:
    """Print the single hero panel for a command's primary output.

    Args:
        title: Short panel title (1-3 words).
        rows: Key-value pairs to display inside.
        border_color: Rich color for the panel border.
        label_width: Column width for labels.
    """
    lines: list[str] = []
    for label, value in rows:
        lines.append(f"  [{C_DIM}]{label:<{label_width}}[/] {value}")
    content = "\n".join(lines)
    console.print(
        Panel(
            content,
            title=f"[bold]{title}[/]",
            title_align="left",
            border_style=border_color,
            padding=(1, 2),
        )
    )


def error_block(message: str, suggestion: str = "") -> None:
    """Print a formatted error with optional fix suggestion.

    Args:
        message: The error message.
        suggestion: Actionable fix suggestion.
    """
    console.print(f"  {SYM_FAIL}  {message}")
    if suggestion:
        console.print()
        for line in suggestion.strip().splitlines():
            console.print(f"     [{C_DIM}]{line}[/]")
    console.print()


def make_table(**kwargs: object) -> Table:
    """Create a pre-styled borderless table.

    Accepts all Rich Table kwargs as overrides.

    Returns:
        A Rich Table with the Launchpad default style.
    """
    defaults: dict[str, object] = {
        "show_header": True,
        "header_style": "bold",
        "show_edge": False,
        "show_lines": False,
        "pad_edge": False,
        "padding": (0, 2),
        "box": None,
    }
    defaults.update(kwargs)
    return Table(**defaults)  # type: ignore[arg-type]
```

---

## Appendix B: Checklist for Each Command

Use this checklist when redesigning each command file:

- [ ] Remove all `Panel(...)` calls except the hero card (if applicable).
- [ ] Replace inline `console.print(f"[bold]...")` with appropriate primitive.
- [ ] Replace `Table(box=box.ROUNDED, ...)` with `make_table()`.
- [ ] Add `section_header()` for each logical group.
- [ ] Add `next_steps()` at the end.
- [ ] Verify error paths use `error_block()`.
- [ ] Verify output fits 80-column width without wrapping.
- [ ] Test with `--no-color` — verify readability without ANSI codes.
- [ ] Test with `--json` — verify no visual output leaks into JSON mode.
- [ ] Test with `--quiet` — verify only essential output appears.
