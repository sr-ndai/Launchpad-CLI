"""Tests for the `launchpad download` command and orchestration helpers."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner
from rich.console import Console

from launchpad_cli.cli import cli
from launchpad_cli.cli import download as download_module
from launchpad_cli.core.compress import ArchiveEntry, ArchiveInspection
from launchpad_cli.core.config import LaunchpadConfig, ResolvedConfig, SSHConfig
from launchpad_cli.core.job_manifest import JobManifest, TaskReference
from launchpad_cli.core.remote_ops import RemotePathEntry
from launchpad_cli.display import LAUNCHPAD_THEME, build_console


def _recording_console(*, no_color: bool = True) -> Console:
    """Return a Rich console that captures rendered download output for assertions."""

    return Console(record=True, no_color=no_color, theme=LAUNCHPAD_THEME, width=120)


def test_download_command_passes_documented_options_to_async_runner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The CLI should expose the Phase 4 download surface and pass options through."""

    captured: dict[str, object] = {}

    monkeypatch.setattr(download_module, "configure_logging", lambda **kwargs: None)

    async def fake_run_download(**kwargs) -> download_module.DownloadResult:  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return download_module.DownloadResult(
            job_id="12345",
            run_name="tank_v3",
            destination_dir=tmp_path / "results_tank_v3",
            remote_job_dir="/shared/sergey/tank_v3",
            transfer_mode="single-file",
            requested_streams=4,
            effective_streams=2,
            downloaded_bytes=1024,
            file_count=3,
            cleaned_up=True,
            selected_tasks=("0", "2"),
            partial=False,
            checksums_verified=True,
            result_size_bytes=4096,
            source_count=2,
        )

    monkeypatch.setattr(download_module, "_run_download", fake_run_download)

    result = CliRunner().invoke(
        cli,
        [
            "download",
            "12345",
            str(tmp_path / "custom-output"),
            "--cleanup",
            "--force",
            "--exclude",
            "*.tmp",
            "--include-scratch",
            "--transfer-mode",
            "single-file",
            "--tasks",
            "2,0",
            "--streams",
            "4",
            "--compression-level",
            "7",
        ],
    )

    assert result.exit_code == 0
    assert captured["job_id"] == "12345"
    assert captured["cleanup"] is True
    assert captured["force"] is True
    assert captured["include_scratch"] is True
    assert captured["transfer_mode"] == "single-file"
    assert captured["remote_compress"] is None
    assert captured["tasks"] == "2,0"
    assert captured["streams"] == 4
    assert captured["compression_level"] == 7
    assert captured["exclude_patterns"] == ("*.tmp",)
    assert captured["local_dir"] == tmp_path / "custom-output"
    assert captured["json_output"] is False
    assert "Download complete" in result.output
    assert "Local path" in result.output
    assert "Integrity" in result.output
    assert "launchpad status 12345" in result.output


def test_download_command_emits_json_when_global_flag_is_set(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The download command should honor the root CLI's `--json` flag."""

    monkeypatch.setattr(download_module, "configure_logging", lambda **kwargs: None)

    async def fake_run_download(**kwargs) -> download_module.DownloadResult:  # type: ignore[no-untyped-def]
        assert kwargs["json_output"] is True
        return download_module.DownloadResult(
            job_id="12345",
            run_name="tank_v3",
            destination_dir=tmp_path / "results_tank_v3",
            remote_job_dir="/shared/sergey/tank_v3",
            transfer_mode="single-file",
            requested_streams=4,
            effective_streams=4,
            downloaded_bytes=1024,
            file_count=3,
            cleaned_up=False,
            selected_tasks=("0",),
            partial=False,
        )

    monkeypatch.setattr(download_module, "_run_download", fake_run_download)

    result = CliRunner().invoke(cli, ["--json", "download", "12345"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["job_id"] == "12345"
    assert payload["transfer_mode"] == "single-file"
    assert payload["selected_tasks"] == ["0"]


@pytest.mark.asyncio
async def test_run_download_executes_single_file_flow_and_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Single-file mode should create, verify, unpack, and clean up the remote payload."""

    config = LaunchpadConfig(
        ssh=SSHConfig(host="cluster.example.com", username="sergey"),
    )
    resolved = ResolvedConfig(config=config, layers=())
    recorded: dict[str, object] = {"deleted": []}
    confirm_prompts: list[str] = []
    console = _recording_console()

    monkeypatch.setattr(download_module, "resolve_config", lambda **kwargs: resolved)

    def fake_confirm(message: str, *args, **kwargs) -> bool:  # type: ignore[no-untyped-def]
        confirm_prompts.append(message)
        return True

    monkeypatch.setattr(download_module.click, "confirm", fake_confirm)

    @asynccontextmanager
    async def fake_ssh_session(_config: SSHConfig):  # type: ignore[no-untyped-def]
        yield object()

    async def fake_query_job_rows(*args, **kwargs) -> tuple[download_module.DownloadJobRow, ...]:  # type: ignore[no-untyped-def]
        return (
            download_module.DownloadJobRow(
                job_id="12345",
                task_id="0",
                run_name="tank_v3",
                state="COMPLETED",
                remote_job_dir="/shared/sergey/tank_v3",
                work_dir="/shared/sergey/tank_v3/results_wing_0",
            ),
        )

    async def fake_measure_remote_path(conn, path: str, **kwargs) -> int:  # type: ignore[no-untyped-def]
        if path.endswith(".tar.zst"):
            return 1024
        return 4096

    async def fake_load_job_manifest(*args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        return None

    async def fake_remote_compression_available(*args, **kwargs) -> bool:  # type: ignore[no-untyped-def]
        return True

    async def fake_create_remote_archive(*args, **kwargs) -> str:  # type: ignore[no-untyped-def]
        recorded["archive_kwargs"] = kwargs
        return kwargs["archive_path"]

    async def fake_striped_download(conn, ssh_config, remote_path: str, local_path: Path, **kwargs) -> object:  # type: ignore[no-untyped-def]
        recorded["downloaded_remote_path"] = remote_path
        recorded["striped_kwargs"] = kwargs
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(b"archive-bytes")
        return SimpleNamespace(effective_streams=2)

    async def fake_compute_remote_sha256(conn, path: str, **kwargs) -> str:  # type: ignore[no-untyped-def]
        return "same-digest"

    def fake_compute_sha256(path: Path, **kwargs) -> str:  # type: ignore[no-untyped-def]
        assert path.exists()
        return "same-digest"

    def fake_inspect_archive(path: Path) -> ArchiveInspection:
        return ArchiveInspection(
            archive_path=path,
            entries=(
                ArchiveEntry(path="results_wing_0", size_bytes=0, is_dir=True),
                ArchiveEntry(path="results_wing_0/summary.txt", size_bytes=12, is_dir=False),
            ),
        )

    def fake_decompress_path(source: Path, destination: Path) -> Path:
        (destination / "results_wing_0").mkdir(parents=True, exist_ok=True)
        (destination / "results_wing_0" / "summary.txt").write_text("done\n", encoding="utf-8")
        return destination

    async def fake_delete_remote_path(conn, path: str, **kwargs) -> str:  # type: ignore[no-untyped-def]
        recorded["deleted"].append((path, kwargs))
        return path

    monkeypatch.setattr(download_module, "ssh_session", fake_ssh_session)
    monkeypatch.setattr(download_module, "_query_job_rows", fake_query_job_rows)
    monkeypatch.setattr(download_module, "load_job_manifest", fake_load_job_manifest)
    monkeypatch.setattr(download_module, "measure_remote_path", fake_measure_remote_path)
    monkeypatch.setattr(
        download_module,
        "_remote_compression_available",
        fake_remote_compression_available,
    )
    monkeypatch.setattr(download_module, "create_remote_archive", fake_create_remote_archive)
    monkeypatch.setattr(download_module, "striped_download", fake_striped_download)
    monkeypatch.setattr(download_module, "compute_remote_sha256", fake_compute_remote_sha256)
    monkeypatch.setattr(download_module, "compute_sha256", fake_compute_sha256)
    monkeypatch.setattr(download_module, "inspect_archive", fake_inspect_archive)
    monkeypatch.setattr(download_module, "decompress_path", fake_decompress_path)
    monkeypatch.setattr(download_module, "delete_remote_path", fake_delete_remote_path)

    result = await download_module._run_download(
        cwd=tmp_path,
        env={},
        console=console,
        json_output=False,
        job_id="12345",
        local_dir=tmp_path / "results_tank_v3",
        output=None,
        cleanup=True,
        force=False,
        exclude_patterns=(),
        include_scratch=False,
        transfer_mode=None,
        remote_compress="auto",
        tasks=None,
        streams=4,
        compression_level=5,
    )

    assert result.transfer_mode == "single-file"
    assert result.requested_streams == 8
    assert result.effective_streams == 2
    assert result.cleaned_up is True
    assert result.file_count == 1
    assert recorded["archive_kwargs"]["source_paths"] == ["results_wing_0"]
    assert recorded["archive_kwargs"]["compression_level"] == 3
    assert recorded["downloaded_remote_path"] == "/shared/sergey/tank_v3/.launchpad-download-12345.tar.zst"
    assert recorded["striped_kwargs"]["streams"] == 8
    assert recorded["deleted"] == [("/shared/sergey/tank_v3", {})]
    assert (tmp_path / "results_tank_v3" / "results_wing_0" / "summary.txt").exists()
    assert confirm_prompts == ["Proceed?"]

    output = console.export_text()
    assert "Job 12345  tank_v3" in output
    assert "1/1 task COMPLETED" in output
    assert "Remote results" in output
    assert "Compressed est." in output
    assert "Local free space" in output
    assert "Compressing on remote..." in output


@pytest.mark.asyncio
async def test_run_download_transfers_multi_file_payload_and_applies_excludes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Multi-file mode should download filtered files through the worker pool."""

    config = LaunchpadConfig(
        ssh=SSHConfig(host="cluster.example.com", username="sergey"),
    )
    resolved = ResolvedConfig(config=config, layers=())
    recorded: dict[str, object] = {"downloads": []}

    monkeypatch.setattr(download_module, "resolve_config", lambda **kwargs: resolved)
    monkeypatch.setattr(download_module.click, "confirm", lambda *args, **kwargs: True)

    @asynccontextmanager
    async def fake_ssh_session(_config: SSHConfig):  # type: ignore[no-untyped-def]
        yield object()

    async def fake_query_job_rows(*args, **kwargs) -> tuple[download_module.DownloadJobRow, ...]:  # type: ignore[no-untyped-def]
        return (
            download_module.DownloadJobRow(
                job_id="12345",
                task_id="0",
                run_name="tank_v3",
                state="COMPLETED",
                remote_job_dir="/shared/sergey/tank_v3",
                work_dir="/shared/sergey/tank_v3/results_wing_0",
            ),
        )

    async def fake_measure_remote_path(conn, path: str, **kwargs) -> int:  # type: ignore[no-untyped-def]
        return 512

    async def fake_load_job_manifest(*args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        return None

    async def fake_list_remote_directory(conn, path: str, **kwargs) -> tuple[RemotePathEntry, ...]:  # type: ignore[no-untyped-def]
        return (
            RemotePathEntry(
                path="/shared/sergey/tank_v3/results_wing_0/subdir",
                size_bytes=0,
                entry_type="directory",
            ),
            RemotePathEntry(
                path="/shared/sergey/tank_v3/results_wing_0/subdir/keep.txt",
                size_bytes=4,
                entry_type="file",
            ),
            RemotePathEntry(
                path="/shared/sergey/tank_v3/results_wing_0/skip.tmp",
                size_bytes=4,
                entry_type="file",
            ),
        )

    async def fake_compute_remote_sha256(conn, path: str, **kwargs) -> str:  # type: ignore[no-untyped-def]
        return "same"

    def fake_compute_sha256(path: Path, **kwargs) -> str:  # type: ignore[no-untyped-def]
        return "same"

    async def fake_download_many(ssh_config, items, **kwargs):  # type: ignore[no-untyped-def]
        recorded["downloads"] = [(item.remote_path, item.local_path) for item in items]
        for item in items:
            item.local_path.parent.mkdir(parents=True, exist_ok=True)
            item.local_path.write_text("keep", encoding="utf-8")
        return SimpleNamespace(effective_streams=2)

    monkeypatch.setattr(download_module, "ssh_session", fake_ssh_session)
    monkeypatch.setattr(download_module, "_query_job_rows", fake_query_job_rows)
    monkeypatch.setattr(download_module, "load_job_manifest", fake_load_job_manifest)
    monkeypatch.setattr(download_module, "measure_remote_path", fake_measure_remote_path)
    monkeypatch.setattr(download_module, "list_remote_directory", fake_list_remote_directory)
    monkeypatch.setattr(download_module, "download_many", fake_download_many)
    monkeypatch.setattr(download_module, "compute_remote_sha256", fake_compute_remote_sha256)
    monkeypatch.setattr(download_module, "compute_sha256", fake_compute_sha256)

    result = await download_module._run_download(
        cwd=tmp_path,
        env={},
        console=build_console(no_color=True),
        json_output=False,
        job_id="12345",
        local_dir=tmp_path / "results_tank_v3",
        output=None,
        cleanup=False,
        force=False,
        exclude_patterns=("results_wing_0/*.tmp",),
        include_scratch=False,
        transfer_mode="multi-file",
        remote_compress=None,
        tasks=None,
        streams=3,
        compression_level=None,
    )

    assert result.transfer_mode == "multi-file"
    assert result.requested_streams == 8
    assert result.effective_streams == 2
    assert result.file_count == 1
    assert recorded["downloads"] == [
        (
            "/shared/sergey/tank_v3/results_wing_0/subdir/keep.txt",
            tmp_path / "results_tank_v3" / "results_wing_0" / "subdir" / "keep.txt",
        )
    ]
    assert not (tmp_path / "results_tank_v3" / "results_wing_0" / "skip.tmp").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("rows", "tasks", "exclude_patterns", "expected_message"),
    [
        (
            (
                download_module.DownloadJobRow(
                    job_id="12345",
                    task_id="0",
                    run_name="tank_v3",
                    state="RUNNING",
                    remote_job_dir="/shared/sergey/tank_v3",
                    work_dir="/shared/sergey/tank_v3/results_wing_0",
                ),
            ),
            None,
            (),
            "only allowed for terminal jobs",
        ),
        (
            (
                download_module.DownloadJobRow(
                    job_id="12345",
                    task_id="0",
                    run_name="tank_v3",
                    state="CANCELLED",
                    remote_job_dir="/shared/sergey/tank_v3",
                    work_dir="/shared/sergey/tank_v3/results_wing_0",
                ),
            ),
            None,
            (),
            "not allowed when cancelled tasks are selected",
        ),
        (
            (
                download_module.DownloadJobRow(
                    job_id="12345",
                    task_id="0",
                    run_name="tank_v3",
                    state="COMPLETED",
                    remote_job_dir="/shared/sergey/tank_v3",
                    work_dir="/shared/sergey/tank_v3/results_wing_0",
                ),
                download_module.DownloadJobRow(
                    job_id="12345",
                    task_id="1",
                    run_name="tank_v3",
                    state="COMPLETED",
                    remote_job_dir="/shared/sergey/tank_v3",
                    work_dir="/shared/sergey/tank_v3/results_wing_1",
                ),
            ),
            "0",
            (),
            "cannot be combined with `--tasks`",
        ),
        (
            (
                download_module.DownloadJobRow(
                    job_id="12345",
                    task_id="0",
                    run_name="tank_v3",
                    state="COMPLETED",
                    remote_job_dir="/shared/sergey/tank_v3",
                    work_dir="/shared/sergey/tank_v3/results_wing_0",
                ),
            ),
            None,
            ("results_wing_0/*.tmp",),
            "cannot be combined with `--exclude`",
        ),
    ],
)
async def test_run_download_rejects_unsafe_cleanup_combinations(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    rows: tuple[download_module.DownloadJobRow, ...],
    tasks: str | None,
    exclude_patterns: tuple[str, ...],
    expected_message: str,
) -> None:
    """Cleanup should fail before confirmation when the download is narrowed or partial."""

    config = LaunchpadConfig(
        ssh=SSHConfig(host="cluster.example.com", username="sergey"),
    )
    resolved = ResolvedConfig(config=config, layers=())

    monkeypatch.setattr(download_module, "resolve_config", lambda **kwargs: resolved)

    @asynccontextmanager
    async def fake_ssh_session(_config: SSHConfig):  # type: ignore[no-untyped-def]
        yield object()

    async def fake_query_job_rows(*args, **kwargs) -> tuple[download_module.DownloadJobRow, ...]:  # type: ignore[no-untyped-def]
        return rows

    async def fake_measure_remote_path(conn, path: str, **kwargs) -> int:  # type: ignore[no-untyped-def]
        return 512

    async def fake_load_job_manifest(*args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        return None

    async def fake_remote_compression_available(*args, **kwargs) -> bool:  # type: ignore[no-untyped-def]
        return True

    def fail_confirm(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("cleanup safety gate should trigger before confirmation")

    monkeypatch.setattr(download_module, "ssh_session", fake_ssh_session)
    monkeypatch.setattr(download_module, "_query_job_rows", fake_query_job_rows)
    monkeypatch.setattr(download_module, "load_job_manifest", fake_load_job_manifest)
    monkeypatch.setattr(download_module, "measure_remote_path", fake_measure_remote_path)
    monkeypatch.setattr(
        download_module,
        "_remote_compression_available",
        fake_remote_compression_available,
    )
    monkeypatch.setattr(download_module.click, "confirm", fail_confirm)

    with pytest.raises(download_module.click.ClickException, match=expected_message):
        await download_module._run_download(
            cwd=tmp_path,
            env={},
            console=build_console(no_color=True),
            json_output=False,
            job_id="12345",
            local_dir=tmp_path / "results_tank_v3",
            output=None,
            cleanup=True,
            force=False,
            exclude_patterns=exclude_patterns,
            include_scratch=False,
            transfer_mode=None,
            remote_compress="auto",
            tasks=tasks,
            streams=4,
            compression_level=3,
        )


def test_parse_task_selection_deduplicates_and_sorts_numeric_values() -> None:
    """Task parsing should normalize repeated selectors without reordering them."""

    assert download_module._parse_task_selection("002,wing.dat,002,inputs/wing.dat") == (
        "002",
        "wing.dat",
        "inputs/wing.dat",
    )


@pytest.mark.asyncio
async def test_build_download_plan_resolves_manifest_task_references(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Manifest-backed aliases and relative paths should select the intended rows."""

    manifest = JobManifest(
        version=1,
        solver="nastran",
        logs={"solver": ".f06"},
        tasks=(
            TaskReference(
                task_id="0",
                alias="001",
                input_relative_path="inputs/root.dat",
                input_filename="root.dat",
                input_stem="root",
                display_label="root",
                result_dir="results_root_0",
            ),
            TaskReference(
                task_id="1",
                alias="002",
                input_relative_path="inputs/wing.dat",
                input_filename="wing.dat",
                input_stem="wing",
                display_label="wing",
                result_dir="results_wing_1",
            ),
        ),
    )
    rows = (
        download_module.DownloadJobRow(
            job_id="12345",
            task_id="0",
            run_name="tank_v3",
            state="COMPLETED",
            remote_job_dir="/shared/sergey/tank_v3",
            work_dir="/shared/sergey/tank_v3/results_root_0",
        ),
        download_module.DownloadJobRow(
            job_id="12345",
            task_id="1",
            run_name="tank_v3",
            state="COMPLETED",
            remote_job_dir="/shared/sergey/tank_v3",
            work_dir="/shared/sergey/tank_v3/results_wing_1",
        ),
    )

    async def fake_measure_remote_path(conn, path: str, **kwargs) -> int:  # type: ignore[no-untyped-def]
        assert path == "/shared/sergey/tank_v3/results_wing_1"
        return 512

    async def fake_select_transfer_mode(*args, **kwargs) -> str:  # type: ignore[no-untyped-def]
        return "multi-file"

    async def fake_load_job_manifest(conn, remote_job_dir) -> object:  # type: ignore[no-untyped-def]
        return manifest

    monkeypatch.setattr(download_module, "measure_remote_path", fake_measure_remote_path)
    monkeypatch.setattr(download_module, "_select_transfer_mode", fake_select_transfer_mode)
    monkeypatch.setattr(download_module, "load_job_manifest", fake_load_job_manifest)

    plan = await download_module._build_download_plan(
        conn=object(),
        config=LaunchpadConfig(ssh=SSHConfig(host="cluster.example.com", username="sergey")),
        job_id="12345",
        rows=rows,
        destination=tmp_path / "results_tank_v3",
        requested_tasks=("002", "inputs/wing.dat"),
        cleanup=False,
        force=False,
        exclude_patterns=(),
        include_scratch=False,
        transfer_mode="multi-file",
        compression_level=3,
        requested_streams=4,
    )

    assert plan.selected_tasks == ("1",)
    assert plan.source_roots == (
        download_module.RemoteSource(
            absolute_path="/shared/sergey/tank_v3/results_wing_1",
            relative_path="results_wing_1",
        ),
    )


def test_download_completion_renderable_surfaces_integrity_and_next_steps(tmp_path: Path) -> None:
    """The final human-readable summary should use the restrained Phase 9 layout."""

    console = _recording_console()
    renderable = download_module._build_completion_renderable(
        download_module.DownloadResult(
            job_id="12345",
            run_name="tank_v3",
            destination_dir=tmp_path / "results_tank_v3",
            remote_job_dir="/shared/sergey/tank_v3",
            transfer_mode="single-file",
            requested_streams=8,
            effective_streams=4,
            downloaded_bytes=1024,
            file_count=3,
            cleaned_up=False,
            selected_tasks=("0",),
            partial=False,
            checksums_verified=True,
            result_size_bytes=4096,
            source_count=1,
        ),
        no_color=True,
    )

    console.print(renderable)
    output = console.export_text()

    assert "Download complete" in output
    assert "Local path" in output
    assert "Size" in output
    assert "Integrity" in output
    assert "all files verified" in output
    assert "launchpad cleanup 12345" in output


@pytest.mark.asyncio
async def test_build_download_plan_rejects_non_numeric_legacy_task_refs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Legacy jobs without a manifest should require raw numeric task IDs."""

    rows = (
        download_module.DownloadJobRow(
            job_id="12345",
            task_id="0",
            run_name="tank_v3",
            state="COMPLETED",
            remote_job_dir="/shared/sergey/tank_v3",
            work_dir="/shared/sergey/tank_v3/results_root_0",
        ),
    )

    async def fake_load_job_manifest_none(conn, remote_job_dir) -> None:  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(download_module, "load_job_manifest", fake_load_job_manifest_none)

    with pytest.raises(ValueError, match="Only raw numeric task IDs are supported"):
        await download_module._build_download_plan(
            conn=object(),
            config=LaunchpadConfig(ssh=SSHConfig(host="cluster.example.com", username="sergey")),
            job_id="12345",
            rows=rows,
            destination=tmp_path / "results_tank_v3",
            requested_tasks=("wing.dat",),
            cleanup=False,
            force=False,
            exclude_patterns=(),
            include_scratch=False,
            transfer_mode="multi-file",
            compression_level=3,
            requested_streams=4,
        )
