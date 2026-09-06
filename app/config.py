"""Config loader: JSON -> AppConfig dataclass with manual validation (no pydantic)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .defaults import (
    DEFAULT_CRITICAL_DOC_TYPES,
    DEFAULT_DOC_TYPE_ALIASES,
    DEFAULT_HEADING_MAP,
    DEFAULT_MIRROR_DOC_TYPES,
    DEFAULT_PHASE_ALIASES,
    DEFAULT_ROLE_ALIASES,
)
from .models import AppConfig, DocumentType, PacketSourceConfig, ProjectConfig


class ConfigError(Exception):
    pass


DEFAULT_TEMPORARY_EXTENSIONS = [
    ".crdownload", ".part", ".tmp", ".download", ".partial",
]

PROJECT_CODE_RE = re.compile(r"^[A-Z0-9_]+$")


def load_config(path: Path) -> AppConfig:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"Invalid JSON in {path}: {e}")
    if not isinstance(raw, dict):
        raise ConfigError("Config root must be a JSON object")
    cfg = parse_config(raw)
    # Resolve template_registry relative to config file dir if given as a
    # relative path.
    if cfg.template_registry_path is not None and not cfg.template_registry_path.is_absolute():
        cfg.template_registry_path = (path.parent / cfg.template_registry_path).resolve()
    _maybe_validate_registry(cfg)
    # REV E-Lazy: resolve packet_sources paths relative to config file dir, then
    # validate per-mode (Q10).
    _resolve_packet_sources(cfg, path.parent)
    _validate_packet_sources(cfg)
    return cfg


def parse_config(raw: Dict[str, Any]) -> AppConfig:
    required = ["watch_folder", "allowed_extensions", "review_folder",
                "log_folder", "projects", "roles"]
    missing = [k for k in required if k not in raw]
    if missing:
        raise ConfigError(f"Missing required keys: {missing}")

    projects = _parse_projects(raw["projects"])
    _validate_no_pod_cycles(projects)
    _validate_project_codes(projects)

    allowed_ext = [_norm_ext(e) for e in raw["allowed_extensions"]]
    temp_ext = [_norm_ext(e) for e in raw.get(
        "temporary_extensions", DEFAULT_TEMPORARY_EXTENSIONS)]

    roles = [str(r).upper() for r in raw["roles"]]
    if not roles:
        raise ConfigError("roles must be a non-empty list")

    # v2 extended fields (all optional; fall back to hardcoded defaults §4)
    mirror_doc_types = _parse_doctype_list(
        raw.get("mirror_doc_types"), DEFAULT_MIRROR_DOC_TYPES, "mirror_doc_types"
    )
    critical_doc_types = _parse_doctype_list(
        raw.get("critical_doc_types"), DEFAULT_CRITICAL_DOC_TYPES, "critical_doc_types"
    )
    role_aliases = _parse_string_map(
        raw.get("role_aliases"), DEFAULT_ROLE_ALIASES, "role_aliases",
        uppercase_values=True,
    )
    phase_aliases = _parse_string_map(
        raw.get("phase_aliases"), DEFAULT_PHASE_ALIASES, "phase_aliases",
    )
    doc_type_aliases = _parse_doctype_map(
        raw.get("doc_type_aliases"), DEFAULT_DOC_TYPE_ALIASES, "doc_type_aliases",
    )
    heading_map = _parse_doctype_map(
        raw.get("heading_map"), DEFAULT_HEADING_MAP, "heading_map",
    )

    registry_path: Any = raw.get("template_registry")
    if registry_path is not None:
        registry_path = Path(str(registry_path))

    auto_drop_inbox_packet = bool(raw.get("auto_drop_inbox_packet", True))
    packet_sources = _parse_packet_sources(raw.get("packet_sources"))

    cfg = AppConfig(
        watch_folder=Path(raw["watch_folder"]),
        allowed_extensions=allowed_ext,
        temporary_extensions=temp_ext,
        review_folder=Path(raw["review_folder"]),
        log_folder=Path(raw["log_folder"]),
        projects=projects,
        roles=roles,
        inbox_suffix=str(raw.get("inbox_suffix", "_INBOX")),
        duplicate_strategy=str(raw.get("duplicate_strategy", "overwrite")),
        dry_run=bool(raw.get("dry_run", False)),
        scan_stable_seconds=int(raw.get("scan_stable_seconds", 3)),
        scan_stable_checks=int(raw.get("scan_stable_checks", 3)),
        max_lock_retries=int(raw.get("max_lock_retries", 5)),
        lock_retry_delay_s=float(raw.get("lock_retry_delay_s", 1.0)),
        reporter_hub_name=str(raw.get("reporter_hub_name", "_REPORTER_HUB")),
        mirror_doc_types=mirror_doc_types,
        critical_doc_types=critical_doc_types,
        role_aliases=role_aliases,
        phase_aliases=phase_aliases,
        doc_type_aliases=doc_type_aliases,
        heading_map=heading_map,
        template_registry_path=registry_path,
        auto_drop_inbox_packet=auto_drop_inbox_packet,
        packet_sources=packet_sources,
    )

    if cfg.duplicate_strategy not in {"overwrite", "suffix"}:
        raise ConfigError(
            f"duplicate_strategy='{cfg.duplicate_strategy}' not supported in v2 "
            "(allowed: 'overwrite', 'suffix')"
        )

    cfg.warnings = _volume_warnings(cfg)
    return cfg


def _parse_projects(raw: Any) -> Dict[str, ProjectConfig]:
    if not isinstance(raw, dict) or not raw:
        raise ConfigError("projects must be a non-empty object")
    out: Dict[str, ProjectConfig] = {}
    for pname, pdata in raw.items():
        if not isinstance(pdata, dict):
            raise ConfigError(
                f"Project '{pname}' must be an object with 'root' and 'pods'")
        if "root" not in pdata or "pods" not in pdata:
            raise ConfigError(
                f"Project '{pname}' must declare both 'root' and 'pods'")
        pods = pdata["pods"]
        if not isinstance(pods, list) or not pods:
            raise ConfigError(
                f"Project '{pname}'.pods must be a non-empty list")

        project_code_raw = pdata.get("project_code")
        display_name = pdata.get("display_name")

        dynamic_pod_pattern_raw = pdata.get("dynamic_pod_pattern")
        dynamic_pod_pattern: Optional[str] = None
        if dynamic_pod_pattern_raw is not None:
            pat_str = str(dynamic_pod_pattern_raw)
            try:
                import re as _re_validate
                _re_validate.compile(pat_str)
            except Exception as exc:
                raise ConfigError(
                    f"Project '{pname}'.dynamic_pod_pattern='{pat_str}' "
                    f"is not a valid regular expression: {exc}"
                )
            dynamic_pod_pattern = pat_str

        out[pname] = ProjectConfig(
            name=pname,
            root=Path(pdata["root"]),
            pods=[str(x) for x in pods],
            project_code=str(project_code_raw) if project_code_raw else "",
            display_name=str(display_name) if display_name else None,
            dynamic_pod_pattern=dynamic_pod_pattern,
        )
    return out


def _validate_project_codes(projects: Dict[str, ProjectConfig]) -> None:
    """§5.5: enforce dual-field rule from plan §1.

    Rules:
    - If config declares `project_code`, it must match ``^[A-Z0-9_]+$`` and be unique.
    - If config omits `project_code`:
        - If the project key is already canonical (matches the regex), auto-fill
          `project_code = key` (legacy-compat, no warning — the key IS canonical).
        - Otherwise (key has spaces, Vietnamese, dashes, ...): raise ConfigError.
          There is **no slugify fallback** in v2.
    """
    seen: Dict[str, str] = {}  # project_code -> project name (for collision msg)
    for pname, pcfg in projects.items():
        code = pcfg.project_code
        if code:
            if not PROJECT_CODE_RE.match(code):
                raise ConfigError(
                    f"Project '{pname}'.project_code='{code}' is invalid. "
                    f"Must match ^[A-Z0-9_]+$."
                )
        else:
            # Missing project_code. Only accept legacy-canonical keys.
            if PROJECT_CODE_RE.match(pname):
                pcfg.project_code = pname
                code = pname
            else:
                raise ConfigError(
                    f"Project '{pname}' has no 'project_code' and its key "
                    f"contains non-canonical characters (outside [A-Z0-9_]). "
                    f"Declare project_code explicitly (e.g. 'TRADE_ALERT'). "
                    f"v2 does NOT slugify — see plan §1."
                )
        if code in seen:
            raise ConfigError(
                f"Duplicate project_code '{code}' between projects "
                f"'{seen[code]}' and '{pname}'. Must be unique."
            )
        seen[code] = pname


def _parse_doctype_list(raw: Any, default: List[str], field_name: str) -> List[str]:
    if raw is None:
        return list(default)
    if not isinstance(raw, list):
        raise ConfigError(f"{field_name} must be a list of DocumentType names")
    out: List[str] = []
    valid = {e.value for e in DocumentType}
    for item in raw:
        s = str(item)
        if s not in valid:
            raise ConfigError(
                f"{field_name}: '{s}' is not a valid DocumentType. "
                f"Allowed: {sorted(valid)}"
            )
        out.append(s)
    return out


def _parse_string_map(raw: Any, default: Dict[str, str], field_name: str,
                      uppercase_values: bool = False) -> Dict[str, str]:
    if raw is None:
        return dict(default)
    if not isinstance(raw, dict):
        raise ConfigError(f"{field_name} must be an object (string -> string)")
    out: Dict[str, str] = {}
    for k, v in raw.items():
        if not isinstance(v, str):
            raise ConfigError(f"{field_name}['{k}'] must be a string")
        out[str(k)] = v.upper() if uppercase_values else v
    return out


def _parse_doctype_map(raw: Any, default: Dict[str, str], field_name: str) -> Dict[str, str]:
    if raw is None:
        return dict(default)
    if not isinstance(raw, dict):
        raise ConfigError(f"{field_name} must be an object (string -> DocumentType name)")
    valid = {e.value for e in DocumentType}
    out: Dict[str, str] = {}
    for k, v in raw.items():
        if not isinstance(v, str) or v not in valid:
            raise ConfigError(
                f"{field_name}['{k}']='{v}' is not a valid DocumentType. "
                f"Allowed: {sorted(valid)}"
            )
        out[str(k)] = v
    return out


def _validate_no_pod_cycles(_projects: Dict[str, ProjectConfig]) -> None:
    """Placeholder for future validations (e.g., duplicate pod names). v1.1: no-op."""
    return None


def _norm_ext(e: str) -> str:
    e = str(e).lower()
    if not e.startswith("."):
        e = "." + e
    return e


def _volume_warnings(cfg: AppConfig) -> List[str]:
    warnings: List[str] = []
    watch_vol = _drive(cfg.watch_folder)
    for pname, p in cfg.projects.items():
        proj_vol = _drive(p.root)
        if watch_vol and proj_vol and watch_vol != proj_vol:
            warnings.append(
                f"[INFO] Project '{pname}' root on volume '{proj_vol}' differs from "
                f"watch_folder volume '{watch_vol}'; mover will use cross_volume_copy."
            )
    return warnings


def _drive(p: Path) -> str:
    return os.path.splitdrive(str(p))[0].lower()


def _parse_packet_sources(raw: Any) -> Dict[str, PacketSourceConfig]:
    """Parse `packet_sources` JSON. Schema:

        {
          "TB":  {"rulecard": "<path>", "anchors": ["<path>", ...]},
          "BIG": {"rulecard": "<path>", "anchors": [...]}
        }

    Bất kỳ mode nào thiếu (không có trong JSON) → mode đó sẽ bị packet_mode_valid
    đánh False (per-mode disable Q10). Không raise.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError("packet_sources must be an object {mode: {rulecard, anchors}}")
    out: Dict[str, PacketSourceConfig] = {}
    for mode, val in raw.items():
        if not isinstance(val, dict):
            raise ConfigError(
                f"packet_sources['{mode}'] must be an object with rulecard + anchors"
            )
        rc = val.get("rulecard")
        if not isinstance(rc, str) or not rc:
            raise ConfigError(
                f"packet_sources['{mode}'].rulecard must be a non-empty string path"
            )
        anchors_raw = val.get("anchors", [])
        if not isinstance(anchors_raw, list):
            raise ConfigError(f"packet_sources['{mode}'].anchors must be a list")
        anchors: List[Path] = [Path(str(a)) for a in anchors_raw]
        out[str(mode)] = PacketSourceConfig(rulecard=Path(rc), anchors=anchors)
    return out


def _resolve_packet_sources(cfg: AppConfig, config_dir: Path) -> None:
    """Make rulecard + anchor paths absolute (resolve relative to config dir)."""
    for mode, src in cfg.packet_sources.items():
        if not src.rulecard.is_absolute():
            src.rulecard = (config_dir / src.rulecard).resolve()
        src.anchors = [
            (a if a.is_absolute() else (config_dir / a).resolve())
            for a in src.anchors
        ]


def _validate_packet_sources(cfg: AppConfig) -> None:
    """Per-mode validation (Q10). TB invalid không tắt BIG.

    Mode valid khi:
    - Có entry trong `packet_sources`
    - Rulecard file tồn tại
    - Tất cả anchor template files tồn tại

    Nếu auto_drop_inbox_packet=False → bỏ qua validation, đánh dấu mode_valid=False
    đồng đều (feature off).
    """
    cfg.packet_mode_valid = {}
    if not cfg.auto_drop_inbox_packet:
        for mode in cfg.packet_sources.keys():
            cfg.packet_mode_valid[mode] = False
        return

    for mode in ("TB", "BIG"):
        src = cfg.packet_sources.get(mode)
        if src is None:
            cfg.packet_mode_valid[mode] = False
            continue
        problems: List[str] = []
        if not src.rulecard.exists():
            problems.append(f"rulecard missing: {src.rulecard}")
        for a in src.anchors:
            if not a.exists():
                problems.append(f"anchor template missing: {a}")
        if problems:
            cfg.warnings.append(
                f"[WARN] packet_sources['{mode}'] invalid — packet drop disabled "
                f"for mode {mode} only. Problems: {'; '.join(problems)}"
            )
            cfg.packet_mode_valid[mode] = False
        else:
            cfg.packet_mode_valid[mode] = True


def _maybe_validate_registry(cfg: AppConfig) -> None:
    """Hard drift check at bus startup. If registry path not given, skip.

    Import locally to avoid a circular import at module load time.
    """
    if cfg.template_registry_path is None:
        return
    try:
        from .template_registry import (
            RegistryDriftError,
            load_registry,
            validate_template_contract_consistency,
        )
    except ImportError:  # pragma: no cover
        return
    if not cfg.template_registry_path.exists():
        cfg.warnings.append(
            f"[WARN] template_registry '{cfg.template_registry_path}' not found; "
            f"skipping drift validation."
        )
        return
    try:
        registry = load_registry(cfg.template_registry_path)
    except Exception as e:
        raise ConfigError(f"Failed to load template_registry: {e}")
    try:
        validate_template_contract_consistency(cfg, registry)
    except RegistryDriftError as e:
        raise ConfigError(f"Template registry drift: {e}")
