"""file_router_bot v2 — deterministic local file router.

Versioning:
- 1.1.0 — v1 baseline (deterministic, no LLM).
- 2.0.0 — v2 workflow-aware (Phase/DocType/Importance, Reporter Hub mirror,
  Template Registry, canonical filename PROJECT_CODE__PHASE__POD__DOCTYPE).
- 2.1.0 — REV D Anti Down-Scope Guardrail v1 (SCOPE_CHANGE_ACK + QA_LIMIT_1 doc
  types + QA→CEO route lock).
- 2.2.0 — REV E-Lazy: inbox auto-packet drop (lazy `_RUNTIME_PACKET.md` cho mỗi
  primary inbox tạo lần đầu, embed rulecard + anchor template, ưu tiên file
  project thật, per-mode disable, idempotent).
- 2.3.0 — Anchor Co-Sign workflow: 2 doc_type mới (ANCHOR_COSIGN_REQUEST + 
  ANCHOR_COSIGN_ACK), heading/loai aliases, phase=CP0, importance=CRITICAL.
  Tuyến CEO↔COO không bị filter; cả 2 doc đã mirror vào Reporter Hub.
"""

__version__ = "2.3.0"
__codename__ = "Anchor Co-Sign"
