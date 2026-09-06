"""Tests for review folder fallback routing (AC4, AC8)."""

from __future__ import annotations

from pathlib import Path

from app.models import Action, ParsedMetadata, ReviewReason
from app.mover import move_safe
from app.router import decide
from tests.conftest import write_md
from app import parser as parser_mod


def _process(path: Path, config):
    meta = parser_mod.parse(path, config)
    decision = decide(meta, path.name, config)
    if decision.destination_path is not None:
        move_safe(path, decision.destination_path, dry_run=False)
    return decision


def test_missing_pod_routes_to_review_subfolder(tmp_path: Path, config):
    f = write_md(config.watch_folder / "missing_pod.md",
                 project="DEMO", from_role="COO", to_role="CEO")
    decision = _process(f, config)
    assert decision.action == Action.REVIEW
    expected = config.review_folder / ReviewReason.MISSING_POD.value / "missing_pod.md"
    assert expected.exists(), f"File not routed to {expected}"


def test_missing_project_routes_to_review(tmp_path: Path, config):
    f = write_md(config.watch_folder / "no_proj.md",
                 pod="POD_UNKNOWN", from_role="COO", to_role="CEO")
    decision = _process(f, config)
    assert decision.action == Action.REVIEW
    expected = config.review_folder / ReviewReason.MISSING_PROJECT.value / "no_proj.md"
    assert expected.exists()


def test_missing_role_routes_to_review(tmp_path: Path, config):
    f = write_md(config.watch_folder / "no_role.md",
                 project="DEMO", pod="POD_CORE", from_role="COO", to_role="ALIEN")
    decision = _process(f, config)
    assert decision.action == Action.REVIEW
    expected = config.review_folder / ReviewReason.MISSING_ROLE.value / "no_role.md"
    assert expected.exists()


def test_ambiguous_content_filename_conflict(tmp_path: Path, config):
    """AC12: content says POD_CORE, filename says POD_FLOW -> AMBIGUOUS."""
    path = config.watch_folder / "DEMO__POD_FLOW__COO_gui_CEO.md"
    path.write_text(
        "Project: DEMO\nPod: POD_CORE\nTừ: COO\nGửi: CEO\n", encoding="utf-8")
    decision = _process(path, config)
    assert decision.action == Action.REVIEW
    expected = config.review_folder / ReviewReason.AMBIGUOUS.value / path.name
    assert expected.exists()


def test_review_preserves_original_filename(tmp_path: Path, config):
    """Per plan §6.1: review folder keeps original filename."""
    f = write_md(config.watch_folder / "weird_name_123.md",
                 project="DEMO", from_role="COO", to_role="CEO")  # missing pod
    decision = _process(f, config)
    expected = config.review_folder / ReviewReason.MISSING_POD.value / "weird_name_123.md"
    assert expected.exists()
    assert decision.new_filename == "weird_name_123.md"


def test_valid_routes_to_inbox_not_review(tmp_path: Path, config):
    """AC2/AC3: valid metadata -> project/pod/inbox, NOT review.

    Uses a non-critical (from,to) pair so UNKNOWN_DOC is not escalated by the
    v2 critical-flow whitelist (plan §5.3.1).
    """
    f = write_md(config.watch_folder / "valid.md",
                 project="DEMO", pod="POD_CORE",
                 from_role="PRODUCT", to_role="ENGINEERING")
    decision = _process(f, config)
    assert decision.action == Action.MOVED
    dest = (
        config.projects["DEMO"].root / "POD_CORE" / "ENGINEERING_INBOX"
        / "DEMO__UNKNOWN_PHASE__POD_CORE__UNKNOWN_DOC__PRODUCT_gui_ENGINEERING.md"
    )
    assert dest.exists()
    assert not (config.review_folder / ReviewReason.MISSING_POD.value / "valid.md").exists()
