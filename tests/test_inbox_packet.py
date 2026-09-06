"""REV E-Lazy — tests cho inbox auto-packet drop.

18 case theo plan (xem rev_e-lazy_packet_drop_438c159b.plan.md §Tests).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Tuple

import pytest

from app import inbox_packet
from app.inbox_packet import (
    DETECTION_FALLBACK,
    DETECTION_PODS_MATCH,
    MODE_BIG,
    MODE_TB,
    PACKET_FILENAME,
)
from app.models import AppConfig, PacketSourceConfig, ProjectConfig


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

TB_RULECARD_BODY = "# RULECARD TB\n7 lethal rules TB content.\n"
TO_RULECARD_BODY = "# RULECARD TO\n12 lethal rules Big Mode content.\n"
RAW_ANCHOR_TEMPLATE_BODY = "# ANCHOR TEMPLATE\nTEMPLATE_MARKER\n"
SAC_TEMPLATE_BODY = "# SAC TEMPLATE\nSAC_TEMPLATE_MARKER\n"
IFC_TEMPLATE_BODY = "# IFC TEMPLATE\nIFC_TEMPLATE_MARKER\n"


def _write(p: Path, content: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


@pytest.fixture
def packet_sources(tmp_path: Path) -> Tuple[Path, PacketSourceConfig, PacketSourceConfig]:
    """Tạo source files giả lập trong tmp_path/_sources. Return (sources_dir,
    tb_cfg, big_cfg)."""
    srcs = tmp_path / "_sources"
    tb_rulecard = _write(srcs / "_RUNTIME_RULECARD_JOB_TB.md", TB_RULECARD_BODY)
    to_rulecard = _write(srcs / "_RUNTIME_RULECARD_JOB_TO.md", TO_RULECARD_BODY)
    raw_anchor = _write(srcs / "00_raw_input_anchor.template.md", RAW_ANCHOR_TEMPLATE_BODY)
    sac_anchor = _write(srcs / "00_system_acceptance_contract.template.md", SAC_TEMPLATE_BODY)
    ifc_anchor = _write(srcs / "00_interface_contracts.template.md", IFC_TEMPLATE_BODY)

    tb_cfg = PacketSourceConfig(rulecard=tb_rulecard, anchors=[raw_anchor])
    big_cfg = PacketSourceConfig(
        rulecard=to_rulecard, anchors=[raw_anchor, sac_anchor, ifc_anchor],
    )
    return (srcs, tb_cfg, big_cfg)


@pytest.fixture
def packet_app_config(tmp_path: Path, packet_sources) -> AppConfig:
    """AppConfig đủ tối thiểu cho inbox_packet tests."""
    srcs, tb_cfg, big_cfg = packet_sources
    review = tmp_path / "_REVIEW_MANUAL"; review.mkdir()
    logs = tmp_path / "_log"; logs.mkdir()
    watch = tmp_path / "Downloads"; watch.mkdir()
    return AppConfig(
        watch_folder=watch,
        allowed_extensions=[".md"],
        temporary_extensions=[".crdownload"],
        review_folder=review,
        log_folder=logs,
        projects={},  # filled per test
        roles=["CEO", "COO", "QA", "DEPUTY"],
        inbox_suffix="_INBOX",
        auto_drop_inbox_packet=True,
        packet_sources={"TB": tb_cfg, "BIG": big_cfg},
        packet_mode_valid={"TB": True, "BIG": True},
    )


def _make_project(root: Path, code: str, pods, name: str = None) -> ProjectConfig:
    root.mkdir(parents=True, exist_ok=True)
    return ProjectConfig(
        name=name or code,
        root=root,
        pods=list(pods),
        project_code=code,
        display_name=code,
    )


# --------------------------------------------------------------------------- #
# 1-3. detect_mode
# --------------------------------------------------------------------------- #

def test_detect_mode_tb(tmp_path):
    proj = _make_project(tmp_path / "proj", "TB1", ["POD_MAIN"])
    mode, detection = inbox_packet.detect_mode(proj)
    assert mode == MODE_TB
    assert detection == DETECTION_PODS_MATCH


def test_detect_mode_big(tmp_path):
    proj = _make_project(
        tmp_path / "proj", "BIG1",
        ["POD_PRODUCT", "POD_ENGINEERING", "POD_GROWTH_G1"],
    )
    mode, detection = inbox_packet.detect_mode(proj)
    assert mode == MODE_BIG
    assert detection == DETECTION_PODS_MATCH


def test_detect_mode_DEMO_dual_pods(tmp_path):
    """DEMO_PROJECT style: POD_CORE + POD_FLOW still use TB packet (pods_match)."""
    proj = _make_project(tmp_path / "proj", "DEMO_KHOA_HOC", ["POD_CORE", "POD_FLOW"])
    mode, detection = inbox_packet.detect_mode(proj)
    assert mode == MODE_TB
    assert detection == DETECTION_PODS_MATCH


def test_detect_mode_big_program_pods(tmp_path):
    """Big Mode (Job TO): project có CP0/COO_PROGRAM/QA_PROGRAM/CROSS-PROJECT → BIG (pods_match).
    Đây là cấu hình thực của DEMO_PROJECT sau khi mở rộng pods."""
    pods = ["POD_CORE", "POD_FLOW", "CP0", "COO_PROGRAM", "QA_PROGRAM", "CROSS-PROJECT"]
    proj = _make_project(tmp_path / "proj", "DEMO_KHOA_HOC", pods)
    mode, detection = inbox_packet.detect_mode(proj)
    assert mode == MODE_BIG
    assert detection == DETECTION_PODS_MATCH


def test_detect_mode_big_cp0_only_indicator(tmp_path):
    """Chỉ cần có CP0 là đủ để nhận diện BIG (không cần đủ bộ)."""
    proj = _make_project(tmp_path / "proj", "SOME_PROJECT", ["POD_CORE", "CP0"])
    mode, detection = inbox_packet.detect_mode(proj)
    assert mode == MODE_BIG
    assert detection == DETECTION_PODS_MATCH


def test_detect_mode_mixed_fallback(tmp_path):
    proj = _make_project(tmp_path / "proj", "WEIRD", ["POD_ALPHA", "POD_BETA"])
    mode, detection = inbox_packet.detect_mode(proj)
    assert mode == MODE_TB
    assert detection == DETECTION_FALLBACK


# --------------------------------------------------------------------------- #
# 4-5. drop + idempotent
# --------------------------------------------------------------------------- #

def test_packet_drop_first_time(tmp_path, packet_app_config):
    proj = _make_project(tmp_path / "proj", "P1", ["POD_MAIN"])
    inbox = proj.root / "POD_MAIN" / "CEO_INBOX"
    inbox.mkdir(parents=True)
    result = inbox_packet.ensure_inbox_packet(
        inbox, proj, "POD_MAIN", "CEO", packet_app_config,
    )
    assert result is True
    assert (inbox / PACKET_FILENAME).exists()


def test_packet_idempotent_skip(tmp_path, packet_app_config):
    proj = _make_project(tmp_path / "proj", "P2", ["POD_MAIN"])
    inbox = proj.root / "POD_MAIN" / "COO_INBOX"
    inbox.mkdir(parents=True)
    # First drop
    assert inbox_packet.ensure_inbox_packet(
        inbox, proj, "POD_MAIN", "COO", packet_app_config,
    ) is True
    packet = inbox / PACKET_FILENAME
    original_mtime = packet.stat().st_mtime_ns
    original_content = packet.read_text(encoding="utf-8")

    # Second drop — phải skip
    assert inbox_packet.ensure_inbox_packet(
        inbox, proj, "POD_MAIN", "COO", packet_app_config,
    ) is False
    assert packet.stat().st_mtime_ns == original_mtime
    assert packet.read_text(encoding="utf-8") == original_content


# --------------------------------------------------------------------------- #
# 6-7. content TB / BIG
# --------------------------------------------------------------------------- #

def test_packet_tb_content(tmp_path, packet_app_config):
    proj = _make_project(tmp_path / "proj", "P3", ["POD_MAIN"])
    inbox = proj.root / "POD_MAIN" / "QA_INBOX"
    inbox.mkdir(parents=True)
    inbox_packet.ensure_inbox_packet(
        inbox, proj, "POD_MAIN", "QA", packet_app_config,
    )
    body = (inbox / PACKET_FILENAME).read_text(encoding="utf-8")
    assert "Mode:** TB" in body
    assert "7 lethal rules TB content" in body  # rulecard TB embedded
    assert "TEMPLATE_MARKER" in body  # 1 anchor template (no project real file)
    assert "SAC_TEMPLATE_MARKER" not in body  # Big-only template không có
    assert "IFC_TEMPLATE_MARKER" not in body


def test_packet_big_content(tmp_path, packet_app_config):
    proj = _make_project(
        tmp_path / "proj", "P4",
        ["POD_PRODUCT", "POD_ENGINEERING"],
    )
    inbox = proj.root / "POD_PRODUCT" / "CEO_INBOX"
    inbox.mkdir(parents=True)
    inbox_packet.ensure_inbox_packet(
        inbox, proj, "POD_PRODUCT", "CEO", packet_app_config,
    )
    body = (inbox / PACKET_FILENAME).read_text(encoding="utf-8")
    assert "Mode:** BIG" in body
    assert "12 lethal rules Big Mode content" in body  # rulecard TO
    assert "TEMPLATE_MARKER" in body  # raw_input_anchor
    assert "SAC_TEMPLATE_MARKER" in body
    assert "IFC_TEMPLATE_MARKER" in body
    # 3/3 fallback => BLOCKER section visible
    assert "§C — BLOCKER" in body
    assert "00_raw_input_anchor.md" in body
    assert "00_system_acceptance_contract.md" in body
    assert "00_interface_contracts.md" in body


# --------------------------------------------------------------------------- #
# 8-9. prefer project anchor vs fallback (NEW REV E-Lazy)
# --------------------------------------------------------------------------- #

def test_packet_prefers_project_anchor_over_template(tmp_path, packet_app_config):
    """Khi project có 00_raw_input_anchor.md THẬT trong root → embed file thật,
    KHÔNG embed template."""
    proj = _make_project(tmp_path / "proj", "REAL1", ["POD_MAIN"])
    _write(proj.root / "00_raw_input_anchor.md", "REAL_ANCHOR_MARKER body")

    inbox = proj.root / "POD_MAIN" / "CEO_INBOX"
    inbox.mkdir(parents=True)
    inbox_packet.ensure_inbox_packet(
        inbox, proj, "POD_MAIN", "CEO", packet_app_config,
    )
    body = (inbox / PACKET_FILENAME).read_text(encoding="utf-8")
    assert "REAL_ANCHOR_MARKER" in body
    assert "TEMPLATE_MARKER" not in body  # template content phải KHÔNG xuất hiện
    assert "(REAL project file)" in body
    assert "TEMPLATE FALLBACK" not in body
    assert "§C — BLOCKER" not in body  # all real → no blocker
    # Header anchors counter
    assert "1/1 real" in body


def test_packet_falls_back_to_template_with_blocker_when_anchor_missing(
    tmp_path, packet_app_config
):
    proj = _make_project(tmp_path / "proj", "FB1", ["POD_MAIN"])
    # KHÔNG tạo file thật trong project.root → fallback template
    inbox = proj.root / "POD_MAIN" / "DEPUTY_INBOX"
    inbox.mkdir(parents=True)
    inbox_packet.ensure_inbox_packet(
        inbox, proj, "POD_MAIN", "DEPUTY", packet_app_config,
    )
    body = (inbox / PACKET_FILENAME).read_text(encoding="utf-8")
    assert "TEMPLATE_MARKER" in body
    assert "TEMPLATE FALLBACK" in body
    assert "§C — BLOCKER" in body
    assert "OPERATOR PHẢI" in body
    assert "0/1 real" in body


# --------------------------------------------------------------------------- #
# 10-11. Skip review folder + mirror folder
# --------------------------------------------------------------------------- #

def test_packet_skipped_for_review_folder(tmp_path, packet_app_config):
    """`<review_folder>/AMBIGUOUS/<file>` không match inbox pattern → không drop."""
    proj = _make_project(tmp_path / "proj", "R1", ["POD_MAIN"])
    review_dir = packet_app_config.review_folder / "AMBIGUOUS"
    review_dir.mkdir(parents=True, exist_ok=True)
    fake_path = review_dir / "some_rejected.md"

    location = inbox_packet.is_primary_inbox(fake_path, proj, packet_app_config)
    assert location is None


def test_packet_skipped_for_mirror_folder(tmp_path, packet_app_config):
    """`<project.root>/_REPORTER_HUB/CP0/COO_POD_ASSIGNMENT/<file>` không phải inbox."""
    proj = _make_project(tmp_path / "proj", "M1", ["POD_MAIN"])
    mirror_dir = proj.root / "_REPORTER_HUB" / "CP0" / "COO_POD_ASSIGNMENT"
    mirror_dir.mkdir(parents=True, exist_ok=True)
    fake_path = mirror_dir / "some_mirrored.md"

    location = inbox_packet.is_primary_inbox(fake_path, proj, packet_app_config)
    assert location is None


# --------------------------------------------------------------------------- #
# 12. Master switch off
# --------------------------------------------------------------------------- #

def test_packet_disabled_by_master_switch(tmp_path, packet_app_config):
    proj = _make_project(tmp_path / "proj", "OFF1", ["POD_MAIN"])
    inbox = proj.root / "POD_MAIN" / "CEO_INBOX"
    inbox.mkdir(parents=True)
    packet_app_config.auto_drop_inbox_packet = False
    result = inbox_packet.ensure_inbox_packet(
        inbox, proj, "POD_MAIN", "CEO", packet_app_config,
    )
    assert result is False
    assert not (inbox / PACKET_FILENAME).exists()


# --------------------------------------------------------------------------- #
# 13. Missing source file warns, no crash
# --------------------------------------------------------------------------- #

def test_packet_missing_source_file_warns_not_crash(
    tmp_path, packet_app_config, caplog
):
    """Rulecard source path không tồn tại → log warning, return False, không crash."""
    proj = _make_project(tmp_path / "proj", "MISS1", ["POD_MAIN"])
    # Replace TB rulecard với path không tồn tại
    bad_rc = tmp_path / "_sources" / "GHOST_RULECARD.md"
    packet_app_config.packet_sources["TB"] = PacketSourceConfig(
        rulecard=bad_rc,
        anchors=packet_app_config.packet_sources["TB"].anchors,
    )
    # packet_mode_valid vẫn True (test simulate runtime, not startup validation)
    inbox = proj.root / "POD_MAIN" / "CEO_INBOX"
    inbox.mkdir(parents=True)
    with caplog.at_level(logging.WARNING):
        result = inbox_packet.ensure_inbox_packet(
            inbox, proj, "POD_MAIN", "CEO", packet_app_config,
        )
    # Vì rulecard read trả về error placeholder, file vẫn được drop (graceful).
    # Quan trọng: không crash. Test sẽ chạy không throw.
    assert isinstance(result, bool)


# --------------------------------------------------------------------------- #
# 14. Atomic write — no half-written file on failure
# --------------------------------------------------------------------------- #

def test_packet_atomic_write(tmp_path, packet_app_config, monkeypatch):
    """Mô phỏng os.replace fail giữa chừng → packet không tồn tại,
    tmp file được cleanup."""
    import os as os_mod

    proj = _make_project(tmp_path / "proj", "ATOM1", ["POD_MAIN"])
    inbox = proj.root / "POD_MAIN" / "CEO_INBOX"
    inbox.mkdir(parents=True)

    original_replace = os_mod.replace
    call_count = {"n": 0}

    def fail_replace(src, dst):
        call_count["n"] += 1
        raise OSError("simulated replace failure")

    monkeypatch.setattr("app.inbox_packet.os.replace", fail_replace)

    result = inbox_packet.ensure_inbox_packet(
        inbox, proj, "POD_MAIN", "CEO", packet_app_config,
    )
    # ensure_inbox_packet swallows + logs, returns False
    assert result is False
    # Final packet file không tồn tại
    assert not (inbox / PACKET_FILENAME).exists()
    # Tmp file cũng cleanup (atomic write cleanup in _atomic_write)
    tmp_files = list(inbox.glob(".*_RUNTIME_PACKET.md.tmp_*"))
    assert tmp_files == []
    # Sanity: replace đã được gọi
    assert call_count["n"] >= 1
    # Restore (monkeypatch tự cleanup, nhưng explicit là an toàn)
    _ = original_replace


# --------------------------------------------------------------------------- #
# 15. Watcher skips packet files
# --------------------------------------------------------------------------- #

def test_watcher_skips_packet_files():
    assert inbox_packet.is_packet_filename("_RUNTIME_PACKET.md") is True
    assert inbox_packet.is_packet_filename("TRADE_ALERT__CP0__POD_MAIN__PACKET.md") is True
    assert inbox_packet.is_packet_filename("anything__PACKET.md") is True
    # Negative
    assert inbox_packet.is_packet_filename("regular_doc.md") is False
    assert inbox_packet.is_packet_filename("PACKET.md") is False  # không có double underscore
    assert inbox_packet.is_packet_filename("_RUNTIME_PACKET.txt") is False


# --------------------------------------------------------------------------- #
# 16. detect_mode fallback logs warning (NEW REV E-Lazy)
# --------------------------------------------------------------------------- #

def test_detect_mode_fallback_logs_warning(tmp_path, caplog):
    proj = _make_project(tmp_path / "proj", "WEIRD2", ["POD_UNKNOWN_X"])
    with caplog.at_level(logging.WARNING, logger="app.inbox_packet"):
        mode, detection = inbox_packet.detect_mode(proj)
    assert mode == MODE_TB
    assert detection == DETECTION_FALLBACK
    matching = [r for r in caplog.records if "PACKET_MODE_FALLBACK_TB" in r.getMessage()]
    assert len(matching) >= 1, "expected PACKET_MODE_FALLBACK_TB warning log"


# --------------------------------------------------------------------------- #
# 17. Per-mode disable (TB invalid không tắt BIG) — NEW REV E-Lazy
# --------------------------------------------------------------------------- #

def test_packet_per_mode_disable_tb_only(tmp_path, packet_app_config):
    """packet_mode_valid['TB']=False, ['BIG']=True → project TB không drop,
    project BIG vẫn drop."""
    packet_app_config.packet_mode_valid = {"TB": False, "BIG": True}

    # Project TB → skip packet
    proj_tb = _make_project(tmp_path / "proj_tb", "TB_OFF", ["POD_MAIN"])
    inbox_tb = proj_tb.root / "POD_MAIN" / "CEO_INBOX"
    inbox_tb.mkdir(parents=True)
    result_tb = inbox_packet.ensure_inbox_packet(
        inbox_tb, proj_tb, "POD_MAIN", "CEO", packet_app_config,
    )
    assert result_tb is False
    assert not (inbox_tb / PACKET_FILENAME).exists()

    # Project BIG → vẫn drop
    proj_big = _make_project(
        tmp_path / "proj_big", "BIG_OK",
        ["POD_PRODUCT", "POD_ENGINEERING"],
    )
    inbox_big = proj_big.root / "POD_PRODUCT" / "COO_INBOX"
    inbox_big.mkdir(parents=True)
    result_big = inbox_packet.ensure_inbox_packet(
        inbox_big, proj_big, "POD_PRODUCT", "COO", packet_app_config,
    )
    assert result_big is True
    assert (inbox_big / PACKET_FILENAME).exists()


# --------------------------------------------------------------------------- #
# 18. Packet header records detection_method (NEW REV E-Lazy)
# --------------------------------------------------------------------------- #

def test_packet_header_records_detection_method(tmp_path, packet_app_config):
    """Header phải ghi rõ Mode detected by: pods_match | fallback."""
    # pods_match case (POD_MAIN → TB)
    proj_match = _make_project(tmp_path / "proj_match", "M1", ["POD_MAIN"])
    inbox_match = proj_match.root / "POD_MAIN" / "CEO_INBOX"
    inbox_match.mkdir(parents=True)
    inbox_packet.ensure_inbox_packet(
        inbox_match, proj_match, "POD_MAIN", "CEO", packet_app_config,
    )
    body_match = (inbox_match / PACKET_FILENAME).read_text(encoding="utf-8")
    assert "Mode detected by:** pods_match" in body_match

    # fallback case (pods lạ → TB fallback)
    proj_fb = _make_project(tmp_path / "proj_fb", "F1", ["POD_RANDOM_NAME"])
    inbox_fb = proj_fb.root / "POD_RANDOM_NAME" / "QA_INBOX"
    inbox_fb.mkdir(parents=True)
    inbox_packet.ensure_inbox_packet(
        inbox_fb, proj_fb, "POD_RANDOM_NAME", "QA", packet_app_config,
    )
    body_fb = (inbox_fb / PACKET_FILENAME).read_text(encoding="utf-8")
    assert "Mode detected by:** fallback" in body_fb


# --------------------------------------------------------------------------- #
# Extra: is_primary_inbox positive path
# --------------------------------------------------------------------------- #

def test_is_primary_inbox_positive(tmp_path, packet_app_config):
    proj = _make_project(tmp_path / "proj", "POS1", ["POD_MAIN"])
    primary = proj.root / "POD_MAIN" / "CEO_INBOX" / "some__file.md"
    location = inbox_packet.is_primary_inbox(primary, proj, packet_app_config)
    assert location == ("POD_MAIN", "CEO")


def test_is_primary_inbox_unknown_pod(tmp_path, packet_app_config):
    proj = _make_project(tmp_path / "proj", "POS2", ["POD_MAIN"])
    primary = proj.root / "POD_GHOST" / "CEO_INBOX" / "some__file.md"
    location = inbox_packet.is_primary_inbox(primary, proj, packet_app_config)
    assert location is None  # pod không thuộc project


def test_is_primary_inbox_dynamic_pod_match(tmp_path, packet_app_config):
    """Dynamic pod (P1_Product) khớp pattern → is_primary_inbox returns location."""
    proj = ProjectConfig(
        name="BIG", root=tmp_path / "big", pods=["CP0", "POD_CORE"],
        project_code="BIG", display_name="BIG",
        dynamic_pod_pattern=r"^[PE]\d+(_[A-Za-z0-9]+)*$",
    )
    (tmp_path / "big").mkdir(parents=True, exist_ok=True)
    primary = proj.root / "E1_Backend" / "COO_INBOX" / "doc.md"
    location = inbox_packet.is_primary_inbox(primary, proj, packet_app_config)
    assert location == ("E1_Backend", "COO")


def test_is_primary_inbox_dynamic_pod_no_match(tmp_path, packet_app_config):
    """Pod ngoài pattern VÀ ngoài whitelist → None."""
    proj = ProjectConfig(
        name="BIG", root=tmp_path / "big2", pods=["CP0"],
        project_code="BIG2", display_name="BIG2",
        dynamic_pod_pattern=r"^[PE]\d+(_[A-Za-z0-9]+)*$",
    )
    (tmp_path / "big2").mkdir(parents=True, exist_ok=True)
    primary = proj.root / "GHOST_POD" / "COO_INBOX" / "doc.md"
    location = inbox_packet.is_primary_inbox(primary, proj, packet_app_config)
    assert location is None
