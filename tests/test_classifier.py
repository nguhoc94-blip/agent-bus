"""Tests for parser/classifier v2 (Hybrid 2)."""

from __future__ import annotations

from pathlib import Path

from app import parser as parser_mod
from app.models import AmbiguityCause, DocumentType, ImportanceLevel, PhaseType
from app.parser import (
    _extract_heading_line,
    _normalize_heading,
    classify_document,
)
from tests.conftest import write_md


# ---------------------------------------------------------------------------
# §3.4 DocType > Loại > heading > filename precedence
# ---------------------------------------------------------------------------


def test_classify_by_doctype_field(tmp_path: Path):
    res = classify_document(
        content_v2={"doc_type": "CEO_BRIEF", "loai": None, "phase": None},
        heading_line="## QA REPORT",  # should be ignored — DocType wins
        from_role="CEO",
        to_role="COO",
        filename="anything.md",
    )
    assert res.doc_type == DocumentType.CEO_BRIEF
    assert res.source == "doctype_field"


def test_classify_by_loai_cp0_trigger():
    res = classify_document(
        content_v2={"doc_type": None, "loai": "cp0-trigger", "phase": None},
        heading_line=None,
        from_role="CEO",
        to_role="COO",
        filename="x.md",
    )
    assert res.doc_type == DocumentType.CEO_CP0_TRIGGER
    assert res.source == "loai_field"


def test_classify_loai_pod_plan_growth():
    res = classify_document(
        content_v2={"doc_type": None, "loai": "pod-plan", "phase": None},
        heading_line=None,
        from_role="GROWTHPODLEAD",
        to_role="COO",
        filename="x.md",
    )
    assert res.doc_type == DocumentType.GROWTH_POD_PLAN


def test_classify_loai_pod_completion_by_from():
    res = classify_document(
        content_v2={"doc_type": None, "loai": "pod-completion-report", "phase": None},
        heading_line=None,
        from_role="PRODUCT",
        to_role="COO",
        filename="x.md",
    )
    assert res.doc_type == DocumentType.PRODUCT_LANE_COMPLETION

    res2 = classify_document(
        content_v2={"doc_type": None, "loai": "pod-completion-report", "phase": None},
        heading_line=None,
        from_role="ENGINEERING",
        to_role="COO",
        filename="x.md",
    )
    assert res2.doc_type == DocumentType.ENGINEERING_LANE_COMPLETION


def test_classify_heading_ceo_brief():
    res = classify_document(
        content_v2={"doc_type": None, "loai": None, "phase": None},
        heading_line="## CEO BRIEF",
        from_role="CEO",
        to_role="COO",
        filename="x.md",
    )
    assert res.doc_type == DocumentType.CEO_BRIEF
    assert res.source == "heading"


def test_classify_heading_qa_plan_review():
    res = classify_document(
        content_v2={"doc_type": None, "loai": None, "phase": None},
        heading_line="## QA PLAN REVIEW",
        from_role="QA",
        to_role="DEPUTY",
        filename="x.md",
    )
    assert res.doc_type == DocumentType.QA_PLAN_REVIEW


def test_classify_heading_qa_report():
    res = classify_document(
        content_v2={"doc_type": None, "loai": None, "phase": None},
        heading_line="## QA REPORT",
        from_role="QA",
        to_role="DEPUTY",
        filename="x.md",
    )
    assert res.doc_type == DocumentType.QA_REPORT


def test_classify_heading_lane_completion_by_from():
    res_prod = classify_document(
        content_v2={"doc_type": None, "loai": None, "phase": None},
        heading_line="## LANE COMPLETION REPORT",
        from_role="PRODUCT",
        to_role="COO",
        filename="x.md",
    )
    assert res_prod.doc_type == DocumentType.PRODUCT_LANE_COMPLETION

    res_eng = classify_document(
        content_v2={"doc_type": None, "loai": None, "phase": None},
        heading_line="## LANE COMPLETION REPORT",
        from_role="ENGINEERING",
        to_role="COO",
        filename="x.md",
    )
    assert res_eng.doc_type == DocumentType.ENGINEERING_LANE_COMPLETION


def test_classify_heading_deputy_closure_ft_vs_normal():
    res_normal = classify_document(
        content_v2={"doc_type": None, "loai": None, "phase": None},
        heading_line="## GÓI CHỐT",
        from_role="DEPUTY", to_role="REPORTER", filename="x.md",
    )
    assert res_normal.doc_type == DocumentType.DEPUTY_CLOSURE

    res_ft = classify_document(
        content_v2={"doc_type": None, "loai": None, "phase": None},
        heading_line="## GÓI XÁC NHẬN CLOSURE FT",
        from_role="DEPUTY", to_role="REPORTER", filename="x.md",
    )
    assert res_ft.doc_type == DocumentType.DEPUTY_CLOSURE_FT


def test_classify_unknown_doc_fallback_review():
    res = classify_document(
        content_v2={"doc_type": None, "loai": None, "phase": None},
        heading_line="## NOT A REAL HEADING",
        from_role="CEO", to_role="COO", filename="x.md",
    )
    assert res.doc_type == DocumentType.UNKNOWN_DOC
    assert res.source == "none"


# ---------------------------------------------------------------------------
# §3.4.1 heading_line selection
# ---------------------------------------------------------------------------


def test_heading_line_skips_metadata_and_blanks(tmp_path: Path):
    p = tmp_path / "t.md"
    p.write_text(
        "Project: DEMO\nPod: POD_CORE\nFrom: CEO\nTo: COO\nPhase: PHASE_1\n\n"
        "## CEO BRIEF\n\nbody",
        encoding="utf-8",
    )
    assert _extract_heading_line(p) == "## CEO BRIEF"


def test_heading_line_is_first_markdown_heading_only(tmp_path: Path):
    """Second heading deeper in the file must NOT be returned."""
    p = tmp_path / "t.md"
    p.write_text(
        "Project: DEMO\n\n## CEO BRIEF\n\nfoo\n\n## QA REPORT\n",
        encoding="utf-8",
    )
    assert _extract_heading_line(p) == "## CEO BRIEF"


def test_heading_line_none_when_no_markdown_heading(tmp_path: Path):
    p = tmp_path / "t.md"
    p.write_text("Project: DEMO\nPod: POD_CORE\n\nno heading here\n", encoding="utf-8")
    assert _extract_heading_line(p) is None


# ---------------------------------------------------------------------------
# §3.4.2 heading normalization
# ---------------------------------------------------------------------------


def test_heading_normalize_dash_variants():
    """All dash variants should collapse to em-dash."""
    v1 = _normalize_heading("## QA PLAN — REVIEW")
    v2 = _normalize_heading("## QA PLAN - REVIEW")
    v3 = _normalize_heading("## QA PLAN – REVIEW")
    v4 = _normalize_heading("## QA PLAN -- REVIEW")
    assert v1 == v2 == v3 == v4


def test_heading_normalize_collapses_double_space():
    v1 = _normalize_heading("## QA PLAN REVIEW")
    v2 = _normalize_heading("## QA PLAN  REVIEW")
    v3 = _normalize_heading("## QA PLAN   REVIEW")
    assert v1 == v2 == v3


def test_heading_normalize_keeps_vietnamese_diacritics():
    with_dia = _normalize_heading("## GÓI CHỐT")
    without_dia = _normalize_heading("## GOI CHOT")
    assert with_dia != without_dia


def test_heading_normalize_case_insensitive():
    upper = _normalize_heading("## CEO BRIEF")
    lower = _normalize_heading("## ceo brief")
    mixed = _normalize_heading("## Ceo BriEF")
    assert upper == lower == mixed


# ---------------------------------------------------------------------------
# Filename v2 parsing
# ---------------------------------------------------------------------------


def test_filename_v2_parses_6_parts():
    parts = parser_mod.parse_filename_v2(
        "TRADE_ALERT__PHASE_1__POD_MAIN__CEO_BRIEF__CEO_gui_COO.md"
    )
    assert parts is not None
    assert parts["project"] == "TRADE_ALERT"
    assert parts["phase"] == "PHASE_1"
    assert parts["pod"] == "POD_MAIN"
    assert parts["doc_type"] == "CEO_BRIEF"
    assert parts["from"] == "CEO"
    assert parts["to"] == "COO"


def test_filename_v1_still_parses(tmp_path: Path, config):
    p = tmp_path / "DEMO__POD_CORE__COO_gui_CEO.md"
    p.write_text("random body", encoding="utf-8")
    meta = parser_mod.parse(p, config)
    assert meta.project == "DEMO"
    assert meta.pod == "POD_CORE"
    assert meta.from_role == "COO"
    assert meta.to_role == "CEO"
    # Doc type undetected → UNKNOWN_DOC
    assert meta.doc_type == DocumentType.UNKNOWN_DOC


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------


def test_conflict_phase_ambiguous(tmp_path: Path, config):
    """Header says Phase: PHASE_1 but v2 filename says PHASE_2 → PHASE_CONFLICT."""
    p = tmp_path / "DEMO__PHASE_2__POD_CORE__CEO_BRIEF__CEO_gui_COO.md"
    write_md(
        p, project="DEMO", pod="POD_CORE", from_role="CEO", to_role="COO",
        phase="PHASE_1", doc_type="CEO_BRIEF",
    )
    meta = parser_mod.parse(p, config)
    assert meta.ambiguity_cause == AmbiguityCause.PHASE_CONFLICT


def test_conflict_doctype_ambiguous(tmp_path: Path, config):
    """Header DocType: QA_REPORT but filename doctype part=CEO_BRIEF → DOCTYPE_CONFLICT."""
    p = tmp_path / "DEMO__PHASE_1__POD_CORE__CEO_BRIEF__CEO_gui_COO.md"
    write_md(
        p, project="DEMO", pod="POD_CORE", from_role="CEO", to_role="COO",
        doc_type="QA_REPORT",
    )
    meta = parser_mod.parse(p, config)
    assert meta.ambiguity_cause == AmbiguityCause.DOCTYPE_CONFLICT


# ---------------------------------------------------------------------------
# Alias normalization
# ---------------------------------------------------------------------------


def test_role_alias_normalize(tmp_path: Path, config):
    p = tmp_path / "DEMO__POD_CORE__PRODUCT_gui_ENGINEERING.md"
    p.write_text(
        "Project: DEMO\nPod: POD_CORE\nTừ: Product\nGửi: Engineering\n",
        encoding="utf-8",
    )
    meta = parser_mod.parse(p, config)
    assert meta.from_role == "PRODUCT"
    assert meta.to_role == "ENGINEERING"


def test_phase_alias_normalize():
    from app.parser import normalize_phase
    assert normalize_phase("Phase 1") == PhaseType.PHASE_1
    assert normalize_phase("Gate Plan") == PhaseType.GATE_PLAN
    assert normalize_phase("Checkpoint 0") == PhaseType.CP0
    assert normalize_phase("CP0") == PhaseType.CP0
    assert normalize_phase(None) == PhaseType.UNKNOWN_PHASE
    assert normalize_phase("bogus") == PhaseType.UNKNOWN_PHASE


# ---------------------------------------------------------------------------
# Importance + mirror policy
# ---------------------------------------------------------------------------


def test_critical_doc_mirrors_by_default(tmp_path: Path, config):
    p = tmp_path / "brief.md"
    write_md(
        p, project="DEMO", pod="POD_CORE", from_role="CEO", to_role="COO",
        doc_type="CEO_BRIEF", phase="PHASE_1",
    )
    meta = parser_mod.parse(p, config)
    assert meta.doc_type == DocumentType.CEO_BRIEF
    assert meta.importance == ImportanceLevel.CRITICAL
    assert meta.mirror_to_reporter is True


def test_normal_doc_does_not_mirror(tmp_path: Path, config):
    p = tmp_path / "task.md"
    write_md(
        p, project="DEMO", pod="POD_CORE", from_role="COO", to_role="CEO",
        doc_type="TASK_ASSIGNMENT", phase="PHASE_1",
    )
    meta = parser_mod.parse(p, config)
    assert meta.importance == ImportanceLevel.NORMAL
    assert meta.mirror_to_reporter is False


def test_placeholder_loai_treated_as_missing():
    """`[report / sub-plan]` placeholder MUST NOT be classified as a real Loại."""
    res = classify_document(
        content_v2={"doc_type": None, "loai": "[report / sub-plan]", "phase": None},
        heading_line="## NOT A REAL HEADING",
        from_role="PRODUCT", to_role="COO", filename="x.md",
    )
    assert res.doc_type == DocumentType.UNKNOWN_DOC


# ---------------------------------------------------------------------------
# CP0 JOB_TO heading mappings (Big Mode templates)
# ---------------------------------------------------------------------------

def test_heading_coo_cp0_discovery_request():
    res = classify_document(
        content_v2={"doc_type": None, "loai": None, "phase": None},
        heading_line="## COO CP0 DISCOVERY REQUEST",
        from_role="COO", to_role="PRODUCT", filename="COO_gui_P1_CP0_DiscoveryRequest_v001.md",
    )
    assert res.doc_type == DocumentType.COO_CP0_OPEN
    assert res.source == "heading"


def test_heading_ceo_yeu_cau_mo_cp0():
    res = classify_document(
        content_v2={"doc_type": None, "loai": None, "phase": None},
        heading_line="## CEO YÊU CẦU MỞ CP0",
        from_role="CEO", to_role="COO", filename="CEO_gui_COO_CP0_v001.md",
    )
    assert res.doc_type == DocumentType.CEO_CP0_TRIGGER


def test_heading_cp0_brief_basis():
    res = classify_document(
        content_v2={"doc_type": None, "loai": None, "phase": None},
        heading_line="## CP0 BRIEF BASIS",
        from_role="COO", to_role="CEO", filename="COO_gui_CEO_CP0_BriefBasis_v001.md",
    )
    assert res.doc_type == DocumentType.COO_PRE_BRIEF_BASIS


def test_heading_cp0_input_spec():
    res = classify_document(
        content_v2={"doc_type": None, "loai": None, "phase": None},
        heading_line="## CP0 INPUT SPEC",
        from_role="PRODUCT", to_role="COO", filename="P1_gui_COO_CP0_InputSpec_v001.md",
    )
    assert res.doc_type == DocumentType.PRODUCT_CP0_INPUT_SPEC


def test_heading_cp0_feasibility_note():
    res = classify_document(
        content_v2={"doc_type": None, "loai": None, "phase": None},
        heading_line="## CP0 FEASIBILITY NOTE",
        from_role="ENGINEERING", to_role="COO", filename="E1_gui_COO_CP0_FeasibilityNote_v001.md",
    )
    assert res.doc_type == DocumentType.ENGINEERING_CP0_FEASIBILITY
