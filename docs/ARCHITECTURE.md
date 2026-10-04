# Architecture: Seat 14 Project Agent

Layers (mirrors Team 04's four-layer split):

- **Transport** (`agent/mcp_client.py`): `urllib`-only MCP JSON-RPC client. Unwraps `structuredContent`, retries 429/5xx with backoff, `call_tool_all` pages with `limit=200` and reports `truncated`, `rest_status` separates 403 (`not_visible`) from 404 (`unknown_name`).
- **Domain** (`agent/domain/`): pure functions over an immutable `Snapshot` — never network, never LLM, never clock. `integrity`, `behind`, `overload`, `critical_path` (local what-if), `reschedule` (proposals + writability), `evm`, `delay` (narrative facts only), `status` (one fact object, two framings). `dates.py` takes `as_of` as a parameter.
- **Safety** (`agent/safety.py`): `RunBudget` (20 steps / 180 s, forced `record_finding` at 2 steps or 20 s left), `ReadDedup`, `probe_capability`, `guarded_update` (re-read → compare → write → re-read), `escalate` (honest `no_assignee`).
- **Loop** (`agent/loop.py`): bounded tool loop with parallel tool calls per turn. The model picks tools and writes the closing summary; it never builds requests. Every run ends with exactly one persisted finding (`complete`/`partial`/`escalated`/`refused`).
- **Tools** (`agent/tools.py`): the only surface the model sees (`company_context`, `load_snapshot`, `schedule_integrity`, `behind_schedule_projects`, `overloaded_next_week`, `critical_path_check`, `propose_reschedule`, `apply_proposal`, `evm_summary`, `delay_facts`, `status_report_facts`, `seat_capability`, `escalate`, `record_finding`). Unknown names/bad args return error dicts, never raise.
- **Findings** (`agent/findings.py`): `validate_finding` (dated cause required, overload/capacity_unknown disjoint, ids exist in snapshot, no credentials), `record_finding` (one `AgentMemory` row, `category fact`/`source system`/numeric `importance`), `read_finding` (by `run_id`).
- **Harness** (`harness/`): offline `FakeMcp` + `ScriptedModel` + JSON fixtures with independent `expected` blocks; state verifiers recompute truth on a different code path from `domain/`; `runner.py` writes `task.json` → `trace.jsonl` → fsync `result.json` → `verdict.json`; `verify.py` re-grades stored runs against live data.

## Where to change what

| Want | Touch |
|---|---|
| New graded answer | fixture + task + verifier, then `domain/` fn, then tool, then finding assembly |
| New write | `guarded_update` path only; proposal in `domain/reschedule.py`, gate ids in `RunState` |
| New narrative | `domain/delay.py` facts + prompt rule in `loop.py SYSTEM_PROMPT`; never free-form model facts |
| Predicate reads X | only `agent/findings.py` storage call (T010a gate); schema stays |
| Live field renamed | `docs/ENTITY_MAP.md` → `data-model.md` + fixture keys + domain accessor fallbacks |
