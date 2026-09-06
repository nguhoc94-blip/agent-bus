"""Tests for router.py v2 additions (project_code, mirrors, review escalation)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from app.config import ConfigError, parse_config
from app.models import (
    Action, AmbiguityCause, DocumentType, ImportanceLevel, ParsedMetadata,
    PhaseType, ProjectConfig, ReviewReason,
)
from app.router import decide


def _meta(**kwargs) -> ParsedMetadata:
    defaults = {
        "project": "DEMO", "pod": "POD_CORE",
        "from_role": "CEO", "to_role": "COO",
        "source_of_metadata": "content", "confidence": 1.0, "reason": "ok",
        "phase": PhaseType.PHASE_1,
        "doc_type": DocumentType.CEO_BRIEF,
        "importance": ImportanceLevel.CRITICAL,
        "mirror_to_reporter": True,
    }
    defaults.update(kwargs)
    return ParsedMetadata(**defaults)


def test_primary_path_uses_project_code_not_display_name(config):
    """TRADE_ALERT-style project (display has spaces, code is canonical)."""
    trade_root = Path(config.projects["DEMO"].root.parent / "TRADE_ALERT_ROOT")
    trade_root.mkdir(parents=True, exist_ok=True)
    config.projects["DEMO_TRADE_PROJECT"] = ProjectConfig(
        name="DEMO_TRADE_PROJECT",
        root=trade_root,
        pods=["POD_MAIN"],
        project_code="TRADE_ALERT",
        display_name="DEMO_TRADE_PROJECT",
    )
    meta = _meta(
        project="DEMO_TRADE_PROJECT", pod="POD_MAIN",
        from_role="CEO", to_role="COO",
    )
    d = decide(meta, "some_input.md", config)
    assert d.action == Action.MOVED
    # Filename uses project_code, NOT underscored display key verbatim in all parts
    assert d.new_filename.startswith("TRADE_ALERT__PHASE_1__POD_MAIN__CEO_BRIEF__")
    assert " " not in d.new_filename


def test_critical_doc_has_mirror_reporter_hub(config):
    d = decide(_meta(), "anything.md", config)
    assert d.action == Action.MOVED
    assert d.mirror_destination_paths, "critical doc must produce a mirror path"
    mirror = d.mirror_destination_paths[0]
    assert config.reporter_hub_name in str(mirror)
    assert "PHASE_1" in str(mirror)
    assert "CEO_BRIEF" in str(mirror)


def test_normal_doc_no_mirror(config):
    meta = _meta(
        doc_type=DocumentType.TASK_ASSIGNMENT,
        importance=ImportanceLevel.NORMAL,
        mirror_to_reporter=False,
    )
    d = decide(meta, "x.md", config)
    assert d.mirror_destination_paths == []


def test_unknown_doc_in_critical_flow_routes_review(config):
    meta = _meta(
        doc_type=DocumentType.UNKNOWN_DOC,
        importance=ImportanceLevel.NORMAL,
        mirror_to_reporter=False,
        from_role="CEO", to_role="COO",  # whitelist pair
    )
    d = decide(meta, "critical_unknown.md", config)
    assert d.action == Action.REVIEW
    assert ReviewReason.AMBIGUOUS.value in str(d.destination_path)
    assert AmbiguityCause.UNKNOWN_DOC_IN_CRITICAL_FLOW.value in d.reason


def test_unknown_doc_outside_critical_flow_routes_inbox(config):
    """(PRODUCT,ENGINEERING) is NOT in the critical flow whitelist → route inbox,
    no mirror, no review."""
    meta = _meta(
        doc_type=DocumentType.UNKNOWN_DOC,
        importance=ImportanceLevel.NORMAL,
        mirror_to_reporter=False,
        from_role="PRODUCT", to_role="ENGINEERING",
    )
    d = decide(meta, "random_draft.md", config)
    assert d.action == Action.MOVED
    assert d.mirror_destination_paths == []


def test_unknown_phase_with_critical_doctype_routes_review(config):
    meta = _meta(
        phase=PhaseType.UNKNOWN_PHASE,
        doc_type=DocumentType.QA_REPORT,
        importance=ImportanceLevel.CRITICAL,
    )
    d = decide(meta, "qa_report.md", config)
    assert d.action == Action.REVIEW
    assert AmbiguityCause.UNKNOWN_PHASE_ON_CRITICAL_DOC.value in d.reason


def test_review_destination_keeps_original_filename(config):
    meta = _meta(doc_type=DocumentType.UNKNOWN_DOC, from_role="CEO", to_role="COO")
    d = decide(meta, "weird_input_name.md", config)
    assert d.action == Action.REVIEW
    assert d.new_filename == "weird_input_name.md"
    # Path ends with the original filename exactly.
    assert str(d.destination_path).endswith("weird_input_name.md")


def test_review_destination_no_mirror(config):
    meta = _meta(doc_type=DocumentType.UNKNOWN_DOC, from_role="CEO", to_role="COO")
    d = decide(meta, "foo.md", config)
    assert d.action == Action.REVIEW
    assert d.mirror_destination_paths == []


def test_project_code_lookup_by_code(config):
    """If parser put project=TRADE_ALERT (from v2 filename), router should still
    resolve to the project whose config key is 'DEMO_TRADE_PROJECT'."""
    trade_root = Path(config.projects["DEMO"].root.parent / "TRADE_LOOKUP")
    trade_root.mkdir(parents=True, exist_ok=True)
    config.projects["DEMO_TRADE_PROJECT"] = ProjectConfig(
        name="DEMO_TRADE_PROJECT",
        root=trade_root,
        pods=["POD_MAIN"],
        project_code="TRADE_ALERT",
        display_name="DEMO_TRADE_PROJECT",
    )
    meta = _meta(project="TRADE_ALERT", pod="POD_MAIN")
    d = decide(meta, "x.md", config)
    assert d.action == Action.MOVED
    assert str(trade_root) in str(d.destination_path)


# ---------------------------------------------------------------------------
# Config loader: project_code validation
# ---------------------------------------------------------------------------


def _base_raw(tmp_path: Path):
    return {
        "watch_folder": str(tmp_path / "dl"),
        "allowed_extensions": [".md"],
        "review_folder": str(tmp_path / "rev"),
        "log_folder": str(tmp_path / "logs"),
        "projects": {},
        "roles": ["CEO", "COO"],
    }


def test_project_code_with_space_fails(tmp_path):
    import pytest
    raw = _base_raw(tmp_path)
    raw["projects"] = {
        "DU AN NO CODE": {
            "root": str(tmp_path / "p1"),
            "pods": ["POD_MAIN"],
            # No project_code → must raise since key has spaces
        }
    }
    with pytest.raises(ConfigError):
        parse_config(raw)


def test_invalid_project_code_fails(tmp_path):
    import pytest
    raw = _base_raw(tmp_path)
    raw["projects"] = {
        "DU AN BAD CODE": {
            "project_code": "trade-alert",  # lowercase + hyphen → invalid
            "root": str(tmp_path / "p1"),
            "pods": ["POD_MAIN"],
        }
    }
    with pytest.raises(ConfigError):
        parse_config(raw)


def test_project_code_legacy_canonical_key_works(tmp_path):
    raw = _base_raw(tmp_path)
    raw["projects"] = {
        "DEMO": {
            "root": str(tmp_path / "p1"),
            "pods": ["POD_MAIN"],
        }
    }
    cfg = parse_config(raw)
    assert cfg.projects["DEMO"].project_code == "DEMO"


def test_duplicate_project_code_fails(tmp_path):
    import pytest
    raw = _base_raw(tmp_path)
    raw["projects"] = {
        "FOO": {"project_code": "SHARED", "root": str(tmp_path / "a"), "pods": ["P"]},
        "BAR": {"project_code": "SHARED", "root": str(tmp_path / "b"), "pods": ["P"]},
    }
    with pytest.raises(ConfigError):
        parse_config(raw)


def test_config_example_parses_valid():
    """config.example.json must parse successfully after the v2 fix."""
    import json

    p = Path(__file__).resolve().parent.parent / "config.example.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "projects" in data
    assert "reporter_hub_name" in data
    # project_code declared for non-canonical key
    proj = data["projects"]["DEMO_TRADE_PROJECT"]
    assert proj["project_code"] == "TRADE_ALERT"


# ---------------------------------------------------------------------------
# Anti Down-Scope Guardrail v1 (REV D 2026-05) — QA→CEO ROUTE LOCK
# Verified: parser.is_critical_flow chỉ apply khi UNKNOWN_DOC; với QA_REPORT
# đã nhận diện thì router build destination theo to_role bình thường — chữ
# "LOCK" CHỈ thực sự enforce qua validation trong app/router.py.
# ---------------------------------------------------------------------------


def test_qa_to_ceo_allowed_only_for_qa_limit_1(config):
    """QA→CEO HỢP LỆ khi doc_type = QA_LIMIT_1.

    QA_LIMIT_1 là tuyến đặc biệt: QA xin CEO ack TRƯỚC khi tự khoá phạm vi
    review (chống self-lock — Manual §7.12).
    """
    meta = _meta(
        doc_type=DocumentType.QA_LIMIT_1,
        from_role="QA",
        to_role="CEO",
        importance=ImportanceLevel.CRITICAL,
        phase=PhaseType.GATE_PLAN,
    )
    d = decide(meta, "qa_limit.md", config)
    assert d.action == Action.MOVED, (
        f"QA→CEO + QA_LIMIT_1 phải MOVED (tuyến đặc biệt hợp lệ); "
        f"got {d.action} reason={d.reason}"
    )


def test_qa_report_to_ceo_routes_to_review(config):
    """QA_REPORT có to_role=CEO → REVIEW vì QA mặc định gửi Deputy.

    Verified Job TB Manual line 987–990: QA output gửi Deputy, copy COO.
    QA→CEO chỉ hợp lệ cho QA_LIMIT_1 — mọi QA_REPORT/QA_PLAN_REVIEW có
    to_role=CEO bị router chặn về REVIEW_MANUAL với cause AMBIGUOUS.
    """
    meta = _meta(
        doc_type=DocumentType.QA_REPORT,
        from_role="QA",
        to_role="CEO",
        importance=ImportanceLevel.CRITICAL,
        phase=PhaseType.GATE_OUTPUT,
    )
    d = decide(meta, "qa_report_to_ceo.md", config)
    assert d.action == Action.REVIEW, (
        f"QA_REPORT + to_role=CEO phải REVIEW (tuyến không hợp lệ); "
        f"got {d.action}"
    )
    assert "QA_TO_CEO_RESERVED_FOR_QA_LIMIT_1" in d.reason
    assert ReviewReason.AMBIGUOUS.value in str(d.destination_path)


def test_qa_plan_review_to_ceo_routes_to_review(config):
    """QA_PLAN_REVIEW có to_role=CEO → REVIEW (đối ứng test trên cho Phase 1)."""
    meta = _meta(
        doc_type=DocumentType.QA_PLAN_REVIEW,
        from_role="QA",
        to_role="CEO",
        importance=ImportanceLevel.CRITICAL,
        phase=PhaseType.GATE_PLAN,
    )
    d = decide(meta, "qa_plan_review_to_ceo.md", config)
    assert d.action == Action.REVIEW
    assert "QA_TO_CEO_RESERVED_FOR_QA_LIMIT_1" in d.reason


def test_qa_to_deputy_still_works_for_qa_report(config):
    """QA → DEPUTY vẫn MOVED bình thường cho QA_REPORT (không bị guard mới chặn)."""
    meta = _meta(
        doc_type=DocumentType.QA_REPORT,
        from_role="QA",
        to_role="DEPUTY",
        importance=ImportanceLevel.CRITICAL,
        phase=PhaseType.GATE_OUTPUT,
    )
    d = decide(meta, "qa_report.md", config)
    assert d.action == Action.MOVED, (
        f"QA→DEPUTY + QA_REPORT phải MOVED bình thường; got {d.action} reason={d.reason}"
    )


def test_scope_change_ack_coo_to_ceo_works(config):
    """SCOPE_CHANGE_ACK COO→CEO phải MOVED (tuyến chuẩn ack downscope)."""
    meta = _meta(
        doc_type=DocumentType.SCOPE_CHANGE_ACK,
        from_role="COO",
        to_role="CEO",
        importance=ImportanceLevel.CRITICAL,
        phase=PhaseType.GATE_PLAN,
    )
    d = decide(meta, "scope_change_ack.md", config)
    assert d.action == Action.MOVED, (
        f"SCOPE_CHANGE_ACK COO→CEO phải MOVED; got {d.action} reason={d.reason}"
    )
