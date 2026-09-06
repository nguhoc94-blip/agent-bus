"""Tests for watcher fingerprint dedup cache (AC13, L5)."""

from __future__ import annotations

import json
from pathlib import Path

from app.logger import JsonlLogger
from app.watcher import RouterWatcher, _DedupCache


def _read_records(log_folder: Path):
    out = []
    for jsonl in log_folder.glob("router_*.jsonl"):
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
    return out


def test_cache_deduplicates_identical_fingerprint():
    cache = _DedupCache(max_entries=16, ttl_s=60)
    assert cache.check_and_set("/a", 100, 555) is True
    assert cache.check_and_set("/a", 100, 555) is False
    assert cache.check_and_set("/a", 100, 555) is False


def test_cache_accepts_changed_size():
    cache = _DedupCache()
    assert cache.check_and_set("/b", 100, 1) is True
    assert cache.check_and_set("/b", 200, 1) is True  # size changed
    assert cache.check_and_set("/b", 200, 1) is False


def test_cache_accepts_changed_mtime():
    cache = _DedupCache()
    assert cache.check_and_set("/c", 100, 1) is True
    assert cache.check_and_set("/c", 100, 2) is True  # mtime changed
    assert cache.check_and_set("/c", 100, 2) is False


def test_cache_invalidate():
    cache = _DedupCache()
    cache.check_and_set("/d", 50, 99)
    cache.invalidate("/d")
    assert cache.check_and_set("/d", 50, 99) is True  # retried after invalidate


def test_cache_eviction_by_max_entries():
    cache = _DedupCache(max_entries=2, ttl_s=60)
    cache.check_and_set("/a", 1, 1)
    cache.check_and_set("/b", 1, 1)
    cache.check_and_set("/c", 1, 1)  # evicts /a
    # /a re-added
    assert cache.check_and_set("/a", 1, 1) is True


def test_watcher_processes_same_file_once(tmp_path: Path, config):
    """AC13: 3 consecutive events on same stable file -> only 1 move happens."""
    logger = JsonlLogger(config.log_folder)
    watcher = RouterWatcher(config, logger)

    src = config.watch_folder / "DEMO__POD_CORE__PRODUCT_gui_ENGINEERING.md"
    src.write_text(
        "Project: DEMO\nPod: POD_CORE\nTừ: PRODUCT\nGửi: ENGINEERING\n",
        encoding="utf-8")

    watcher.process_path(src)
    # After first call file has been moved; re-fire event on now-missing src
    watcher.process_path(src)
    watcher.process_path(src)

    records = _read_records(config.log_folder)
    moved = [r for r in records if r["action"] == "moved"]
    assert len(moved) == 1, f"expected 1 move, got {len(moved)}: {moved}"


def test_watcher_reprocesses_after_size_change(tmp_path: Path, config):
    logger = JsonlLogger(config.log_folder)
    watcher = RouterWatcher(config, logger)

    src = config.watch_folder / "foo.md"
    src.write_text(
        "Project: DEMO\nPod: POD_CORE\nTừ: PRODUCT\nGửi: ENGINEERING\n",
        encoding="utf-8")
    watcher.process_path(src)  # move #1

    # Write a different valid file (same filename) with a size-changing body
    src.write_text(
        "Project: DEMO\nPod: POD_FLOW\nTừ: PRODUCT\nGửi: ENGINEERING\n"
        + ("padding line\n" * 5),
        encoding="utf-8")
    watcher.process_path(src)

    records = _read_records(config.log_folder)
    moved = [r for r in records if r["action"] == "moved"]
    assert len(moved) == 2, f"expected 2 separate moves, got: {moved}"
