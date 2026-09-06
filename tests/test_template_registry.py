"""Tests for app/template_registry.py (plan §13)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.defaults import DEFAULT_DOC_TYPE_ALIASES, DEFAULT_HEADING_MAP
from app.models import AppConfig, ProjectConfig
from app.template_registry import (
    RegistryDriftError,
    get_doc_type_aliases_from_registry,
    get_heading_map_from_registry,
    load_registry,
    validate_template_contract_consistency,
)


def _tiny_config(
    *, heading_map=None, doc_type_aliases=None, tmp_path: Path = None,
) -> AppConfig:
    root = (tmp_path or Path("/tmp")) / "p"
    root.mkdir(parents=True, exist_ok=True)
    return AppConfig(
        watch_folder=root / "dl",
        allowed_extensions=[".md"],
        temporary_extensions=[],
        review_folder=root / "rev",
        log_folder=root / "log",
        projects={"FOO": ProjectConfig(name="FOO", root=root, pods=["POD_X"], project_code="FOO")},
        roles=["CEO"],
        heading_map=heading_map if heading_map is not None else dict(DEFAULT_HEADING_MAP),
        doc_type_aliases=doc_type_aliases if doc_type_aliases is not None else dict(DEFAULT_DOC_TYPE_ALIASES),
    )


def _write_registry(path: Path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"entries": entries}), encoding="utf-8")


def test_registry_schema_validates_all_required_fields(tmp_path: Path):
    p = tmp_path / "reg.json"
    _write_registry(p, [
        {
            "template_path": "x.md",
            "company_type": "job_trung_binh",
            "contract_source": "heading",
            "doc_type": "CEO_BRIEF",
            "heading_exact": "## CEO BRIEF",
            "status": "active",
        }
    ])
    entries = load_registry(p)
    assert len(entries) == 1
    assert entries[0].doc_type == "CEO_BRIEF"


def test_registry_drift_heading_missing_in_config_raises(tmp_path: Path):
    p = tmp_path / "reg.json"
    _write_registry(p, [
        {
            "template_path": "x.md",
            "company_type": "job_trung_binh",
            "contract_source": "heading",
            "doc_type": "CEO_BRIEF",
            "heading_exact": "## SOMETHING BRAND NEW",
            "status": "active",
        }
    ])
    entries = load_registry(p)
    cfg = _tiny_config(tmp_path=tmp_path)
    with pytest.raises(RegistryDriftError):
        validate_template_contract_consistency(cfg, entries)


def test_registry_drift_loai_missing_in_config_raises(tmp_path: Path):
    p = tmp_path / "reg.json"
    _write_registry(p, [
        {
            "template_path": "x.md",
            "company_type": "job_trung_binh",
            "contract_source": "loai",
            "doc_type": "CEO_BRIEF",
            "doc_type_alias_values": ["totally-new-loai"],
            "status": "active",
        }
    ])
    entries = load_registry(p)
    cfg = _tiny_config(tmp_path=tmp_path)
    with pytest.raises(RegistryDriftError):
        validate_template_contract_consistency(cfg, entries)


def test_registry_active_critical_without_contract_raises(tmp_path: Path):
    """Self-inconsistent entry: contract_source=heading but heading_exact empty."""
    p = tmp_path / "reg.json"
    _write_registry(p, [
        {
            "template_path": "x.md",
            "company_type": "job_trung_binh",
            "contract_source": "heading",
            "doc_type": "CEO_BRIEF",
            "heading_exact": "",
            "status": "active",
            "importance_default": "CRITICAL",
        }
    ])
    entries = load_registry(p)
    cfg = _tiny_config(tmp_path=tmp_path)
    with pytest.raises(RegistryDriftError):
        validate_template_contract_consistency(cfg, entries)


def test_registry_deprecated_entry_skipped_in_validation(tmp_path: Path):
    """Drift on a deprecated entry must NOT raise."""
    p = tmp_path / "reg.json"
    _write_registry(p, [
        {
            "template_path": "x.md",
            "company_type": "job_trung_binh",
            "contract_source": "heading",
            "doc_type": "CEO_BRIEF",
            "heading_exact": "## GONE FOREVER",
            "status": "deprecated",
        }
    ])
    entries = load_registry(p)
    cfg = _tiny_config(tmp_path=tmp_path)
    # Should NOT raise.
    validate_template_contract_consistency(cfg, entries)


def test_registry_explicit_doctype_exempt_from_map_checks(tmp_path: Path):
    """contract_source=explicit_doctype entries must not require heading_map
    or doc_type_aliases entries."""
    p = tmp_path / "reg.json"
    _write_registry(p, [
        {
            "template_path": "x.md",
            "company_type": "job_trung_binh",
            "contract_source": "explicit_doctype",
            "doc_type": "CEO_BRIEF",
            "has_explicit_doctype_field": True,
            "status": "active",
        }
    ])
    entries = load_registry(p)
    cfg = _tiny_config(
        heading_map={}, doc_type_aliases={}, tmp_path=tmp_path,
    )
    validate_template_contract_consistency(cfg, entries)


def test_registry_build_heading_map(tmp_path: Path):
    p = tmp_path / "reg.json"
    _write_registry(p, [
        {
            "template_path": "x.md",
            "company_type": "job_trung_binh",
            "contract_source": "heading",
            "doc_type": "CEO_BRIEF",
            "heading_exact": "## CEO BRIEF",
            "status": "active",
        },
        {
            "template_path": "y.md",
            "company_type": "job_trung_binh",
            "contract_source": "heading",
            "doc_type": "QA_REPORT",
            "heading_exact": "## OLD REPORT",
            "status": "deprecated",
        },
    ])
    entries = load_registry(p)
    m = get_heading_map_from_registry(entries)
    # Only active entries included.
    assert m == {"## CEO BRIEF": "CEO_BRIEF"}


def test_registry_does_not_override_doctype_precedence(tmp_path: Path, config):
    """Runtime precedence test (AC17): registry is NOT consulted at runtime."""
    from app import parser as parser_mod
    p = tmp_path / "DEMO__PHASE_1__POD_CORE__CEO_BRIEF__CEO_gui_COO.md"
    # Even if registry had some weird mapping, the runtime classifier must
    # prioritize the DocType field.
    p.write_text(
        "Project: DEMO\nPod: POD_CORE\nTừ: CEO\nGửi: COO\nDocType: CEO_BRIEF\n"
        "\n## QA REPORT\n",
        encoding="utf-8",
    )
    meta = parser_mod.parse(p, config)
    from app.models import DocumentType
    assert meta.doc_type == DocumentType.CEO_BRIEF  # DocType field wins


def test_registry_bundled_snapshot_passes_with_defaults(tmp_path: Path):
    """The shipped config/template_registry.json must not drift vs defaults."""
    repo_root = Path(__file__).resolve().parent.parent
    snapshot = repo_root / "config" / "template_registry.json"
    if not snapshot.exists():  # pragma: no cover — defensive
        pytest.skip("bundled registry not present")
    entries = load_registry(snapshot)
    cfg = _tiny_config(tmp_path=tmp_path)
    validate_template_contract_consistency(cfg, entries)


def test_registry_get_doc_type_aliases(tmp_path: Path):
    p = tmp_path / "reg.json"
    _write_registry(p, [
        {
            "template_path": "x.md",
            "company_type": "job_trung_binh",
            "contract_source": "loai",
            "doc_type": "COO_PRE_BRIEF_BASIS",
            "doc_type_alias_values": ["pre-brief-basis"],
            "status": "active",
        }
    ])
    entries = load_registry(p)
    m = get_doc_type_aliases_from_registry(entries)
    assert m == {"pre-brief-basis": "COO_PRE_BRIEF_BASIS"}


# ---------------------------------------------------------------------------
# Anti Down-Scope Guardrail v1 (REV D 2026-05) — REGRESSION TESTS
# 4 test below ensure SCOPE_CHANGE_ACK + QA_LIMIT_1 plumbing is wired through:
# (1) DocumentType enum, (2) DEFAULT_HEADING_MAP, (3) CRITICAL_FLOW_WHITELIST,
# (4) bundled config/template_registry.json has all 4 entries.
# ---------------------------------------------------------------------------


def test_anti_downscope_doctypes_in_enum():
    """SCOPE_CHANGE_ACK + QA_LIMIT_1 phải tồn tại trong DocumentType enum."""
    from app.models import DocumentType
    assert DocumentType.SCOPE_CHANGE_ACK.value == "SCOPE_CHANGE_ACK"
    assert DocumentType.QA_LIMIT_1.value == "QA_LIMIT_1"


def test_anti_downscope_headings_in_default_map():
    """DEFAULT_HEADING_MAP phải chứa heading mới cho 2 form ack."""
    from app.defaults import DEFAULT_HEADING_MAP
    from app.models import DocumentType
    assert DEFAULT_HEADING_MAP["SCOPE CHANGE ACK"] == DocumentType.SCOPE_CHANGE_ACK.value
    assert DEFAULT_HEADING_MAP["QA LIMIT FORM"] == DocumentType.QA_LIMIT_1.value


def test_anti_downscope_critical_flow_whitelist():
    """Tuyến QA→CEO phải có trong CRITICAL_FLOW_WHITELIST.

    Lưu ý: whitelist chỉ apply cho UNKNOWN_DOC. Enforcement thật cho QA→CEO
    (chỉ hợp lệ khi doc_type=QA_LIMIT_1) nằm trong app/router.py — xem
    test_router.test_qa_to_ceo_allowed_only_for_qa_limit_1.
    """
    from app.defaults import CRITICAL_FLOW_WHITELIST
    assert ("QA", "CEO") in CRITICAL_FLOW_WHITELIST


def test_anti_downscope_registry_entries_present(tmp_path: Path):
    """config/template_registry.json phải có đủ 4 entry mới:
    Job TB ScopeChangeAck + Job TB QALimit1 + Job To ScopeChangeAck + Job To QALimit1.

    Lý do: 3 test enum/heading/flow phía trên vẫn pass nếu quên cập nhật registry
    JSON. Test này chặn tình trạng patch code mà quên patch registry → bot có
    DocumentType nhưng không có template tham chiếu.
    """
    repo_root = Path(__file__).resolve().parent.parent
    snapshot = repo_root / "config" / "template_registry.json"
    if not snapshot.exists():  # pragma: no cover — defensive
        pytest.skip("bundled registry not present")
    entries = load_registry(snapshot)

    # Group by (company_type, doc_type) for assertion.
    keys = {(e.company_type, e.doc_type) for e in entries if e.status == "active"}

    expected = {
        ("job_trung_binh", "SCOPE_CHANGE_ACK"),
        ("job_trung_binh", "QA_LIMIT_1"),
        ("job_sieu_to", "SCOPE_CHANGE_ACK"),
        ("job_sieu_to", "QA_LIMIT_1"),
    }
    missing = expected - keys
    assert not missing, (
        f"Registry thiếu {len(missing)} entry anti-downscope: "
        f"{sorted(missing)}. Cần cập nhật config/template_registry.json."
    )

    # Verify heading_exact đúng cho từng entry — chống registry drift.
    by_key = {(e.company_type, e.doc_type): e for e in entries if e.status == "active"}
    assert by_key[("job_trung_binh", "SCOPE_CHANGE_ACK")].heading_exact == "## SCOPE CHANGE ACK"
    assert by_key[("job_trung_binh", "QA_LIMIT_1")].heading_exact == "## QA LIMIT FORM"
    assert by_key[("job_sieu_to", "SCOPE_CHANGE_ACK")].heading_exact == "## SCOPE CHANGE ACK"
    assert by_key[("job_sieu_to", "QA_LIMIT_1")].heading_exact == "## QA LIMIT FORM"

    # Verify routing default đúng (QA_LIMIT_1 = QA→CEO direct; SCOPE_CHANGE_ACK = COO→CEO).
    assert by_key[("job_trung_binh", "QA_LIMIT_1")].from_role_default == "QA"
    assert by_key[("job_trung_binh", "QA_LIMIT_1")].to_role_default == "CEO"
    assert by_key[("job_sieu_to", "QA_LIMIT_1")].from_role_default == "QA"
    assert by_key[("job_sieu_to", "QA_LIMIT_1")].to_role_default == "CEO"
    assert by_key[("job_trung_binh", "SCOPE_CHANGE_ACK")].from_role_default == "COO"
    assert by_key[("job_trung_binh", "SCOPE_CHANGE_ACK")].to_role_default == "CEO"
    assert by_key[("job_sieu_to", "SCOPE_CHANGE_ACK")].from_role_default == "COO"
    assert by_key[("job_sieu_to", "SCOPE_CHANGE_ACK")].to_role_default == "CEO"
