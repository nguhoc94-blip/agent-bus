"""Tests for dry_run semantics (AC7)."""

from __future__ import annotations

from pathlib import Path

from app.mover import move_safe


def test_dry_run_does_not_move(tmp_path: Path):
    src = tmp_path / "src.md"
    src.write_text("hello", encoding="utf-8")
    dest = tmp_path / "dest" / "file.md"

    result = move_safe(src, dest, dry_run=True)
    assert src.exists(), "source must still exist under dry_run"
    assert not dest.exists(), "destination must not be created under dry_run"
    assert result.moved is False
    assert result.overwrite_applied is False
    assert result.strategy is None
    assert result.planned_path == dest


def test_dry_run_detects_duplicate_without_mutation(tmp_path: Path):
    src = tmp_path / "src.md"
    src.write_text("NEW", encoding="utf-8")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    dest = dest_dir / "file.md"
    dest.write_text("OLD", encoding="utf-8")

    result = move_safe(src, dest, dry_run=True)
    assert result.duplicate_detected is True
    assert result.overwrite_applied is False
    assert result.moved is False
    assert dest.read_text(encoding="utf-8") == "OLD"  # unchanged
    assert src.exists()


def test_dry_run_suffix_plans_rev_path_without_mutation(tmp_path: Path):
    src = tmp_path / "src.md"
    src.write_text("NEW", encoding="utf-8")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    dest = dest_dir / "file.md"
    dest.write_text("OLD", encoding="utf-8")

    result = move_safe(src, dest, dry_run=True, duplicate_strategy="suffix")
    assert result.duplicate_detected is True
    assert result.moved is False
    assert result.overwrite_applied is False
    assert result.strategy is None
    assert result.planned_path.name == "file__REV_001.md"
    assert dest.read_text(encoding="utf-8") == "OLD"
    assert not (dest_dir / "file__REV_001.md").exists()
    assert src.exists()
