"""Manual / CI helper to refresh config/template_registry.json.

Scope (plan §13.1):
- Scan the drafts/ folders of the two companies.
- For each markdown template, extract:
    - first markdown heading after metadata (§3.4.1)
    - `Loại:` / `Loai:` / `Type:` value if present
    - From / To / Phase / Pod defaults from the header block
- Emit a JSON array of TemplateEntry dicts.

NOT in scope:
- Parsing template body / business logic.
- Auto-updating config/bot.json or config.example.json (AC18).
- Running as a watcher at runtime.

Usage:
    python -m scripts.refresh_template_registry --roots <dir1> <dir2> [--write]

`--write` writes to config/template_registry.json next to this repo; without
it, prints to stdout.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from app.defaults import DEFAULT_DOC_TYPE_ALIASES, default_importance  # noqa: E402
from app.models import DocumentType, PhaseType  # noqa: E402
from app.parser import (  # noqa: E402
    _extract_heading_line,
    _normalize_heading,
    parse_content_v2,
)

HEADER_VALUE_RE = re.compile(r"^\s*([A-Za-zÀ-ỹ ]+)\s*:\s*(.+)$")


def scan_roots(roots: Iterable[Path]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for root in roots:
        root = Path(root)
        if not root.exists():
            print(f"[WARN] Root does not exist: {root}", file=sys.stderr)
            continue
        company_type = _guess_company_type(root)
        for md in sorted(root.rglob("*.md")):
            try:
                entry = _entry_for(md, company_type)
            except Exception as e:  # pragma: no cover — defensive
                print(f"[WARN] Failed to parse {md}: {e}", file=sys.stderr)
                continue
            if entry is not None:
                entries.append(entry)
    return entries


def _guess_company_type(root: Path) -> str:
    name = str(root).lower()
    if "sieu" in name or "siêu to" in name:
        return "job_sieu_to"
    return "job_trung_binh"


def _entry_for(md: Path, company_type: str) -> Optional[Dict[str, Any]]:
    text = md.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    header_fields = _parse_header_fields(lines)
    content_v2 = parse_content_v2(md)
    heading_line = _extract_heading_line(md)
    heading_clean = _clean_heading_label(heading_line) if heading_line else None

    doc_type_raw = (content_v2.get("doc_type") or "").strip()
    has_explicit_doctype = bool(doc_type_raw)

    loai_raw = (content_v2.get("loai") or "").strip()
    alias_values = [loai_raw] if loai_raw else []

    # Resolve the entry's doc_type (best-effort, deterministic).
    doc_type = _resolve_doc_type(doc_type_raw, loai_raw, heading_clean)
    if doc_type is None:
        return None  # template not recognizable; let registry omit it

    contract_source = _resolve_contract_source(
        has_explicit_doctype, bool(alias_values), bool(heading_clean)
    )

    phase_default = _resolve_phase(content_v2.get("phase") or header_fields.get("phase"))
    importance_default = default_importance(doc_type).value
    mirror_default = importance_default == "CRITICAL"

    entry: Dict[str, Any] = {
        "template_path": str(md),
        "company_type": company_type,
        "contract_source": contract_source,
        "doc_type": doc_type,
        "status": "active",
    }
    if heading_clean:
        entry["heading_exact"] = heading_clean
    if alias_values:
        entry["doc_type_alias_values"] = alias_values
    entry["has_explicit_doctype_field"] = has_explicit_doctype
    if phase_default:
        entry["phase_default"] = phase_default
    if header_fields.get("from"):
        entry["from_role_default"] = header_fields["from"].upper()
    if header_fields.get("to"):
        entry["to_role_default"] = header_fields["to"].upper()
    if header_fields.get("pod"):
        entry["pod_default"] = header_fields["pod"]
    entry["filename_pattern"] = "PROJECT_CODE__PHASE__POD__DOCTYPE__FROM_gui_TO.md"
    entry["importance_default"] = importance_default
    entry["mirror_to_reporter_default"] = mirror_default
    entry["notes"] = ""
    return entry


def _parse_header_fields(lines: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for i, line in enumerate(lines[:30]):
        m = HEADER_VALUE_RE.match(line)
        if not m:
            continue
        key = m.group(1).strip().lower()
        val = m.group(2).strip()
        if key in {"từ", "tu", "from"}:
            out["from"] = val
        elif key in {"gửi", "gui", "to"}:
            out["to"] = val
        elif key in {"pod"}:
            out["pod"] = val
        elif key in {"phase"}:
            out["phase"] = val
    return out


def _clean_heading_label(line: str) -> str:
    stripped = re.sub(r"^\s*#{1,6}\s+", "", line).strip()
    return "## " + stripped


def _resolve_doc_type(doctype_field: str, loai_field: str, heading: Optional[str]) -> Optional[str]:
    valid = {e.value for e in DocumentType}
    if doctype_field and doctype_field in valid:
        return doctype_field
    if loai_field:
        mapped = DEFAULT_DOC_TYPE_ALIASES.get(loai_field.strip().casefold())
        if mapped:
            return mapped
    if heading:
        from app.defaults import DEFAULT_HEADING_MAP
        norm = _normalize_heading(heading)
        for k, v in DEFAULT_HEADING_MAP.items():
            if _normalize_heading(k) == norm:
                return v
    return None


def _resolve_contract_source(
    has_explicit_doctype: bool, has_loai: bool, has_heading: bool
) -> str:
    sources = sum([has_explicit_doctype, has_loai, has_heading])
    if sources >= 2:
        return "mixed"
    if has_explicit_doctype:
        return "explicit_doctype"
    if has_loai:
        return "loai"
    if has_heading:
        return "heading"
    return "heading"  # fallback; will likely drift and caller flags


def _resolve_phase(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    from app.defaults import DEFAULT_PHASE_ALIASES
    key = raw.strip().upper()
    if key in DEFAULT_PHASE_ALIASES:
        return DEFAULT_PHASE_ALIASES[key]
    valid = {p.value for p in PhaseType}
    if key in valid:
        return key
    return None


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roots", nargs="+", type=Path, required=True,
                        help="Template root directories to scan (drafts/ folders)")
    parser.add_argument("--write", action="store_true",
                        help="Write to config/template_registry.json instead of stdout")
    parser.add_argument("--out", type=Path, default=HERE / "config" / "template_registry.json",
                        help="Output path when --write is set")
    args = parser.parse_args(argv)

    entries = scan_roots(args.roots)
    payload = {"entries": entries}
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.write:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"[OK] Wrote {len(entries)} entries -> {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
