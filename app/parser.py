"""Metadata parser v2.

Layers:
- Layer 1 content (.md/.txt only): parses Project/Pod/From/To + Phase + DocType
  + Loại/Loai/Type. Also extracts the first heading line (§3.4.1).
- Layer 2 filename regex: FILENAME_V2 (6 parts) and FILENAME_FULL (v1, 4 parts)
  and FILENAME_TOLERANT (pod + roles only).
- Layer 3 merge/classify: `classify_document()` implements Hybrid 2 (§3.4):
  DocType field > Loại field > heading_map fallback > filename_v2 > UNKNOWN.

Classifier is purely rule-based — no fuzzy, no semantic, no LLM (plan §10).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Optional, Tuple

from .defaults import (
    CRITICAL_FLOW_WHITELIST,
    DEFAULT_DOCTYPE_PHASE_MAP,
    DEFAULT_DOC_TYPE_ALIASES,
    DEFAULT_HEADING_MAP,
    DEFAULT_PHASE_ALIASES,
    DEFAULT_ROLE_ALIASES,
    DOC_TYPE_FROM_DISAMBIG,
    DOC_TYPE_NON_RESOLVABLE,
    default_importance,
)
from .models import (
    AmbiguityCause,
    AppConfig,
    ClassificationResult,
    DocumentType,
    ImportanceLevel,
    ParsedMetadata,
    PhaseType,
)

CONTENT_MAX_LINES = 50

# v1 patterns — preserved for backward compat.
CONTENT_PATTERNS: Dict[str, "re.Pattern[str]"] = {
    "project": re.compile(r"^\s*Project\s*:\s*(.+)", re.IGNORECASE),
    # Pod: strip optional leading "(" so "(cross-project — …)" → "cross-project".
    # Only captures [A-Za-z0-9_-]+ so placeholder tokens like "[điền tên pod]"
    # yield None (→ MISSING_POD), rather than an un-normalizable string.
    "pod":     re.compile(r"^\s*Pod\s*:\s*\(?([A-Za-z0-9_-]+)", re.IGNORECASE),
    "from":    re.compile(r"^\s*(?:Từ|Tu|From)\s*:\s*(\S+)", re.IGNORECASE),
    "to":      re.compile(r"^\s*(?:Gửi|Gui|To)\s*:\s*(\S+)", re.IGNORECASE),
}

# v2 patterns — allow greedy rest-of-line for Phase/DocType/Loại.
CONTENT_PATTERNS_V2: Dict[str, "re.Pattern[str]"] = {
    "phase":    re.compile(r"^\s*Phase\s*:\s*(.+)", re.IGNORECASE),
    "doc_type": re.compile(r"^\s*DocType\s*:\s*(.+)", re.IGNORECASE),
    "loai":     re.compile(r"^\s*(?:Loại|Loai|Type)\s*:\s*(.+)", re.IGNORECASE),
}

# v2 canonical filename: PROJECT_CODE__PHASE__POD__DOCTYPE__FROM_gui_TO.ext
FILENAME_V2 = re.compile(
    r"^(?P<project>[A-Z0-9_]+)__(?P<phase>[A-Z0-9_]+)__(?P<pod>[A-Z0-9_]+)"
    r"__(?P<doctype>[A-Z0-9_]+)__(?P<from>[A-Z]+)_gui_(?P<to>[A-Z]+)"
    r"\.[a-z0-9]+$",
    re.IGNORECASE,
)

# Legacy v1 filenames.
FILENAME_FULL = re.compile(
    r"^(?P<project>[A-Z0-9_]+)__(?P<pod>[A-Z0-9_]+)__(?P<from>[A-Z]+)_gui_(?P<to>[A-Z]+)\.[a-z0-9]+$",
    re.IGNORECASE,
)

FILENAME_TOLERANT = re.compile(
    r"^(?P<pod>POD_[A-Z0-9_]+)__(?P<from>[A-Z]+)_gui_(?P<to>[A-Z]+)\.[a-z0-9]+$",
    re.IGNORECASE,
)

TEXT_EXTENSIONS = {".md", ".txt"}

HEADING_LINE_RE = re.compile(r"^#{1,6}\s+.+$")
METADATA_KV_RE = re.compile(r"^\s*[A-Za-zÀ-ỹ][A-Za-zÀ-ỹ0-9 _-]*\s*:\s*.+$")


# ---------------------------------------------------------------------------
# Content parsing
# ---------------------------------------------------------------------------


def parse_content(path: Path) -> Dict[str, Optional[str]]:
    """v1: read first CONTENT_MAX_LINES, extract Project/Pod/From/To."""
    result: Dict[str, Optional[str]] = {k: None for k in ("project", "pod", "from", "to")}
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f):
                if i >= CONTENT_MAX_LINES:
                    break
                for key, pat in CONTENT_PATTERNS.items():
                    if result[key] is None:
                        m = pat.match(line)
                        if m:
                            result[key] = m.group(1)
    except OSError:
        pass
    return result


def parse_content_v2(path: Path) -> Dict[str, Optional[str]]:
    """v2: extract Phase, DocType, Loại from the first CONTENT_MAX_LINES."""
    result: Dict[str, Optional[str]] = {k: None for k in ("phase", "doc_type", "loai")}
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f):
                if i >= CONTENT_MAX_LINES:
                    break
                for key, pat in CONTENT_PATTERNS_V2.items():
                    if result[key] is None:
                        m = pat.match(line)
                        if m:
                            result[key] = m.group(1).strip()
    except OSError:
        pass
    return result


def _extract_heading_line(path: Path) -> Optional[str]:
    """§3.4.1: return the first markdown heading line, after skipping metadata
    key-value lines, blank lines, and `---` separators. Scans at most
    CONTENT_MAX_LINES.
    """
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f):
                if i >= CONTENT_MAX_LINES:
                    break
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped == "---" or stripped.startswith("---"):
                    # allow `---` separators OR dash lines; skip
                    if set(stripped) <= {"-"}:
                        continue
                if HEADING_LINE_RE.match(stripped):
                    return stripped
                if METADATA_KV_RE.match(stripped):
                    continue
                # Non-metadata, non-heading text — stop; no heading available.
                return None
    except OSError:
        return None
    return None


# ---------------------------------------------------------------------------
# Heading normalization §3.4.2
# ---------------------------------------------------------------------------

_DASH_RE = re.compile(r"[—–‒―-]+")
_MD_PREFIX_RE = re.compile(r"^\s*#{1,6}\s+")
_WS_RE = re.compile(r"\s+")


def _normalize_heading(raw: str) -> str:
    """Pipeline: strip markdown prefix -> trim -> collapse whitespace ->
    normalize any dash sequence to em-dash -> casefold.
    Preserves Vietnamese diacritics."""
    if not raw:
        return ""
    s = _MD_PREFIX_RE.sub("", raw)
    s = s.strip()
    s = _WS_RE.sub(" ", s)
    s = _DASH_RE.sub("—", s)
    # Single dashes that are now em-dash — also needs to collapse any accidental
    # trailing spaces introduced by the substitution. Trim again.
    s = _WS_RE.sub(" ", s).strip()
    return s.casefold()


# ---------------------------------------------------------------------------
# Filename parsing
# ---------------------------------------------------------------------------


def parse_filename(filename: str) -> Tuple[Optional[Dict[str, Optional[str]]],
                                           Optional[Dict[str, Optional[str]]]]:
    """Return (full_match, tolerant_match) for v1-style filenames.

    Guard: if the filename ALSO matches the v2 6-part pattern, the v1 regex is
    skipped entirely. Otherwise the greedy v1 `pod` group can swallow the
    phase/doctype segments and fabricate a spurious match (see parser tests).
    """
    full: Optional[Dict[str, Optional[str]]] = None
    tol: Optional[Dict[str, Optional[str]]] = None
    if FILENAME_V2.match(filename):
        return None, None
    m = FILENAME_FULL.match(filename)
    if m:
        full = {
            "project": m.group("project").upper(),
            "pod": m.group("pod").upper(),
            "from": m.group("from").upper(),
            "to": m.group("to").upper(),
        }
    m2 = FILENAME_TOLERANT.match(filename)
    if m2:
        tol = {
            "project": None,
            "pod": m2.group("pod").upper(),
            "from": m2.group("from").upper(),
            "to": m2.group("to").upper(),
        }
    return full, tol


def parse_filename_v2(filename: str) -> Optional[Dict[str, Optional[str]]]:
    """Return parts dict if filename matches the v2 canonical format, else None."""
    m = FILENAME_V2.match(filename)
    if not m:
        return None
    return {
        "project": m.group("project").upper(),
        "phase": m.group("phase").upper(),
        "pod": m.group("pod").upper(),
        "doc_type": m.group("doctype").upper(),
        "from": m.group("from").upper(),
        "to": m.group("to").upper(),
    }


# ---------------------------------------------------------------------------
# Role / phase alias helpers
# ---------------------------------------------------------------------------


def _norm(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    v = v.strip()
    if not v:
        return None
    return v.upper()


def normalize_role(raw: Optional[str], aliases: Optional[Dict[str, str]] = None) -> Optional[str]:
    if raw is None:
        return None
    key = raw.strip().upper()
    if not key:
        return None
    table = aliases or DEFAULT_ROLE_ALIASES
    if key in table:
        return table[key].upper()
    return key  # pass-through (router will reject if not in config.roles)


def normalize_phase(raw: Optional[str], aliases: Optional[Dict[str, str]] = None) -> PhaseType:
    if raw is None:
        return PhaseType.UNKNOWN_PHASE
    key = raw.strip().upper()
    if not key:
        return PhaseType.UNKNOWN_PHASE
    table = aliases or DEFAULT_PHASE_ALIASES
    val = table.get(key)
    if val is None:
        # Accept raw phase enum name if user wrote it literally.
        try:
            return PhaseType(key)
        except ValueError:
            return PhaseType.UNKNOWN_PHASE
    try:
        return PhaseType(val)
    except ValueError:
        return PhaseType.UNKNOWN_PHASE


# ---------------------------------------------------------------------------
# Classifier (Hybrid 2)
# ---------------------------------------------------------------------------


def classify_document(
    content_v2: Dict[str, Optional[str]],
    heading_line: Optional[str],
    from_role: Optional[str],
    to_role: Optional[str],  # noqa: ARG001 — future use; kept for API symmetry
    filename: str,
    *,
    heading_map: Optional[Dict[str, str]] = None,
    doc_type_aliases: Optional[Dict[str, str]] = None,
) -> ClassificationResult:
    """Implements the Hybrid 2 flow (§3.4).

    Priority:
    1. `DocType:` field (if present and valid DocumentType enum value)
    2. `Loại:/Loai:/Type:` value (with from_role disambiguation where needed)
    3. Heading fallback (config heading_map, normalized per §3.4.2)
    4. Filename v2 (if matches FILENAME_V2, extract doc_type part)
    5. Otherwise UNKNOWN_DOC.
    """
    heading_map = heading_map if heading_map is not None else DEFAULT_HEADING_MAP
    doc_type_aliases = doc_type_aliases if doc_type_aliases is not None else DEFAULT_DOC_TYPE_ALIASES
    valid = {e.value for e in DocumentType}

    # 1. DocType field — highest precedence.
    doc_type_field = (content_v2.get("doc_type") or "").strip()
    if doc_type_field:
        # Ignore placeholder tokens like [CEO_BRIEF / ...] that templates ship
        # with unfilled.
        if _is_placeholder(doc_type_field):
            pass
        elif doc_type_field.upper() in valid:
            return ClassificationResult(
                doc_type=DocumentType(doc_type_field.upper()),
                source="doctype_field",
                reason=f"DocType={doc_type_field}",
            )
        # If the field is present but unrecognized, we DO NOT fall through to
        # the legacy behavior blindly — we keep looking, because the user may
        # have written a human label while the actual classification still
        # lives in heading/Loại.

    # 2. Loại / Loai / Type field.
    loai_raw = (content_v2.get("loai") or "").strip()
    if loai_raw and not _is_placeholder(loai_raw):
        loai_key = loai_raw.casefold()
        if loai_key in DOC_TYPE_NON_RESOLVABLE:
            # "report" / "sub-plan" — keep looking, don't claim UNKNOWN yet.
            pass
        elif loai_key in DOC_TYPE_FROM_DISAMBIG:
            rule = DOC_TYPE_FROM_DISAMBIG[loai_key]
            fr = (from_role or "").upper()
            mapped = rule.get(fr) or rule.get("__default__")
            if mapped:
                return ClassificationResult(
                    doc_type=DocumentType(mapped),
                    source="loai_field",
                    reason=f"Loại={loai_raw} + From={from_role}",
                )
        else:
            # Normal lookup (config map first, then defaults).
            mapped = _loai_lookup(loai_raw, doc_type_aliases)
            if mapped:
                return ClassificationResult(
                    doc_type=DocumentType(mapped),
                    source="loai_field",
                    reason=f"Loại={loai_raw}",
                )

    # 3. Heading fallback.
    if heading_line:
        norm = _normalize_heading(heading_line)
        # Look up in a normalized version of the heading_map.
        for key, val in heading_map.items():
            if _normalize_heading(key) == norm:
                # Special-case: "LANE COMPLETION REPORT" must disambiguate by
                # from_role; if user maps it in config, the custom mapping wins,
                # otherwise we resolve here.
                if val == DocumentType.PRODUCT_LANE_COMPLETION.value and (
                    from_role or ""
                ).upper().startswith("ENGINEERING"):
                    val = DocumentType.ENGINEERING_LANE_COMPLETION.value
                return ClassificationResult(
                    doc_type=DocumentType(val),
                    source="heading",
                    reason=f"heading={heading_line}",
                )
        # Built-in disambiguation for "LANE COMPLETION REPORT" which is NOT in
        # DEFAULT_HEADING_MAP (intentionally left out).
        if norm == _normalize_heading("## LANE COMPLETION REPORT"):
            fr = (from_role or "").upper()
            if fr.startswith("PRODUCT"):
                return ClassificationResult(
                    doc_type=DocumentType.PRODUCT_LANE_COMPLETION,
                    source="heading",
                    reason=f"LANE COMPLETION REPORT + From={from_role}",
                )
            if fr.startswith("ENGINEERING"):
                return ClassificationResult(
                    doc_type=DocumentType.ENGINEERING_LANE_COMPLETION,
                    source="heading",
                    reason=f"LANE COMPLETION REPORT + From={from_role}",
                )
            # else fall through to UNKNOWN

    # 4. Filename v2 — lowest precedence.
    v2 = parse_filename_v2(filename)
    if v2 and v2.get("doc_type"):
        dt = v2["doc_type"]
        if dt in valid:
            return ClassificationResult(
                doc_type=DocumentType(dt),
                source="filename_v2",
                reason=f"filename v2 doctype={dt}",
            )

    return ClassificationResult(
        doc_type=DocumentType.UNKNOWN_DOC,
        source="none",
        reason="no DocType/Loại/heading/filename-v2 match",
    )


def _is_placeholder(val: str) -> bool:
    """Detect template placeholders like `[report / sub-plan]` or `[CEO_BRIEF]`."""
    s = val.strip()
    return s.startswith("[") and s.endswith("]")


def _loai_lookup(raw: str, aliases_map: Dict[str, str]) -> Optional[str]:
    """Case-insensitive lookup with trim; returns DocumentType value string."""
    key = raw.strip()
    # Try exact first, then casefold
    if key in aliases_map:
        return aliases_map[key]
    for k, v in aliases_map.items():
        if k.casefold() == key.casefold():
            return v
    return None


# ---------------------------------------------------------------------------
# Phase / importance derivation
# ---------------------------------------------------------------------------


def derive_phase(
    phase_field: Optional[str],
    doc_type: DocumentType,
    phase_aliases: Optional[Dict[str, str]] = None,
    filename_v2_phase: Optional[str] = None,
) -> Tuple[PhaseType, bool]:
    """Return (phase, conflict). conflict=True if the header Phase and the
    filename-v2 Phase disagree."""
    from_header = normalize_phase(phase_field, phase_aliases)
    from_fn = normalize_phase(filename_v2_phase, phase_aliases) if filename_v2_phase else PhaseType.UNKNOWN_PHASE

    # Conflict check: both explicit and different
    if (
        from_header is not PhaseType.UNKNOWN_PHASE
        and from_fn is not PhaseType.UNKNOWN_PHASE
        and from_header != from_fn
    ):
        return from_header, True

    if from_header is not PhaseType.UNKNOWN_PHASE:
        return from_header, False
    if from_fn is not PhaseType.UNKNOWN_PHASE:
        return from_fn, False
    # Fall back to doc_type -> phase default.
    mapped = DEFAULT_DOCTYPE_PHASE_MAP.get(doc_type.value)
    if mapped:
        try:
            return PhaseType(mapped), False
        except ValueError:
            pass
    return PhaseType.UNKNOWN_PHASE, False


def derive_importance(doc_type: DocumentType, config: Optional[AppConfig] = None) -> ImportanceLevel:
    if config is not None and config.critical_doc_types and doc_type.value in config.critical_doc_types:
        return ImportanceLevel.CRITICAL
    return default_importance(doc_type.value)


def should_mirror(doc_type: DocumentType, importance: ImportanceLevel, config: Optional[AppConfig]) -> bool:
    if doc_type == DocumentType.UNKNOWN_DOC:
        return False
    if importance == ImportanceLevel.CRITICAL:
        return True
    mirror_types = (config.mirror_doc_types if config is not None else None) or []
    return doc_type.value in mirror_types


def is_critical_flow(from_role: Optional[str], to_role: Optional[str]) -> bool:
    """§5.3.1 critical_flow_whitelist check for UNKNOWN_DOC escalation."""
    if not from_role or not to_role:
        return False
    pair = (from_role.upper(), to_role.upper())
    return pair in CRITICAL_FLOW_WHITELIST


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


def parse(path: Path, config: AppConfig) -> ParsedMetadata:
    """Parse + classify. Returns ParsedMetadata ready for router.

    Backward-compat: v1 happy path is preserved — callers that don't read the
    v2 fields keep working.
    """
    ext = path.suffix.lower()
    filename = path.name

    if ext in TEXT_EXTENSIONS:
        content_raw = parse_content(path)
        content_v2_raw = parse_content_v2(path)
        heading_line = _extract_heading_line(path)
    else:
        content_raw = {k: None for k in ("project", "pod", "from", "to")}
        content_v2_raw = {k: None for k in ("phase", "doc_type", "loai")}
        heading_line = None

    fn_full, fn_tol = parse_filename(filename)
    fn_v2 = parse_filename_v2(filename)

    content = {k: _norm(v) for k, v in content_raw.items()}
    # v2 content stays raw for case-sensitive matching of Loại values.
    content_v2 = {k: (v.strip() if v else None) for k, v in content_v2_raw.items()}

    # Merge primary 4 fields using existing v1 logic, then augment with v2.
    merged = _merge_primary_fields(
        content=content,
        fn_full=fn_full,
        fn_tol=fn_tol,
        fn_v2=fn_v2,
        filename=filename,
    )

    # If merging flagged AMBIGUOUS, short-circuit.
    if merged.ambiguity_cause is not None:
        return merged

    # Normalize roles.
    if merged.from_role:
        merged.from_role = normalize_role(merged.from_role, config.role_aliases)
    if merged.to_role:
        merged.to_role = normalize_role(merged.to_role, config.role_aliases)

    # Classify.
    result = classify_document(
        content_v2=content_v2,
        heading_line=heading_line,
        from_role=merged.from_role,
        to_role=merged.to_role,
        filename=filename,
        heading_map=config.heading_map or None,
        doc_type_aliases=config.doc_type_aliases or None,
    )
    merged.doc_type = result.doc_type
    merged.classification_source = result.source

    # DocType conflict: v2 content says X, filename v2 says Y.
    if fn_v2 and fn_v2.get("doc_type"):
        fn_dt = fn_v2["doc_type"]
        # If content-based classification came from a header field and differs
        # from filename v2's doctype -> DOCTYPE_CONFLICT.
        if (
            result.source in ("doctype_field", "loai_field", "heading")
            and merged.doc_type.value != fn_dt
        ):
            merged.ambiguity_cause = AmbiguityCause.DOCTYPE_CONFLICT
            merged.reason = (
                f"AMBIGUOUS:DOCTYPE_CONFLICT (content={merged.doc_type.value} "
                f"vs filename={fn_dt})"
            )
            merged.source_of_metadata = "conflict"
            return merged

    # Phase derivation + conflict detection.
    phase, phase_conflict = derive_phase(
        phase_field=content_v2.get("phase"),
        doc_type=merged.doc_type,
        phase_aliases=config.phase_aliases or None,
        filename_v2_phase=fn_v2.get("phase") if fn_v2 else None,
    )
    merged.phase = phase
    if phase_conflict:
        merged.ambiguity_cause = AmbiguityCause.PHASE_CONFLICT
        merged.reason = (
            f"AMBIGUOUS:PHASE_CONFLICT (header vs filename disagree)"
        )
        merged.source_of_metadata = "conflict"
        return merged

    merged.importance = derive_importance(merged.doc_type, config)
    merged.mirror_to_reporter = should_mirror(merged.doc_type, merged.importance, config)

    return merged


def _merge_primary_fields(
    content: Dict[str, Optional[str]],
    fn_full: Optional[Dict[str, Optional[str]]],
    fn_tol: Optional[Dict[str, Optional[str]]],
    fn_v2: Optional[Dict[str, Optional[str]]],
    filename: str,  # noqa: ARG001
) -> ParsedMetadata:
    """Merge content + filename (v1 or v2) into the 4 primary fields.

    Same semantics as v1 `parse()` (preserved verbatim) with the addition that
    if filename is v2, we also treat its project/pod/from/to as a filename
    source.
    """
    content_complete = all(content.values())
    # Treat v2 filename as a full filename source for merging purposes.
    fn_full_effective = fn_full
    if fn_full_effective is None and fn_v2 is not None:
        fn_full_effective = {
            "project": fn_v2["project"],
            "pod": fn_v2["pod"],
            "from": fn_v2["from"],
            "to": fn_v2["to"],
        }
    fn_complete = fn_full_effective is not None and all(
        fn_full_effective.get(k) for k in ("project", "pod", "from", "to")
    )

    multi_fn = False
    if fn_full_effective and fn_tol:
        for key in ("pod", "from", "to"):
            if fn_full_effective[key] != fn_tol[key]:
                multi_fn = True
                break

    if content_complete and fn_complete:
        assert fn_full_effective is not None
        diff = [k for k in ("project", "pod", "from", "to")
                if content[k] != fn_full_effective[k]]
        if diff:
            return ParsedMetadata(
                project=content["project"],
                pod=content["pod"],
                from_role=content["from"],
                to_role=content["to"],
                source_of_metadata="conflict",
                confidence=0.0,
                reason=f"AMBIGUOUS:CONTENT_FILENAME_CONFLICT (diff: {','.join(diff)})",
                ambiguity_cause=AmbiguityCause.CONTENT_FILENAME_CONFLICT,
            )
        return ParsedMetadata(
            project=content["project"],
            pod=content["pod"],
            from_role=content["from"],
            to_role=content["to"],
            source_of_metadata="both",
            confidence=1.0,
            reason="ok",
        )

    if content_complete:
        return ParsedMetadata(
            project=content["project"],
            pod=content["pod"],
            from_role=content["from"],
            to_role=content["to"],
            source_of_metadata="content",
            confidence=1.0,
            reason="ok",
        )

    if multi_fn:
        return ParsedMetadata(
            source_of_metadata="filename",
            reason="AMBIGUOUS:MULTIPLE_FILENAME_MATCHES",
            ambiguity_cause=AmbiguityCause.MULTIPLE_FILENAME_MATCHES,
        )

    filled: Dict[str, Optional[str]] = dict(content)
    fn_any = fn_full_effective or fn_tol
    if fn_any is not None:
        for k in ("project", "pod", "from", "to"):
            if filled[k] is None and fn_any.get(k):
                filled[k] = fn_any[k]

    has_content = any(content.values())
    has_fn = fn_any is not None

    if has_content and has_fn:
        source = "content+filename"
    elif has_content:
        source = "content"
    elif has_fn:
        source = "filename"
    else:
        source = "none"

    is_complete = all(filled.values())
    return ParsedMetadata(
        project=filled["project"],
        pod=filled["pod"],
        from_role=filled["from"],
        to_role=filled["to"],
        source_of_metadata=source,
        confidence=0.5 if source != "none" else 0.0,
        reason="ok" if is_complete else "partial",
    )
