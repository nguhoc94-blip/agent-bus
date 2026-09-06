# Agent Bus — Multi-Agent File Router

A deterministic Python file router for personal multi-agent AI workflows. When operating 9–13 ChatGPT/Cursor agent roles (CEO, COO, Product/Engineering/Growth PODs, QA, Deputy, …), manually sorting markdown artifacts between `{project}/{pod}/{role}_INBOX/` folders becomes error-prone and slow. Agent Bus automates that routing layer — no LLM, no cloud API, no cost per file.

> **Portfolio note:** This is a scrubbed excerpt of a production tool used in a personal "AI company" workflow. Some operational details and internal templates are omitted. See [docs/](docs/) for the broader system context.

---

## Problem

Running multiple AI agents as organizational roles requires strict file-based communication:

- Each agent outputs versioned `.md` artifacts (`CEO_gui_COO_v001.md`, …)
- Files must land in the correct `{project}/{pod}/{role}_INBOX/`
- Critical documents need mirroring to a central Reporter Hub for audit
- Misrouted files on critical flows (CEO Brief, QA Report) cause scope drift

Manual drag-and-drop across 9–13 roles × multiple projects does not scale.

## Solution

**Agent Bus** watches a folder (typically Downloads), classifies each file deterministically, and routes it to the correct inbox:

```
Downloads/brief.md  →  C:\Projects\demo\POD_PRODUCT\COO_INBOX\DEMO__PHASE_1__...__CEO_gui_COO.md
                   →  C:\Projects\demo\_REPORTER_HUB\PHASE_1\CEO_BRIEF\...  (mirror)
```

Key properties:
- **Deterministic classifier** — DocType field → Loại alias → heading match → filename pattern. No LLM inference.
- **Watcher with dedup** — handles partial downloads, temp extensions, fingerprint deduplication.
- **Cross-volume safe moves** — copy-verify-delete when source and destination are on different drives.
- **Inbox auto-packet** — drops `_RUNTIME_PACKET.md` (rulecard + anchors) on first inbox creation for operator paste workflow.
- **Review queue** — ambiguous or critical-flow failures go to `REVIEW_MANUAL/` instead of silent misroute.

## Tech Stack

- **Python 3.9+** (tested on 3.10)
- **watchdog** — filesystem event monitoring
- **pytest** — 15+ test modules, 120+ assertions

## Quick Start

```powershell
# Install dependencies
pip install -r requirements.txt

# Configure paths
copy config.example.json config.json
# Edit config.json — set watch_folder, project roots, pods

# Run watcher
python main.py --config config.json

# Or on Windows
run.bat
```

### Dry-run (no filesystem changes)

```powershell
python main.py --config config.json --dry-run
```

### Run tests

```powershell
python -m pytest tests/ -v
```

## Configuration

Copy `config.example.json` → `config.json`. Key fields:

| Field | Purpose |
|---|---|
| `watch_folder` | Folder to monitor (e.g. Downloads) |
| `projects` | Map of project key → `{root, project_code, pods}` |
| `roles` | Valid agent roles (CEO, COO, PRODUCT, …) |
| `review_folder` | Fallback for ambiguous/unclassifiable files |
| `reporter_hub_name` | Mirror folder name (default `_REPORTER_HUB`) |
| `mirror_doc_types` | Doc types copied to Reporter Hub |
| `auto_drop_inbox_packet` | Auto-drop runtime packet on inbox creation |

See [config.example.json](config.example.json) for a complete example with generic paths.

## Classification

Metadata can come from file content (first 50 lines) or filename:

```
Project: DEMO
Pod: POD_PRODUCT
Từ: CEO
Gửi: COO
Phase: PHASE_1
DocType: CEO_BRIEF
```

Or canonical filename: `DEMO__PHASE_1__POD_PRODUCT__CEO_BRIEF__CEO_gui_COO.md`

Legacy v1 filenames (`PROJECT__POD__FROM_gui_TO.ext`) are still supported.

## Test Suite

| Module | Coverage |
|---|---|
| `test_classifier.py` | Hybrid-2 classification tiers, Vietnamese diacritics |
| `test_parser.py` | Content/filename parsing, merge logic |
| `test_router.py`, `test_router_v2.py` | Canonical paths, mirror, escalation |
| `test_mover_v2.py` | Atomic replace, cross-volume, mirror isolation |
| `test_watcher_dedup.py` | Event deduplication |
| `test_duplicate_strategy.py` | Overwrite vs. skip |
| `test_dry_run.py` | No-op mode |
| `test_stability.py` | Download completion detection |
| `test_shutdown.py` | Graceful shutdown |
| `test_template_registry.py` | Contract drift detection |
| `test_inbox_packet.py` | Runtime packet auto-drop |
| `test_cross_volume_move.py` | Cross-drive safety |
| `test_review_fallbacks.py` | Review queue routing |

## Project Structure

```
agent-bus/
├── app/                  # Core modules (watcher, parser, router, mover, …)
├── tests/                # pytest suite (~15 modules)
├── docs/                 # Multi-agent workflow documentation
│   ├── architecture.md   # System architecture + mermaid diagram
│   ├── governance-rules.md
│   ├── mode-selection-framework.md
│   └── multi-agent-setup.md
├── scripts/              # Utility scripts (release build, registry refresh)
├── config.example.json   # Example configuration (generic paths)
├── main.py               # Entry point
├── cli.py                # CLI argument parsing
└── requirements.txt
```

## Broader Context

Agent Bus is one component of a larger personal multi-agent operating system:

| Document | Description |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Full workflow: CEO → COO → CP0 → PODs → QA/Deputy → Closure |
| [docs/governance-rules.md](docs/governance-rules.md) | Agent behavior rules (BUS validation, anchors, gates) |
| [docs/mode-selection-framework.md](docs/mode-selection-framework.md) | AD-HOC / SMALL / BIG mode selection |
| [docs/multi-agent-setup.md](docs/multi-agent-setup.md) | One-time ChatGPT Project setup per role |

The bus handles **file routing**; governance rules and agent prompts handle **workflow enforcement**.

## License

All Rights Reserved — Portfolio Viewing Only. See [LICENSE](LICENSE).
