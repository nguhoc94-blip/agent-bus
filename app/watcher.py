"""Watcher pipeline: watchdog events -> stability -> parse -> route -> move -> log.

Implements L5 (fingerprint dedup) + L7 (graceful shutdown + orphan cleanup).
"""

from __future__ import annotations

import os
import signal
import sys
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Optional, Tuple

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
    _WATCHDOG = True
except ImportError:  # pragma: no cover — runtime dep, tests can mock
    FileSystemEventHandler = object  # type: ignore[assignment,misc]
    Observer = None  # type: ignore[assignment]
    _WATCHDOG = False

from . import inbox_packet
from . import parser as parser_mod
from . import router as router_mod
from .logger import JsonlLogger, build_log_record
from .models import (
    Action, AppConfig, ErrorReason, ProjectConfig, SkipReason,
)
from .mover import apply_route, cleanup_orphan_tmp
from .stability import has_temp_extension, size_stable, wait_until_readable


class _DedupCache:
    """Bounded LRU cache of (size, mtime_ns, first_seen_ts) keyed by abs path.

    Implements L5: prevents duplicate processing when Windows fires multiple
    events for the same already-stable file.
    """

    def __init__(self, max_entries: int = 512, ttl_s: float = 60.0):
        self._data: "OrderedDict[str, Tuple[int, int, float]]" = OrderedDict()
        self._lock = threading.Lock()
        self.max_entries = max_entries
        self.ttl_s = ttl_s

    def check_and_set(self, path: str, size: int, mtime_ns: int) -> bool:
        """Return True if the fingerprint is new or changed. False = duplicate."""
        now = time.time()
        with self._lock:
            self._evict(now)
            existing = self._data.get(path)
            if existing is not None:
                esize, emtime, _ = existing
                if esize == size and emtime == mtime_ns:
                    self._data.move_to_end(path)
                    return False
            self._data[path] = (size, mtime_ns, now)
            self._data.move_to_end(path)
            while len(self._data) > self.max_entries:
                self._data.popitem(last=False)
            return True

    def invalidate(self, path: str) -> None:
        with self._lock:
            self._data.pop(path, None)

    def _evict(self, now: float) -> None:
        stale = [k for k, (_, _, ts) in self._data.items() if now - ts > self.ttl_s]
        for k in stale:
            self._data.pop(k, None)


class RouterWatcher:
    """Core worker that processes a single file path through the pipeline."""

    def __init__(self, config: AppConfig, logger: JsonlLogger):
        self.config = config
        self.logger = logger
        self.cache = _DedupCache()
        self._stopping = threading.Event()
        self._busy = threading.Lock()
        self._allowed_ext = {e.lower() for e in config.allowed_extensions}
        self._temp_ext = list(config.temporary_extensions)

    def stop(self) -> None:
        self._stopping.set()

    def is_stopping(self) -> bool:
        return self._stopping.is_set()

    def process_path(self, path: Path) -> None:
        if self._stopping.is_set():
            return
        path = Path(path)
        if not path.exists() or not path.is_file():
            return

        if has_temp_extension(path, self._temp_ext):
            # Partial download — wait silently. Real file will fire another event.
            return

        # REV E-Lazy (Q8): skip packet files to avoid recursive routing if
        # operator accidentally copies a packet into the watch folder.
        if inbox_packet.is_packet_filename(path.name):
            return

        try:
            st = path.stat()
        except OSError:
            return

        key = str(path.resolve())
        if not self.cache.check_and_set(key, st.st_size, st.st_mtime_ns):
            return  # L5: same fingerprint already processed

        ext = path.suffix.lower()

        if ext not in self._allowed_ext:
            self.logger.log(build_log_record(
                source_path=path,
                original_filename=path.name,
                action=Action.SKIPPED.value,
                reason=SkipReason.UNSUPPORTED_EXT.value,
                dry_run=self.config.dry_run,
            ))
            return

        # Stability — if still growing, invalidate cache so next event retries.
        checks = max(2, self.config.scan_stable_checks)
        interval = max(0.01, float(self.config.scan_stable_seconds) / (checks - 1))
        if not size_stable(path, checks=checks, interval_s=interval):
            self.cache.invalidate(key)
            return

        if not wait_until_readable(
            path,
            max_retries=self.config.max_lock_retries,
            delay_s=self.config.lock_retry_delay_s,
        ):
            self.cache.invalidate(key)
            self.logger.log(build_log_record(
                source_path=path,
                original_filename=path.name,
                action=Action.ERROR.value,
                reason=ErrorReason.FILE_LOCKED_AFTER_RETRIES.value,
                dry_run=self.config.dry_run,
            ))
            return

        with self._busy:
            meta = parser_mod.parse(path, self.config)
            decision = router_mod.decide(meta, path.name, self.config)

            if decision.destination_path is None:
                self.logger.log(build_log_record(
                    source_path=path,
                    original_filename=path.name,
                    parsed=meta,
                    action=decision.action.value,
                    reason=decision.reason,
                    dry_run=self.config.dry_run,
                ))
                return

            project_cfg = self._lookup_project_cfg(meta)

            try:
                apply_res = apply_route(
                    decision,
                    path,
                    dry_run=self.config.dry_run,
                    duplicate_strategy=self.config.duplicate_strategy,
                    project_cfg=project_cfg,
                    app_cfg=self.config,
                )
            except Exception as e:
                self.logger.log(build_log_record(
                    source_path=path,
                    original_filename=path.name,
                    parsed=meta,
                    action=Action.ERROR.value,
                    reason=f"{ErrorReason.COPY_FAILED.value}: {e}",
                    destination_path=decision.destination_path,
                    new_filename=decision.new_filename,
                    dry_run=self.config.dry_run,
                ))
                return

            primary = apply_res.primary
            strategy_val = (
                primary.strategy.value
                if primary is not None and primary.strategy is not None
                else None
            )
            self.logger.log(build_log_record(
                source_path=path,
                original_filename=path.name,
                parsed=meta,
                action=decision.action.value,
                reason=decision.reason,
                destination_path=decision.destination_path,
                new_filename=decision.new_filename,
                duplicate_detected=primary.duplicate_detected if primary else False,
                overwrite_applied=primary.overwrite_applied if primary else False,
                move_strategy=strategy_val,
                dry_run=self.config.dry_run,
                mirror_destination_paths=decision.mirror_destination_paths,
                mirror_failed=apply_res.mirror_failed,
                mirror_status=apply_res.mirror_status,
                mirror_errors=apply_res.mirror_errors,
            ))

    def _lookup_project_cfg(self, meta) -> Optional[ProjectConfig]:
        """REV E-Lazy: tìm ProjectConfig từ parsed metadata để truyền xuống
        apply_route (chỉ cần khi packet drop được kích hoạt).

        Match theo project_code (canonical) trước, fallback theo project key.
        Trả None nếu không tìm được — apply_route sẽ skip packet drop.
        """
        if meta is None:
            return None
        code = getattr(meta, "project_code", None)
        if code:
            key = self.config.project_code_to_key().get(code)
            if key:
                return self.config.projects.get(key)
        pname = getattr(meta, "project", None)
        if pname and pname in self.config.projects:
            return self.config.projects[pname]
        return None

    def scan_existing(self) -> None:
        if not self.config.watch_folder.exists():
            return
        for p in sorted(self.config.watch_folder.iterdir()):
            if self._stopping.is_set():
                break
            if p.is_file():
                self.process_path(p)

    def cleanup_orphans(self) -> int:
        roots = [p.root for p in self.config.projects.values()]
        # v2: also scan _REPORTER_HUB per project (mirror orphans).
        hub = self.config.reporter_hub_name or "_REPORTER_HUB"
        for p in self.config.projects.values():
            roots.append(p.root / hub)
        roots.append(self.config.review_folder)
        return cleanup_orphan_tmp(roots, os.getpid())


class _Handler(FileSystemEventHandler):  # type: ignore[misc]
    def __init__(self, watcher: RouterWatcher):
        self.watcher = watcher

    def on_created(self, event):
        if getattr(event, "is_directory", False):
            return
        self.watcher.process_path(Path(event.src_path))

    def on_modified(self, event):
        if getattr(event, "is_directory", False):
            return
        self.watcher.process_path(Path(event.src_path))

    def on_moved(self, event):
        if getattr(event, "is_directory", False):
            return
        self.watcher.process_path(Path(event.dest_path))


def run(config: AppConfig, once: bool = False, scan_existing: bool = True) -> int:
    """Top-level entry. Returns exit code."""
    logger = JsonlLogger(config.log_folder)
    for w in config.warnings or []:
        print(w)

    watcher = RouterWatcher(config, logger)

    removed = watcher.cleanup_orphans()
    if removed:
        logger.log({
            "timestamp": None,  # JsonlLogger will fill
            "action": "startup",
            "reason": f"cleaned {removed} orphan tmp files",
            "original_filename": None,
            "destination_path": None,
            "dry_run": config.dry_run,
        })

    if scan_existing:
        watcher.scan_existing()

    if once:
        return 0

    if not _WATCHDOG or Observer is None:
        print("[ERROR] watchdog is not installed; cannot run live watcher. "
              "Use --once for a single scan.", file=sys.stderr)
        return 3

    observer = Observer()
    handler = _Handler(watcher)
    observer.schedule(handler, str(config.watch_folder), recursive=False)
    observer.start()

    stop_event = threading.Event()

    def _shutdown(signum, frame):  # noqa: ARG001
        watcher.stop()
        stop_event.set()

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        try:
            signal.signal(signal.SIGTERM, _shutdown)
        except (ValueError, OSError):
            pass

    try:
        while not stop_event.is_set():
            stop_event.wait(0.5)
    finally:
        observer.stop()
        observer.join(timeout=10)
    return 0
