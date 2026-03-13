"""Tests for local zstd archive helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from launchpad_cli.core.compress import compress_path, decompress_path


def test_compress_and_decompress_directory_round_trip(tmp_path: Path) -> None:
    """Directories should round-trip through a `.tar.zst` archive."""

    source = tmp_path / "model"
    nested = source / "nested"
    nested.mkdir(parents=True)
    (source / "input.dat").write_text("GRID,1\n", encoding="utf-8")
    (nested / "material.inc").write_text("MAT1,1\n", encoding="utf-8")

    archive = tmp_path / "artifacts" / "model.tar.zst"
    extracted = tmp_path / "restored"

    result_archive = compress_path(source, archive, level=5)
    result_directory = decompress_path(result_archive, extracted)

    assert result_archive == archive
    assert result_archive.exists()
    assert result_directory == extracted
    assert (extracted / "model" / "input.dat").read_text(encoding="utf-8") == "GRID,1\n"
    assert (
        extracted / "model" / "nested" / "material.inc"
    ).read_text(encoding="utf-8") == "MAT1,1\n"


def test_compress_path_requires_existing_source(tmp_path: Path) -> None:
    """Compression should fail fast for missing sources."""

    with pytest.raises(FileNotFoundError):
        compress_path(tmp_path / "missing", tmp_path / "missing.tar.zst")


def test_decompress_path_requires_existing_archive(tmp_path: Path) -> None:
    """Decompression should fail fast for missing archives."""

    with pytest.raises(FileNotFoundError):
        decompress_path(tmp_path / "missing.tar.zst", tmp_path / "output")
