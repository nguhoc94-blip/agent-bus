"""Data models: enums + dataclasses for the pipeline (v2)."""

from __future__ import annotations

import re as _re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


class Action(str, Enum):
    MOVED = "moved"
    REVIEW = "review"
    SKIPPED = "skipped"
    ERROR = "error"


class ReviewReason(str, Enum):
    """Only the 4 values that map to a REVIEW_MANUAL/<subfolder>. L2: UNSUPPORTED_EXT is NOT here."""

    MISSING_PROJECT = "MISSING_PROJECT"
    MISSING_POD = "MISSING_POD"
    MISSING_ROLE = "MISSING_ROLE"
    AMBIGUOUS = "AMBIGUOUS"


class SkipReason(str, Enum):
    UNSUPPORTED_EXT = "UNSUPPORTED_EXT"
    TEMPORARY_EXTENSION = "TEMPORARY_EXTENSION"
    ALREADY_PROCESSED_FINGERPRINT = "ALREADY_PROCESSED_FINGERPRINT"


class ErrorReason(str, Enum):
    FILE_LOCKED_AFTER_RETRIES = "FILE_LOCKED_AFTER_RETRIES"
    COPY_FAILED = "COPY_FAILED"
    DEST_VOLUME_UNAVAILABLE = "DEST_VOLUME_UNAVAILABLE"


class AmbiguityCause(str, Enum):
    POD_IN_MULTI_PROJECT = "POD_IN_MULTI_PROJECT"
    CONTENT_FILENAME_CONFLICT = "CONTENT_FILENAME_CONFLICT"
    MULTIPLE_FILENAME_MATCHES = "MULTIPLE_FILENAME_MATCHES"
    UNKNOWN_DOC_IN_CRITICAL_FLOW = "UNKNOWN_DOC_IN_CRITICAL_FLOW"
    UNKNOWN_PHASE_ON_CRITICAL_DOC = "UNKNOWN_PHASE_ON_CRITICAL_DOC"
    PHASE_CONFLICT = "PHASE_CONFLICT"
    DOCTYPE_CONFLICT = "DOCTYPE_CONFLICT"


class MoveStrategy(str, Enum):
    ATOMIC_REPLACE = "atomic_replace"
    CROSS_VOLUME_COPY = "cross_volume_copy"


class PhaseType(str, Enum):
    CP0 = "CP0"
    PHASE_1 = "PHASE_1"
    PHASE_1_SUBPLAN = "PHASE_1_SUBPLAN"
    PHASE_2 = "PHASE_2"
    GATE_PLAN = "GATE_PLAN"
    GATE_OUTPUT = "GATE_OUTPUT"
    FAST_TRACK = "FAST_TRACK"
    FAST_TRACK_CLOSURE = "FAST_TRACK_CLOSURE"
    PROMPT_CHANGE = "PROMPT_CHANGE"
    SKILL_GAP = "SKILL_GAP"
    UNKNOWN_PHASE = "UNKNOWN_PHASE"


class DocumentType(str, Enum):
    # CEO
    CEO_BRIEF = "CEO_BRIEF"
    CEO_GATE_DIRECTIVE = "CEO_GATE_DIRECTIVE"
    CEO_CP0_TRIGGER = "CEO_CP0_TRIGGER"
    CEO_FAST_TRACK_DECISION = "CEO_FAST_TRACK_DECISION"
    CEO_INFORM_QA = "CEO_INFORM_QA"
    # COO
    COO_PRE_BRIEF_BASIS = "COO_PRE_BRIEF_BASIS"
    COO_STATUS_PACKAGE = "COO_STATUS_PACKAGE"
    COO_QA_REVIEW_REQUEST = "COO_QA_REVIEW_REQUEST"
    COO_POD_ASSIGNMENT = "COO_POD_ASSIGNMENT"
    COO_CP0_OPEN = "COO_CP0_OPEN"
    COO_FAST_TRACK_PROPOSAL = "COO_FAST_TRACK_PROPOSAL"
    # Product
    PRODUCT_LANE_PLAN = "PRODUCT_LANE_PLAN"
    PRODUCT_LANE_COMPLETION = "PRODUCT_LANE_COMPLETION"
    PRODUCT_CP0_INPUT_SPEC = "PRODUCT_CP0_INPUT_SPEC"
    PRODUCT_TO_ENGINEERING = "PRODUCT_TO_ENGINEERING"
    # Engineering
    ENGINEERING_LANE_PLAN = "ENGINEERING_LANE_PLAN"
    ENGINEERING_LANE_COMPLETION = "ENGINEERING_LANE_COMPLETION"
    ENGINEERING_CP0_FEASIBILITY = "ENGINEERING_CP0_FEASIBILITY"
    ENGINEERING_TO_PRODUCT = "ENGINEERING_TO_PRODUCT"
    # Pod (POD-based company)
    POD_PLAN = "POD_PLAN"
    GROWTH_POD_PLAN = "GROWTH_POD_PLAN"
    INTERFACE_SYNC = "INTERFACE_SYNC"
    GROWTH_SIGNAL = "GROWTH_SIGNAL"
    # QA
    QA_PLAN_REVIEW = "QA_PLAN_REVIEW"
    QA_REPORT = "QA_REPORT"
    QA_LIGHTWEIGHT_FT = "QA_LIGHTWEIGHT_FT"
    QA_CROSS_POD_REVIEW = "QA_CROSS_POD_REVIEW"
    # Deputy / Executive
    EXECUTIVE_REVIEW = "EXECUTIVE_REVIEW"
    DEPUTY_CLOSURE = "DEPUTY_CLOSURE"
    DEPUTY_CLOSURE_FT = "DEPUTY_CLOSURE_FT"
    # Specialist / Builder / Tasks
    SPECIALIST_REPORT = "SPECIALIST_REPORT"
    BUILDER_REPORT = "BUILDER_REPORT"
    TASK_ASSIGNMENT = "TASK_ASSIGNMENT"
    # Prompt change
    PROMPT_CHANGE_REQUEST = "PROMPT_CHANGE_REQUEST"
    PROMPT_CHANGE_PROPOSAL = "PROMPT_CHANGE_PROPOSAL"
    PROMPT_IMPACT_REVIEW = "PROMPT_IMPACT_REVIEW"
    PROMPT_APPROVAL = "PROMPT_APPROVAL"
    # Skill gap / specialist activation
    SKILL_GAP_REPORT = "SKILL_GAP_REPORT"
    SKILL_GAP_ESCALATION = "SKILL_GAP_ESCALATION"
    SPECIALIST_ACTIVATION_REQUEST = "SPECIALIST_ACTIVATION_REQUEST"
    # Anti Down-Scope Guardrail v1 (added 2026-05 — REV D)
    SCOPE_CHANGE_ACK = "SCOPE_CHANGE_ACK"
    QA_LIMIT_1 = "QA_LIMIT_1"
    # Anchor Co-Sign workflow (added 2026-05 — Anchor Co-Sign)
    ANCHOR_COSIGN_REQUEST = "ANCHOR_COSIGN_REQUEST"
    ANCHOR_COSIGN_ACK = "ANCHOR_COSIGN_ACK"
    # Fallback
    UNKNOWN_DOC = "UNKNOWN_DOC"


class ImportanceLevel(str, Enum):
    CRITICAL = "CRITICAL"
    IMPORTANT = "IMPORTANT"
    NORMAL = "NORMAL"


@dataclass
class ClassificationResult:
    """Outcome of `classify_document()`. Kept as a small struct so parser can
    return both the decision and the source (for audit/logging)."""

    doc_type: DocumentType = DocumentType.UNKNOWN_DOC
    source: str = "none"  # "doctype_field" | "loai_field" | "heading" | "filename_v2" | "none"
    reason: str = ""


@dataclass
class ParsedMetadata:
    project: Optional[str] = None
    pod: Optional[str] = None
    from_role: Optional[str] = None
    to_role: Optional[str] = None
    source_of_metadata: str = "none"
    confidence: float = 0.0
    reason: str = ""
    ambiguity_cause: Optional[AmbiguityCause] = None

    # v2 additions
    phase: PhaseType = PhaseType.UNKNOWN_PHASE
    doc_type: DocumentType = DocumentType.UNKNOWN_DOC
    importance: ImportanceLevel = ImportanceLevel.NORMAL
    mirror_to_reporter: bool = False
    # Project identity (resolved from config during routing). Parser leaves these
    # None; router copies the raw `project` key and then resolves code/display.
    project_code: Optional[str] = None
    display_project_name: Optional[str] = None
    classification_source: str = "none"

    def is_complete(self) -> bool:
        return all([self.project, self.pod, self.from_role, self.to_role])


@dataclass
class RouteDecision:
    action: Action
    destination_path: Optional[Path] = None
    new_filename: Optional[str] = None
    reason: str = ""
    # v2: primary = destination_path (keep alias for backward-compat), mirrors = list
    primary_destination_path: Optional[Path] = None
    mirror_destination_paths: List[Path] = field(default_factory=list)

    def __post_init__(self):
        # Keep primary_destination_path in sync with destination_path so callers
        # that still read the old field keep working.
        if self.primary_destination_path is None and self.destination_path is not None:
            self.primary_destination_path = self.destination_path
        elif self.destination_path is None and self.primary_destination_path is not None:
            self.destination_path = self.primary_destination_path


@dataclass
class ProjectConfig:
    name: str  # the config key, preserved as-is for log/backward compat
    root: Path
    pods: List[str]
    # v2: machine ID for canonical filename / reporter hub / regex matching.
    # Mandatory when `name` has non-canonical chars. Validated in config.py.
    project_code: str = ""
    display_name: Optional[str] = None
    # Optional regex for Big-Mode projects whose pod IDs are dynamic
    # (e.g. P1, E1_Backend, G2_Growth). Pod must match this pattern OR be
    # in the static `pods` list. Validated + compiled at config load time.
    dynamic_pod_pattern: Optional[str] = None

    @property
    def effective_display(self) -> str:
        return self.display_name or self.name

    def pod_allowed(self, pod: str) -> bool:
        """Return True if pod is in static whitelist OR matches dynamic_pod_pattern."""
        if pod in self.pods:
            return True
        if self.dynamic_pod_pattern:
            return bool(_re.match(self.dynamic_pod_pattern, pod, _re.IGNORECASE))
        return False


@dataclass
class PacketSourceConfig:
    """REV E-Lazy: nguồn rulecard + anchor templates cho từng mode (TB/BIG).

    Resolved tại config load time. Bus sẽ validate file tồn tại per-mode (Q10):
    TB source thiếu không tắt BIG, và ngược lại.
    """

    rulecard: Path
    anchors: List[Path]


@dataclass
class AppConfig:
    watch_folder: Path
    allowed_extensions: List[str]
    temporary_extensions: List[str]
    review_folder: Path
    log_folder: Path
    projects: Dict[str, ProjectConfig]
    roles: List[str]
    inbox_suffix: str = "_INBOX"
    duplicate_strategy: str = "overwrite"
    dry_run: bool = False
    scan_stable_seconds: int = 3
    scan_stable_checks: int = 3
    max_lock_retries: int = 5
    lock_retry_delay_s: float = 1.0
    warnings: List[str] = field(default_factory=list)
    # v2 additions
    reporter_hub_name: str = "_REPORTER_HUB"
    mirror_doc_types: List[str] = field(default_factory=list)
    critical_doc_types: List[str] = field(default_factory=list)
    role_aliases: Dict[str, str] = field(default_factory=dict)
    phase_aliases: Dict[str, str] = field(default_factory=dict)
    doc_type_aliases: Dict[str, str] = field(default_factory=dict)
    heading_map: Dict[str, str] = field(default_factory=dict)
    template_registry_path: Optional[Path] = None
    # REV E-Lazy: inbox auto-packet drop.
    auto_drop_inbox_packet: bool = True
    packet_sources: Dict[str, "PacketSourceConfig"] = field(default_factory=dict)
    packet_mode_valid: Dict[str, bool] = field(default_factory=dict)

    def pod_to_projects(self) -> Dict[str, List[str]]:
        """Reverse map pod -> list of projects that contain it."""
        out: Dict[str, List[str]] = {}
        for pname, pcfg in self.projects.items():
            for pod in pcfg.pods:
                out.setdefault(pod, []).append(pname)
        return out

    def project_code_to_key(self) -> Dict[str, str]:
        """Reverse map project_code -> config key, for canonical filename lookup."""
        out: Dict[str, str] = {}
        for pname, pcfg in self.projects.items():
            if pcfg.project_code:
                out[pcfg.project_code] = pname
        return out
