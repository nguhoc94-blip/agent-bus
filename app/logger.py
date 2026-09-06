"""Dual sink logger: human-readable console + append-only JSONL per day."""

from __future__ import annotations

import io
import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Force UTF-8 stdout/stderr so Vietnamese filenames print correctly in cmd.exe
# (chcp 65001 alone is not enough; Python needs reconfigure too)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def now_iso() -> str:
    """Local time with tz offset, e.g. 2026-04-20T15:41:22+07:00."""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class JsonlLogger:
    """Writes one JSON object per line to `router_YYYY-MM-DD.jsonl`.

    Log failures degrade gracefully — never raise into the pipeline.
    """

    def __init__(self, log_folder: Path):
        self.log_folder = Path(log_folder)
        self._lock = threading.Lock()

    def _path_for_today(self) -> Path:
        date = datetime.now().strftime("%Y-%m-%d")
        return self.log_folder / f"router_{date}.jsonl"

    def log(self, record: Dict[str, Any]) -> None:
        record = dict(record)
        record.setdefault("timestamp", now_iso())
        try:
            line = json.dumps(record, ensure_ascii=False, default=str)
        except (TypeError, ValueError) as e:
            print(f"[LOG-SERIALIZE-ERR] {e}: keys={list(record.keys())}",
                  file=sys.stderr)
            return

        self._console(record)

        try:
            self.log_folder.mkdir(parents=True, exist_ok=True)
            with self._lock:
                with self._path_for_today().open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
        except OSError as e:
            print(f"[LOG-DISK-FALLBACK] {line}  (err: {e})", file=sys.stderr)

    def _console(self, record: Dict[str, Any]) -> None:
        action = str(record.get("action", "?")).upper()
        filename = record.get("original_filename") or "-"
        reason = record.get("reason") or ""
        dest = record.get("destination_path") or ""
        tag = " [DRY]" if record.get("dry_run") else ""
        print(f"[{action}]{tag} {filename} -> {dest} ({reason})")


def build_log_record(
    *,
    source_path: Optional[Path] = None,
    original_filename: Optional[str] = None,
    parsed: Optional[Any] = None,
    action: Optional[str] = None,
    reason: Optional[str] = None,
    destination_path: Optional[Path] = None,
    new_filename: Optional[str] = None,
    duplicate_detected: bool = False,
    overwrite_applied: bool = False,
    move_strategy: Optional[str] = None,
    dry_run: bool = False,
    # v2 additions (all optional to keep backward-compat)
    project_code: Optional[str] = None,
    display_project_name: Optional[str] = None,
    phase: Optional[str] = None,
    doc_type: Optional[str] = None,
    importance: Optional[str] = None,
    classification_source: Optional[str] = None,
    mirror_destination_paths: Optional[Any] = None,
    mirror_failed: bool = False,
    mirror_status: Optional[str] = None,
    mirror_errors: Optional[Any] = None,
) -> Dict[str, Any]:
    """Assemble a log record matching the plan §7 schema (extended in v2)."""
    # Extract v2 fields from parsed if not explicitly passed.
    def _p(attr, default=None):
        return getattr(parsed, attr, default) if parsed is not None else default

    return {
        "timestamp": now_iso(),
        "source_path": str(source_path) if source_path else None,
        "original_filename": original_filename,
        "new_filename": new_filename,
        "destination_path": str(destination_path) if destination_path else None,
        "project": _p("project"),
        "pod": _p("pod"),
        "from_role": _p("from_role"),
        "to_role": _p("to_role"),
        "action": action,
        "reason": reason,
        "source_of_metadata": _p("source_of_metadata"),
        "duplicate_detected": duplicate_detected,
        "overwrite_applied": overwrite_applied,
        "move_strategy": move_strategy,
        "dry_run": dry_run,
        # v2 fields
        "project_code": project_code if project_code is not None else _p("project_code"),
        "display_project_name": (
            display_project_name if display_project_name is not None
            else _p("display_project_name")
        ),
        "phase": phase if phase is not None
                 else (_p("phase").value if _p("phase") is not None and hasattr(_p("phase"), "value") else None),
        "doc_type": doc_type if doc_type is not None
                    else (_p("doc_type").value if _p("doc_type") is not None and hasattr(_p("doc_type"), "value") else None),
        "importance": importance if importance is not None
                      else (_p("importance").value if _p("importance") is not None and hasattr(_p("importance"), "value") else None),
        "classification_source": classification_source if classification_source is not None else _p("classification_source"),
        "mirror_destination_paths": (
            [str(x) for x in mirror_destination_paths] if mirror_destination_paths else []
        ),
        "mirror_failed": mirror_failed,
        "mirror_status": mirror_status,
        "mirror_errors": list(mirror_errors) if mirror_errors else [],
    }
