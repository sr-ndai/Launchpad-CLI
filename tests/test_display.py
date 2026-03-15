"""Focused tests for shared CLI display primitives."""

from __future__ import annotations

from rich.console import Console

from launchpad_cli.display import (
    build_console,
    build_error_block,
    build_hero_panel,
    build_inline_kv,
    build_logs_picker_panel,
    build_next_steps,
    build_status_entry,
    build_status_line,
    build_suggestion_line,
    make_table,
)


def _render(renderable, *, no_color: bool = False) -> str:
    console: Console = build_console(no_color=no_color)
    with console.capture() as capture:
        console.print(renderable)
    return capture.get()


def test_status_line_uses_symbol_when_color_output_is_enabled() -> None:
    """Semantic status lines should default to the new symbol grammar."""

    rendered = _render(build_status_line("success", "Connected", "cluster.example.com"))

    assert "✓  Connected cluster.example.com" in rendered


def test_status_line_uses_plain_text_fallback_when_color_is_disabled() -> None:
    """No-color flows should degrade symbols to text tokens."""

    rendered = _render(
        build_status_line("success", "Connected", "cluster.example.com", no_color=True),
        no_color=True,
    )

    assert "PASS  Connected cluster.example.com" in rendered


def test_next_steps_and_error_block_render_restrained_text_surfaces() -> None:
    """The Phase 9 next-step and error helpers should stay panel-free."""

    rendered_next = _render(build_next_steps(["launchpad status 12345"]))
    rendered_error = _render(
        build_error_block("Remote root is not writable.", "Set cluster.workspace_root and retry.")
    )

    assert "Next" in rendered_next
    assert "launchpad status 12345" in rendered_next
    assert "Remote root is not writable." in rendered_error
    assert "→ Set cluster.workspace_root and retry." in rendered_error
    assert "Set cluster.workspace_root and retry." in rendered_error


def test_hero_panel_and_table_factory_cover_shared_phase_nine_layout() -> None:
    """The hero panel and table factory should expose the new shared defaults."""

    panel_output = _render(build_hero_panel("Submission Complete", [("Job ID", "923"), ("Run name", "tank_v3")]))
    table = make_table()

    assert "Submission Complete" in panel_output
    assert "Job ID" in panel_output
    assert "923" in panel_output
    assert table.box is None
    assert table.show_edge is False
    assert table.pad_edge is False


def test_inline_kv_uses_wider_label_column_for_values() -> None:
    """Shared key/value rows should keep values bright and labels out of their way."""

    rendered = _render(build_inline_kv("host", "cluster.example.com"))

    assert "host                 cluster.example.com" in rendered


def test_status_entry_wraps_long_detail_and_suggestions_use_action_affordance() -> None:
    """Doctor-style status entries should drop long detail below the label."""

    rendered_entry = _render(
        build_status_entry(
            "success",
            "Config Resolution",
            "config.toml -> ssh.host=cluster.example.com, ssh.username=sergey",
        )
    )
    rendered_suggestion = _render(build_suggestion_line("Set ssh.key_path to a readable private key file."))

    assert "✓  Config Resolution" in rendered_entry
    assert "config.toml -> ssh.host=cluster.example.com, ssh.username=sergey" in rendered_entry
    assert rendered_entry.count("\n") >= 2
    assert "→ Set ssh.key_path to a readable private key file." in rendered_suggestion


def test_status_entry_indents_every_embedded_newline_in_detail_block() -> None:
    """Multiline detail should keep each continuation line inside the status gutter."""

    rendered = _render(build_status_entry("warn", "Connectivity", "line one\nline two"))

    assert "▲  Connectivity" in rendered
    assert "\n     line one" in rendered
    assert "\n     line two" in rendered


def test_logs_picker_panel_uses_restrained_text_guidance() -> None:
    """The interactive logs picker helper should stay on the corrected Phase 9 text hierarchy."""

    rendered = _render(build_logs_picker_panel(job_id="12345", log_kind="stdout", task_count=3))

    assert "Multiple task logs match this request." in rendered
    assert "job          12345" in rendered
    assert "log kind     stdout" in rendered
    assert "choices      3" in rendered
