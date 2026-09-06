"""Tests for cross-volume move safety (AC11, L3) and orphan cleanup (AC14, L7).

We monkeypatch `os.path.splitdrive` to simulate different volumes because pytest
tmp_path is always on a single drive.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from app import mover as mover_mod
from app.mover import MoveStrategy, cleanup_orphan_tmp, move_safe


@pytest.fixture
def fake_cross_volume(monkeypatch):
    """Force same_volume() to return False so cross-volume path is exercised."""
    monkeypatch.setattr(mover_mod, "same_volume", lambda a, b: False)


def test_cross_volume_copy_then_remove(tmp_path: Path, fake_cross_volume):
    src = tmp_path / "src.md"
    src.write_text("payload", encoding="utf-8")
    dest = tmp_path / "dest" / "file.md"

    result = move_safe(src, dest, dry_run=False)
    assert result.moved is True
    assert result.strategy == MoveStrategy.CROSS_VOLUME_COPY
    assert dest.exists()
    assert dest.read_text(encoding="utf-8") == "payload"
    assert not src.exists()


def test_cross_volume_overwrite(tmp_path: Path, fake_cross_volume):
    src = tmp_path / "src.md"
    src.write_text("NEW", encoding="utf-8")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    dest = dest_dir / "file.md"
    dest.write_text("OLD", encoding="utf-8")

    result = move_safe(src, dest, dry_run=False)
    assert result.overwrite_applied is True
    assert dest.read_text(encoding="utf-8") == "NEW"


def test_cross_volume_suffix_creates_rev_file(tmp_path: Path, fake_cross_volume):
    src = tmp_path / "src.md"
    src.write_text("NEW", encoding="utf-8")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    dest = dest_dir / "file.md"
    dest.write_text("OLD", encoding="utf-8")

    result = move_safe(src, dest, dry_run=False, duplicate_strategy="suffix")
    # base dest kept
    assert dest.read_text(encoding="utf-8") == "OLD"
    # rev created
    rev = dest_dir / "file__REV_001.md"
    assert rev.exists()
    assert rev.read_text(encoding="utf-8") == "NEW"
    assert result.duplicate_detected is True
    assert result.overwrite_applied is False


def test_cross_volume_copy_fails_source_preserved(
    tmp_path: Path, fake_cross_volume, monkeypatch
):
    """AC11: if copy2 raises, source file MUST remain intact and no tmp orphan remains."""
    src = tmp_path / "src.md"
    src.write_text("critical data", encoding="utf-8")
    dest = tmp_path / "dest" / "file.md"

    def boom(src_p, dst_p):
        # Create partial tmp file then raise to simulate crash mid-copy
        Path(dst_p).write_bytes(b"partial")
        raise IOError("disk full simulated")

    monkeypatch.setattr(shutil, "copy2", boom)

    with pytest.raises(IOError):
        move_safe(src, dest, dry_run=False)

    assert src.exists(), "source must be preserved on copy failure"
    assert src.read_text(encoding="utf-8") == "critical data"
    # No orphan tmp should remain — mover cleans it before re-raising
    tmps = list(dest.parent.glob("*.tmp_*"))
    assert tmps == [], f"orphan tmp leaked: {tmps}"


def test_cross_volume_size_mismatch_source_preserved(
    tmp_path: Path, fake_cross_volume, monkeypatch
):
    """Simulate copy that silently truncates -> mover must detect and preserve src."""
    src = tmp_path / "src.md"
    src.write_text("A" * 1000, encoding="utf-8")
    dest = tmp_path / "dest" / "file.md"

    def truncate_copy(src_p, dst_p):
        # Copy only first 10 bytes to simulate partial write
        Path(dst_p).write_text("A" * 10, encoding="utf-8")

    monkeypatch.setattr(shutil, "copy2", truncate_copy)

    with pytest.raises(IOError):
        move_safe(src, dest, dry_run=False)

    assert src.exists()
    assert src.read_text(encoding="utf-8") == "A" * 1000
    assert not dest.exists()


def test_cleanup_orphan_tmp(tmp_path: Path):
    """AC14: orphan *.tmp_<pid>_* from other pids must be removed at startup."""
    root = tmp_path / "r"
    root.mkdir()
    current_pid = os.getpid()
    other_pid = 99999999

    alive = root / "file.md"
    alive.write_text("live data", encoding="utf-8")
    my_tmp = root / f"file.md.tmp_{current_pid}_abcd1234"
    my_tmp.write_text("mine", encoding="utf-8")
    orphan = root / f"file.md.tmp_{other_pid}_deadbeef"
    orphan.write_text("stale", encoding="utf-8")
    unrelated = root / "other.md.tmp_notpid_xxx"
    unrelated.write_text("hand-typed name, safe", encoding="utf-8")

    removed = cleanup_orphan_tmp([root], current_pid)
    assert removed == 1
    assert alive.exists()
    assert my_tmp.exists()
    assert not orphan.exists()
    assert unrelated.exists()
