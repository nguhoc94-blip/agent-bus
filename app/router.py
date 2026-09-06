"""Pure routing logic v2: ParsedMetadata -> RouteDecision.

Adds to v1:
- Canonical filename format PROJECT_CODE__PHASE__POD__DOCTYPE__FROM_gui_TO.ext
- Primary destination (inbox) + optional mirror destinations (_REPORTER_HUB)
- Review escalation for UNKNOWN_DOC on critical flows and UNKNOWN_PHASE on
  critical doc types (§5.3 + §5.3.1).

No filesystem I/O; that lives in `mover.apply_route`.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from .models import (
    Action,
    AmbiguityCause,
    AppConfig,
    DocumentType,
    ImportanceLevel,
    ParsedMetadata,
    PhaseType,
    ProjectConfig,
    ReviewReason,
    RouteDecision,
)
from .parser import is_critical_flow


def decide(meta: ParsedMetadata, original_filename: str, config: AppConfig) -> RouteDecision:
    # Parser-level ambiguity (content/filename conflict, phase/doctype conflict,
    # multi-filename match, ...) → review folder immediately.
    if meta.ambiguity_cause is not None:
        return _review(
            config, ReviewReason.AMBIGUOUS, original_filename,
            reason_detail=meta.reason or f"AMBIGUOUS:{meta.ambiguity_cause.value}",
        )

    # Pod-only fill (inherited from v1).
    if not meta.project and meta.pod:
        owners = config.pod_to_projects().get(meta.pod, [])
        if len(owners) > 1:
            return _review(
                config, ReviewReason.AMBIGUOUS, original_filename,
                reason_detail=(
                    f"AMBIGUOUS:{AmbiguityCause.POD_IN_MULTI_PROJECT.value} "
                    f"(pod={meta.pod} in {owners})"
                ),
            )
        if len(owners) == 1:
            meta.project = owners[0]

    # Resolve project: either `meta.project` matches a config key (the human
    # name) OR a project_code reverse map.
    proj_cfg = _resolve_project(meta, config)
    if proj_cfg is None:
        if not meta.project:
            return _review(
                config, ReviewReason.MISSING_PROJECT, original_filename,
                reason_detail="MISSING_PROJECT",
            )
        return _review(
            config, ReviewReason.MISSING_PROJECT, original_filename,
            reason_detail=f"MISSING_PROJECT (unknown: {meta.project})",
        )

    # Fill identity fields on meta for logging/downstream.
    meta.project_code = proj_cfg.project_code
    meta.display_project_name = proj_cfg.effective_display

    if not meta.pod:
        return _review(
            config, ReviewReason.MISSING_POD, original_filename,
            reason_detail="MISSING_POD",
        )
    if not proj_cfg.pod_allowed(meta.pod):
        detail = f"MISSING_POD (pod={meta.pod} not in project={proj_cfg.name})"
        if proj_cfg.dynamic_pod_pattern:
            detail += f" and does not match dynamic_pod_pattern={proj_cfg.dynamic_pod_pattern!r}"
        return _review(
            config, ReviewReason.MISSING_POD, original_filename,
            reason_detail=detail,
        )

    if not meta.to_role:
        return _review(
            config, ReviewReason.MISSING_ROLE, original_filename,
            reason_detail="MISSING_ROLE (to_role empty)",
        )
    if not meta.from_role:
        return _review(
            config, ReviewReason.MISSING_ROLE, original_filename,
            reason_detail="MISSING_ROLE (from_role empty)",
        )
    if meta.to_role not in config.roles or meta.from_role not in config.roles:
        return _review(
            config, ReviewReason.MISSING_ROLE, original_filename,
            reason_detail=(
                f"MISSING_ROLE (unknown role: from={meta.from_role}, to={meta.to_role}; "
                f"whitelist={config.roles})"
            ),
        )

    # §5.3.1 review escalations on critical flows.
    if meta.doc_type == DocumentType.UNKNOWN_DOC:
        if is_critical_flow(meta.from_role, meta.to_role):
            return _review(
                config, ReviewReason.AMBIGUOUS, original_filename,
                reason_detail=(
                    f"AMBIGUOUS:{AmbiguityCause.UNKNOWN_DOC_IN_CRITICAL_FLOW.value} "
                    f"(from={meta.from_role},to={meta.to_role})"
                ),
            )
        # Not a critical flow; route to inbox normally but do NOT mirror.
        meta.mirror_to_reporter = False

    # REV D — Anti Down-Scope Guardrail v1: QA→CEO route LOCK.
    # Tuyến QA→CEO chỉ hợp lệ khi doc_type = QA_LIMIT_1 (QA xin CEO ack TRƯỚC khi
    # tự khoá phạm vi review). Mọi QA_REPORT / QA_PLAN_REVIEW có to_role=CEO bị
    # chặn về REVIEW_MANUAL với cause AMBIGUOUS — QA mặc định gửi Deputy
    # (Job TB Manual line 987–990; Job To Manual đối ứng).
    # Lý do enforce ở đây (chứ không chỉ qua CRITICAL_FLOW_WHITELIST): whitelist
    # chỉ áp dụng khi doc_type == UNKNOWN_DOC. Doc type đã nhận diện như
    # QA_REPORT vẫn route bình thường nếu không có guard này.
    if (
        meta.from_role
        and meta.to_role
        and meta.from_role.upper() == "QA"
        and meta.to_role.upper() == "CEO"
        and meta.doc_type != DocumentType.QA_LIMIT_1
    ):
        return _review(
            config, ReviewReason.AMBIGUOUS, original_filename,
            reason_detail=(
                f"AMBIGUOUS:QA_TO_CEO_RESERVED_FOR_QA_LIMIT_1 "
                f"(doc_type={meta.doc_type.value}; QA→CEO chỉ hợp lệ cho "
                f"QA_LIMIT_1, các form QA khác phải gửi Deputy)"
            ),
        )

    if meta.phase == PhaseType.UNKNOWN_PHASE and (
        meta.doc_type.value in (config.critical_doc_types or [])
        or meta.importance == ImportanceLevel.CRITICAL
    ):
        return _review(
            config, ReviewReason.AMBIGUOUS, original_filename,
            reason_detail=(
                f"AMBIGUOUS:{AmbiguityCause.UNKNOWN_PHASE_ON_CRITICAL_DOC.value} "
                f"(doc_type={meta.doc_type.value})"
            ),
        )

    # Build canonical filename + destinations.
    ext = Path(original_filename).suffix.lower()
    new_name = _canonical_filename(
        project_code=proj_cfg.project_code,
        phase=meta.phase,
        pod=meta.pod,
        doc_type=meta.doc_type,
        from_role=meta.from_role,
        to_role=meta.to_role,
        ext=ext,
    )
    primary_dir = proj_cfg.root / meta.pod / f"{meta.to_role}{config.inbox_suffix}"
    primary_path = primary_dir / new_name

    mirrors: List[Path] = []
    if meta.mirror_to_reporter and meta.doc_type != DocumentType.UNKNOWN_DOC:
        mirror_dir = (
            proj_cfg.root / config.reporter_hub_name
            / meta.phase.value / meta.doc_type.value
        )
        mirrors.append(mirror_dir / new_name)

    return RouteDecision(
        action=Action.MOVED,
        destination_path=primary_path,
        primary_destination_path=primary_path,
        mirror_destination_paths=mirrors,
        new_filename=new_name,
        reason="ok",
    )


def _resolve_project(meta: ParsedMetadata, config: AppConfig) -> Optional[ProjectConfig]:
    """Find the ProjectConfig by either config-key or project_code."""
    if not meta.project:
        return None
    if meta.project in config.projects:
        return config.projects[meta.project]
    code_map = config.project_code_to_key()
    # meta.project usually arrives as UPPER from filename/content. project_code
    # is uppercase by regex. Keys may have spaces though.
    key = code_map.get(meta.project) or code_map.get(meta.project.upper())
    if key is not None:
        return config.projects[key]
    return None


def _canonical_filename(
    *,
    project_code: str,
    phase: PhaseType,
    pod: str,
    doc_type: DocumentType,
    from_role: str,
    to_role: str,
    ext: str,
) -> str:
    return (
        f"{project_code}__{phase.value}__{pod}__{doc_type.value}"
        f"__{from_role}_gui_{to_role}{ext}"
    )


def _review(config: AppConfig, reason: ReviewReason, original_filename: str,
            reason_detail: str) -> RouteDecision:
    dest_dir = config.review_folder / reason.value
    dest_path = dest_dir / original_filename
    return RouteDecision(
        action=Action.REVIEW,
        destination_path=dest_path,
        primary_destination_path=dest_path,
        mirror_destination_paths=[],
        new_filename=original_filename,
        reason=reason_detail,
    )
