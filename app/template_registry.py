"""Template registry — snapshot of template contract (§13).

The registry is a build-time artifact, NOT a runtime classifier source. It
exists so we can detect drift between the real templates of the two companies
and the classifier maps in config (heading_map, doc_type_aliases).

Runtime precedence (AC17) is unchanged:
    DocType > Loại > heading_map > filename > UNKNOWN
The registry is consulted exactly at load_config() startup and by
`scripts/refresh_template_registry.py`. It NEVER feeds the runtime classifier.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import AppConfig, DocumentType


class RegistryDriftError(Exception):
    """Raised on drift between registry (status=active) and config maps."""


VALID_CONTRACT_SOURCES = {"heading", "loai", "explicit_doctype", "mixed"}
VALID_STATUSES = {"active", "deprecated"}


@dataclass
class TemplateEntry:
    template_path: str
    company_type: str
    contract_source: str
    doc_type: str
    status: str
    heading_exact: Optional[str] = None
    doc_type_alias_values: List[str] = field(default_factory=list)
    has_explicit_doctype_field: bool = False
    phase_default: Optional[str] = None
    from_role_default: Optional[str] = None
    to_role_default: Optional[str] = None
    pod_default: Optional[str] = None
    filename_pattern: Optional[str] = None
    importance_default: Optional[str] = None
    mirror_to_reporter_default: Optional[bool] = None
    notes: str = ""


def load_registry(path: Path) -> List[TemplateEntry]:
    """Parse + schema-validate a registry JSON file. Returns the entry list."""
    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries_raw = _extract_entries(raw)
    out: List[TemplateEntry] = []
    for i, e in enumerate(entries_raw):
        if not isinstance(e, dict):
            raise RegistryDriftError(f"Entry #{i} is not an object: {e!r}")
        out.append(_parse_entry(e, i))
    return out


def _extract_entries(raw: Any) -> List[Any]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict) and "entries" in raw:
        ents = raw["entries"]
        if not isinstance(ents, list):
            raise RegistryDriftError("'entries' must be a list")
        return ents
    raise RegistryDriftError(
        "Registry root must be a list or an object with an 'entries' array"
    )


def _parse_entry(e: Dict[str, Any], idx: int) -> TemplateEntry:
    required = ["template_path", "company_type", "contract_source", "doc_type", "status"]
    missing = [k for k in required if k not in e]
    if missing:
        raise RegistryDriftError(
            f"Entry #{idx} ({e.get('template_path', '?')}): missing required "
            f"fields {missing}"
        )

    contract_source = str(e["contract_source"])
    if contract_source not in VALID_CONTRACT_SOURCES:
        raise RegistryDriftError(
            f"Entry #{idx}: contract_source='{contract_source}' invalid "
            f"(must be one of {sorted(VALID_CONTRACT_SOURCES)})"
        )
    status = str(e["status"])
    if status not in VALID_STATUSES:
        raise RegistryDriftError(
            f"Entry #{idx}: status='{status}' invalid "
            f"(must be one of {sorted(VALID_STATUSES)})"
        )

    doc_type = str(e["doc_type"])
    valid_doctypes = {d.value for d in DocumentType}
    if doc_type not in valid_doctypes:
        raise RegistryDriftError(
            f"Entry #{idx}: doc_type='{doc_type}' is not a DocumentType"
        )

    return TemplateEntry(
        template_path=str(e["template_path"]),
        company_type=str(e["company_type"]),
        contract_source=contract_source,
        doc_type=doc_type,
        status=status,
        heading_exact=e.get("heading_exact") or None,
        doc_type_alias_values=[str(x) for x in e.get("doc_type_alias_values") or []],
        has_explicit_doctype_field=bool(e.get("has_explicit_doctype_field", False)),
        phase_default=e.get("phase_default") or None,
        from_role_default=e.get("from_role_default") or None,
        to_role_default=e.get("to_role_default") or None,
        pod_default=e.get("pod_default") or None,
        filename_pattern=e.get("filename_pattern") or None,
        importance_default=e.get("importance_default") or None,
        mirror_to_reporter_default=e.get("mirror_to_reporter_default"),
        notes=str(e.get("notes") or ""),
    )


def get_heading_map_from_registry(entries: List[TemplateEntry]) -> Dict[str, str]:
    """Build heading->doctype map from active heading/mixed entries."""
    out: Dict[str, str] = {}
    for e in entries:
        if e.status != "active":
            continue
        if e.contract_source in ("heading", "mixed") and e.heading_exact:
            out[e.heading_exact] = e.doc_type
    return out


def get_doc_type_aliases_from_registry(entries: List[TemplateEntry]) -> Dict[str, str]:
    """Build Loại-alias->doctype map from active loai/mixed entries."""
    out: Dict[str, str] = {}
    for e in entries:
        if e.status != "active":
            continue
        if e.contract_source in ("loai", "mixed"):
            for val in e.doc_type_alias_values:
                out[val] = e.doc_type
    return out


def validate_template_contract_consistency(
    config: AppConfig, entries: List[TemplateEntry]
) -> None:
    """Raise RegistryDriftError if any active entry drifts from config maps.

    Rules per §13.5 + §5.4A:
    - contract_source=heading / mixed-with-heading: heading_exact MUST appear in
      config.heading_map (after parser-level normalization).
    - contract_source=loai / mixed-with-loai: every doc_type_alias_value MUST
      appear in config.doc_type_aliases.
    - contract_source=explicit_doctype: only doc_type must be a valid
      DocumentType; heading_map / doc_type_aliases are NOT checked.
    - CRITICAL templates with self-inconsistent contract (e.g. contract_source
      says 'heading' but heading_exact empty) drift.
    - status=deprecated entries are skipped silently.
    """
    # Import here to avoid a hard dep-cycle with parser.
    from .parser import _normalize_heading

    config_heading_map_norm = {
        _normalize_heading(k): v for k, v in config.heading_map.items()
    }
    config_loai_map = {
        k.strip().casefold(): v for k, v in config.doc_type_aliases.items()
    }

    drifts: List[str] = []
    for e in entries:
        if e.status != "active":
            continue
        src = e.contract_source

        # Self-consistency check (§5.4A bullet 5).
        if src == "heading" and not e.heading_exact:
            drifts.append(
                f"{e.template_path}: contract_source=heading but heading_exact empty"
            )
            continue
        if src == "loai" and not e.doc_type_alias_values:
            drifts.append(
                f"{e.template_path}: contract_source=loai but doc_type_alias_values empty"
            )
            continue
        if src == "explicit_doctype" and not e.has_explicit_doctype_field:
            drifts.append(
                f"{e.template_path}: contract_source=explicit_doctype but "
                f"has_explicit_doctype_field=false"
            )
            continue

        # explicit_doctype is exempt from map checks.
        if src == "explicit_doctype":
            continue

        # heading or mixed -> check heading_map
        if src in ("heading", "mixed") and e.heading_exact:
            norm = _normalize_heading(e.heading_exact)
            if norm not in config_heading_map_norm:
                drifts.append(
                    f"{e.template_path}: heading '{e.heading_exact}' "
                    f"not in config.heading_map"
                )
            else:
                mapped = config_heading_map_norm[norm]
                if mapped != e.doc_type:
                    drifts.append(
                        f"{e.template_path}: heading '{e.heading_exact}' maps "
                        f"to '{mapped}' in config but registry says '{e.doc_type}'"
                    )
        # loai or mixed -> check doc_type_aliases
        if src in ("loai", "mixed") and e.doc_type_alias_values:
            for val in e.doc_type_alias_values:
                norm = val.strip().casefold()
                if norm not in config_loai_map:
                    drifts.append(
                        f"{e.template_path}: Loại '{val}' not in "
                        f"config.doc_type_aliases"
                    )
                elif config_loai_map[norm] != e.doc_type:
                    drifts.append(
                        f"{e.template_path}: Loại '{val}' maps to "
                        f"'{config_loai_map[norm]}' in config but registry "
                        f"says '{e.doc_type}'"
                    )

    if drifts:
        raise RegistryDriftError(
            "Template registry drift detected (status=active):\n  - "
            + "\n  - ".join(drifts)
        )
