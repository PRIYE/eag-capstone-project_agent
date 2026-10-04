# Implementation Plan: Project Agent (Seat 14)

**Branch**: `001-project-agent` (directory only; the repo is not under git) | **Date**: 2026-10-04 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-project-agent/spec.md`

## Summary

Build the Seat 14 Project Agent by mirroring Team 04's four-layer split, on top of the
scaffold already in this repo (`agent/`, `harness/`, `run.py`):

1. **Transport** - the existing `agent/mcp_client.py`, extended with an independent REST
   status probe so a `403` and a `404` are never conflated.
2. **Domain** - a new `agent/domain/` package of pure functions over already-fetched
   records: schedule integrity, behind-schedule, overload, critical-path what-if, EVM,
   delay facts, reschedule proposals. No network and no LLM inside it.
3. **Loop** - `agent/loop.py` rewritten around a fixed tool set. The model chooses which
   tool to call and writes the closing summary; it never builds a request itself. Every
   run is bounded by a step budget and a 3-minute wall clock, and ends with a persisted
   finding.
4. **Harness** - `harness/` gains an offline mode (fake MCP + seeded JSON fixtures) and
   state-reading verifiers, so both graded predicates can be graded before touching the
   live evaluator.

The two graded answers (`project.behind_schedule`, `project.overloaded_next_week`) are
the first deliverables. Everything else (critical-path check, reschedule, EVM, narrative,
status report) layers on the same domain and safety primitives.

## Technical Context

**Language/Version**: Python 3.11+ (3.14.6 is installed locally); standard library only for transport (`urllib`), as the existing client does.

**Primary Dependencies**: none for the agent core. LLM access through the existing `agent/ai_models.py` wrappers (OpenAI / Anthropic / Google / OpenRouter keys from `.env`). `pytest` for tests.

**Storage**: none of our own. All business data is read through the shared AgentSwitch API. The agent's conclusions are persisted to the platform (`AgentMemory`, see research R3). Run traces are written to local `harness/runs/`.

**Testing**: `pytest`, hand-written (the brief gives AI-generated tests zero credit). Offline domain tests plus harness fixtures; live read-only verifiers behind an explicit flag.

**Target Platform**: Operator's own machine (macOS/Linux), CLI via `python run.py ...`. Two AgentSwitch instances: Suryodaya (India) and Keystone (US), selected by `.env`.

**Project Type**: CLI agent plus test harness (single project).

**Performance Goals**: A graded-question run finishes with its finding persisted in under 3 minutes (spec SC-008). Plan target: under 90 seconds typical, via batched/parallel paginated reads.

**Constraints**: Step budget of 20 model turns; 180-second wall-clock deadline; default read page size 200 (platform default is 20 and silently truncates); no writes unless the operator opts in; no writes to rows this team did not create when running the harness.

**Scale/Scope**: About 101 projects on Suryodaya per gap_report.md; tasks, allocations and timesheets are larger. Entities are paged, never sampled.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design (below).*

| # | Principle | How this plan satisfies it | Status |
|---|-----------|----------------------------|--------|
| I | State Over Prose | `agent/findings.py::record_finding` writes a structured finding (lists of project ids / employee ids plus causes) to the platform; the loop refuses to end a run without one. Verifiers read it back by `run_id`. Contract: [contracts/finding-schema.md](./contracts/finding-schema.md). | PASS |
| II | Re-Read Before Write | All writes go through the single function `agent/safety.py::guarded_update`. It re-fetches the row, compares `updated_at` and `status` with the snapshot taken at proposal time, and returns `changed_underneath` instead of writing. After the first conflict, every later write in the run is refused. It re-reads again after writing to confirm persistence. | PASS |
| III | Capability Probed | `agent/safety.py::probe_capability` checks the live tool catalogue first, then REST status for the entity: 403 -> `not_visible`, 404 -> `unknown_name`. Never merged. A wrong operation name on a visible entity resolves to that entity's real operation set (tasks.md T017/T020) rather than a generic error. Used before any optional entity read (CRM, Timesheet) and before any write. | PASS |
| IV | Escalate, Never Fabricate | `agent/safety.py::escalate` lists the platform's escalation assignees; if none exist it returns `raised: false, reason: no_assignee` and the summary says so. `record_finding` is refused until a required escalation was attempted; a failed escalation is itself recorded. | PASS |
| V | Bounded Runs | `RunBudget` holds a step limit (20) and a monotonic deadline (180 s). `ReadDedup` short-circuits identical repeated reads. In the last 2 steps or last 20 s the loop forces `record_finding` via forced tool choice. A timeout or model error still writes a `status: partial` finding. | PASS |
| VI | No Hardcoded Tenancy | `company_context` is the first tool each run (company, currency, country from the API). No currency symbols, holiday calendars or tenant names in code or prompts. Tool availability comes from `tools/list`. | PASS |
| VII | Scoped Change Only | Only files under `agent/`, `harness/`, `tests/`, `docs/`, `specs/` change. `AgentSwitch_team04-main/` is read-only reference and is not imported. Harness live mode never edits rows it did not create; offline mode writes nothing to the platform. Platform defects go to `docs/BUGS_FILED.md`. | PASS |
| - | Workflow: fixture and verifier before wiring | Each capability's task list starts with its fixture and verifier (see tasks phase). | PASS |
| - | Workflow: hand-written tests | `tests/` is hand-written only; AI-assisted fixtures are labelled as such in their `note` field, as Team 04 does. | PASS |

**Bounded read/write safety, in one place**

- *Reads*: paginated with `limit=200`, up to the platform maximum of 1000, with `total` checked so a truncated list is detected and reported, not silently analysed. Repeats with identical arguments return a cached note.
- *Writes*: opt-in (`--apply`), per-write human `y/n`, restricted to an allowed-id set derived from the proposal, executed only through `guarded_update`.
- *Escalation path*: locked / out-of-seat / conflicting / undatable -> `escalate()`; no assignee -> say so; failure -> recorded as an outcome.
- *Step budget*: 20 turns, 180 s, forced terminal `record_finding`.

**Post-design re-check (after Phase 1)**: unchanged, all PASS. The data model adds no write path other than `guarded_update` and `record_finding`. No violations, so the Complexity Tracking table is empty.

## Project Structure

### Documentation (this feature)

```text
specs/001-project-agent/
├── plan.md              # This file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   ├── platform-surface.md   # per capability: entities/endpoints read and written
│   ├── agent-tools.md        # the tools the model may call
│   ├── finding-schema.md     # persisted finding shape
│   └── cli.md                # run.py commands and exit codes
├── checklists/requirements.md
└── tasks.md             # created later by /speckit-tasks
```

### Source Code (repository root)

```text
agent/
├── __init__.py
├── mcp_client.py        # EXISTING - extend: REST status probe, retry on transient errors, parallel page fetch
├── ai_models.py         # EXISTING - unchanged except forced tool_choice support if missing
├── loop.py              # REWRITE - bounded loop, tool dispatch, forced finding
├── tools.py             # NEW - tool specs the model sees + dispatch table to domain/data
├── data.py              # NEW - fetch layer: MCP reads -> plain dict bundles for the domain
├── safety.py            # NEW - RunBudget, ReadDedup, probe_capability, guarded_update, escalate
├── findings.py          # NEW - record_finding / read_finding
└── domain/              # NEW - pure functions, no I/O
    ├── __init__.py
    ├── dates.py         # today injection, 7-day window, working-day helpers
    ├── integrity.py     # task integrity scan (FR-004)
    ├── behind.py        # behind-schedule projects + causes (FR-001)
    ├── overload.py      # per-employee per-day load vs capacity (FR-002, 005, 006)
    ├── critical_path.py # local single-predecessor what-if + comparison to platform CP (FR-007)
    ├── reschedule.py    # proposals + writability classification (FR-009)
    ├── evm.py           # planned / actual / earned value (FR-010)
    └── delay.py         # structured delay facts the LLM narrates (FR-011)

harness/
├── runner.py            # EXISTING - extend: --offline, --task, --instance, writes verdict.json after result.json is fsynced
├── verifiers.py         # EXISTING - keep the hand-written refusal/consistency checks
├── verifiers_state.py   # NEW - predicate-style checks that read the persisted finding and recompute truth independently
├── fakes.py             # NEW - FakeMcp serving fixture data, including injectable concurrent edits
├── tasks.json           # EXISTING - extend with the new task ids
├── fixtures/            # NEW - seeded JSON datasets (behind/on-track/overloaded/capacity-unknown/locked/etc.)
└── runs/                # trace.jsonl, result.json, verdict.json per run (git-ignored)

tests/                   # NEW - hand-written pytest: domain/ and safety.py, no network
docs/                    # NEW - ARCHITECTURE.md, BUGS_FILED.md (platform defects we find)
gap_report.md            # EXISTING - kept current as limits are discovered
run.py                   # EXISTING - add `agent --apply`, `test --offline`, `verify`
```

**Structure Decision**: Single Python project that keeps the repo's existing `agent/` + `harness/` + `run.py` layout, so nothing already working is moved. The new work is additive: a `domain/` package (the Team 04 `domain.py` role, split by capability because we have eight of them), plus `safety.py` to hold the guards Team 04 scattered through `domain.py` and `agent.py`.

## Complexity Tracking

No Constitution Check violations. Table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| - | - | - |
