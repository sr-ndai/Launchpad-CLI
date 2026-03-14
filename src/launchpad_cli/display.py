"""Shared Rich display helpers for CLI-facing output."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

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
LAUNCHPAD_THEME = Theme(
    {
        "lp.brand.primary": f"bold {PALETTE['ice']}",
        "lp.brand.secondary": f"bold {PALETTE['cyan']}",
        "lp.brand.accent": f"bold {PALETTE['amber']}",
        "lp.brand.subtle": f"dim {PALETTE['mist']}",
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
GET_STARTED_BREADCRUMB = (
    "Get started: launchpad config init -> doctor -> submit --dry-run ."
)
WELCOME_COMMANDS = (
    ("submit", "Package a run and preview the SLURM handoff."),
    ("status", "Watch the queue and inspect task state."),
    ("download", "Pull completed results back to your machine."),
    ("doctor", "Check config, SSH, and cluster readiness."),
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


def build_console(*, stderr: bool = False, no_color: bool = False) -> Console:
    """Create a Rich console with the repository's baseline output defaults."""

    return Console(stderr=stderr, no_color=no_color, theme=LAUNCHPAD_THEME)


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


def build_get_started_text(*, subdued: bool = False) -> Text:
    """Return the shared Phase 7 onboarding breadcrumb."""

    style = "lp.brand.subtle" if subdued else "lp.brand.primary"
    return Text(GET_STARTED_BREADCRUMB, style=style)


def build_welcome_screen(*, show_wordmark: bool, width: int | None = None) -> Group:
    """Build the non-interactive root welcome surface."""

    commands = Table.grid(padding=(0, 2))
    commands.add_column(style="lp.label", no_wrap=True)
    commands.add_column(style="lp.value")
    for name, detail in WELCOME_COMMANDS:
        commands.add_row(name, detail)

    renderables = []
    if show_wordmark:
        wordmark = build_launchpad_wordmark(width=width)
        if wordmark is not None:
            renderables.append(wordmark)
    renderables.append(
        Text("From folder to cluster in one command.", style="lp.brand.secondary")
    )
    renderables.append(
        Text(
            "Use launchpad <command> --help for command-specific help.",
            style="lp.brand.subtle",
        )
    )
    renderables.append(build_detail_panel(commands, title="Key Commands"))
    renderables.append(build_get_started_text())
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
    """Render a Rich dry-run preview for `launchpad submit`."""

    intro = Text()
    intro.append("Ready to stage this run. ", style="lp.brand.secondary")
    intro.append(
        "Nothing has been uploaded yet; review the manifest and script below.",
        style="lp.brand.subtle",
    )

    summary = build_summary_table()
    summary.add_row("Run name", run_name)
    summary.add_row("Solver", solver_name)
    summary.add_row("Input dir", str(input_dir))
    summary.add_row("Transfer mode", transfer_mode)
    summary.add_row("Streams", str(requested_streams))
    summary.add_row("Payload", payload_label)
    summary.add_row("Remote job dir", remote_job_dir)
    summary.add_row("Partition", partition)
    summary.add_row("Time", time_limit)
    summary.add_row("Begin", begin or "immediate")

    manifest = Table(title="Detected Inputs", show_header=True, header_style="bold")
    manifest.add_column("Label")
    manifest.add_column("Alias")
    manifest.add_column("Task", justify="right")
    manifest.add_column("Primary input")
    manifest.add_column("Size (bytes)", justify="right")
    for task_ref, item in zip(task_references, primary_inputs, strict=True):
        manifest.add_row(
            task_ref.display_label,
            task_ref.alias,
            task_ref.task_id,
            item.relative_path.as_posix(),
            str(item.size_bytes),
        )

    package_table = Table(title="Payload Contents", show_header=True, header_style="bold")
    package_table.add_column("Path")
    for path in package_files:
        package_table.add_row(str(path))

    console.print(build_detail_panel(Group(intro, summary), title="Submit Preview"))
    console.print(manifest)
    console.print(package_table)
    console.print(build_detail_panel(script_preview, title="Generated SLURM Script"))
    console.print(
        build_next_steps_panel(
            [
                f"launchpad submit {input_dir}",
                "Adjust flags and rerun --dry-run if anything looks off.",
            ],
            title="If This Looks Right",
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
    """Render the Rich submit confirmation panel."""

    intro = Text()
    intro.append("Submission accepted. ", style="lp.brand.secondary")
    intro.append("Use the job ID below as the anchor for the rest of the workflow.", style="lp.brand.subtle")

    summary = build_summary_table()
    summary.add_row("Run name", run_name)
    summary.add_row("Job ID", job_id)
    summary.add_row("Remote job dir", remote_job_dir)
    summary.add_row("Transfer mode", transfer_mode)
    summary.add_row(
        "Streams", f"requested {requested_streams}, effective {effective_streams}"
    )
    summary.add_row("Payload", payload_label)
    summary.add_row("Remote payload", remote_payload_path)

    console.print(
        build_detail_panel(Group(intro, summary), title="Submission Complete", tone="success")
    )
    if len(task_references) > 1:
        references = Table(show_header=True, header_style="bold")
        references.add_column("Label")
        references.add_column("Alias")
        references.add_column("Task", justify="right")
        references.add_column("Input")
        for task_ref in task_references:
            references.add_row(
                task_ref.display_label,
                task_ref.alias,
                task_ref.task_id,
                task_ref.input_relative_path,
            )
        console.print(build_detail_panel(references, title="Task References"))
    console.print(
        build_next_steps_panel(
            [
                f"launchpad status {job_id}",
                f"launchpad status {job_id} --watch",
                f"launchpad download {job_id}",
            ]
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
        )

    return _build_status_overview_renderable(
        queried_user=queried_user,
        include_all=include_all,
        generated_at=generated_at,
        state_counts=state_counts,
        rows=rows,
        watch_mode=watch_mode,
        refresh_interval=refresh_interval,
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
) -> Group:
    title = "Live Status" if watch_mode else "Status Overview"
    if watch_mode:
        intro = Text()
        intro.append("Watching", style="lp.brand.secondary")
        intro.append(
            f" current jobs with a {refresh_interval}s refresh cadence.",
            style="lp.brand.subtle",
        )
    else:
        intro = Text("Current queue snapshot for the configured operator.", style="lp.brand.subtle")

    summary = build_summary_table()
    summary.add_row("User", queried_user or "configured user")
    summary.add_row(
        "Scope", "active + recent completed" if include_all else "active only"
    )
    summary.add_row("Updated", generated_at)
    summary.add_row("Rows", str(len(rows)))
    summary.add_row("Summary", _format_state_counts(state_counts))

    if not rows:
        empty = build_detail_panel(
            "No matching SLURM jobs were found. If you expected older jobs, rerun with `--all`.",
            title="Nothing To Show",
            tone="warn",
        )
        return Group(
            build_detail_panel(Group(intro, summary), title=title),
            empty,
            build_next_steps_panel(
                ["launchpad status --all", "launchpad doctor"],
                title="Try Next",
            ),
        )

    table = Table(title="Jobs", show_header=True, header_style="bold")
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
            build_status_badge(row.get("state")),
            str(row.get("partition") or "—"),
            str(row.get("node") or "—"),
            str(row.get("elapsed") or "—"),
        )

    return Group(build_detail_panel(Group(intro, summary), title=title), table)


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
) -> Group:
    title = "Live Job Status" if watch_mode else "Job Status"
    intro = Text()
    if watch_mode:
        intro.append("Watching", style="lp.brand.secondary")
        intro.append(
            f" job {requested_job_id} with a {refresh_interval}s refresh cadence.",
            style="lp.brand.subtle",
        )
    else:
        intro.append(f"Job {requested_job_id}", style="lp.brand.secondary")
        intro.append(" detail across the active and accounting views.", style="lp.brand.subtle")

    summary = build_summary_table()
    summary.add_row("Job", requested_job_id)
    summary.add_row("Run name", run_name or "—")
    summary.add_row("Partition", partition or "—")
    summary.add_row("Array", array_range or "—")
    summary.add_row("Remote job dir", remote_job_dir or "—")
    summary.add_row("Updated", generated_at)
    summary.add_row("Summary", _format_state_counts(state_counts))

    table = Table(title="Tasks", show_header=True, header_style="bold")
    table.add_column("Label")
    table.add_column("Alias")
    table.add_column("Task", justify="right")
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
            str(row.get("display_label") or row.get("task_id") or "—"),
            str(row.get("alias") or "—"),
            str(row.get("task_id") or "—"),
            build_status_badge(row.get("state")),
            str(row.get("node") or "—"),
            str(row.get("elapsed") or "—"),
        ]
        if include_cpu:
            columns.append(str(row.get("total_cpu") or "—"))
        if include_mem:
            columns.append(str(row.get("max_rss") or "—"))
        table.add_row(*columns)

    return Group(
        build_detail_panel(Group(intro, summary), title=title),
        table,
        build_next_steps_panel(
            [
                f"launchpad status {requested_job_id} --watch",
                f"launchpad download {requested_job_id}",
            ],
            title="Next Commands",
        ),
    )


def _format_state_counts(counts: Mapping[str, int]) -> str:
    if not counts:
        return "no jobs"
    return ", ".join(f"{state.lower()}={count}" for state, count in counts.items())
