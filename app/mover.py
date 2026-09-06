"""Filesystem move + copy logic.

v1 kept `move_safe` for atomic same-volume moves and cross-volume copy+replace.
v2 adds:
- `copy_safe`: like move_safe but does NOT delete src. Used for reporter-hub
  mirroring.
- `apply_route`: orchestrate primary move + optional mirror copies. Mirror
  failures never compromise the primary move.
"""

from __future__ import annotations

import os
import re
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional

from .models import AppConfig, MoveStrategy, ProjectConfig, RouteDecision


@dataclass
class MoveResult:
    planned_path: Path
    duplicate_detected: bool
    moved: bool
    overwrite_applied: bool = False
    strategy: Optional[MoveStrategy] = None


@dataclass
class CopyResult:
    planned_path: Path
    duplicate_detected: bool
    copied: bool
    overwrite_applied: bool = False
    strategy: Optional[MoveStrategy] = None


@dataclass
class ApplyResult:
    primary: Optional[MoveResult]
    mirrors: List[CopyResult] = field(default_factory=list)
    mirror_errors: List[str] = field(default_factory=list)
    mirror_failed: bool = False
    mirror_status: str = "none"  # "none" | "ok" | "partial" | "failed"


ORPHAN_PAT = re.compile(r"\.tmp_(\d+)_[0-9a-f]+$")


def same_volume(p1: Path, p2: Path) -> bool:
    d1 = os.path.splitdrive(str(p1))[0].lower()
    d2 = os.path.splitdrive(str(p2))[0].lower()
    return d1 == d2


def _tmp_path(dest: Path) -> Path:
    return dest.with_name(
        f"{dest.name}.tmp_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    )


def _resolve_dest_for_strategy(dest: Path, duplicate_strategy: str) -> Path:
    """Return the effective destination path for the given strategy.

    - overwrite: return dest as-is (os.replace will overwrite).
    - suffix: if dest exists, append a numeric suffix to the stem until free.
      Example: file.md -> file__dup1.md, file__dup2.md, ...
    """
    if duplicate_strategy == "overwrite":
        return dest
    if duplicate_strategy != "suffix":
        raise ValueError(f"Unsupported duplicate_strategy: {duplicate_strategy}")
    if not dest.exists():
        return dest
    stem = dest.stem
    ext = dest.suffix
    for i in range(1, 10_000):
        candidate = dest.with_name(f"{stem}__REV_{i:03d}{ext}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not find free duplicate suffix for: {dest}")


def move_safe(
    src: Path,
    dest: Path,
    dry_run: bool = False,
    *,
    duplicate_strategy: str = "overwrite",
) -> MoveResult:
    """Move src -> dest with overwrite semantics.

    Same-volume  -> os.replace (atomic).
    Cross-volume -> shutil.copy2 to tmp, os.replace, os.remove(src).
    Dry-run      -> compute flags only, no FS mutation.
    On any exception during cross-volume copy, clean up tmp before re-raising.
    """
    duplicate = dest.exists()
    effective_dest = _resolve_dest_for_strategy(dest, duplicate_strategy)
    # In suffix mode, we never overwrite; a duplicate is detected if the base dest exists.
    # In overwrite mode, duplicate means we will atomically replace.
    if duplicate_strategy == "suffix":
        overwrite_applied = False
    else:
        overwrite_applied = duplicate
    dest = effective_dest
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dry_run:
        return MoveResult(
            planned_path=dest,
            duplicate_detected=duplicate,
            moved=False,
            overwrite_applied=False,
            strategy=None,
        )

    if same_volume(src, dest):
        os.replace(str(src), str(dest))
        return MoveResult(
            planned_path=dest,
            duplicate_detected=duplicate,
            moved=True,
            overwrite_applied=overwrite_applied,
            strategy=MoveStrategy.ATOMIC_REPLACE,
        )

    tmp = _tmp_path(dest)
    try:
        src_size = src.stat().st_size
        shutil.copy2(str(src), str(tmp))
        copied_size = tmp.stat().st_size
        if copied_size < src_size:
            raise IOError(
                f"Copy size mismatch: tmp={copied_size} < src={src_size}")
        os.replace(str(tmp), str(dest))
    except BaseException:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise

    try:
        os.remove(str(src))
    except OSError:
        # Source could not be removed (permissions, deleted racy) — data already at dest.
        pass

    return MoveResult(
        planned_path=dest,
        duplicate_detected=duplicate,
        moved=True,
        overwrite_applied=overwrite_applied,
        strategy=MoveStrategy.CROSS_VOLUME_COPY,
    )


def copy_safe(
    src: Path,
    dest: Path,
    dry_run: bool = False,
    *,
    duplicate_strategy: str = "overwrite",
) -> CopyResult:
    """Atomic copy src -> dest, leaving src intact.

    Same-volume  -> shutil.copy2 to tmp in dest dir, then os.replace to dest.
    Cross-volume -> identical flow (copy2 always works cross-volume).
    Overwrite policy matches move_safe: if dest exists, we atomically replace
    it through the tmp file, no timestamp suffix, no backup.
    """
    duplicate = dest.exists()
    effective_dest = _resolve_dest_for_strategy(dest, duplicate_strategy)
    if duplicate_strategy == "suffix":
        overwrite_applied = False
    else:
        overwrite_applied = duplicate
    dest = effective_dest
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dry_run:
        return CopyResult(
            planned_path=dest,
            duplicate_detected=duplicate,
            copied=False,
            overwrite_applied=False,
            strategy=None,
        )

    strategy = (
        MoveStrategy.ATOMIC_REPLACE if same_volume(src, dest)
        else MoveStrategy.CROSS_VOLUME_COPY
    )

    tmp = _tmp_path(dest)
    try:
        src_size = src.stat().st_size
        shutil.copy2(str(src), str(tmp))
        copied_size = tmp.stat().st_size
        if copied_size < src_size:
            raise IOError(
                f"Copy size mismatch: tmp={copied_size} < src={src_size}")
        os.replace(str(tmp), str(dest))
    except BaseException:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise

    return CopyResult(
        planned_path=dest,
        duplicate_detected=duplicate,
        copied=True,
        overwrite_applied=overwrite_applied,
        strategy=strategy,
    )


def apply_route(
    decision: RouteDecision,
    src: Path,
    dry_run: bool = False,
    *,
    duplicate_strategy: str = "overwrite",
    project_cfg: Optional[ProjectConfig] = None,
    app_cfg: Optional[AppConfig] = None,
) -> ApplyResult:
    """Execute a RouteDecision: move primary, then copy each mirror.

    Ordering: primary FIRST. Mirror copies happen only after primary succeeds,
    and they read from the destination path (not src, because src is gone after
    a successful move). If the primary move raises, we do not attempt any
    mirror and re-raise.

    Mirror failures are captured but never roll back the primary — the file is
    already safely routed. Callers read ApplyResult.mirror_failed / .mirror_errors
    for logging.

    REV E-Lazy (optional kwargs `project_cfg` + `app_cfg`): sau khi primary move
    thành công và primary_dest match `<POD>/<ROLE>_INBOX/` pattern, drop
    `_RUNTIME_PACKET.md` vào inbox nếu chưa có (idempotent). Bỏ qua nếu
    `project_cfg`/`app_cfg` không được truyền (backward compat) hoặc nếu
    `app_cfg.auto_drop_inbox_packet=False`.
    """
    result = ApplyResult(primary=None)

    if decision.destination_path is None and decision.primary_destination_path is None:
        return result

    primary_dest = decision.primary_destination_path or decision.destination_path
    assert primary_dest is not None
    primary_res = move_safe(
        src,
        primary_dest,
        dry_run=dry_run,
        duplicate_strategy=duplicate_strategy,
    )
    result.primary = primary_res

    # REV E-Lazy: drop packet sau khi primary move thật sự thành công, skip dry_run.
    if (
        not dry_run
        and primary_res.moved
        and project_cfg is not None
        and app_cfg is not None
    ):
        _maybe_drop_inbox_packet(primary_res.planned_path, project_cfg, app_cfg)

    mirrors = decision.mirror_destination_paths or []
    if not mirrors:
        result.mirror_status = "none"
        return result

    # Source of the mirror copy is the primary dest (real file now lives there).
    # Under dry_run the primary file still lives at `src`; use it so the
    # conceptual copy size still resolves.
    mirror_src = src if dry_run or not primary_res.moved else primary_dest

    any_fail = False
    any_ok = False
    for mdest in mirrors:
        try:
            cres = copy_safe(
                mirror_src,
                mdest,
                dry_run=dry_run,
                duplicate_strategy=duplicate_strategy,
            )
            result.mirrors.append(cres)
            if cres.copied or dry_run:
                any_ok = True
        except Exception as e:  # noqa: BLE001 — intentional broad: we log
            result.mirror_errors.append(f"{mdest}: {e}")
            any_fail = True

    if any_fail and not any_ok:
        result.mirror_status = "failed"
    elif any_fail:
        result.mirror_status = "partial"
    else:
        result.mirror_status = "ok"
    result.mirror_failed = any_fail
    return result


def _maybe_drop_inbox_packet(
    primary_path: Path,
    project_cfg: ProjectConfig,
    app_cfg: AppConfig,
) -> None:
    """REV E-Lazy hook: drop _RUNTIME_PACKET.md into the inbox folder of
    `primary_path` if (a) the path matches `<POD>/<ROLE>_INBOX/` pattern and
    (b) packet doesn't already exist.

    Lazy import to avoid circular dependency (inbox_packet may import models).
    Never raises — packet drop failures must not break routing.
    """
    try:
        from . import inbox_packet
    except ImportError:  # pragma: no cover
        return
    location = inbox_packet.is_primary_inbox(primary_path, project_cfg, app_cfg)
    if location is None:
        return  # not a primary agent inbox (mirror / review / unknown layout)
    pod, role = location
    try:
        inbox_packet.ensure_inbox_packet(
            primary_path.parent, project_cfg, pod, role, app_cfg,
        )
    except Exception:  # noqa: BLE001 — never fail routing
        # ensure_inbox_packet already logs internally; swallow here.
        pass


def cleanup_orphan_tmp(roots: Iterable[Path], current_pid: int) -> int:
    """Recursively scan `roots`, delete *.tmp_<pid>_<hex> files whose pid != current_pid.

    In v2, callers should pass both project roots AND their _REPORTER_HUB
    subfolders (the watcher handles this). This function only walks whatever
    is given; it's intentionally dumb.
    """
    removed = 0
    for root in roots:
        if not root or not Path(root).exists():
            continue
        for p in Path(root).rglob("*"):
            if not p.is_file():
                continue
            m = ORPHAN_PAT.search(p.name)
            if not m:
                continue
            try:
                pid = int(m.group(1))
            except ValueError:
                continue
            if pid == current_pid:
                continue
            try:
                p.unlink()
                removed += 1
            except OSError:
                pass
    return removed
