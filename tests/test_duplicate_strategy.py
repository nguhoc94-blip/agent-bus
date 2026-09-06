"""Tests for duplicate_strategy=overwrite (AC5 updated, L6)."""

from __future__ import annotations

from pathlib import Path

from app.mover import MoveResult, move_safe
from app.models import MoveStrategy


def test_overwrite_dest_same_volume(tmp_path: Path):
    src = tmp_path / "src.md"
    src.write_text("NEW content", encoding="utf-8")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    dest = dest_dir / "file.md"
    dest.write_text("OLD content", encoding="utf-8")

    result = move_safe(src, dest, dry_run=False)
    assert result.moved is True
    assert result.duplicate_detected is True
    assert result.overwrite_applied is True
    assert result.strategy == MoveStrategy.ATOMIC_REPLACE
    assert dest.read_text(encoding="utf-8") == "NEW content"
    assert not src.exists()


def test_overwrite_no_duplicate(tmp_path: Path):
    src = tmp_path / "src.md"
    src.write_text("hello", encoding="utf-8")
    dest = tmp_path / "dest" / "file.md"
    result = move_safe(src, dest, dry_run=False)
    assert result.duplicate_detected is False
    assert result.overwrite_applied is False
    assert result.moved is True
    assert dest.read_text(encoding="utf-8") == "hello"


def test_overwrite_in_review_folder(tmp_path: Path, config):
    """L6: overwrite applies uniformly, including the review folder."""
    review_sub = config.review_folder / "MISSING_POD"
    review_sub.mkdir(parents=True, exist_ok=True)
    existing = review_sub / "foo.md"
    existing.write_text("OLD review", encoding="utf-8")

    src = config.watch_folder / "foo.md"
    src.write_text("NEW review", encoding="utf-8")

    result = move_safe(src, existing, dry_run=False)
    assert result.overwrite_applied is True
    assert existing.read_text(encoding="utf-8") == "NEW review"


def test_overwrite_creates_missing_parent(tmp_path: Path):
    src = tmp_path / "s.md"
    src.write_text("data", encoding="utf-8")
    dest = tmp_path / "a" / "b" / "c" / "d.md"
    assert not dest.parent.exists()
    result = move_safe(src, dest, dry_run=False)
    assert dest.exists()
    assert result.moved is True


def test_suffix_does_not_overwrite(tmp_path: Path):
    src1 = tmp_path / "src1.md"
    src1.write_text("ONE", encoding="utf-8")
    src2 = tmp_path / "src2.md"
    src2.write_text("TWO", encoding="utf-8")

    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    dest = dest_dir / "file.md"

    r1 = move_safe(src1, dest, dry_run=False, duplicate_strategy="suffix")
    assert r1.moved is True
    assert r1.planned_path == dest
    assert dest.read_text(encoding="utf-8") == "ONE"

    r2 = move_safe(src2, dest, dry_run=False, duplicate_strategy="suffix")
    assert r2.moved is True
    assert r2.planned_path.name == "file__REV_001.md"
    assert (dest_dir / "file__REV_001.md").read_text(encoding="utf-8") == "TWO"
