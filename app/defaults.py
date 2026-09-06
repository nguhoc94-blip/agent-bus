"""Hardcoded default maps shared by parser/classifier and config loader.

These defaults are derived from the actual templates of the two companies
(see plan §2.1, §2.2, §2.3, §4). They're used when the config file does not
override them; config values replace (not merge) the defaults to keep the
"single source of truth" rule in §4.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from .models import DocumentType, ImportanceLevel, PhaseType


# ---------------------------------------------------------------------------
# 4.3 role_aliases and phase_aliases
# ---------------------------------------------------------------------------

DEFAULT_ROLE_ALIASES: Dict[str, str] = {
    # Canonical roles from plan §4.3 + existing v1 set.
    "CEO": "CEO",
    "COO": "COO",
    "PRODUCT": "PRODUCT",
    "ENGINEERING": "ENGINEERING",
    "QA": "QA",
    "DEPUTY": "DEPUTY",
    "REPORTER": "REPORTER",
    "BUILDER": "BUILDER",
    "SPECIALIST": "SPECIALIST",
    "SPECIALISTKT": "SPECIALISTKT",
    "SPECIALISTNV": "SPECIALISTNV",
    "PRODUCTPODLEAD": "PRODUCTPODLEAD",
    "ENGINEERINGPODLEAD": "ENGINEERINGPODLEAD",
    "GROWTHPODLEAD": "GROWTHPODLEAD",
    "PODLEAD": "PODLEAD",
    "PE": "PE",
    "AGENTBATKY": "AGENTBATKY",
}

DEFAULT_PHASE_ALIASES: Dict[str, str] = {
    "CP0": PhaseType.CP0.value,
    "CHECKPOINT 0": PhaseType.CP0.value,
    "CHECKPOINT0": PhaseType.CP0.value,
    "PHASE 1": PhaseType.PHASE_1.value,
    "PHASE_1": PhaseType.PHASE_1.value,
    "PHASE 1 SUBPLAN": PhaseType.PHASE_1_SUBPLAN.value,
    "PHASE_1_SUBPLAN": PhaseType.PHASE_1_SUBPLAN.value,
    "PHASE 2": PhaseType.PHASE_2.value,
    "PHASE_2": PhaseType.PHASE_2.value,
    "GATE PLAN": PhaseType.GATE_PLAN.value,
    "GATE_PLAN": PhaseType.GATE_PLAN.value,
    "GATE OUTPUT": PhaseType.GATE_OUTPUT.value,
    "GATE_OUTPUT": PhaseType.GATE_OUTPUT.value,
    "FAST TRACK": PhaseType.FAST_TRACK.value,
    "FAST_TRACK": PhaseType.FAST_TRACK.value,
    "FAST TRACK CLOSURE": PhaseType.FAST_TRACK_CLOSURE.value,
    "FAST_TRACK_CLOSURE": PhaseType.FAST_TRACK_CLOSURE.value,
    "PROMPT CHANGE": PhaseType.PROMPT_CHANGE.value,
    "PROMPT_CHANGE": PhaseType.PROMPT_CHANGE.value,
    "SKILL GAP": PhaseType.SKILL_GAP.value,
    "SKILL_GAP": PhaseType.SKILL_GAP.value,
}


# ---------------------------------------------------------------------------
# 4.1 doc_type_aliases: Loại: value (lower, trimmed) -> DocumentType name.
# Ambiguous values that need disambiguation by From-role are listed separately
# in DOC_TYPE_FROM_DISAMBIG.
# ---------------------------------------------------------------------------

DEFAULT_DOC_TYPE_ALIASES: Dict[str, str] = {
    "cp0-trigger": DocumentType.CEO_CP0_TRIGGER.value,
    "pre-brief-basis": DocumentType.COO_PRE_BRIEF_BASIS.value,
    "pre-brief-discovery": DocumentType.COO_CP0_OPEN.value,
    "pre-brief-input-spec": DocumentType.PRODUCT_CP0_INPUT_SPEC.value,
    "cp0-input-discovery": DocumentType.PRODUCT_CP0_INPUT_SPEC.value,
    "pre-brief-feasibility": DocumentType.ENGINEERING_CP0_FEASIBILITY.value,
    "qa-lightweight": DocumentType.QA_LIGHTWEIGHT_FT.value,
    "fast-track-request": DocumentType.COO_FAST_TRACK_PROPOSAL.value,
    "fast track closure": DocumentType.DEPUTY_CLOSURE_FT.value,
    "phase closure": DocumentType.DEPUTY_CLOSURE.value,
    "prompt-change-request": DocumentType.PROMPT_CHANGE_REQUEST.value,
    "prompt-change-proposal": DocumentType.PROMPT_CHANGE_PROPOSAL.value,
    "prompt-impact-review": DocumentType.PROMPT_IMPACT_REVIEW.value,
    "prompt-approval": DocumentType.PROMPT_APPROVAL.value,
    "capability-gap": DocumentType.SKILL_GAP_REPORT.value,
    "skill-gap-escalation": DocumentType.SKILL_GAP_ESCALATION.value,
    "specialist-activation-request": DocumentType.SPECIALIST_ACTIVATION_REQUEST.value,
    "interface-lock": DocumentType.INTERFACE_SYNC.value,
    "gate plan": DocumentType.QA_PLAN_REVIEW.value,
    "gate output": DocumentType.QA_REPORT.value,
    "pod-structure-change": DocumentType.COO_POD_ASSIGNMENT.value,
    # Anchor Co-Sign workflow (added 2026-05)
    "anchor-cosign-request": DocumentType.ANCHOR_COSIGN_REQUEST.value,
    "anchor-cosign-ack": DocumentType.ANCHOR_COSIGN_ACK.value,
}

# Ambiguous values needing (from_role) disambiguation: base value -> dict of
# from_role (canonical UPPER) -> target DocumentType.
DOC_TYPE_FROM_DISAMBIG: Dict[str, Dict[str, str]] = {
    "pod-plan": {
        "GROWTHPODLEAD": DocumentType.GROWTH_POD_PLAN.value,
        "PRODUCTPODLEAD": DocumentType.POD_PLAN.value,
        "ENGINEERINGPODLEAD": DocumentType.POD_PLAN.value,
        "PODLEAD": DocumentType.POD_PLAN.value,
        "__default__": DocumentType.POD_PLAN.value,
    },
    "pod-completion-report": {
        "PRODUCT": DocumentType.PRODUCT_LANE_COMPLETION.value,
        "PRODUCTPODLEAD": DocumentType.PRODUCT_LANE_COMPLETION.value,
        "ENGINEERING": DocumentType.ENGINEERING_LANE_COMPLETION.value,
        "ENGINEERINGPODLEAD": DocumentType.ENGINEERING_LANE_COMPLETION.value,
    },
}

# Values that must NOT be auto-resolved; caller must look at heading or filename.
# See plan §4.1: "report" / "sub-plan" are placeholders.
DOC_TYPE_NON_RESOLVABLE = {"report", "sub-plan"}


# ---------------------------------------------------------------------------
# 4.2 heading_map: normalized heading text -> DocumentType name.
# Normalization is applied by parser._normalize_heading (see §3.4.2). These
# source strings match exactly the headings actually used in the two companies.
# ---------------------------------------------------------------------------

DEFAULT_HEADING_MAP: Dict[str, str] = {
    # CEO
    "CEO BRIEF": DocumentType.CEO_BRIEF.value,
    "CEO CHỈ THỊ SAU GATE": DocumentType.CEO_GATE_DIRECTIVE.value,
    "CEO YÊU CẦU MỞ CHECKPOINT 0": DocumentType.CEO_CP0_TRIGGER.value,
    "CEO QUYẾT ĐỊNH FAST TRACK": DocumentType.CEO_FAST_TRACK_DECISION.value,
    "CEO INFORM QA": DocumentType.CEO_INFORM_QA.value,
    # Brief basis (COO)
    "BRIEF BASIS — CƠ SỞ ĐỂ CEO RA BRIEF": DocumentType.COO_PRE_BRIEF_BASIS.value,
    "BRIEF BASIS — CP0": DocumentType.COO_PRE_BRIEF_BASIS.value,
    # COO routing
    "COO GỬI PRODUCT": DocumentType.COO_POD_ASSIGNMENT.value,
    "COO GỬI ENGINEERING": DocumentType.COO_POD_ASSIGNMENT.value,
    "COO GỬI QA REVIEW": DocumentType.COO_QA_REVIEW_REQUEST.value,
    "COO GỬI PRODUCT — MỞ CHECKPOINT 0": DocumentType.COO_CP0_OPEN.value,
    "COO MỞ CHECKPOINT 0": DocumentType.COO_CP0_OPEN.value,
    "GÓI TRẠNG THÁI": DocumentType.COO_STATUS_PACKAGE.value,
    "COO POD ASSIGNMENT": DocumentType.COO_POD_ASSIGNMENT.value,
    "COO POD ASSIGNMENT — GROWTH POD": DocumentType.COO_POD_ASSIGNMENT.value,
    # Product / Engineering lanes
    "PRODUCT LANE PLAN": DocumentType.PRODUCT_LANE_PLAN.value,
    "ENGINEERING LANE PLAN": DocumentType.ENGINEERING_LANE_PLAN.value,
    # LANE COMPLETION REPORT is ambiguous -> disambiguated by from_role upstream;
    # heading_map default points to UNKNOWN_DOC so classifier picks from_role rule.
    # (We deliberately do NOT map "LANE COMPLETION REPORT" here to force the
    # disambiguation path in classify_document.)
    "PRODUCT GỬI ENGINEERING": DocumentType.PRODUCT_TO_ENGINEERING.value,
    "ENGINEERING GỬI PRODUCT": DocumentType.ENGINEERING_TO_PRODUCT.value,
    # Pod-based
    "POD PLAN": DocumentType.POD_PLAN.value,
    "GROWTH POD PLAN": DocumentType.GROWTH_POD_PLAN.value,
    "INTERFACE SYNC NOTE": DocumentType.INTERFACE_SYNC.value,
    "GROWTH SIGNAL NOTE": DocumentType.GROWTH_SIGNAL.value,
    # QA
    "QA PLAN REVIEW": DocumentType.QA_PLAN_REVIEW.value,
    "QA REPORT": DocumentType.QA_REPORT.value,
    "QA CROSS-POD INTEGRATION REVIEW": DocumentType.QA_CROSS_POD_REVIEW.value,
    "FORM QA-FT — QA LIGHTWEIGHT REPORT": DocumentType.QA_LIGHTWEIGHT_FT.value,
    # Deputy / Executive
    "EXECUTIVE REVIEW": DocumentType.EXECUTIVE_REVIEW.value,
    "GÓI CHỐT": DocumentType.DEPUTY_CLOSURE.value,
    "GÓI XÁC NHẬN CLOSURE": DocumentType.DEPUTY_CLOSURE.value,
    "GÓI XÁC NHẬN CLOSURE FT": DocumentType.DEPUTY_CLOSURE_FT.value,
    # Specialist / Builder / Task
    "SPECIALIST REPORT": DocumentType.SPECIALIST_REPORT.value,
    "BUILDER REPORT": DocumentType.BUILDER_REPORT.value,
    "GIAO TASK": DocumentType.TASK_ASSIGNMENT.value,
    # CP0 — COO opens discovery for candidate pods (Big Mode JOB_TO templates)
    "COO CP0 DISCOVERY REQUEST": DocumentType.COO_CP0_OPEN.value,
    # CP0 — CEO triggers CP0 (short form used in JOB_TO template)
    "CEO YÊU CẦU MỞ CP0": DocumentType.CEO_CP0_TRIGGER.value,
    # CP0 — COO synthesises brief basis (JOB_TO template uses reversed order)
    "CP0 BRIEF BASIS": DocumentType.COO_PRE_BRIEF_BASIS.value,
    # CP0 specs (JOB_TO style: type comes first in heading)
    "CP0 INPUT SPEC": DocumentType.PRODUCT_CP0_INPUT_SPEC.value,
    "CP0 FEASIBILITY NOTE": DocumentType.ENGINEERING_CP0_FEASIBILITY.value,
    # CP0 specs (JOB_TB / legacy style: type comes after dash)
    "INPUT SPEC — ĐẶC TẢ ĐẦU VÀO": DocumentType.PRODUCT_CP0_INPUT_SPEC.value,
    "INPUT SPEC — CP0": DocumentType.PRODUCT_CP0_INPUT_SPEC.value,
    "FEASIBILITY NOTE — CHECKPOINT 0": DocumentType.ENGINEERING_CP0_FEASIBILITY.value,
    "FEASIBILITY NOTE — CP0 (OPTIONAL)": DocumentType.ENGINEERING_CP0_FEASIBILITY.value,
    # Forms
    "FORM 12A-1": DocumentType.PROMPT_CHANGE_REQUEST.value,
    "FORM 12A-2": DocumentType.PROMPT_CHANGE_PROPOSAL.value,
    "FORM 12A-3": DocumentType.PROMPT_IMPACT_REVIEW.value,
    "FORM 12A-4": DocumentType.PROMPT_APPROVAL.value,
    "FORM 11E-1": DocumentType.SKILL_GAP_REPORT.value,
    "FORM 11E-2": DocumentType.SKILL_GAP_ESCALATION.value,
    "FORM 11E-3": DocumentType.SPECIALIST_ACTIVATION_REQUEST.value,
    "FORM ĐỀ XUẤT SPECIALIST": DocumentType.SPECIALIST_ACTIVATION_REQUEST.value,
    "FORM FT-1 — ĐỀ XUẤT FAST TRACK": DocumentType.COO_FAST_TRACK_PROPOSAL.value,
    # Anti Down-Scope Guardrail v1 (added 2026-05 — REV D)
    "SCOPE CHANGE ACK": DocumentType.SCOPE_CHANGE_ACK.value,
    "QA LIMIT FORM": DocumentType.QA_LIMIT_1.value,
    # Anchor Co-Sign workflow (added 2026-05)
    "CEO YÊU CẦU COO ĐỒNG KÝ ANCHOR": DocumentType.ANCHOR_COSIGN_REQUEST.value,
    "CEO YÊU CẦU COO ĐỒNG KÝ ANCHOR (BIG MODE)": DocumentType.ANCHOR_COSIGN_REQUEST.value,
    "COO ĐỒNG KÝ ANCHOR ACK": DocumentType.ANCHOR_COSIGN_ACK.value,
    "COO ĐỒNG KÝ ANCHOR ACK (BIG MODE)": DocumentType.ANCHOR_COSIGN_ACK.value,
}


# ---------------------------------------------------------------------------
# §3.5 Phase map (doc_type -> default phase when header has no Phase:)
# ---------------------------------------------------------------------------

DEFAULT_DOCTYPE_PHASE_MAP: Dict[str, str] = {
    # CP0 flow
    DocumentType.CEO_CP0_TRIGGER.value: PhaseType.CP0.value,
    DocumentType.COO_CP0_OPEN.value: PhaseType.CP0.value,
    DocumentType.COO_PRE_BRIEF_BASIS.value: PhaseType.CP0.value,
    DocumentType.PRODUCT_CP0_INPUT_SPEC.value: PhaseType.CP0.value,
    DocumentType.ENGINEERING_CP0_FEASIBILITY.value: PhaseType.CP0.value,
    # Phase 1
    DocumentType.CEO_BRIEF.value: PhaseType.PHASE_1.value,
    DocumentType.PRODUCT_LANE_PLAN.value: PhaseType.PHASE_1.value,
    DocumentType.ENGINEERING_LANE_PLAN.value: PhaseType.PHASE_1.value,
    DocumentType.POD_PLAN.value: PhaseType.PHASE_1.value,
    DocumentType.GROWTH_POD_PLAN.value: PhaseType.PHASE_1.value,
    DocumentType.COO_POD_ASSIGNMENT.value: PhaseType.PHASE_1.value,
    DocumentType.INTERFACE_SYNC.value: PhaseType.PHASE_1.value,
    DocumentType.GROWTH_SIGNAL.value: PhaseType.PHASE_1.value,
    DocumentType.TASK_ASSIGNMENT.value: PhaseType.PHASE_1.value,
    # Phase 2 (execution output)
    DocumentType.PRODUCT_LANE_COMPLETION.value: PhaseType.PHASE_2.value,
    DocumentType.ENGINEERING_LANE_COMPLETION.value: PhaseType.PHASE_2.value,
    DocumentType.BUILDER_REPORT.value: PhaseType.PHASE_2.value,
    DocumentType.SPECIALIST_REPORT.value: PhaseType.PHASE_2.value,
    # Gate
    DocumentType.QA_PLAN_REVIEW.value: PhaseType.GATE_PLAN.value,
    DocumentType.QA_REPORT.value: PhaseType.GATE_OUTPUT.value,
    DocumentType.QA_CROSS_POD_REVIEW.value: PhaseType.GATE_OUTPUT.value,
    DocumentType.COO_QA_REVIEW_REQUEST.value: PhaseType.GATE_PLAN.value,
    DocumentType.CEO_INFORM_QA.value: PhaseType.GATE_PLAN.value,
    DocumentType.EXECUTIVE_REVIEW.value: PhaseType.GATE_OUTPUT.value,
    DocumentType.DEPUTY_CLOSURE.value: PhaseType.GATE_OUTPUT.value,
    DocumentType.CEO_GATE_DIRECTIVE.value: PhaseType.GATE_OUTPUT.value,
    DocumentType.COO_STATUS_PACKAGE.value: PhaseType.GATE_OUTPUT.value,
    # Fast Track
    DocumentType.COO_FAST_TRACK_PROPOSAL.value: PhaseType.FAST_TRACK.value,
    DocumentType.CEO_FAST_TRACK_DECISION.value: PhaseType.FAST_TRACK.value,
    DocumentType.QA_LIGHTWEIGHT_FT.value: PhaseType.FAST_TRACK_CLOSURE.value,
    DocumentType.DEPUTY_CLOSURE_FT.value: PhaseType.FAST_TRACK_CLOSURE.value,
    # Prompt change
    DocumentType.PROMPT_CHANGE_REQUEST.value: PhaseType.PROMPT_CHANGE.value,
    DocumentType.PROMPT_CHANGE_PROPOSAL.value: PhaseType.PROMPT_CHANGE.value,
    DocumentType.PROMPT_IMPACT_REVIEW.value: PhaseType.PROMPT_CHANGE.value,
    DocumentType.PROMPT_APPROVAL.value: PhaseType.PROMPT_CHANGE.value,
    # Skill gap
    DocumentType.SKILL_GAP_REPORT.value: PhaseType.SKILL_GAP.value,
    DocumentType.SKILL_GAP_ESCALATION.value: PhaseType.SKILL_GAP.value,
    DocumentType.SPECIALIST_ACTIVATION_REQUEST.value: PhaseType.SKILL_GAP.value,
    # Anti Down-Scope Guardrail v1 (added 2026-05 — REV D).
    # SCOPE_CHANGE_ACK: phát hành chủ yếu khi accept downgrade ở Gate Plan;
    # nếu xảy ra ở Gate Output → caller phải override qua `Phase:` header trong file.
    # QA_LIMIT_1: phải gửi TRƯỚC QA Plan Review = Gate Plan default.
    DocumentType.SCOPE_CHANGE_ACK.value: PhaseType.GATE_PLAN.value,
    DocumentType.QA_LIMIT_1.value: PhaseType.GATE_PLAN.value,
    # Anchor Co-Sign (added 2026-05). Workflow chạy ở CP0 phase TRƯỚC CEO BRIEF.
    DocumentType.ANCHOR_COSIGN_REQUEST.value: PhaseType.CP0.value,
    DocumentType.ANCHOR_COSIGN_ACK.value: PhaseType.CP0.value,
    # Unknown
    DocumentType.UNKNOWN_DOC.value: PhaseType.UNKNOWN_PHASE.value,
}


# ---------------------------------------------------------------------------
# §3.6 Importance tiers
# ---------------------------------------------------------------------------

DEFAULT_CRITICAL_DOC_TYPES: List[str] = [
    DocumentType.CEO_BRIEF.value,
    DocumentType.PRODUCT_LANE_PLAN.value,
    DocumentType.ENGINEERING_LANE_PLAN.value,
    DocumentType.POD_PLAN.value,
    DocumentType.GROWTH_POD_PLAN.value,
    DocumentType.QA_PLAN_REVIEW.value,
    DocumentType.QA_REPORT.value,
    DocumentType.EXECUTIVE_REVIEW.value,
    DocumentType.DEPUTY_CLOSURE.value,
    DocumentType.DEPUTY_CLOSURE_FT.value,
    DocumentType.PROMPT_APPROVAL.value,
    # Anti Down-Scope Guardrail v1 (added 2026-05 — REV D)
    DocumentType.SCOPE_CHANGE_ACK.value,  # gating ack — CEO ký TRƯỚC khi accept downgrade
    DocumentType.QA_LIMIT_1.value,  # QA scope arbitration — CEO ký TRƯỚC khi QA review
    # Anchor Co-Sign workflow (added 2026-05).
    # Cả 2 đều gating CEO BRIEF — nếu thiếu, project không thể proceed.
    DocumentType.ANCHOR_COSIGN_REQUEST.value,
    DocumentType.ANCHOR_COSIGN_ACK.value,
]

DEFAULT_IMPORTANT_DOC_TYPES: List[str] = [
    DocumentType.CEO_GATE_DIRECTIVE.value,
    DocumentType.CEO_FAST_TRACK_DECISION.value,
    DocumentType.COO_STATUS_PACKAGE.value,
    DocumentType.QA_LIGHTWEIGHT_FT.value,
    DocumentType.COO_POD_ASSIGNMENT.value,
    DocumentType.SPECIALIST_REPORT.value,
]

# Default mirror_doc_types = critical + important. Config may override to prune
# or extend, e.g. to mirror only critical.
DEFAULT_MIRROR_DOC_TYPES: List[str] = (
    DEFAULT_CRITICAL_DOC_TYPES + DEFAULT_IMPORTANT_DOC_TYPES
)


def default_importance(doc_type: str) -> ImportanceLevel:
    if doc_type in DEFAULT_CRITICAL_DOC_TYPES:
        return ImportanceLevel.CRITICAL
    if doc_type in DEFAULT_IMPORTANT_DOC_TYPES:
        return ImportanceLevel.IMPORTANT
    return ImportanceLevel.NORMAL


# ---------------------------------------------------------------------------
# §5.3.1 critical_flow_whitelist
# ---------------------------------------------------------------------------

CRITICAL_FLOW_WHITELIST: List[Tuple[str, str]] = [
    ("CEO", "COO"),
    ("COO", "CEO"),
    ("COO", "PRODUCT"),
    ("COO", "ENGINEERING"),
    ("PRODUCT", "COO"),
    ("ENGINEERING", "COO"),
    ("PRODUCTPODLEAD", "COO"),
    ("ENGINEERINGPODLEAD", "COO"),
    ("GROWTHPODLEAD", "COO"),
    ("QA", "DEPUTY"),
    ("DEPUTY", "CEO"),
    ("DEPUTY", "REPORTER"),
    ("CEO", "REPORTER"),
    ("COO", "REPORTER"),
    # Anti Down-Scope Guardrail v1 (added 2026-05 — REV D).
    # Tuyến QA→CEO ĐẶC BIỆT chỉ hợp lệ cho doc_type = QA_LIMIT_1
    # (QA gửi xin CEO ack trước khi tự khoá phạm vi review).
    # Mọi QA_REPORT / QA_PLAN_REVIEW có to_role=CEO sẽ bị router chặn (REVIEW_MANUAL,
    # cause AMBIGUOUS:QA_TO_CEO_RESERVED_FOR_QA_LIMIT_1) — xem app/router.py.
    ("QA", "CEO"),
]
