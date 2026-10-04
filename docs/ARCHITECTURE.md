# Architecture

Four layers, mirroring Team 04's `prod_agent/` split (reference only -
no code or runtime is shared with that team's seat):

```
agent/mcp_client.py   transport: AgentSwitchClient (login, call_tool,
                       call_tool_all w/ pagination+truncation+retry,
                       rest_status for 403-vs-404 probing)
agent/config.py        instance table, .env loading, run constants
agent/redact.py         strip secrets from anything headed to a trace/finding

agent/domain/           PURE functions, no I/O, no clock reads:
  types.py              Snapshot, Cause, BehindProject, EmployeeLoad,
                         OverloadResult, Proposal, CriticalPathDelta,
                         EvmRow, DelayFacts
  dates.py               date parsing, next_seven_days(as_of)
  integrity.py            schedule integrity scan
  behind.py               behind-schedule detection (GRADED)
  overload.py             overload-next-week detection (GRADED)
  critical_path.py        (not yet implemented - Phase 5)
  reschedule.py           (not yet implemented - Phase 5)
  evm.py / delay.py       (not yet implemented - Phase 6)

agent/data.py           load_snapshot(client, scope) - the only place
                         that calls call_tool_all for list entities
agent/safety.py          RunBudget, ReadDedup, probe_capability,
                         WriteGate + guarded_update, escalate
agent/findings.py        assemble_finding, validate_finding,
                         record_finding, read_finding
agent/tools.py           tool registry + dispatch table the model can call
agent/loop.py            run_agent(): the bounded LLM loop
agent/ai_models.py       OpenAI/Anthropic/Google chat clients (existing,
                         extended with force_tool for forced tool_choice)

harness/fakes.py         FakeMcp (offline transport), ScriptedModel
                         (offline model) - SAME call surface as the real
                         ones, so loop.py runs identically in tests
harness/fixtures.py      loads harness/fixtures/*.json
harness/fixtures/*.json  {note, as_of, data, expected[, entity_statuses,
                         entity_total_overrides]}
harness/tasks/*.json     {id, note, instances, mode, prompt, fixture,
                         script, verifier, checks} - see
                         harness/tasks/README.md
harness/verifiers_state.py   state-based verifiers: recompute truth with
                         plain loops (NOT by importing agent/domain/),
                         compare to the stored finding
harness/verifiers.py     ORIGINAL prose-based verifiers (untouched),
                         used only by the old flat harness/tasks.json
harness/runner.py        run_tasks(mode, task_id, instance): drives
                         offline or live task runs, writes
                         harness/runs/<ts>-<instance>/{task,trace,
                         result,verdict}.json
harness/verify.py        run.py verify <run_dir>: live re-check of a
                         stored finding
run.py                   CLI: check / agent / test / verify
```

## Where to change what

- A new graded-answer rule -> `agent/domain/*.py` (pure function) plus
  its hand-written test in `tests/`.
- A new tool the model can call -> `agent/tools.py` (schema + dispatch
  entry) - never let the model pass a raw entity name or filter string.
- A new write path -> MUST go through `agent/safety.py::guarded_update`.
  No other write path exists; this is enforced by review, not by code
  (grep `call_tool.*\.update` outside `safety.py` before merging).
- A new finding field -> `agent/findings.py::assemble_finding` AND
  `contracts/finding-schema.md`, in the same change.
- A new offline-gradable scenario -> a fixture in `harness/fixtures/`,
  a task in `harness/tasks/`, and (if genuinely new logic) a verifier in
  `harness/verifiers_state.py`. Written and seen failing before the
  domain function that makes it pass.

## Known deviations / incomplete work (be upfront about these)

- **T010a (predicate source) is unconfirmed** - no live network access
  during this implementation pass. See `docs/ENTITY_MAP.md`. The
  finding schema was built swappable for this reason.
- **Phases 5-7 (critical-path reschedule, EVM/delay narrative, status
  report) are not implemented.** Phases 1-4 (Setup, Foundational, both
  graded predicates) are complete and offline-tested; see
  `specs/001-project-agent/tasks.md` for the checkbox state.
- **No live run has happened against a real AgentSwitch instance** -
  `python run.py check`, `python run.py agent`, and `python run.py
  verify` are implemented and should work, but are unverified against
  the real platform (T009, T050, T060, T077, T089, T095, T102 all
  require that and are unchecked).
- `scripts/snapshot_schemas.py` has not been run.
