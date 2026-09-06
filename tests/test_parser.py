"""Tests for app/parser.py — covers AC9, AC12 and content/filename merge rules."""

from __future__ import annotations

from pathlib import Path

import pytest

from app import parser as parser_mod
from app.models import AmbiguityCause
from tests.conftest import write_md


def test_content_full_vn_keys(tmp_path: Path, config):
    f = write_md(tmp_path / "foo.md",
                 project="DEMO", pod="POD_CORE", from_role="COO", to_role="CEO")
    meta = parser_mod.parse(f, config)
    assert meta.project == "DEMO"
    assert meta.pod == "POD_CORE"
    assert meta.from_role == "COO"
    assert meta.to_role == "CEO"
    assert meta.source_of_metadata == "content"
    assert meta.ambiguity_cause is None
    assert meta.reason == "ok"


def test_content_full_en_keys(tmp_path: Path, config):
    p = tmp_path / "en.md"
    p.write_text(
        "Project: DEMO\nPod: POD_CORE\nFrom: COO\nTo: CEO\n", encoding="utf-8")
    meta = parser_mod.parse(p, config)
    assert meta.is_complete()
    assert meta.source_of_metadata == "content"


def test_content_case_insensitive_key(tmp_path: Path, config):
    p = tmp_path / "case.md"
    p.write_text(
        "project: DEMO\nPOD: POD_CORE\nfROM: COO\nTO: CEO\n", encoding="utf-8")
    meta = parser_mod.parse(p, config)
    assert meta.is_complete()


def test_content_missing_pod(tmp_path: Path, config):
    f = write_md(tmp_path / "no_pod.md",
                 project="DEMO", from_role="COO", to_role="CEO")
    meta = parser_mod.parse(f, config)
    assert meta.pod is None
    assert not meta.is_complete()


def test_content_missing_project(tmp_path: Path, config):
    f = write_md(tmp_path / "no_proj.md",
                 pod="POD_CORE", from_role="COO", to_role="CEO")
    meta = parser_mod.parse(f, config)
    assert meta.project is None


def test_content_missing_to(tmp_path: Path, config):
    f = write_md(tmp_path / "no_to.md",
                 project="DEMO", pod="POD_CORE", from_role="COO")
    meta = parser_mod.parse(f, config)
    assert meta.to_role is None


def test_filename_only_md(tmp_path: Path, config):
    p = tmp_path / "DEMO__POD_CORE__COO_gui_CEO.md"
    p.write_text("random body without metadata header", encoding="utf-8")
    meta = parser_mod.parse(p, config)
    assert meta.project == "DEMO"
    assert meta.pod == "POD_CORE"
    assert meta.from_role == "COO"
    assert meta.to_role == "CEO"
    assert meta.source_of_metadata == "filename"


def test_filename_only_txt(tmp_path: Path, config):
    p = tmp_path / "DEMO__POD_FLOW__PRODUCT_gui_ENGINEERING.txt"
    p.write_text("no metadata here", encoding="utf-8")
    meta = parser_mod.parse(p, config)
    assert meta.is_complete()
    assert meta.source_of_metadata == "filename"


def test_pdf_not_parsed_even_with_plaintext_header(tmp_path: Path, config):
    """AC9 (L1): .pdf must NOT attempt content parse; filename is the only source."""
    p = tmp_path / "DEMO__POD_CORE__COO_gui_CEO.pdf"
    # Write fake header that LOOKS like plaintext metadata — parser must ignore.
    p.write_bytes(b"Project: HACKED\nPod: FAKE\nFrom: X\nTo: Y\n%PDF-1.4 garbage")
    meta = parser_mod.parse(p, config)
    assert meta.project == "DEMO"  # from filename, NOT from fake header
    assert meta.pod == "POD_CORE"
    assert meta.source_of_metadata == "filename"


def test_docx_filename_only(tmp_path: Path, config):
    p = tmp_path / "DEMO_HEALTH__POD_PORTAL__PRODUCT_gui_ENGINEERING.docx"
    p.write_bytes(b"PK\x03\x04 fake docx bytes")
    meta = parser_mod.parse(p, config)
    assert meta.project == "DEMO_HEALTH"
    assert meta.source_of_metadata == "filename"


def test_content_and_filename_same(tmp_path: Path, config):
    """Case A, no conflict -> source=both."""
    p = tmp_path / "DEMO__POD_CORE__COO_gui_CEO.md"
    p.write_text(
        "Project: DEMO\nPod: POD_CORE\nTừ: COO\nGửi: CEO\n", encoding="utf-8")
    meta = parser_mod.parse(p, config)
    assert meta.source_of_metadata == "both"
    assert meta.ambiguity_cause is None


def test_content_and_filename_conflict(tmp_path: Path, config):
    """AC12 / L4: content and filename both complete but disagree -> AMBIGUOUS."""
    p = tmp_path / "DEMO__POD_FLOW__COO_gui_CEO.md"
    p.write_text(
        "Project: DEMO\nPod: POD_CORE\nTừ: COO\nGửi: CEO\n", encoding="utf-8")
    meta = parser_mod.parse(p, config)
    assert meta.ambiguity_cause == AmbiguityCause.CONTENT_FILENAME_CONFLICT
    assert "CONTENT_FILENAME_CONFLICT" in meta.reason
    assert meta.source_of_metadata == "conflict"


def test_content_partial_filename_fills(tmp_path: Path, config):
    """Content has pod only; filename fills project + roles. Not a conflict."""
    p = tmp_path / "DEMO__POD_CORE__COO_gui_CEO.md"
    p.write_text("Pod: POD_CORE\n", encoding="utf-8")
    meta = parser_mod.parse(p, config)
    assert meta.is_complete()
    assert meta.source_of_metadata in ("content+filename", "filename")


def test_content_empty_file(tmp_path: Path, config):
    p = tmp_path / "random_name.md"
    p.write_text("", encoding="utf-8")
    meta = parser_mod.parse(p, config)
    assert meta.source_of_metadata == "none"
    assert not meta.is_complete()


def test_filename_tolerant_pod_only(tmp_path: Path, config):
    p = tmp_path / "POD_CORE__COO_gui_CEO.md"
    p.write_text("", encoding="utf-8")
    meta = parser_mod.parse(p, config)
    assert meta.pod == "POD_CORE"
    assert meta.from_role == "COO"
    assert meta.to_role == "CEO"
    assert meta.project is None  # tolerant has no project


def test_pod_cross_project_decorator_stripped(tmp_path: Path, config):
    """Pod: (cross-project — không thuộc pod cụ thể) → raw pod = 'cross-project'.
    Sau _norm() sẽ thành 'CROSS-PROJECT' để khớp whitelist."""
    p = tmp_path / "anchor_ack.md"
    p.write_text(
        "Project: DEMO\n"
        "Pod: (cross-project — không thuộc pod cụ thể)\n"
        "Từ: COO\nGửi: CEO\n",
        encoding="utf-8",
    )
    raw = parser_mod.parse_content(p)
    # parse_content trả về raw string (chưa upper); _norm() sẽ upper trong parse()
    assert raw["pod"] == "cross-project"


def test_pod_cp0_annotation_stripped(tmp_path: Path, config):
    """Pod: CP0 — chưa active pod → raw pod = 'CP0' (annotation sau space bị bỏ)."""
    p = tmp_path / "cp0_form.md"
    p.write_text(
        "Project: DEMO\n"
        "Pod: CP0 — chưa active pod\n"
        "Từ: CEO\nGửi: COO\n",
        encoding="utf-8",
    )
    raw = parser_mod.parse_content(p)
    assert raw["pod"] == "CP0"


def test_pod_placeholder_yields_none(tmp_path: Path, config):
    """Pod: [điền tên pod] → pod = None vì placeholder bắt đầu bằng '[' không match regex."""
    p = tmp_path / "template_form.md"
    p.write_text(
        "Project: DEMO\n"
        "Pod: [điền tên pod]\n"
        "Từ: CEO\nGửi: COO\n",
        encoding="utf-8",
    )
    raw = parser_mod.parse_content(p)
    assert raw["pod"] is None
