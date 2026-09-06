"""File stability checks — temporary-extension filter, size stability, lock retry."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Iterable, Optional


def has_temp_extension(path: Path, temporary_extensions: Iterable[str]) -> bool:
    name = path.name.lower()
    for ext in temporary_extensions:
        ext_l = ext.lower()
        if not ext_l.startswith("."):
            ext_l = "." + ext_l
        if name.endswith(ext_l):
            return True
    return False


def size_stable(
    path: Path,
    checks: int = 3,
    interval_s: float = 1.0,
    sleep: Optional[Callable[[float], None]] = None,
) -> bool:
    """Return True if file size stays constant across `checks` polls."""
    if checks < 2:
        checks = 2
    sleep_fn = sleep or time.sleep
    try:
        last = path.stat().st_size
    except OSError:
        return False
    for _ in range(checks - 1):
        sleep_fn(interval_s)
        try:
            cur = path.stat().st_size
        except OSError:
            return False
        if cur != last:
            return False
        last = cur
    return True


def is_locked(path: Path) -> bool:
    """Best-effort: try opening in write-shared mode. True if OS denies."""
    try:
        with path.open("r+b"):
            return False
    except OSError:
        return True


def wait_until_readable(
    path: Path,
    max_retries: int = 5,
    delay_s: float = 1.0,
    sleep: Optional[Callable[[float], None]] = None,
) -> bool:
    """Retry opening for read until it succeeds or retries are exhausted."""
    sleep_fn = sleep or time.sleep
    attempts = max(1, max_retries)
    for i in range(attempts):
        try:
            with path.open("rb"):
                return True
        except OSError:
            if i < attempts - 1:
                sleep_fn(delay_s)
    return False
