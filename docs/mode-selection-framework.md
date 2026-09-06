# Mode Selection Framework

> How to choose AD-HOC, SMALL, or BIG coordination mode for a multi-agent project. Mode measures **organizational synchronization need**, not technical difficulty.

---

## Philosophy

| Dimension | What it measures | Affects |
|---|---|---|
| Coordination Complexity (CC) | Ownership domains, cross-domain dependencies, parallel streams | **Mode selection** |
| Verification Burden (VB) | Blast radius, silent failure risk, audit need | QA intensity |
| Operational Criticality (OC) | Production/brand/security impact | Gate / approval level |
| Packetizability (PS) | How bounded and self-contained the task is | Execution style |

**Key insight:** A technically hard task with one owner and clear output can stay AD-HOC. A simple task spanning three PODs with interface dependencies needs BIG.

---

## Mode Definitions

### AD-HOC — Precision execution

Use when:
- One brain + one builder is sufficient
- Low coordination, bounded scope, clear task packet
- Few handoffs, few ownership conflicts

Even if technical precision (TP) or verification burden (VB) is high, AD-HOC may still apply.

### SMALL — Product + Engineering coordination

Use when:
- Product ↔ Engineering alignment is required
- User flow / behavior decisions need ongoing clarification
- Rollout and QA coordination begins to appear

### BIG — Organizational synchronization

Use only when:
- Multiple PODs/lanes/interfaces run in parallel
- Large dependency graph with real release orchestration
- Multiple ownership domains need continuous sync

BIG does **not** mean "technically hard" or "high risk."

---

## Scoring Dimensions

### Technical Precision (TP) — 0..16
Logic parity difficulty, platform mismatch, determinism requirements, edge-case density.

**Does not decide mode.**

### Coordination Complexity (CC) — 0..24
Ownership domains, cross-domain dependencies, interface synchronization, parallel workstreams, decision coordination, release orchestration.

**This decides mode.**

### Verification Burden (VB) — 0..16
Blast radius, silent failure risk, audit/reporting burden, verification difficulty.

### Operational Criticality (OC) — 0..4

| Score | Meaning |
|---|---|
| 0 | Failure is harmless |
| 1 | Easy to fix |
| 2 | Minor user impact |
| 3 | Production / brand / revenue |
| 4 | Security / legal / irreversible |

Rules: OC ≥ 3 → minimum QA Heavy. OC = 4 → mandatory dual review + audit log.

### Packetizability (PS) — High / Medium / Low

| Level | Meaning |
|---|---|
| High | Clear packet, builder works independently |
| Medium | Some clarification needed |
| Low | Exploratory, high ambiguity |

Rules: PS High → prefer AD-HOC. PS Low → start with SMALL flow.

---

## Decision Rules

| Condition | Mode |
|---|---|
| CC ≤ 6, ownership domains ≤ 2, parallel streams ≤ 1 | **AD-HOC** (default) |
| CC = 7–14, Product ↔ Engineering alignment needed | **SMALL** |
| CC ≥ 15, ≥ 3 ownership domains, ≥ 3 synchronized streams | **BIG** |

---

## QA Intensity (independent of mode)

| Level | When |
|---|---|
| Light | Local task |
| Medium | Feature / product scope |
| Heavy | Parity / risk / audit |
| Formal | Enterprise / regulatory |

Rules: TP high + VB high → Heavy/Formal. OC ≥ 3 → minimum Heavy. OC = 4 → Formal.

---

## Gate Matrix

| Condition | Gate |
|---|---|
| AD-HOC + QA Light | No gate |
| AD-HOC + QA Heavy | QA gate |
| SMALL + user-facing | Product / QA gate |
| BIG | Integration gate |
| OC = 4 | Mandatory Deputy / CEO approval |

---

## Anti-Overbuild Rules

1. Do not add agents unless they reduce cognitive load, risk, or coordination entropy.
2. Do not add scoring dimensions that do not change the actual decision.
3. Do not use BIG if one brain + one builder still works well.
4. If planning time exceeds execution time repeatedly, reduce ceremony or downgrade mode.
5. **BIG must expire** after integration/release completes — downgrade to SMALL or AD-HOC.

---

## Standard Output Format

When scoring a task, produce:

1. TP / CC / VB / OC / PS scores
2. Current Mode + QA Intensity + Execution Style
3. Required Gate
4. Why not smaller? / Why not bigger?
5. Next escalation trigger + downgrade trigger
