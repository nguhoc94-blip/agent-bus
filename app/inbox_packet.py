"""REV E-Lazy — Inbox auto-packet drop.

Khi bus mkdir `<POD>/<ROLE>_INBOX/` lần đầu, drop kèm `_RUNTIME_PACKET.md`
chứa rulecard + anchor templates để operator paste nguyên xi lên prompt agent.
Idempotent: lần thứ 2 trở đi nếu file đã tồn tại thì skip.

Decisions (xem plan REV E-Lazy):
- Mode detect: heuristic theo `project_cfg.pods` (Q1) — POD_MAIN, subset POD_CORE/FLOW,
  hoặc BIG prefixes. Fallback TB + log warning (Q9).
- Packet content: embed rulecard + anchors. Ưu tiên project anchor THẬT
  (`<project.root>/00_raw_input_anchor.md`); thiếu → fallback template + BLOCKER (Q2).
- Mode invalid (source missing): per-mode disable (Q10) — TB invalid không tắt BIG.
- Static, no overwrite: operator xóa file để refresh (Q4).
- Skip mirror/review folder: chỉ drop cho primary inbox (Q3 phạm vi).
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Literal, Optional, Tuple

from .models import AppConfig, PacketSourceConfig, ProjectConfig

log = logging.getLogger(__name__)


PACKET_FILENAME = "_RUNTIME_PACKET.md"

# Detection method labels — exposed in packet header for transparency.
DETECTION_PODS_MATCH = "pods_match"
DETECTION_FALLBACK = "fallback"

# Mode literals (mirror keys of AppConfig.packet_sources).
MODE_TB = "TB"
MODE_BIG = "BIG"

ModeLiteral = Literal["TB", "BIG"]
DetectionLiteral = Literal["pods_match", "fallback"]

# Big Mode pod prefixes — heuristic detect. Có ít nhất 1 pod match prefix → BIG.
_BIG_POD_PATTERN = re.compile(r"^POD_(PRODUCT|ENGINEERING|GROWTH)")

# Program-management pods đặc trưng cho workflow Job TO (Big Mode):
# CP0 (Checkpoint 0 lane), COO_PROGRAM (điều phối chương trình), QA_PROGRAM (QA cross-pod),
# CROSS-PROJECT (anchor co-sign / scope change). Sự xuất hiện của bất kỳ pod nào trong
# tập này → project dùng Big Mode → dùng packet_sources["BIG"].
_BIG_PROGRAM_POD_PATTERN = re.compile(
    r"^(CP0|COO_PROGRAM|QA_PROGRAM|CROSS-PROJECT)$"
)

# Dual-pod Tử Vi / khoa học (CORE + FLOW trong cùng project, không có program pods) —
# vẫn workflow Job TB; không ép BIG cũng không fallback cảnh báo.
_DEMO_DUAL_PODS = frozenset({"POD_CORE", "POD_FLOW"})


def detect_mode(project_cfg: ProjectConfig) -> Tuple[ModeLiteral, DetectionLiteral]:
    """Return (mode, detection_method) for the given project.

    - `pods == ["POD_MAIN"]` → ("TB", "pods_match")
    - Pods chỉ thuộc `{POD_CORE, POD_FLOW}` (non-empty subset) → ("TB", "pods_match")
      (dual-pod style không có program overhead)
    - Có ít nhất 1 pod match `^POD_(PRODUCT|ENGINEERING|GROWTH)` → ("BIG", "pods_match")
    - Có ít nhất 1 pod match `_BIG_PROGRAM_POD_PATTERN` (CP0/COO_PROGRAM/…)
      → ("BIG", "pods_match")  (Job TO Big Mode với program-management lane)
    - Pods lạ (không match các pattern trên) → ("TB", "fallback") + log warning.

    Q9 (REV E-Lazy): fallback KHÔNG được silent — phải log để operator biết.
    """
    pods = list(project_cfg.pods or [])
    if pods == ["POD_MAIN"]:
        return (MODE_TB, DETECTION_PODS_MATCH)
    pod_set = set(pods)
    if pod_set and pod_set <= _DEMO_DUAL_PODS:
        return (MODE_TB, DETECTION_PODS_MATCH)
    if any(_BIG_POD_PATTERN.match(p) for p in pods):
        return (MODE_BIG, DETECTION_PODS_MATCH)
    if any(_BIG_PROGRAM_POD_PATTERN.match(p) for p in pods):
        return (MODE_BIG, DETECTION_PODS_MATCH)
    log.warning(
        "PACKET_MODE_FALLBACK_TB project=%s pods=%s — không match pattern TB/BIG, "
        "fallback TB. Nếu đây là Big Mode với pod tên mới, mở rộng "
        "_BIG_POD_PATTERN trong inbox_packet.py.",
        project_cfg.name, pods,
    )
    return (MODE_TB, DETECTION_FALLBACK)


def is_primary_inbox(
    primary_path: Path,
    project_cfg: ProjectConfig,
    app_cfg: AppConfig,
) -> Optional[Tuple[str, str]]:
    """Return (pod, role) nếu `primary_path` thuộc một `<POD>/<ROLE>_INBOX/`
    hợp lệ trong project, ngược lại None.

    Path expected: `<project.root>/<POD>/<ROLE>_INBOX/<filename>`.
    """
    parent = primary_path.parent
    inbox_name = parent.name
    suffix = app_cfg.inbox_suffix or "_INBOX"
    if not inbox_name.endswith(suffix):
        return None
    role = inbox_name[: -len(suffix)]
    if not role:
        return None
    pod_dir = parent.parent
    pod = pod_dir.name
    if not project_cfg.pod_allowed(pod):
        return None
    return (pod, role)


@dataclass
class AnchorResolution:
    """Result of resolve_anchor_source()."""

    name: str
    path: Path
    is_real: bool


def resolve_anchor_source(
    anchor_filename: str,
    project_cfg: ProjectConfig,
    template_path: Path,
) -> AnchorResolution:
    """Resolve which file embed cho anchor.

    Ưu tiên (Q2):
    1. `<project.root>/<anchor_filename>` (file thật trong project)
    2. Fallback: `template_path` từ packet_sources (template + BLOCKER warning)
    """
    real_candidate = project_cfg.root / anchor_filename
    if real_candidate.exists() and real_candidate.is_file():
        return AnchorResolution(
            name=anchor_filename,
            path=real_candidate,
            is_real=True,
        )
    return AnchorResolution(
        name=anchor_filename,
        path=template_path,
        is_real=False,
    )


def _anchor_filename_from_template(template_path: Path) -> str:
    """Strip `.template` segment to compute the corresponding real-project filename.

    Examples:
        00_raw_input_anchor.template.md → 00_raw_input_anchor.md
        00_system_acceptance_contract.template.md → 00_system_acceptance_contract.md
    """
    name = template_path.name
    return name.replace(".template.md", ".md").replace(".template", "")


def _read_text_safe(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except OSError as e:
        log.warning("PACKET_SOURCE_READ_FAILED path=%s err=%s", p, e)
        return f"<!-- ERROR reading {p.name}: {e} -->"


def _mtime_iso(p: Path) -> str:
    try:
        ts = p.stat().st_mtime
    except OSError:
        return "unknown"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_packet_content(
    *,
    mode: ModeLiteral,
    detection_method: DetectionLiteral,
    project_cfg: ProjectConfig,
    pod: str,
    role: str,
    packet_source: PacketSourceConfig,
) -> str:
    """Build full text content of `_RUNTIME_PACKET.md`."""
    generated_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    rulecard_path = packet_source.rulecard
    rulecard_text = _read_text_safe(rulecard_path)
    rulecard_mtime = _mtime_iso(rulecard_path)

    # Resolve each anchor: prefer project real file, fallback template.
    anchors: List[Tuple[AnchorResolution, str, str]] = []
    n_real = 0
    for tpl_path in packet_source.anchors:
        anchor_name = _anchor_filename_from_template(tpl_path)
        resolution = resolve_anchor_source(anchor_name, project_cfg, tpl_path)
        body = _read_text_safe(resolution.path)
        anchor_mtime = _mtime_iso(resolution.path)
        anchors.append((resolution, body, anchor_mtime))
        if resolution.is_real:
            n_real += 1
    n_total = len(anchors)
    fallback_count = n_total - n_real

    # ----- Build markdown -----
    lines: List[str] = []
    lines.append(f"# RUNTIME PACKET — {project_cfg.project_code} / {pod} / {role}")
    lines.append("")
    lines.append(f"> **Mode:** {mode}")
    lines.append(f"> **Mode detected by:** {detection_method}")
    lines.append(f"> **Generated:** {generated_at}")
    lines.append(f"> **Source rulecard:** `{rulecard_path}` (mtime {rulecard_mtime})")
    lines.append(
        f"> **Anchors:** {n_real}/{n_total} real "
        f"({fallback_count} template fallback)"
    )
    lines.append(
        "> **Refresh:** xóa file này → bus drop lại packet mới khi route file "
        "kế tiếp vào inbox."
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## §A — RUNTIME RULECARD (embed)")
    lines.append("")
    lines.append(rulecard_text.rstrip())
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## §B — PROJECT ANCHORS (embed)")
    lines.append("")

    for idx, (resolution, body, anchor_mtime) in enumerate(anchors, start=1):
        lines.append(f"### B.{idx} — `{resolution.name}`")
        if resolution.is_real:
            lines.append(
                f"> **Source:** `{resolution.path}` (REAL project file) | "
                f"mtime {anchor_mtime}"
            )
        else:
            lines.append(
                f"> **Source:** `{resolution.path}` "
                f"(TEMPLATE FALLBACK — project anchor missing) | "
                f"mtime {anchor_mtime}"
            )
        lines.append("")
        lines.append(body.rstrip())
        lines.append("")

    # ----- §C BLOCKER (only when at least one anchor fell back to template) -----
    if fallback_count > 0:
        lines.append("---")
        lines.append("")
        lines.append("## §C — BLOCKER  *(scope-drift risk)*")
        lines.append("")
        lines.append(
            "> Project chưa có file thật cho các anchor sau "
            "(đang dùng template fallback):"
        )
        lines.append(">")
        for resolution, _body, _mt in anchors:
            if not resolution.is_real:
                lines.append(f"> - `{resolution.name}`")
        lines.append(">")
        lines.append(
            "> **OPERATOR PHẢI**: tạo file thật trong `<project.root>/` "
            "TRƯỚC khi giao task lethal. Sau khi tạo, xóa file packet này "
            "để bus drop lại với anchor thật."
        )
        lines.append("")

    # ----- §D Hướng dẫn operator -----
    lines.append("---")
    lines.append("")
    lines.append("## §D — HƯỚNG DẪN OPERATOR")
    lines.append("")
    lines.append(
        "1. Khi giao task cho agent **{role}**, paste nguyên packet này lên đầu "
        "prompt.".format(role=role)
    )
    lines.append(
        "2. Packet có §A (rulecard) + §B (anchor thật/template) đủ context lethal."
    )
    lines.append(
        "3. Nếu §C BLOCKER xuất hiện → ưu tiên tạo anchor thật, KHÔNG giao task "
        "lethal khi còn template fallback."
    )
    lines.append(
        "4. Xóa file để bus refresh khi rulecard/anchor source thay đổi."
    )
    lines.append("")
    return "\n".join(lines)


def _atomic_write(dest: Path, content: str) -> None:
    """Write `content` to `dest` atomically (tmp + os.replace).

    Phòng race condition khi 2 file cùng tạo inbox: cả hai sẽ chỉ ghi đè cùng nội
    dung lên packet, không để lại file half-written.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(
        f".{dest.name}.tmp_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    )
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(str(tmp), str(dest))
    except BaseException:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise


def ensure_inbox_packet(
    inbox_dir: Path,
    project_cfg: ProjectConfig,
    pod: str,
    role: str,
    app_cfg: AppConfig,
) -> bool:
    """Idempotent drop `_RUNTIME_PACKET.md` vào `inbox_dir`.

    Return True nếu vừa drop packet mới. False nếu skip (đã tồn tại / master
    switch off / mode invalid / source thiếu).

    Q4 static design: nếu file đã tồn tại — không overwrite, không refresh.
    Operator phải xóa thủ công để refresh.
    """
    if not app_cfg.auto_drop_inbox_packet:
        return False

    packet_path = inbox_dir / PACKET_FILENAME
    if packet_path.exists():
        return False

    mode, detection = detect_mode(project_cfg)

    # Q10 per-mode disable: nếu source mode tương ứng invalid → skip riêng mode đó.
    if not app_cfg.packet_mode_valid.get(mode, False):
        log.warning(
            "PACKET_DROP_SKIPPED_MODE_INVALID project=%s pod=%s role=%s mode=%s "
            "— packet_sources['%s'] không hợp lệ (xem startup warnings).",
            project_cfg.name, pod, role, mode, mode,
        )
        return False

    packet_source = app_cfg.packet_sources.get(mode)
    if packet_source is None:
        log.warning(
            "PACKET_DROP_SKIPPED_NO_SOURCE project=%s mode=%s — chưa khai báo "
            "packet_sources['%s'] trong config.",
            project_cfg.name, mode, mode,
        )
        return False

    try:
        content = build_packet_content(
            mode=mode,
            detection_method=detection,
            project_cfg=project_cfg,
            pod=pod,
            role=role,
            packet_source=packet_source,
        )
        _atomic_write(packet_path, content)
    except Exception as e:  # noqa: BLE001 — bus must not crash
        log.warning(
            "PACKET_DROP_FAILED project=%s pod=%s role=%s mode=%s err=%s",
            project_cfg.name, pod, role, mode, e,
        )
        return False

    log.info(
        "PACKET_DROPPED path=%s mode=%s detection=%s anchors_real=%d/%d",
        packet_path, mode, detection,
        sum(1 for tpl in packet_source.anchors
            if (project_cfg.root / _anchor_filename_from_template(tpl)).exists()),
        len(packet_source.anchors),
    )
    return True


def is_packet_filename(name: str) -> bool:
    """Skip routing cho `_RUNTIME_PACKET.md` hoặc `*__PACKET.md` (Q8).

    Phòng trường hợp operator vô tình copy packet vào watch_folder → bus
    không thử route packet.
    """
    if name == PACKET_FILENAME:
        return True
    if name.endswith("__PACKET.md"):
        return True
    return False
