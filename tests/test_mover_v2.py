"""Tests for mover v2: copy_safe + apply_route + orphan scan for _REPORTER_HUB."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from app import mover as mover_mod
from app.models import Action, RouteDecision
from app.mover import (
    ApplyResult, apply_route, cleanup_orphan_tmp, copy_safe, move_safe,
)


def _decision(primary: Path, mirrors):
    return RouteDecision(
        action=Action.MOVED,
        destination_path=primary,
        primary_destination_path=primary,
        mirror_destination_paths=list(mirrors),
        new_filename=primary.name,
        reason="ok",
    )


def test_copy_safe_basic(tmp_path: Path):
    src = tmp_path / "src.md"
    src.write_text("data", encoding="utf-8")
    dest = tmp_path / "dest" / "out.md"
    res = copy_safe(src, dest, dry_run=False)
    assert res.copied is True
    assert dest.read_text(encoding="utf-8") == "data"
    assert src.exists(), "copy_safe must NOT delete source"


def test_copy_safe_duplicate_overwrites(tmp_path: Path):
    """Mirror overwrite: atomic replace, no timestamp suffix, no backup."""
    src = tmp_path / "src.md"
    src.write_text("NEW", encoding="utf-8")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    dest = dest_dir / "out.md"
    dest.write_text("OLD", encoding="utf-8")

    res = copy_safe(src, dest, dry_run=False)
    assert res.overwrite_applied is True
    assert dest.read_text(encoding="utf-8") == "NEW"
    # No timestamped/backup files left behind
    siblings = list(dest_dir.iterdir())
    assert siblings == [dest]


def test_copy_safe_dry_run(tmp_path: Path):
    src = tmp_path / "src.md"
    src.write_text("x", encoding="utf-8")
    dest = tmp_path / "dest" / "out.md"
    res = copy_safe(src, dest, dry_run=True)
    assert res.copied is False
    assert not dest.exists()
    assert src.exists()


def test_apply_route_same_volume_primary_and_mirror_ok(tmp_path: Path):
    src = tmp_path / "src.md"
    src.write_text("payload", encoding="utf-8")
    primary = tmp_path / "inbox" / "canon.md"
    mirror = tmp_path / "_REPORTER_HUB" / "PHASE_1" / "CEO_BRIEF" / "canon.md"
    d = _decision(primary, [mirror])
    result = apply_route(d, src, dry_run=False)
    assert primary.exists()
    assert mirror.exists()
    assert mirror.read_text(encoding="utf-8") == "payload"
    assert result.mirror_status == "ok"
    assert result.mirror_failed is False


def test_apply_route_duplicate_mirror_uses_suffix(tmp_path: Path):
    """In suffix mode, mirror duplicates must not overwrite; they get __REV_001."""
    src = tmp_path / "src.md"
    src.write_text("payload", encoding="utf-8")
    primary = tmp_path / "inbox" / "canon.md"
    mirror_dir = tmp_path / "_REPORTER_HUB" / "PHASE_1" / "CEO_BRIEF"
    mirror_dir.mkdir(parents=True, exist_ok=True)
    mirror = mirror_dir / "canon.md"
    mirror.write_text("OLD", encoding="utf-8")

    d = _decision(primary, [mirror])
    result = apply_route(d, src, dry_run=False, duplicate_strategy="suffix")

    assert primary.exists()
    assert mirror.exists(), "existing mirror must remain"
    assert mirror.read_text(encoding="utf-8") == "OLD"
    rev = mirror_dir / "canon__REV_001.md"
    assert rev.exists()
    assert rev.read_text(encoding="utf-8") == "payload"
    assert result.mirror_status == "ok"


def test_apply_route_cross_volume_primary_and_mirror_ok(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(mover_mod, "same_volume", lambda a, b: False)
    src = tmp_path / "src.md"
    src.write_text("payload", encoding="utf-8")
    primary = tmp_path / "inbox" / "canon.md"
    mirror = tmp_path / "_REPORTER_HUB" / "PHASE_1" / "CEO_BRIEF" / "canon.md"
    result = apply_route(_decision(primary, [mirror]), src, dry_run=False)
    assert primary.exists() and mirror.exists()
    assert result.mirror_status == "ok"


def test_apply_route_mirror_fail_keeps_primary(tmp_path: Path, monkeypatch):
    """AC5 / plan §5.4: if copy_safe raises for mirror, primary stays intact."""
    src = tmp_path / "src.md"
    src.write_text("payload", encoding="utf-8")
    primary = tmp_path / "inbox" / "canon.md"
    mirror = tmp_path / "hub" / "x" / "canon.md"

    real_copy2 = shutil.copy2
    call_count = {"n": 0}

    def flaky_copy2(a, b):
        call_count["n"] += 1
        # First call: primary move_safe path is same-volume, uses os.replace —
        # so it doesn't call copy2. copy_safe is the first to call copy2.
        if call_count["n"] == 1:
            raise IOError("simulated mirror crash")
        return real_copy2(a, b)

    monkeypatch.setattr(shutil, "copy2", flaky_copy2)

    result = apply_route(_decision(primary, [mirror]), src, dry_run=False)
    assert primary.exists()
    assert primary.read_text(encoding="utf-8") == "payload"
    assert not mirror.exists()
    assert result.mirror_failed is True
    assert result.mirror_status == "failed"
    assert "simulated mirror crash" in result.mirror_errors[0]


def test_apply_route_dry_run_no_mutation(tmp_path: Path):
    src = tmp_path / "src.md"
    src.write_text("x", encoding="utf-8")
    primary = tmp_path / "inbox" / "c.md"
    mirror = tmp_path / "hub" / "c.md"
    result = apply_route(_decision(primary, [mirror]), src, dry_run=True)
    assert src.exists()
    assert not primary.exists()
    assert not mirror.exists()
    assert result.primary is not None


def test_apply_route_no_mirrors(tmp_path: Path):
    src = tmp_path / "src.md"
    src.write_text("x", encoding="utf-8")
    primary = tmp_path / "inbox" / "c.md"
    result = apply_route(_decision(primary, []), src, dry_run=False)
    assert result.mirror_status == "none"
    assert result.mirrors == []


def test_cleanup_orphan_tmp_includes_reporter_hub(tmp_path: Path):
    """Orphan scanner must descend into _REPORTER_HUB just like project root."""
    root = tmp_path / "proj"
    hub = root / "_REPORTER_HUB" / "PHASE_1" / "CEO_BRIEF"
    hub.mkdir(parents=True)
    other_pid = 99999999
    orphan = hub / f"x.md.tmp_{other_pid}_deadbeef"
    orphan.write_text("stale", encoding="utf-8")
    removed = cleanup_orphan_tmp([root], os.getpid())
    assert removed == 1
    assert not orphan.exists()
