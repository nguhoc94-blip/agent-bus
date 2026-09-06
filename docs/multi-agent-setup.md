# Multi-Agent Setup Guide

> How to configure 9–13 ChatGPT/Claude Projects as specialized agent roles for a Big Mode project. One-time setup per role; ~60–90 minutes total for all roles.

---

## Prerequisites

Before setting up any agent, the project root must contain these anchor and tracking files:

| File | Purpose | Created by |
|---|---|---|
| `00_raw_input_anchor.md` | Verbatim raw input | CEO Agent + COO co-sign |
| `00_system_acceptance_contract.md` | System-level AC + integration scenarios | COO, CEO approves at Gate Plan |
| `00_interface_contracts.md` | Interface inventory between PODs | COO when ≥ 2 active PODs |
| `01_project_brief.md` | Project summary | Reporter |
| `03_current_status.md` | Live status | Reporter |
| `04_reports.md` | Evidence and reports | Reporter |
| `05_decision_log.md` | Decision history | Reporter |

**Do not set up any agent before the raw input anchor is co-signed.** Empty anchor templates cause scope drift from turn 1.

---

## Three-Layer Setup (per role)

| Layer | Where | Frequency |
|---|---|---|
| **Layer 1 — Custom Instructions** | Project Instructions field | Once per role |
| **Layer 2 — Project Knowledge** | Project Files upload | Once (re-upload on anchor changes) |
| **Layer 3 — Role prompt** | First pinned message | Once per role |

Setup time: ~7 minutes per role.

---

## Step 1: Create a Project per Role

Create one ChatGPT/Claude Project for each role:

| Role | Count |
|---|---|
| CEO | 1 |
| COO | 1 |
| Product Pod Lead | 1 |
| Engineering Pod Lead | 1 |
| Growth Pod Lead | 0–1 |
| QA | 1 |
| Deputy | 1 |
| Reporter | 1 |
| Builder / Specialist | 0–N (as needed) |

Naming convention: `{PROJECT_CODE}_{ROLE}` (e.g. `PROJECT_A_CEO`, `PROJECT_A_POD_ENGINEERING_LEAD`).

**Bootstrap minimum:** CEO + COO + 1 Pod Lead matching the raw input. Open QA/Deputy/Reporter near gate milestones.

---

## Step 2: Custom Instructions (Layer 1)

Paste governance rules into each Project's Instructions field. All roles share the same Layer 1 content — see [governance-rules.md](governance-rules.md) for the rule set agents must follow.

Key rules to emphasize:
- BUS VALIDATION block on every outbound file
- CP0 discovery routing (COO does not auto-assign PODs)
- Three anchor artifacts for Big Mode
- DRIFT CHECK at six gates
- No self-scoping or route bypass

---

## Step 3: Upload Project Knowledge (Layer 2)

Upload ~10 files per Project (within platform limits):

- Governance rules
- Runtime rulecard (12 lethal rules for Big Mode)
- Three anchor files (real, co-signed — not templates)
- Role-specific prompt section
- Project brief, status, reports, decision log

**Critical:** Anchor + SAC + IFC must be real project files, not empty templates.

If IFC is not yet finalized when setting up a Pod Lead, upload the template with a "IFC pending" note and re-upload when COO locks the Interface Matrix.

---

## Step 4: Pin Role Prompt (Layer 3)

Paste the role-specific system prompt as the first message and pin it. Agent should reply `{ROLE} READY` to confirm.

Include project context:
- `project_code`, mode (BIG), active PODs
- Which POD this role manages (for Pod Leads)
- Confirmation that three anchors are uploaded

---

## Step 5: Sanity Check (4 questions)

Before accepting setup, verify the agent can answer:

| # | Question | Expected |
|---|---|---|
| 1 | What is your role? List INPUT FROM and OUTPUT TO. | Matches role prompt |
| 2 | List the 12 lethal rules (one line each). | L1–L12 from rulecard |
| 3 | Quote first 3 lines of anchor §1 (raw input). | Matches real anchor file |
| 4 | List SAC IDs from §2 of the acceptance contract. | Matches real SAC |

All 4 must PASS before the role is operational.

---

## Per-Turn Workflow (after setup)

When Agent Bus drops a file into `{POD}/{ROLE}_INBOX/`:

1. Open the inbox file and `_RUNTIME_PACKET.md` (auto-dropped by the bus on first inbox creation).
2. Paste one message into the target Project:

```
[paste _RUNTIME_PACKET.md contents]

---

INBOUND FILE: {filename}.md

[paste inbox file contents]
```

3. Save the agent's reply as `{Sender}_gui_{Recipient}_vNNN.md` in the appropriate drafts subfolder.
4. Drop the output file into `_OPERATOR_OUTBOX/` — Agent Bus routes it to the next role's inbox.

---

## Refresh Triggers

| File changed | Action |
|---|---|
| Governance rules | Re-upload + verify Custom Instructions |
| Role prompt | Re-upload + re-paste Layer 3 |
| Anchor (SCOPE_CHANGE_ACK) | Re-upload to **all** role Projects |
| SAC or IFC | Re-upload to CEO/COO/affected Pod Leads/QA |
| Stale `_RUNTIME_PACKET.md` | Delete from inbox — bus re-drops on next route |

---

## Common Setup Mistakes

| Mistake | Consequence |
|---|---|
| SAC not created before Phase 1 | Pod Lead doesn't know which SAC IDs to cover → QA reject |
| IFC missing with ≥ 2 PODs | Cross-pod conflicts have no source of truth |
| Empty anchor template uploaded | Agent operates on blank scope → immediate drift |
| Skipping sanity check Q4 (SAC IDs) | Pod Lead guesses scope → drift at Pod Plan |
