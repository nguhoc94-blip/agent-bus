# Governance Rules — Multi-Agent Workflow

> Illustrative rules for operating a personal "AI company" with 9–13 specialized agent roles (CEO, COO, Product/Engineering/Growth PODs, QA, Deputy, Reporter). These rules govern how agents communicate via structured markdown artifacts — not chat transcripts.

---

## Core Principles

1. **Trace output must be a `.md` file** saved under the correct project subfolder, named `[Sender]_gui_[Recipient]_vNNN.md` (NNN = 001, 002, …). A task is complete only when the file exists on disk — not when markdown appears in chat.

2. **Fixed input/output routes.** Each agent accepts work only from designated sources and sends output only to designated destinations. No ad-hoc route expansion.

3. **Internal loops stay internal.** Pod-to-pod clarification and iteration do not bypass QA, Deputy, or CEO gates.

4. **CEO gates are mandatory** at end of Phase 1 (Gate Plan) and Phase 2 (Gate Output).

5. **No self-scoping.** Agents do not expand scope, add features, or bypass routing without explicit approval.

6. **Fast Track** requires COO proposal (form FT-1) and explicit CEO approval — never assumed.

7. **CEO is an AI agent**, not a human operator. The CEO Agent receives raw input, issues briefs, approves plans, and approves outputs after QA + Deputy review.

---

## Discovery & Routing (CP0)

8. **CP0 is discovery routing — not execution.** COO parses raw input and selects candidate PODs for feasibility notes only. Active PODs are assigned after the CEO Brief.

9. **Pod-based default.** Every project has Product and Engineering PODs at minimum. POD count and type depend on the CEO Brief, not a fixed template.

10. **Specialist ownership.** Specialists and Builders belong to the POD that assigned them — no floating resource pool.

---

## Anchor Artifacts (Big Mode)

11. **Three anchor files are required** for Big Mode projects:
    - `00_raw_input_anchor.md` — verbatim raw input (CEO creates, COO co-signs)
    - `00_system_acceptance_contract.md` — system-level acceptance criteria (SAC)
    - `00_interface_contracts.md` — interface inventory between PODs (IFC)

12. **Co-sign workflow.** CEO Brief cannot be issued until the raw input anchor exists and COO has acknowledged it (APPROVE).

13. **Anchors are immutable** after co-sign/approval. Changes require a `SCOPE_CHANGE_ACK` signed by CEO + COO + affected Pod Lead.

---

## Quality Gates

14. **BUS VALIDATION block** is mandatory at the end of every outbound `.md` artifact. Receiving agents must print `INBOUND CHECK: PASS/FAIL` before processing.

15. **DRIFT CHECK** is mandatory at six Big Mode gates: CEO Brief Approval, Pod Plan Review, QA Plan Review, Cross-Pod Integration Gate, QA Output Review, Deputy Closure.

16. **QA cannot self-limit scope** (QA_LIMIT_1 rule). Limiting QA coverage requires explicit CEO approval before review begins.

17. **Cross-Pod Integration Gate** is mandatory before Deputy Closure. Every SAC integration scenario must have evidence (logs, screenshots, test output).

18. **Interface Contracts are source of truth.** When project brief and IFC disagree, IFC wins.

---

## Artifact vs. Real Code

19. **Drafts are communication traces**, not deliverables. Real artifacts (code, builds, URLs) live in the project tree and are referenced by path — never copied into `drafts/`.

20. **Relay/Bus Protocol** separates four layers: RAW INPUT → RELAY NOTE → OFFICIAL DECISION → OUTBOUND DRAFT. Relay notes cannot substitute for raw input when setting goals.

21. **Local and sandbox paths are both valid** for provenance when an artifact is built locally and uploaded to a sandbox environment. BUS validation does not fail on path mismatch if both paths reference the same artifact.

---

## Mode Escalation

22. **Default mode is AD-HOC.** Escalate to SMALL or BIG only when coordination complexity genuinely increases — not because technical difficulty or audit burden is high. See [mode-selection-framework.md](mode-selection-framework.md).

23. **Big Mode must expire** after integration/release is complete. Downgrade to SMALL or AD-HOC promptly.

---

## Agent Bus Integration

24. **Agent Bus routes files deterministically** from the operator's Downloads folder into `{project}/{pod}/{role}_INBOX/` based on metadata fields (Project, Pod, From, To, Phase, DocType). See [architecture.md](architecture.md).

25. **Operator workflow:** read inbox file → paste `_RUNTIME_PACKET.md` + file content into the target ChatGPT/Claude Project → save agent reply as the next versioned `.md` → drop into `_OPERATOR_OUTBOX/` for the bus to route onward.
