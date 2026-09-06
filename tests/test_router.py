"""Tests for app/router.py — routing decisions and ambiguity triggers."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.models import (
    Action, AmbiguityCause, AppConfig, ParsedMetadata, ProjectConfig, ReviewReason,
)
from app.router import decide


def _meta(**kwargs) -> ParsedMetadata:
    defaults = {
        "project": "DEMO", "pod": "POD_CORE",
        "from_role": "PRODUCT", "to_role": "ENGINEERING",
        "source_of_metadata": "content", "confidence": 1.0, "reason": "ok",
    }
    defaults.update(kwargs)
    return ParsedMetadata(**defaults)


def test_happy_path(config):
    d = decide(_meta(), "DEMO__POD_CORE__PRODUCT_gui_ENGINEERING.md", config)
    assert d.action == Action.MOVED
    assert d.new_filename == (
        "DEMO__UNKNOWN_PHASE__POD_CORE__UNKNOWN_DOC__PRODUCT_gui_ENGINEERING.md"
    )
    assert d.destination_path is not None
    assert d.destination_path.parent.name == "ENGINEERING_INBOX"
    assert d.destination_path.parent.parent.name == "POD_CORE"
    assert d.destination_path.parent.parent.parent.name == "DEMO"


def test_missing_project(config):
    """Both project and pod missing -> MISSING_PROJECT (no inference possible)."""
    d = decide(_meta(project=None, pod=None), "random.md", config)
    assert d.action == Action.REVIEW
    assert ReviewReason.MISSING_PROJECT.value in str(d.destination_path)


def test_unknown_project(config):
    d = decide(_meta(project="GHOST"), "random.md", config)
    assert d.action == Action.REVIEW
    assert ReviewReason.MISSING_PROJECT.value in str(d.destination_path)
    assert "GHOST" in d.reason


def test_missing_pod(config):
    d = decide(_meta(pod=None), "random.md", config)
    assert d.action == Action.REVIEW
    assert ReviewReason.MISSING_POD.value in str(d.destination_path)


def test_pod_not_in_project(config):
    d = decide(_meta(pod="POD_PORTAL"), "random.md", config)  # POD_PORTAL belongs to DEMO_HEALTH
    assert d.action == Action.REVIEW
    assert ReviewReason.MISSING_POD.value in str(d.destination_path)


def test_missing_to_role(config):
    d = decide(_meta(to_role=None), "random.md", config)
    assert d.action == Action.REVIEW
    assert ReviewReason.MISSING_ROLE.value in str(d.destination_path)


def test_unknown_role(config):
    d = decide(_meta(to_role="HACKER"), "random.md", config)
    assert d.action == Action.REVIEW
    assert ReviewReason.MISSING_ROLE.value in str(d.destination_path)


def test_ambiguity_from_parser(config):
    m = _meta(ambiguity_cause=AmbiguityCause.CONTENT_FILENAME_CONFLICT,
              reason="AMBIGUOUS:CONTENT_FILENAME_CONFLICT")
    d = decide(m, "foo.md", config)
    assert d.action == Action.REVIEW
    assert ReviewReason.AMBIGUOUS.value in str(d.destination_path)
    assert "CONTENT_FILENAME_CONFLICT" in d.reason


def test_pod_in_multi_project_ambiguous(config_overlapping_pod):
    """Pod declared without project, and pod belongs to 2 projects -> AMBIGUOUS."""
    m = ParsedMetadata(
        project=None, pod="POD_SHARED", from_role="COO", to_role="CEO",
        source_of_metadata="filename", reason="",
    )
    d = decide(m, "POD_SHARED__COO_gui_CEO.md", config_overlapping_pod)
    assert d.action == Action.REVIEW
    assert ReviewReason.AMBIGUOUS.value in str(d.destination_path)
    assert AmbiguityCause.POD_IN_MULTI_PROJECT.value in d.reason


def test_pod_in_single_project_inferred(config):
    """Pod declared without project, single-owner pod -> infer project deterministically."""
    m = ParsedMetadata(
        project=None, pod="POD_CORE", from_role="PRODUCT", to_role="ENGINEERING",
        source_of_metadata="filename", reason="",
    )
    d = decide(m, "POD_CORE__PRODUCT_gui_ENGINEERING.md", config)
    assert d.action == Action.MOVED
    assert d.new_filename == (
        "DEMO__UNKNOWN_PHASE__POD_CORE__UNKNOWN_DOC__PRODUCT_gui_ENGINEERING.md"
    )


def test_destination_path_uses_project_root(config):
    d = decide(_meta(), "foo.md", config)
    assert d.destination_path is not None
    assert str(config.projects["DEMO"].root) in str(d.destination_path)


# ---------------------------------------------------------------------------
# dynamic_pod_pattern tests
# ---------------------------------------------------------------------------

@pytest.fixture
def config_with_dynamic_pod(tmp_path: Path) -> AppConfig:
    """Config with a project that accepts dynamic pods matching ^[PE]\\d+(_\\w+)*$."""
    proj_root = tmp_path / "BIG_PROJECT"
    proj_root.mkdir(parents=True, exist_ok=True)
    watch = tmp_path / "dl"; watch.mkdir(exist_ok=True)
    rev = tmp_path / "rev"; rev.mkdir(exist_ok=True)
    logs = tmp_path / "logs"; logs.mkdir(exist_ok=True)
    from app.defaults import (
        DEFAULT_DOC_TYPE_ALIASES, DEFAULT_HEADING_MAP,
        DEFAULT_PHASE_ALIASES, DEFAULT_ROLE_ALIASES,
    )
    return AppConfig(
        watch_folder=watch,
        allowed_extensions=[".md"],
        temporary_extensions=[".crdownload"],
        review_folder=rev,
        log_folder=logs,
        projects={
            "BIG": ProjectConfig(
                name="BIG", root=proj_root,
                pods=["POD_CORE", "POD_FLOW", "CP0"],
                project_code="BIG",
                display_name="BIG",
                dynamic_pod_pattern=r"^[PE]\d+(_[A-Za-z0-9]+)*$",
            ),
        },
        roles=["CEO", "COO", "PRODUCT", "ENGINEERING"],
        scan_stable_checks=2, scan_stable_seconds=1,
        max_lock_retries=1, lock_retry_delay_s=0.01,
        # Disable critical/mirror checks so UNKNOWN_DOC is not flagged
        critical_doc_types=[],
        mirror_doc_types=[],
        role_aliases=DEFAULT_ROLE_ALIASES,
        phase_aliases=DEFAULT_PHASE_ALIASES,
        doc_type_aliases=DEFAULT_DOC_TYPE_ALIASES,
        heading_map=DEFAULT_HEADING_MAP,
    )


def test_dynamic_pod_pattern_matches_are_routed(config_with_dynamic_pod):
    """P1_Product and E1_Backend match dynamic pattern -> MOVED.

    Uses PRODUCT->ENGINEERING (not in CRITICAL_FLOW_WHITELIST) to avoid the
    UNKNOWN_DOC_IN_CRITICAL_FLOW ambiguity guard.
    """
    for pod in ("P1_Product", "E1_Backend", "P2", "E3_Feature_X"):
        m = ParsedMetadata(
            project="BIG", pod=pod,
            from_role="PRODUCT", to_role="ENGINEERING",
            source_of_metadata="content", confidence=1.0,
        )
        d = decide(m, f"PRODUCT_gui_ENGINEERING_{pod}.md", config_with_dynamic_pod)
        assert d.action == Action.MOVED, (
            f"Expected MOVED for pod={pod!r}, got {d.action}: {d.reason}"
        )


def test_dynamic_pod_pattern_static_pods_still_work(config_with_dynamic_pod):
    """Static pods (CP0, POD_CORE) still pass alongside dynamic pattern."""
    for pod in ("POD_CORE", "POD_FLOW", "CP0"):
        m = ParsedMetadata(
            project="BIG", pod=pod,
            from_role="PRODUCT", to_role="ENGINEERING",
            source_of_metadata="content", confidence=1.0,
        )
        d = decide(m, f"PRODUCT_gui_ENGINEERING_{pod}.md", config_with_dynamic_pod)
        assert d.action == Action.MOVED, (
            f"Expected MOVED for static pod={pod!r}, got {d.action}"
        )


def test_dynamic_pod_pattern_no_match_goes_to_review(config_with_dynamic_pod):
    """Pod that doesn't match pattern AND is not in static list -> MISSING_POD."""
    m = ParsedMetadata(
        project="BIG", pod="GHOST_POD",
        from_role="COO", to_role="ENGINEERING",
        source_of_metadata="content", confidence=1.0,
    )
    d = decide(m, "COO_gui_ENGINEERING_GHOST.md", config_with_dynamic_pod)
    assert d.action == Action.REVIEW
    assert ReviewReason.MISSING_POD.value in str(d.destination_path)
    assert "GHOST_POD" in d.reason


# ---------------------------------------------------------------------------
# ProjectConfig.pod_allowed unit tests
# ---------------------------------------------------------------------------

def test_pod_allowed_static_hit():
    cfg = ProjectConfig(name="X", root=Path("/x"), pods=["POD_CORE"], project_code="X")
    assert cfg.pod_allowed("POD_CORE") is True


def test_pod_allowed_static_miss_no_pattern():
    cfg = ProjectConfig(name="X", root=Path("/x"), pods=["POD_CORE"], project_code="X")
    assert cfg.pod_allowed("E1_Backend") is False


def test_pod_allowed_dynamic_hit():
    cfg = ProjectConfig(
        name="X", root=Path("/x"), pods=["CP0"], project_code="X",
        dynamic_pod_pattern=r"^[PE]\d+(_[A-Za-z0-9]+)*$",
    )
    assert cfg.pod_allowed("P1_Product") is True
    assert cfg.pod_allowed("E2") is True
    assert cfg.pod_allowed("CP0") is True   # static wins too


def test_pod_allowed_dynamic_miss():
    cfg = ProjectConfig(
        name="X", root=Path("/x"), pods=["CP0"], project_code="X",
        dynamic_pod_pattern=r"^[PE]\d+(_[A-Za-z0-9]+)*$",
    )
    assert cfg.pod_allowed("GHOST") is False
    assert cfg.pod_allowed("G1_Growth") is False   # G not in [PE]


# ---------------------------------------------------------------------------
# Config parsing: invalid regex raises ConfigError
# ---------------------------------------------------------------------------

def test_config_rejects_invalid_dynamic_pod_pattern(tmp_path):
    import json
    from app.config import load_config, ConfigError

    bot = {
        "watch_folder": str(tmp_path / "dl"),
        "allowed_extensions": [".md"],
        "temporary_extensions": [],
        "review_folder": str(tmp_path / "rev"),
        "log_folder": str(tmp_path / "logs"),
        "projects": {
            "MYPROJ": {
                "root": str(tmp_path / "proj"),
                "pods": ["POD_A"],
                "dynamic_pod_pattern": "[invalid("   # intentionally broken regex
            }
        },
        "roles": ["CEO"],
    }
    cfg_file = tmp_path / "bot.json"
    cfg_file.write_text(json.dumps(bot), encoding="utf-8")
    (tmp_path / "dl").mkdir(exist_ok=True)
    (tmp_path / "rev").mkdir(exist_ok=True)
    (tmp_path / "logs").mkdir(exist_ok=True)
    (tmp_path / "proj").mkdir(exist_ok=True)

    with pytest.raises(ConfigError, match="dynamic_pod_pattern"):
        load_config(cfg_file)
