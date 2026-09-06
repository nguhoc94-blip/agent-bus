"""Tests for unsupported extension = SKIPPED (AC10, L2).

These tests exercise the end-to-end pipeline but for unsupported extensions
the watcher returns before routing, so we test via the RouterWatcher directly.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.logger import JsonlLogger
from app.watcher import RouterWatcher


def _read_log_records(log_folder: Path):
    records = []
    for jsonl in log_folder.glob("router_*.jsonl"):
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    return records


def test_unsupported_ext_is_skipped_not_reviewed(tmp_path: Path, config):
    logger = JsonlLogger(config.log_folder)
    watcher = RouterWatcher(config, logger)

    # .exe is NOT in allowed_extensions
    src = config.watch_folder / "malware.exe"
    src.write_bytes(b"MZ fake exe")

    watcher.process_path(src)

    records = _read_log_records(config.log_folder)
    assert len(records) == 1
    rec = records[0]
    assert rec["action"] == "skipped"
    assert rec["reason"] == "UNSUPPORTED_EXT"
    assert rec["original_filename"] == "malware.exe"
    assert rec["destination_path"] is None
    assert rec["new_filename"] is None

    # File must NOT have been moved anywhere
    assert src.exists()
    assert not any((config.review_folder).rglob("malware.exe"))
    for pcfg in config.projects.values():
        assert not any(pcfg.root.rglob("malware.exe"))


def test_allowed_ext_not_skipped(tmp_path: Path, config):
    """Sanity: .md is in allowed list, goes through normal pipeline."""
    logger = JsonlLogger(config.log_folder)
    watcher = RouterWatcher(config, logger)

    src = config.watch_folder / "DEMO__POD_CORE__PRODUCT_gui_ENGINEERING.md"
    src.write_text(
        "Project: DEMO\nPod: POD_CORE\nTừ: PRODUCT\nGửi: ENGINEERING\n",
        encoding="utf-8",
    )

    watcher.process_path(src)

    records = _read_log_records(config.log_folder)
    assert any(r["action"] == "moved" for r in records)
    assert not any(r["reason"] == "UNSUPPORTED_EXT" for r in records)


def test_temp_extension_is_silently_ignored(tmp_path: Path, config):
    """Temporary ext (.crdownload) must not produce any log record — it's a partial download."""
    logger = JsonlLogger(config.log_folder)
    watcher = RouterWatcher(config, logger)

    src = config.watch_folder / "foo.md.crdownload"
    src.write_bytes(b"incomplete")

    watcher.process_path(src)

    records = _read_log_records(config.log_folder)
    assert records == []
    assert src.exists()  # not moved
