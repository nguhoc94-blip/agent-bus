"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.defaults import (  # noqa: E402
    DEFAULT_CRITICAL_DOC_TYPES,
    DEFAULT_DOC_TYPE_ALIASES,
    DEFAULT_HEADING_MAP,
    DEFAULT_MIRROR_DOC_TYPES,
    DEFAULT_PHASE_ALIASES,
    DEFAULT_ROLE_ALIASES,
)
from app.models import AppConfig, ProjectConfig  # noqa: E402


@pytest.fixture
def DEMO_projects(tmp_path: Path) -> Dict[str, ProjectConfig]:
    DEMO_root = tmp_path / "AgentCompany" / "DEMO"
    fd_root = tmp_path / "AgentCompany" / "DEMO_HEALTH"
    DEMO_root.mkdir(parents=True, exist_ok=True)
    fd_root.mkdir(parents=True, exist_ok=True)
    return {
        "DEMO": ProjectConfig(
            name="DEMO",
            root=DEMO_root,
            pods=["POD_CORE", "POD_FLOW", "POD_GROWTH"],
            project_code="DEMO",
            display_name="DEMO",
        ),
        "DEMO_HEALTH": ProjectConfig(
            name="DEMO_HEALTH",
            root=fd_root,
            pods=["POD_PORTAL", "POD_BACKEND"],
            project_code="DEMO_HEALTH",
            display_name="DEMO_HEALTH",
        ),
    }


@pytest.fixture
def config(tmp_path: Path, DEMO_projects) -> AppConfig:
    watch = tmp_path / "Downloads"
    watch.mkdir(parents=True, exist_ok=True)
    review = tmp_path / "AgentCompany" / "REVIEW_MANUAL"
    review.mkdir(parents=True, exist_ok=True)
    logs = tmp_path / "AgentCompany" / "_logs"
    logs.mkdir(parents=True, exist_ok=True)
    return AppConfig(
        watch_folder=watch,
        allowed_extensions=[".md", ".txt", ".pdf", ".docx"],
        temporary_extensions=[".crdownload", ".part", ".tmp", ".download", ".partial"],
        review_folder=review,
        log_folder=logs,
        projects=DEMO_projects,
        roles=["CEO", "COO", "PRODUCT", "ENGINEERING", "REPORTER", "QA", "DEPUTY"],
        inbox_suffix="_INBOX",
        duplicate_strategy="overwrite",
        dry_run=False,
        scan_stable_seconds=1,
        scan_stable_checks=2,
        max_lock_retries=2,
        lock_retry_delay_s=0.05,
        reporter_hub_name="_REPORTER_HUB",
        mirror_doc_types=list(DEFAULT_MIRROR_DOC_TYPES),
        critical_doc_types=list(DEFAULT_CRITICAL_DOC_TYPES),
        role_aliases=dict(DEFAULT_ROLE_ALIASES),
        phase_aliases=dict(DEFAULT_PHASE_ALIASES),
        doc_type_aliases=dict(DEFAULT_DOC_TYPE_ALIASES),
        heading_map=dict(DEFAULT_HEADING_MAP),
    )


@pytest.fixture
def config_overlapping_pod(tmp_path: Path) -> AppConfig:
    """Config where POD_SHARED appears in 2 projects -> ambiguity trigger."""
    t1_root = tmp_path / "P1"
    t2_root = tmp_path / "P2"
    t1_root.mkdir(parents=True, exist_ok=True)
    t2_root.mkdir(parents=True, exist_ok=True)
    watch = tmp_path / "dl"; watch.mkdir(exist_ok=True)
    rev = tmp_path / "rev"; rev.mkdir(exist_ok=True)
    logs = tmp_path / "logs"; logs.mkdir(exist_ok=True)
    return AppConfig(
        watch_folder=watch,
        allowed_extensions=[".md", ".txt"],
        temporary_extensions=[".crdownload"],
        review_folder=rev,
        log_folder=logs,
        projects={
            "ALPHA": ProjectConfig(
                name="ALPHA", root=t1_root, pods=["POD_SHARED", "POD_A"],
                project_code="ALPHA", display_name="ALPHA",
            ),
            "BETA":  ProjectConfig(
                name="BETA",  root=t2_root, pods=["POD_SHARED", "POD_B"],
                project_code="BETA", display_name="BETA",
            ),
        },
        roles=["CEO", "COO"],
        scan_stable_checks=2,
        scan_stable_seconds=1,
        max_lock_retries=1,
        lock_retry_delay_s=0.01,
        role_aliases=dict(DEFAULT_ROLE_ALIASES),
        phase_aliases=dict(DEFAULT_PHASE_ALIASES),
        doc_type_aliases=dict(DEFAULT_DOC_TYPE_ALIASES),
        heading_map=dict(DEFAULT_HEADING_MAP),
    )


def write_md(path: Path, project=None, pod=None, from_role=None, to_role=None,
             body: str = "", phase=None, doc_type=None, loai=None) -> Path:
    """Helper to write a markdown file with optional v2 fields."""
    lines = []
    if project:
        lines.append(f"Project: {project}")
    if pod:
        lines.append(f"Pod: {pod}")
    if from_role:
        lines.append(f"Từ: {from_role}")
    if to_role:
        lines.append(f"Gửi: {to_role}")
    if phase:
        lines.append(f"Phase: {phase}")
    if doc_type:
        lines.append(f"DocType: {doc_type}")
    if loai:
        lines.append(f"Loại: {loai}")
    lines.append("")
    lines.append(body)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
