"""Tests for shutdown flag + orphan cleanup on startup (AC14, L7).

We don't start the live observer here (that requires watchdog thread/signal);
we test the contractual pieces: `stop()` short-circuits processing, and
`cleanup_orphans()` removes stale *.tmp_<other_pid>_* files.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from app.logger import JsonlLogger
from app.watcher import RouterWatcher


def _records(log_folder: Path):
    out = []
    for jsonl in log_folder.glob("router_*.jsonl"):
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
    return out


def test_stop_prevents_further_processing(tmp_path: Path, config):
    logger = JsonlLogger(config.log_folder)
    watcher = RouterWatcher(config, logger)
    watcher.stop()
    assert watcher.is_stopping()

    src = config.watch_folder / "DEMO__POD_CORE__COO_gui_CEO.md"
    src.write_text("Project: DEMO\nPod: POD_CORE\nTừ: COO\nGửi: CEO\n",
                   encoding="utf-8")
    watcher.process_path(src)

    # After stop() processing must be a no-op
    records = _records(config.log_folder)
    assert records == []
    assert src.exists()  # not moved


def test_cleanup_orphans_removes_other_pid_tmp(tmp_path: Path, config):
    logger = JsonlLogger(config.log_folder)
    watcher = RouterWatcher(config, logger)

    # Plant orphan tmp files inside project root + review folder
    DEMO_root = config.projects["DEMO"].root
    DEMO_root.mkdir(parents=True, exist_ok=True)
    (DEMO_root / "POD_CORE").mkdir(parents=True, exist_ok=True)

    other_pid = 12345678
    orphan1 = DEMO_root / "POD_CORE" / f"a.md.tmp_{other_pid}_dead0001"
    orphan1.write_text("stale A", encoding="utf-8")

    config.review_folder.mkdir(parents=True, exist_ok=True)
    (config.review_folder / "AMBIGUOUS").mkdir(parents=True, exist_ok=True)
    orphan2 = config.review_folder / "AMBIGUOUS" / f"b.md.tmp_{other_pid}_dead0002"
    orphan2.write_text("stale B", encoding="utf-8")

    mine = DEMO_root / f"c.md.tmp_{os.getpid()}_cafecafe"
    mine.write_text("keep me", encoding="utf-8")

    removed = watcher.cleanup_orphans()
    assert removed == 2
    assert not orphan1.exists()
    assert not orphan2.exists()
    assert mine.exists()  # same-pid tmp is kept


def test_cleanup_orphans_empty_when_no_tmps(tmp_path: Path, config):
    logger = JsonlLogger(config.log_folder)
    watcher = RouterWatcher(config, logger)
    removed = watcher.cleanup_orphans()
    assert removed == 0
