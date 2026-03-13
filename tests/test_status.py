"""Tests for the `launchpad status` command and polling helpers."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from launchpad_cli.cli import cli
from launchpad_cli.cli import status as status_module


def test_status_command_renders_overview_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    """The status command should render a human-facing overview snapshot."""

    captured: dict[str, object] = {}

    monkeypatch.setattr(status_module, "configure_logging", lambda **kwargs: None)

    async def fake_run_status(**kwargs) -> status_module.StatusSnapshot:  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return status_module.StatusSnapshot(
            requested_job_id=None,
            queried_user="sergey",
            include_all=False,
            generated_at="2026-03-12 21:45:00",
            rows=(
                status_module.StatusRow(
                    job_id="12345",
                    task_id="2",
                    run_name="tank_v3",
                    state="RUNNING",
                    partition="simulation-r6i-8x",
                    node="compute-dy-2",
                    elapsed="00:10:00",
                ),
            ),
        )

    monkeypatch.setattr(status_module, "_run_status", fake_run_status)

    result = CliRunner().invoke(cli, ["status"])

    assert result.exit_code == 0
    assert captured["watch"] is False
    assert "tank_v3" in result.output
    assert "RUNNING" in result.output
    assert "12345" in result.output


def test_status_command_emits_json_for_specific_job(monkeypatch: pytest.MonkeyPatch) -> None:
    """The status command should expose a structured payload via the root JSON flag."""

    monkeypatch.setattr(status_module, "configure_logging", lambda **kwargs: None)

    async def fake_run_status(**kwargs) -> status_module.StatusSnapshot:  # type: ignore[no-untyped-def]
        return status_module.StatusSnapshot(
            requested_job_id="12345",
            queried_user="sergey",
            include_all=True,
            generated_at="2026-03-12 21:45:00",
            rows=(
                status_module.StatusRow(
                    job_id="12345",
                    task_id="0",
                    run_name="tank_v3",
                    state="COMPLETED",
                    partition="simulation-r6i-8x",
                    node="compute-dy-1",
                    elapsed="01:45:12",
                    total_cpu="17:33.221",
                    max_rss="178G",
                    remote_job_dir="/shared/sergey/tank_v3",
                ),
            ),
            run_name="tank_v3",
            partition="simulation-r6i-8x",
            array_range="0",
            remote_job_dir="/shared/sergey/tank_v3",
        )

    monkeypatch.setattr(status_module, "_run_status", fake_run_status)

    result = CliRunner().invoke(cli, ["--json", "status", "12345"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["requested_job_id"] == "12345"
    assert payload["run_name"] == "tank_v3"
    assert payload["state_counts"] == {"COMPLETED": 1}
    assert payload["rows"][0]["max_rss"] == "178G"


def test_status_command_watch_passes_interval_to_async_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    """Watch mode should delegate interval and callback handling to the async runner."""

    captured: dict[str, object] = {}

    monkeypatch.setattr(status_module, "configure_logging", lambda **kwargs: None)

    async def fake_run_status(**kwargs) -> status_module.StatusSnapshot:  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        snapshot = status_module.StatusSnapshot(
            requested_job_id="12345",
            queried_user="sergey",
            include_all=True,
            generated_at="2026-03-12 21:45:00",
            rows=(
                status_module.StatusRow(
                    job_id="12345",
                    task_id="0",
                    run_name="tank_v3",
                    state="RUNNING",
                    partition="simulation-r6i-8x",
                    node="compute-dy-1",
                    elapsed="00:12:00",
                ),
            ),
            run_name="tank_v3",
            partition="simulation-r6i-8x",
            array_range="0",
            remote_job_dir="/shared/sergey/tank_v3",
        )
        callback = kwargs.get("on_snapshot")
        if callable(callback):
            callback(snapshot)
        return snapshot

    monkeypatch.setattr(status_module, "_run_status", fake_run_status)

    result = CliRunner().invoke(cli, ["status", "12345", "--watch", "--interval", "5"])

    assert result.exit_code == 0
    assert captured["watch"] is True
    assert captured["interval"] == 5
    assert callable(captured["on_snapshot"])


@pytest.mark.asyncio
async def test_poll_status_repeats_until_max_iterations() -> None:
    """The polling helper should emit each snapshot and stop when instructed."""

    seen: list[str] = []
    sleep_calls: list[float] = []
    counter = 0

    async def fake_fetch() -> status_module.StatusSnapshot:
        nonlocal counter
        counter += 1
        return status_module.StatusSnapshot(
            requested_job_id=None,
            queried_user="sergey",
            include_all=False,
            generated_at=f"2026-03-12 21:45:0{counter}",
            rows=(
                status_module.StatusRow(
                    job_id=str(12340 + counter),
                    task_id=None,
                    run_name=f"run-{counter}",
                    state="RUNNING",
                ),
            ),
        )

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    snapshot = await status_module._poll_status(
        fake_fetch,
        interval=7,
        on_snapshot=lambda item: seen.append(item.rows[0].job_id),
        sleep=fake_sleep,
        max_iterations=2,
    )

    assert seen == ["12341", "12342"]
    assert sleep_calls == [7]
    assert snapshot.rows[0].job_id == "12342"
