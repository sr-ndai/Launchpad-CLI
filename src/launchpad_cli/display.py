"""Shared Rich display helpers for CLI-facing output."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence
from rich.console import Console, Group
from rich.padding import Padding
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.prompt import Confirm, Prompt
from rich.rule import Rule
from rich.status import Status
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from launchpad_cli import __version__
from launchpad_cli.core.job_manifest import TaskReference
from launchpad_cli.solvers import DiscoveredInput

PALETTE = {
    "ink": "#13212b",
    "slate": "#38586c",
    "mist": "#7f9aab",
    "ice": "#d9edf7",
    "cyan": "#3cc5d9",
    "green": "#5cc88b",
    "amber": "#f0b45a",
    "red": "#df6d57",
}

C_SUCCESS = PALETTE["green"]
C_ERROR = PALETTE["red"]
C_WARN = PALETTE["amber"]
C_INFO = PALETTE["cyan"]
C_ACCENT = PALETTE["cyan"]
C_MUTED = PALETTE["mist"]
C_LABEL = f"bold {PALETTE['ice']}"
C_VALUE = PALETTE["ice"]
DEFAULT_INDENT = 2
DEFAULT_LABEL_WIDTH = 16

LAUNCHPAD_THEME = Theme(
    {
        "lp.brand.primary": f"bold {PALETTE['ice']}",
        "lp.brand.secondary": f"bold {PALETTE['cyan']}",
        "lp.brand.accent": f"bold {PALETTE['amber']}",
        "lp.brand.subtle": f"dim {PALETTE['mist']}",
        "lp.rule": f"dim {PALETTE['mist']}",
        "lp.panel.border": PALETTE["cyan"],
        "lp.panel.border.success": PALETTE["green"],
        "lp.panel.border.warn": PALETTE["amber"],
        "lp.panel.border.danger": PALETTE["red"],
        "lp.section": f"bold {PALETTE['ice']}",
        "lp.badge.info": f"bold {PALETTE['ink']} on {PALETTE['cyan']}",
        "lp.badge.success": f"bold {PALETTE['ink']} on {PALETTE['green']}",
        "lp.badge.warn": f"bold {PALETTE['ink']} on {PALETTE['amber']}",
        "lp.badge.danger": f"bold {PALETTE['ice']} on {PALETTE['red']}",
        "lp.badge.neutral": f"bold {PALETTE['ink']} on {PALETTE['mist']}",
        "lp.label": f"bold {PALETTE['ice']}",
        "lp.value": PALETTE["ice"],
        "lp.text.label": f"bold {PALETTE['mist']}",
        "lp.text.detail": f"dim {PALETTE['mist']}",
        "lp.status.success": f"bold {PALETTE['green']}",
        "lp.status.error": f"bold {PALETTE['red']}",
        "lp.status.warn": f"bold {PALETTE['amber']}",
        "lp.status.info": f"bold {PALETTE['cyan']}",
        "lp.status.pending": f"dim {PALETTE['mist']}",
    }
)
STATUS_TONES = {
    "RUNNING": "info",
    "COMPLETED": "success",
    "PENDING": "warn",
    "FAILED": "danger",
    "CANCELLED": "danger",
    "TIMEOUT": "danger",
}
STATUS_SYMBOLS = {
    "success": ("✓", "PASS"),
    "error": ("✗", "FAIL"),
    "running": ("●", "RUN"),
    "pending": ("○", "WAIT"),
    "warn": ("▲", "WARN"),
    "muted": ("—", "N/A"),
    "next": ("→", "->"),
}
GET_STARTED_BREADCRUMB = (
    "Get started: launchpad config init -> doctor -> submit --dry-run ."
)
WELCOME_COMMANDS = (
    ("launchpad submit", "Compress, upload, and submit a job."),
    ("launchpad status [JOB_ID]", "Check job status."),
    ("launchpad doctor", "Verify your setup."),
)
_FULL_WORDMARK_LINES = (
    "    __                           __                    __",
    "   / /   ____ ___  ______  _____/ /_  ____  ____ _____/ /",
    "  / /   / __ `/ / / / __ \\/ ___/ __ \\/ __ \\/ __ `/ __  /",
    " / /___/ /_/ / /_/ / / / / /__/ / / / /_/ / /_/ / /_/ /",
    "/_____/\\__,_/\\__,_/_/ /_/\\___/_/ /_/ .___/\\__,_/\\__,_/",
    "                                  /_/",
)
_COMPACT_WORDMARK = "Launchpad"
ROOT_HELP_FOOTER = "Use launchpad <command> --help for command-specific examples."


def build_console(*, stderr: bool = False, no_color: bool = False) -> Console:
    """Create a Rich console with the repository's baseline output defaults."""

    return Console(stderr=stderr, no_color=no_color, theme=LAUNCHPAD_THEME)


def build_syntax_renderable(code: str, *, lexer: str) -> Syntax:
    """Return a syntax-highlighted block that respects the active console settings."""

    return Syntax(code, lexer, background_color="default", line_numbers=False, word_wrap=False)


def build_launchpad_wordmark(*, width: int | None = None) -> Text | None:
    """Return the welcome-screen wordmark or a compact fallback."""

    if width is not None and width < len(_COMPACT_WORDMARK):
        return None

    text = Text()
    if width is None or width >= max(len(line) for line in _FULL_WORDMARK_LINES):
        styles = (
            "lp.brand.primary",
            "lp.brand.secondary",
            "lp.brand.primary",
            "lp.brand.accent",
            "lp.brand.secondary",
            "lp.brand.secondary",
        )
        for line, style in zip(_FULL_WORDMARK_LINES, styles, strict=True):
            text.append(f"{line}\n", style=style)
        text.rstrip()
        return text

    text.append(_COMPACT_WORDMARK, style="lp.brand.primary")
    return text


def _symbol(name: str, *, no_color: bool = False) -> str:
    symbol, fallback = STATUS_SYMBOLS[name]
    return fallback if no_color else symbol


def _status_style(name: str, *, no_color: bool = False) -> str | None:
    if no_color:
        return None

    mapping = {
        "success": "lp.status.success",
        "error": "lp.status.error",
        "running": "lp.status.success",
        "pending": "lp.status.pending",
        "warn": "lp.status.warn",
        "muted": "lp.brand.subtle",
        "next": "lp.status.info",
    }
    return mapping.get(name)


def build_section_rule(title: str) -> Rule:
    """Return the restrained ruled section header introduced for Phase 9."""

    return Rule(title, style="lp.rule", align="left")


def build_inline_kv(
    label: str,
    value: object,
    *,
    label_width: int = DEFAULT_LABEL_WIDTH,
    indent: int = DEFAULT_INDENT,
) -> Text:
    """Return an aligned key/value line suitable for hero cards and summaries."""

    text = Text(" " * indent)
    text.append(f"{label:<{label_width}}", style="lp.text.label")
    text.append(f" {value}", style="lp.value")
    return text


def build_kv_group(
    rows: Sequence[tuple[str, object]],
    *,
    label_width: int = DEFAULT_LABEL_WIDTH,
    indent: int = DEFAULT_INDENT,
) -> Group:
    """Return a stack of aligned key/value rows."""

    return Group(
        *(build_inline_kv(label, value, label_width=label_width, indent=indent) for label, value in rows)
    )


def build_status_line(
    tone: str,
    label: str,
    detail: str | None = None,
    *,
    indent: int = DEFAULT_INDENT,
    label_width: int | None = None,
    no_color: bool = False,
    emphasize_label: bool = True,
) -> Text:
    """Return an inline status line with a symbol or no-color fallback token."""

    text = Text(" " * indent)
    text.append(_symbol(tone, no_color=no_color), style=_status_style(tone, no_color=no_color))
    text.append("  ")
    rendered_label = f"{label:<{label_width}}" if label_width is not None and label else label
    text.append(rendered_label, style="lp.label" if emphasize_label and not no_color else None)
    if detail:
        if label:
            text.append(" ")
        text.append(detail, style="lp.text.detail" if not no_color else None)
    return text


def build_action_line(
    command: str,
    detail: str | None = None,
    *,
    indent: int = DEFAULT_INDENT,
    no_color: bool = False,
) -> Text:
    """Return a copy-friendly action line used by welcome and next-step lists."""

    text = Text(" " * indent)
    text.append(_symbol("next", no_color=no_color), style=_status_style("next", no_color=no_color))
    text.append(" ")
    text.append(command, style="lp.label" if not no_color else None)
    if detail:
        text.append(f"  {detail}", style="lp.text.detail" if not no_color else None)
    return text


def build_next_steps(
    steps: Sequence[str],
    *,
    title: str = "Next",
    no_color: bool = False,
) -> Group:
    """Return the lightweight next-step list introduced for Phase 9."""

    renderables: list[Any] = [build_section_rule(title)]
    renderables.extend(build_action_line(step, no_color=no_color) for step in steps)
    return Group(*renderables)


def make_table(**kwargs: object) -> Table:
    """Create a pre-styled borderless table."""

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


def build_hero_panel(
    title: str,
    rows: Sequence[tuple[str, object]],
    *,
    tone: str = "accent",
    label_width: int = DEFAULT_LABEL_WIDTH,
) -> Panel:
    """Return the single emphasized summary panel allowed in the new grammar."""

    border_style = {
        "success": "lp.panel.border.success",
        "warn": "lp.panel.border.warn",
        "danger": "lp.panel.border.danger",
    }.get(tone, "lp.panel.border")
    return Panel(
        build_kv_group(rows, label_width=label_width),
        title=title,
        title_align="left",
        border_style=border_style,
        padding=(1, 2),
    )


def build_error_block(
    message: str,
    suggestion: str | None = None,
    *,
    no_color: bool = False,
) -> Group:
    """Return the restrained error block used by later Phase 9 tasks."""

    renderables: list[Any] = [build_status_line("error", "", message, no_color=no_color, emphasize_label=False)]
    if suggestion:
        for line in suggestion.splitlines():
            renderables.append(Text(f"     {line}", style="lp.text.detail" if not no_color else None))
    return Group(*renderables)


def build_success_line(message: str, *, no_color: bool = False) -> Text:
    """Return a single-line success message."""

    return build_status_line("success", "", message, no_color=no_color, emphasize_label=False)


def build_warning_line(message: str, *, no_color: bool = False) -> Text:
    """Return a single-line warning message."""

    return build_status_line("warn", "", message, no_color=no_color, emphasize_label=False)


def build_progress(
    *,
    console: Console | None = None,
    transient: bool = True,
) -> Progress:
    """Return the shared minimal progress bar configuration for later tasks."""

    return Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=32, complete_style=C_SUCCESS, finished_style=C_SUCCESS, style=C_ACCENT),
        TaskProgressColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=transient,
    )


def build_spinner(console: Console, message: str) -> Status:
    """Return the shared spinner surface for short indeterminate work."""

    return console.status(message, spinner="dots")


def confirm_action(message: str, *, default: bool = False) -> bool:
    """Prompt for confirmation using the shared builder-compatible surface."""

    return Confirm.ask(message, default=default)


def prompt_text(message: str, *, default: str | None = None) -> str:
    """Prompt for a text value using the shared builder-compatible surface."""

    if default is None:
        return Prompt.ask(message)
    return Prompt.ask(message, default=default)


def build_root_help_footer() -> Text:
    """Return the restrained root help footer."""

    return Text(ROOT_HELP_FOOTER, style="lp.text.detail")


def build_get_started_text(*, subdued: bool = False) -> Text:
    """Return the legacy onboarding breadcrumb for transitional compatibility."""

    style = "lp.brand.subtle" if subdued else "lp.brand.primary"
    return Text(GET_STARTED_BREADCRUMB, style=style)


def build_welcome_screen(
    *,
    show_wordmark: bool,
    width: int | None = None,
    no_color: bool = False,
) -> Group:
    """Build the restrained root welcome surface for bare `launchpad`."""

    renderables: list[Any] = []
    if show_wordmark:
        wordmark = build_launchpad_wordmark(width=width)
        if wordmark is not None:
            renderables.append(wordmark)
            renderables.append(Text(f"Launchpad  v{__version__}", style="lp.brand.subtle"))

    if not renderables:
        title = Text()
        title.append("Launchpad", style="lp.brand.secondary" if not no_color else None)
        title.append(f"  v{__version__}", style="lp.text.detail" if not no_color else None)
        renderables.append(title)

    renderables.append(Text())
    renderables.append(
        Text(
            "Submit, monitor, and retrieve solver jobs on your SLURM cluster.",
            style="lp.value" if not no_color else None,
        )
    )
    renderables.append(Text())
    for command, detail in WELCOME_COMMANDS:
        renderables.append(build_action_line(command, detail, no_color=no_color))
    renderables.append(Text())
    renderables.append(Text("Run launchpad -h for all commands.", style="lp.text.detail" if not no_color else None))
    return Group(*renderables)


def build_badge(label: str, *, tone: str = "neutral") -> Text:
    """Return a reusable pill-style status badge."""

    normalized = (
        tone if tone in {"info", "success", "warn", "danger", "neutral"} else "neutral"
    )
    return Text(f" {label.upper()} ", style=f"lp.badge.{normalized}")


def build_status_badge(state: object) -> Text:
    """Return the shared state badge used across later command surfaces."""

    text = str(state or "UNKNOWN").upper()
    tone = STATUS_TONES.get(text, "neutral")
    return build_badge(text, tone=tone)


def build_state_text(state: object, *, no_color: bool = False) -> Text:
    """Return an inline Phase 9 state label with symbol and color semantics."""

    text = str(state or "UNKNOWN").upper()
    symbol_name = {
        "RUNNING": "running",
        "COMPLETED": "success",
        "PENDING": "pending",
        "FAILED": "error",
        "CANCELLED": "error",
        "TIMEOUT": "error",
    }.get(text, "warn")
    style = {
        "RUNNING": "lp.status.success",
        "COMPLETED": "lp.status.info",
        "PENDING": "lp.status.pending",
        "FAILED": "lp.status.error",
        "CANCELLED": "lp.status.error",
        "TIMEOUT": "lp.status.error",
    }.get(text)

    state_text = Text()
    state_text.append(_symbol(symbol_name, no_color=no_color), style=_status_style(symbol_name, no_color=no_color))
    state_text.append("  ")
    state_text.append(text, style=style if not no_color else None)
    return state_text


def build_section_heading(title: str, *, detail: str | None = None) -> Text:
    """Return a reusable section heading."""

    heading = Text(title, style="lp.section")
    if detail:
        heading.append(f"  {detail}", style="lp.brand.subtle")
    return heading


def build_summary_table() -> Table:
    """Return the shared two-column summary grid."""

    table = Table.grid(padding=(0, 2))
    table.add_column(style="lp.label")
    table.add_column(style="lp.value")
    return table


def build_detail_panel(
    renderable,
    *,
    title: str,
    tone: str = "neutral",
    expand: bool = False,
) -> Panel:
    """Wrap a renderable in the shared Launchpad panel shell."""

    border_style = {
        "success": "lp.panel.border.success",
        "warn": "lp.panel.border.warn",
        "danger": "lp.panel.border.danger",
    }.get(tone, "lp.panel.border")
    return Panel(renderable, title=title, expand=expand, border_style=border_style)


def build_next_steps_panel(
    steps: Sequence[str],
    *,
    title: str = "Next Steps",
) -> Panel:
    """Render a simple shared next-step block for later Phase 7 tasks."""

    table = Table.grid(padding=(0, 1))
    for index, step in enumerate(steps, start=1):
        table.add_row(f"{index}.", step)
    return build_detail_panel(table, title=title)


def build_logs_picker_panel(
    *,
    job_id: str,
    log_kind: str,
    task_count: int,
) -> Panel:
    """Render the pre-picker panel for interactive `launchpad logs` flows."""

    intro = Text()
    intro.append("Multiple task logs match this request. ", style="lp.brand.secondary")
    intro.append(
        "Choose one task before Launchpad reads or follows the remote file.",
        style="lp.brand.subtle",
    )

    summary = build_summary_table()
    summary.add_row("Job", job_id)
    summary.add_row("Log kind", log_kind)
    summary.add_row("Choices", str(task_count))
    summary.add_row("Controls", "Up/Down to move, Enter to select, Ctrl+C to cancel")
    summary.add_row("Rows", "Label | Alias | Task | State | Kind | File")
    return build_detail_panel(Group(intro, summary), title="Task Picker")


def render_submit_dry_run(
    console: Console,
    *,
    run_name: str,
    solver_name: str,
    input_dir: Path,
    primary_inputs: Sequence[DiscoveredInput],
    task_references: Sequence[TaskReference],
    package_files: Sequence[Path],
    remote_job_dir: str,
    payload_label: str,
    transfer_mode: str,
    requested_streams: int,
    partition: str,
    time_limit: str,
    begin: str | None,
    script_preview: str,
) -> None:
    """Render the Phase 9 dry-run preview for `launchpad submit`."""

    no_color = bool(getattr(console, "no_color", False))
    console.print(
        build_hero_panel(
            "Submit Preview",
            [
                ("Run name", run_name),
                ("Solver", solver_name),
                ("Remote", remote_job_dir),
            ],
            label_width=12,
        )
    )
    console.print()
    console.print(Text("  Tasks", style="lp.label" if not no_color else None))
    manifest = make_table()
    manifest.add_column("Alias", style="lp.text.label")
    manifest.add_column("Label", style="lp.label")
    manifest.add_column("Input", style="lp.text.detail")
    for task_ref, item in zip(task_references, primary_inputs, strict=True):
        manifest.add_row(
            task_ref.alias,
            task_ref.display_label,
            item.relative_path.as_posix(),
        )
    console.print(Padding(manifest, (0, 0, 0, 2)))

    console.print()
    console.print(Text("  Transfer", style="lp.label" if not no_color else None))
    for label, value in (
        ("mode", transfer_mode),
        ("streams", str(requested_streams)),
        ("payload", payload_label),
        ("input_dir", str(input_dir)),
        ("partition", partition),
        ("time", time_limit),
        ("begin", begin or "immediate"),
    ):
        console.print(build_inline_kv(label, value, indent=4, label_width=14))

    if package_files:
        console.print()
        console.print(Text("  Payload", style="lp.label" if not no_color else None))
        package_table = make_table(show_header=False)
        package_table.add_column("Path", style="lp.text.detail")
        for path in package_files:
            package_table.add_row(str(path))
        console.print(Padding(package_table, (0, 0, 0, 2)))

    console.print()
    console.print(build_section_rule("Generated Script"))
    console.print(Padding(build_syntax_renderable(script_preview, lexer="bash"), (0, 0, 0, 2)))
    console.print()
    console.print(
        build_next_steps(
            [
                f"launchpad submit {input_dir}",
                "Adjust flags and rerun --dry-run if anything looks off.",
            ],
            no_color=no_color,
        )
    )


def render_submit_confirmation(
    console: Console,
    *,
    run_name: str,
    job_id: str,
    task_references: Sequence[TaskReference],
    remote_job_dir: str,
    payload_label: str,
    remote_payload_path: str,
    transfer_mode: str,
    requested_streams: int,
    effective_streams: int,
) -> None:
    """Render the Phase 9 submit confirmation surface."""

    no_color = bool(getattr(console, "no_color", False))
    console.print(
        build_hero_panel(
            "Submitted",
            [
                ("Run name", run_name),
                ("Job ID", job_id),
                ("Remote", remote_job_dir),
            ],
            tone="success",
            label_width=12,
        )
    )
    console.print()
    console.print(Text("  Tasks", style="lp.label" if not no_color else None))
    references = make_table()
    references.add_column("Alias", style="lp.text.label")
    references.add_column("Label", style="lp.label")
    references.add_column("Input", style="lp.text.detail")
    for task_ref in task_references:
        references.add_row(
            task_ref.alias,
            task_ref.display_label,
            task_ref.input_relative_path,
        )
    console.print(Padding(references, (0, 0, 0, 2)))
    console.print()
    console.print(Text("  Transfer", style="lp.label" if not no_color else None))
    for label, value in (
        ("mode", transfer_mode),
        ("streams", f"requested {requested_streams} -> effective {effective_streams}"),
        ("payload", payload_label),
        ("remote_payload", remote_payload_path),
    ):
        console.print(build_inline_kv(label, value, indent=4, label_width=16))
    console.print()
    console.print(
        build_next_steps(
            [
                f"launchpad status {job_id}",
                f"launchpad status {job_id} --watch",
                f"launchpad download {job_id}",
            ],
            no_color=no_color,
        )
    )


def build_status_renderable(
    *,
    requested_job_id: str | None,
    queried_user: str | None,
    include_all: bool,
    generated_at: str,
    run_name: str | None,
    partition: str | None,
    array_range: str | None,
    remote_job_dir: str | None,
    state_counts: Mapping[str, int],
    rows: Sequence[Mapping[str, object]],
    watch_mode: bool = False,
    refresh_interval: int | None = None,
    no_color: bool = False,
):
    """Build the Rich renderable used by `launchpad status`."""

    if requested_job_id:
        return _build_job_detail_renderable(
            requested_job_id=requested_job_id,
            generated_at=generated_at,
            run_name=run_name,
            partition=partition,
            array_range=array_range,
            remote_job_dir=remote_job_dir,
            state_counts=state_counts,
            rows=rows,
            watch_mode=watch_mode,
            refresh_interval=refresh_interval,
            no_color=no_color,
        )

    return _build_status_overview_renderable(
        queried_user=queried_user,
        include_all=include_all,
        generated_at=generated_at,
        state_counts=state_counts,
        rows=rows,
        watch_mode=watch_mode,
        refresh_interval=refresh_interval,
        no_color=no_color,
    )


def _build_status_overview_renderable(
    *,
    queried_user: str | None,
    include_all: bool,
    generated_at: str,
    state_counts: Mapping[str, int],
    rows: Sequence[Mapping[str, object]],
    watch_mode: bool,
    refresh_interval: int | None,
    no_color: bool,
) -> Group:
    renderables: list[Any] = []
    if watch_mode:
        renderables.append(
            build_status_line(
                "running",
                "Watching",
                f"current jobs with a {refresh_interval}s refresh cadence.",
                no_color=no_color,
            )
        )
        renderables.append(Text())
    else:
        renderables.append(build_section_rule("Status"))

    renderables.append(build_inline_kv("user", queried_user or "configured user", indent=2, label_width=12))
    renderables.append(
        build_inline_kv(
            "scope",
            "active + recent completed" if include_all else "active only",
            indent=2,
            label_width=12,
        )
    )
    renderables.append(build_inline_kv("updated", generated_at, indent=2, label_width=12))

    if not rows:
        renderables.append(Text())
        renderables.append(
            build_warning_line(
                "No matching SLURM jobs were found. If you expected older jobs, rerun with --all.",
                no_color=no_color,
            )
        )
        renderables.append(Text())
        renderables.append(build_next_steps(["launchpad status --all", "launchpad doctor"], no_color=no_color))
        return Group(*renderables)

    renderables.append(Text())
    table = make_table()
    table.add_column("Job", justify="right")
    table.add_column("Task", justify="right")
    table.add_column("Name")
    table.add_column("State")
    table.add_column("Partition")
    table.add_column("Node")
    table.add_column("Elapsed")

    for row in rows:
        table.add_row(
            str(row.get("job_id") or "—"),
            str(row.get("task_id") or "—"),
            str(row.get("run_name") or "—"),
            build_state_text(row.get("state"), no_color=no_color),
            str(row.get("partition") or "—"),
            str(row.get("node") or "—"),
            str(row.get("elapsed") or "—"),
        )

    renderables.append(Padding(table, (0, 0, 0, 2)))
    renderables.append(Text())
    renderables.append(_build_summary_text(state_counts, no_color=no_color))
    renderables.append(Text())
    renderables.append(build_next_steps(["launchpad status --all", "launchpad doctor"], no_color=no_color))
    return Group(*renderables)


def _build_job_detail_renderable(
    *,
    requested_job_id: str,
    generated_at: str,
    run_name: str | None,
    partition: str | None,
    array_range: str | None,
    remote_job_dir: str | None,
    state_counts: Mapping[str, int],
    rows: Sequence[Mapping[str, object]],
    watch_mode: bool,
    refresh_interval: int | None,
    no_color: bool,
) -> Group:
    renderables: list[Any] = []
    if watch_mode:
        renderables.append(
            build_status_line(
                "running",
                "Watching",
                f"job {requested_job_id} with a {refresh_interval}s refresh cadence.",
                no_color=no_color,
            )
        )
        renderables.append(Text())

    header = Text("  ")
    header.append(f"Job {requested_job_id}", style="lp.label" if not no_color else None)
    if run_name:
        header.append(f"  {run_name}", style="lp.status.info" if not no_color else None)
    renderables.append(header)

    detail_line = Text("  ")
    detail_line.append(f"Array {array_range or '—'}", style="lp.text.label" if not no_color else None)
    detail_line.append(f"  Partition {partition or '—'}", style="lp.text.label" if not no_color else None)
    detail_line.append(f"  Updated {generated_at}", style="lp.text.detail" if not no_color else None)
    renderables.append(detail_line)
    if remote_job_dir:
        renderables.append(build_inline_kv("remote", remote_job_dir, indent=2, label_width=12))
    renderables.append(Text())

    table = make_table()
    table.add_column("Alias", style="lp.text.label")
    table.add_column("Label", style="lp.label")
    table.add_column("State")
    table.add_column("Node")
    table.add_column("Elapsed")

    include_cpu = any(row.get("total_cpu") for row in rows)
    include_mem = any(row.get("max_rss") for row in rows)
    if include_cpu:
        table.add_column("CPU")
    if include_mem:
        table.add_column("Max RSS")

    for row in rows:
        columns = [
            str(row.get("alias") or row.get("task_id") or "—"),
            str(row.get("display_label") or row.get("task_id") or "—"),
            build_state_text(row.get("state"), no_color=no_color),
            str(row.get("node") or "—"),
            str(row.get("elapsed") or "—"),
        ]
        if include_cpu:
            columns.append(str(row.get("total_cpu") or "—"))
        if include_mem:
            columns.append(str(row.get("max_rss") or "—"))
        table.add_row(*columns)

    renderables.append(Padding(table, (0, 0, 0, 2)))
    renderables.append(Text())
    renderables.append(_build_summary_text(state_counts, no_color=no_color))
    renderables.append(Text())
    first_alias = next((str(row.get("alias")) for row in rows if row.get("alias")), None)
    next_steps = [f"launchpad download {requested_job_id}"]
    if first_alias:
        next_steps.insert(0, f"launchpad logs {requested_job_id} {first_alias}")
    else:
        next_steps.insert(0, f"launchpad status {requested_job_id} --watch")
    renderables.append(build_next_steps(next_steps, no_color=no_color))
    return Group(*renderables)


def _format_state_counts(counts: Mapping[str, int]) -> str:
    if not counts:
        return "no jobs"
    return ", ".join(f"{count} {state.lower()}" for state, count in counts.items())


def _build_summary_text(counts: Mapping[str, int], *, no_color: bool) -> Text:
    summary = Text("  Summary: ")
    if not counts:
        summary.append("no jobs", style="lp.text.detail" if not no_color else None)
        return summary

    segments: list[Text] = []
    for state, count in counts.items():
        part = Text()
        style = {
            "RUNNING": "lp.status.success",
            "COMPLETED": "lp.status.info",
            "PENDING": "lp.status.pending",
            "FAILED": "lp.status.error",
            "CANCELLED": "lp.status.error",
            "TIMEOUT": "lp.status.error",
        }.get(state)
        part.append(str(count), style=style if not no_color else None)
        part.append(f" {state.lower()}")
        segments.append(part)

    for index, part in enumerate(segments):
        if index:
            summary.append(", ")
        summary.append_text(part)
    return summary
