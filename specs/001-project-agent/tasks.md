# Tasks: Project Agent (Seat 14)

**Input**: Design documents from `/specs/001-project-agent/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included. The constitution requires an offline harness fixture and verifier for every capability before it is wired into the live loop, and requires hand-written tests (AI-generated tests earn no credit). Test and verifier tasks therefore come **before** the implementation they check, and must be seen failing first.

**On "hand-written" labels below**: a task description saying "(hand-written)" states the
*credit requirement* for that test, not a claim about who typed the first draft. If an
AI assistant (including via `/speckit-implement`) drafts a test marked "(hand-written)",
a team member MUST read it, understand it, and explicitly sign off on it as the actual
test case they intend before it counts toward hand-written credit — otherwise it must be
relabeled `(AI-assisted)` per T104 below and claims no hand-written credit.

**Organization**: One phase per priority tier you asked for. Spec story IDs are kept so tasks trace back to `spec.md`.

| Tier | Phase | Spec stories |
|------|-------|--------------|
| P1 | Phase 3 - `project.behind_schedule` | US1 (+ US3 integrity scan, which produces its causes) |
| P2 | Phase 4 - `project.overloaded_next_week` | US2 |
| P3 | Phase 5 - critical-path-aware reschedule | US5 + US6 |
| P4 | Phase 6 - EVM proxy + delay narrative | US7 + US4 |
| P5 | Phase 7 - role-specific status report | US8 |

## Format: `- [ ] T### [P?] [Story?] Description with file path`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- Paths follow plan.md "Source Code". `agent/` and `harness/` already exist; "extend" means edit the existing file, "create" means new.

---

## Phase 1: Setup (client, config, project scaffolding)

**Purpose**: Mirror Team 04's `config.py` + `mcp_client.py` roles on top of the existing scaffold.

- [X] T001 Add `requirements-dev.txt` (pytest) and a root `conftest.py` that puts the repo root on `sys.path`; create empty `tests/__init__.py`
- [X] T002 [P] Create `agent/config.py`: instance table (`suryodaya`, `keystone`) read from `.env`, `.env` loader that ignores comments, run constants (`MAX_STEPS=20`, `DEADLINE_S=180`, `PAGE_SIZE=200`, `OVERRUN_RATIO=1.5`, `FINDING_PREFIX="PROJECT_AGENT_FINDING:"`, `HARNESS_MARKER="team14-harness"`), and credential lookup per instance
- [X] T003 [P] Create `.env.example` (variable names only, no values) and confirm `.gitignore` excludes `.env`, `harness/runs/`, `__pycache__/`
- [X] T004 [P] Create `agent/redact.py`: function that strips bearer tokens, passwords and key-shaped strings from any dict or string before it is written to a trace
- [X] T005 Extend `agent/mcp_client.py`: build the client from `config` (instance selection), retry transient network errors with backoff, and make `call_tool_all` fetch remaining pages in parallel once `total` is known
- [X] T006 Extend `agent/mcp_client.py`: make `call_tool_all` return `fetched`, `total` and a `truncated` flag (fetched < total) instead of silently returning a short list
- [X] T007 Extend `agent/mcp_client.py`: add `rest_status(entity)` doing an independent REST `GET /api/<entity>` and returning the HTTP status (used to tell 403 from 404)
- [X] T008 [P] Create `scripts/snapshot_schemas.py` that fetches `GET /api/schemas` and writes the fields of Task, Project, Milestone, ProjectResourceAllocation, ProjectResourceProfile, CalendarEvent, Timesheet and AgentMemory to `docs/ENTITY_MAP.md`
- [ ] T009 Run `scripts/snapshot_schemas.py` on both instances; correct any field names in `specs/001-project-agent/data-model.md` and `contracts/platform-surface.md` that differ from the live schema (status vocabularies, allocation hours source, project end-date field)
- [ ] T010 Extend `run.py` `check` command: accept `--instance`, probe `AgentMemory.create`, the escalation assignee endpoint, and the shape of `endpoint.projects.critical_path` / `endpoint.projects.client_status_report`; print seat capabilities; exit 2 on failure. Record results in `docs/ENTITY_MAP.md`
- [ ] T010a **GATE - blocks T046, T057, T074 (finding assembly)**: Confirm via the API explorer/`redoc`, course staff, or a deliberate probing call what `project.behind_schedule` and `project.overloaded_next_week` actually read (entity, and whether they expect a flat id list or a nested shape like `causes`). Record the confirmed source and shape in `docs/ENTITY_MAP.md`. If it is not `AgentMemory` with our assumed shape, update only the storage call in `agent/findings.py` and the fields the finding exposes at its top level — do not change `contracts/finding-schema.md`'s internal `causes`/`days` detail unless the predicate itself requires it
- [X] T011 Extend `run.py` argument parsing for `agent "<question>" [--instance] [--apply] [--escalate]`, `test [--offline|--live] [--task]`, `verify <run_dir>` per `contracts/cli.md` (handlers may be stubs that print "not implemented")

**Checkpoint**: `python run.py check` reports connectivity, finding storage and escalation visibility for both instances; schema doc exists; T010a's confirmed predicate source and shape are recorded in `docs/ENTITY_MAP.md` before any Phase 3/4 finding-assembly task starts.

---

## Phase 2: Foundational (domain base, safety primitives, harness base, loop)

**Purpose**: Everything every story shares. No story work starts before this phase passes.

**CRITICAL**: Constitution principles I, II, III, IV, V live here.

### Domain base and data layer

- [X] T012 [P] Create `agent/domain/__init__.py` and `agent/domain/types.py` with the dataclasses from `data-model.md`: `Snapshot`, `IntegrityFlag`, `Cause`, `BehindProject`, `EmployeeLoad`, `OverloadResult`, `Proposal`, `CriticalPathDelta`, `EvmRow`, `DelayFacts`
- [X] T013 [P] Create `agent/domain/dates.py`: parse platform date/datetime strings, `as_of` passed in (never read the clock inside `domain/`), `next_seven_days(as_of)` (tomorrow through +7), weekday-name lookup for capacity fields
- [X] T014 Create `agent/data.py`: `load_snapshot(client, scope)` for scopes `projects`, `capacity`, `money`; paginated reads via `call_tool_all`; fills `Snapshot.truncated`; caches per run; returns plain dicts only

### Safety primitives (agent/safety.py)

- [X] T015 [P] Create `tests/test_budget_dedup.py` (hand-written): `RunBudget` reports `must_finalize()` at 2 steps left or 20 s left; `ReadDedup` returns a note for an identical repeated read and runs a read with different arguments; use an injected clock
- [X] T016 [P] Create `tests/test_guarded_update.py` (hand-written): re-read happens before every write; changed `updated_at` -> `changed_underneath` and no write; changed `status` -> `changed_underneath`; after one conflict every later write is `refused`; id outside the allowed set -> `refused`; post-write re-read mismatch -> `write_not_persisted`
- [X] T017 [P] Create `tests/test_capability_probe.py` (hand-written): 403 -> `not_visible`, 404 -> `unknown_name`, tool present and reachable -> `ok`; the two failure outcomes are never merged; a wrong operation name on a visible entity (e.g. `Task.updat`) returns the entity's real operation set instead of a generic error, per Constitution Principle III
- [X] T018 [P] Create `tests/test_escalation.py` (hand-written): assignee list empty -> `raised: false, reason: no_assignee`; platform refusal inside a success envelope -> `raised: false`; success -> number and assignee returned
- [X] T019 Implement `RunBudget` and `ReadDedup` in `agent/safety.py` until T015 passes
- [X] T020 Implement `probe_capability(client, entity, op)` in `agent/safety.py` using the tool catalogue plus `rest_status`; when the entity is visible but `op` is not a real operation on it, resolve and return the entity's actual operation list from the tool catalogue (e.g. by matching `{entity}.` prefixes in `tools/list`) rather than a bare error, until T017 passes
- [X] T021 Implement `WriteGate` and `guarded_update(client, proposal, gate)` in `agent/safety.py` (re-read, compare `updated_at` and `status`, write, re-read to confirm), until T016 passes
- [X] T022 Implement `escalate(client, reason, reason_code)` in `agent/safety.py` (list assignees, raise, honest `no_assignee` result), until T018 passes

### Finding persistence (agent/findings.py)

- [X] T023 [P] Create `tests/test_findings_contract.py` (hand-written): a finding with an empty `causes` list is rejected; a project with no dated cause is rejected; an employee in both `overloaded_employees` and `capacity_unknown_employees` is rejected; an id absent from the snapshot is rejected; the serialized content carries no credentials
- [X] T024 Create `agent/findings.py`: `validate_finding(finding, snapshot)` per `contracts/finding-schema.md` rules 1-6, `record_finding(client, run_id, finding)` writing one `AgentMemory` row, `read_finding(client, run_id)`; refuses to record when a required escalation has not been attempted; until T023 passes

### Harness base (offline mode)

- [X] T025 [P] Create `harness/fakes.py`: `FakeMcp` with the same `call_tool` / `call_tool_all` / `rest_status` surface as the real client, serving a fixture; supports `on_read(entity, id)` hooks to inject a concurrent edit, a write log, and a controllable clock/latency
- [X] T026 [P] Create `harness/fixtures.py`: load a fixture JSON from `harness/fixtures/`, validate it has a `data` block and an independently authored `expected` block, and apply the `note` label ("hand-written" or "AI-assisted")
- [X] T027 Extend `harness/runner.py`: add `--offline` / `--live`, `--task`, `--instance`; create `harness/runs/<timestamp>-<instance>/`; write `task.json`, then `trace.jsonl` event by event, then fsync `result.json`, and only then write `verdict.json` (`approve` / `revise` / `unevaluated`; `unevaluated` never counts as a pass)
- [X] T028 [P] Create `harness/verifiers_state.py`: verifier registry, helper to read the stored finding by `run_id`, helper to load `expected` from a fixture, and the rule that a missing finding yields `revise`. Keep the existing prose-based `harness/verifiers.py` untouched for the refusal and data-reread checks
- [X] T029 Create `harness/tasks/README.md` describing the task JSON format used below (`id`, `note`, `instances`, `mode`, `prompt`, `fixture`, `verifier`, `checks`), mirroring Team 04's `harness/tasks/README.md`

### Tool layer and bounded loop

- [X] T030 Create `agent/tools.py`: tool registry with the compact argument schemas from `contracts/agent-tools.md`; the dispatch table maps each tool name to one function; unknown tool names and bad arguments return an error result, never an exception; tool calls from one model turn run in parallel
- [X] T031 [P] Implement the `company_context` and `seat_capability` tools in `agent/tools.py` (company, country, currency from the API; capability via `probe_capability`)
- [X] T032 Verify and, if missing, add forced `tool_choice` support for each provider in `agent/ai_models.py`; add a scripted fake model `harness/fakes.py::ScriptedModel` that replays a list of tool calls for loop tests
- [X] T033 [P] Create `tests/test_loop_bounded.py` (hand-written, uses `ScriptedModel` and `FakeMcp`): a model that never stops calling tools still ends with a stored `partial` finding at 20 turns; a deadline hit ends with a stored finding; a model exception ends with a stored `partial` finding; `record_finding` is called exactly once; the forced-finding turn is used near the budget
- [X] T034 Rewrite `agent/loop.py`: `run_agent(client, model, question, options)` with `RunBudget`, `ReadDedup`, parallel tool execution, forced `record_finding` near the limits, a `partial` finding built from stored domain results on any failure, and a system prompt containing no tenant, currency or country text (uses `company_context`); keep a `main()` for `python run.py agent`; until T033 passes
- [X] T035 Wire `run.py agent` to `agent.loop.run_agent`, write the run directory via the runner's trace writer, apply `agent/redact.py` to every trace event, and map outcomes to exit codes 0 / 1 / 2

**Checkpoint**: `pytest tests/ -q` passes for budget, dedup, guarded update, probe, escalation, findings and bounded loop; `python run.py agent` with a scripted offline model stores a finding.

---

## Phase 3: P1 - Which projects are behind schedule (US1, with US3 integrity scan) 🎯 MVP

**Goal**: The agent returns exactly the projects that are behind, each with a dated cause, and stores that as a finding. Answers the first graded predicate.

**Independent Test**: `python run.py test --offline --task behind_schedule_basic` approves, and `python run.py agent --instance suryodaya` followed by `python run.py verify <run_dir>` approves against live data.

### Fixtures, verifier and tests first (write these, watch them fail)

- [X] T036 [P] [US1] Create `harness/fixtures/behind_basic.json`: projects with an overdue open task; all tasks on track; a task blocked by an overdue predecessor; a task blocked by a cancelled predecessor; a project with a missed milestone; a project with no tasks or milestones; a project with two simultaneous causes; plus an independently authored `expected` list of behind project ids and causes
- [X] T037 [P] [US1] Create `harness/fixtures/truncated_projects.json`: `total` larger than the rows returned, to prove truncation is reported
- [X] T038 [P] [US1] Create `harness/tasks/behind_schedule_basic.json` and `harness/tasks/behind_schedule_truncated.json` (prompt "Which projects are behind schedule?", fixture, verifier name, `checks` text)
- [X] T039 [US1] Add `behind_schedule_matches` to `harness/verifiers_state.py`: recompute the behind set from the fixture with plain loops (a different code path from `agent/domain/`), then check the stored finding lists exactly that set, every entry has a dated cause, the no-data project is under `insufficient_data_projects`, and `status` is `partial` for the truncated task
- [X] T040 [P] [US3] Create `tests/test_integrity.py` (hand-written): no assignee and no due date are two separate flags; predecessor cancelled and predecessor overdue each flagged; `logged_hours` of exactly 150% of the reference is not flagged and 151% is; reference falls back from `budget_hours` to `estimated_hours`; both missing yields a `no_baseline_hours` note, not a flag
- [X] T041 [P] [US1] Create `tests/test_behind.py` (hand-written): each fixture project classified correctly; a project with only integrity flags and no dated cause is not behind; a project with no tasks or milestones is `insufficient_data`; multiple causes are all reported; primary cause is the dated cause with the most days late
- [X] T042 [P] [US1] Create `harness/tasks/refuse_payroll.json` and `harness/tasks/refuse_manufacturing.json` plus a verifier `refused_with_finding` in `harness/verifiers_state.py`: no domain tool called, boundary statement given, finding `status: refused` stored (spec FR-013)

### Implementation

- [X] T043 [P] [US3] Implement `agent/domain/integrity.py` (`scan(snapshot, project_id=None)` returning `IntegrityFlag` records) until T040 passes
- [X] T044 [US1] Implement `agent/domain/behind.py` (`behind_projects(snapshot)` using integrity flags as contributing causes only) until T041 passes
- [X] T045 [US1] Add `load_snapshot` scope `projects` handling to `agent/data.py` if not already complete, and tools `schedule_integrity` and `behind_schedule_projects` to `agent/tools.py`; the latter stores its result for the final finding
- [X] T046 [US1] **Requires T010a confirmed.** Add the behind-schedule section to finding assembly in `agent/findings.py` (`behind_projects`, `insufficient_data_projects`, `integrity_summary`, `limits.truncated`); set `status: partial` when any read was truncated
- [X] T047 [US1] Implement the refusal path in `agent/loop.py`/`agent/tools.py`: before answering, use `seat_capability` on the entity implied by the request; if `not_visible`, give the boundary statement and store a `refused` finding; until T042 passes
- [X] T048 [US1] Run `python run.py test --offline --task behind_schedule_basic`, `behind_schedule_truncated`, `refuse_payroll`, `refuse_manufacturing`; fix until all four verdicts are `approve`
- [ ] T049 [US1] Implement `python run.py verify <run_dir>` in `harness/verify.py` and `run.py`: re-read live Projects/Tasks/Milestones, recompute the behind set independently, compare with the finding read back from `AgentMemory`
- [ ] T050 [US1] Live read-only run on Suryodaya then Keystone (`python run.py agent --instance ...` then `verify`); confirm elapsed time is under 180 s; record any discrepancy, platform limit or unclear status value in `gap_report.md` with an evidence label (documented / observed / inferred / untested)

**Checkpoint**: Predicate 1 is answered, stored, offline-graded and live-verified. This is the MVP; stop here and demo if time runs out.

---

## Phase 4: P2 - Who is overloaded next week (US2)

**Goal**: The agent returns the employees whose allocated hours exceed capacity on any of the next 7 days, summed across projects, with capacity-unknown employees listed separately. Answers the second graded predicate.

**Independent Test**: `python run.py test --offline --task overloaded_next_week_basic` approves, then live `agent` + `verify` approves.

### Fixtures, verifier and tests first

- [X] T051 [P] [US2] Create `harness/fixtures/overload_basic.json`: an employee over capacity on one day; an employee within capacity all week; an employee split over two projects who is overloaded only in total; an employee with allocations and no capacity profile; a zero-capacity weekend day with an allocation; a calendar block crossing midnight; a block outside the 7-day window; plus an independently authored `expected` block
- [X] T052 [P] [US2] Create `harness/tasks/overloaded_next_week_basic.json` (prompt "Who is overloaded next week?")
- [X] T053 [US2] Add `overloaded_matches` to `harness/verifiers_state.py`: recompute per-employee per-day totals with plain loops, check the stored overloaded set, per-day excess within 0.01 h, capacity-unknown set, and that the two sets are disjoint
- [X] T054 [P] [US2] Create `tests/test_overload.py` (hand-written): cross-project sum; over on one day only still counts; exactly at capacity is not overloaded; capacity-unknown excluded from overloaded and listed separately; multi-day block split across days; blocks outside the window ignored; window is tomorrow through +7 for a given `as_of`

### Implementation

- [X] T055 [US2] Implement `agent/domain/overload.py` (`overloaded(snapshot, as_of)` returning `OverloadResult`) until T054 passes
- [X] T056 [US2] Extend `agent/data.py` `load_snapshot` scope `capacity` (allocations, calendar events, profiles) and add tool `overloaded_next_week` to `agent/tools.py`
- [X] T057 [US2] **Requires T010a confirmed.** Add the overload section to finding assembly in `agent/findings.py` (`window`, `overloaded_employees`, `capacity_unknown_employees`) and the disjointness check in `validate_finding`
- [X] T058 [US2] Update the system prompt in `agent/loop.py` so the combined graded request ("which projects are behind and who is overloaded next week") calls both tools and records one finding
- [X] T059 [US2] Run `python run.py test --offline --task overloaded_next_week_basic` until `approve`; re-run the Phase 3 tasks to confirm no regression
- [ ] T060 [US2] Extend `harness/verify.py` to recompute overload from live data; run live on both instances; document how allocation hours are really expressed (calendar event vs hours field), time zone handling, and any mismatch in `docs/ENTITY_MAP.md` and `gap_report.md`

**Checkpoint**: Both graded predicates are answered, stored, offline-graded and live-verified.

---

## Phase 5: P3 - Critical-path-aware reschedule proposals (US5 + US6)

**Goal**: Before any date change the agent says whether the project finish moves and by how many days; where the seat may write it applies the change safely after approval, otherwise it escalates or states the limit.

**Independent Test**: The offline tasks `critical_path_unaffected`, `critical_path_slips`, `reschedule_applies`, `concurrent_edit_before_write` and `locked_task_escalates` all approve.

### Fixtures, verifiers and tests first

- [ ] T061 [P] [US5] Create `harness/fixtures/critical_path.json`: a project with a predecessor chain; one off-path task with slack; one on-path task; with independently authored expected finish dates and slip days
- [ ] T062 [P] [US6] Create `harness/fixtures/reschedule.json`: an editable task, a locked task (platform refuses the update), a task whose row will be edited between read and write, and an escalation assignee list (second variant with none)
- [ ] T063 [P] [US5] Create `harness/tasks/critical_path_unaffected.json` and `harness/tasks/critical_path_slips.json`
- [ ] T064 [P] [US6] Create `harness/tasks/reschedule_applies.json`, `harness/tasks/concurrent_edit_before_write.json`, `harness/tasks/locked_task_escalates.json`, `harness/tasks/locked_task_no_assignee.json`, `harness/tasks/decline_write.json`
- [ ] T065 [US5] Add `critical_path_matches` to `harness/verifiers_state.py`: independent longest-path recomputation; check the reported delta, and that no write occurred during evaluation (FakeMcp write log is empty)
- [ ] T066 [US6] Add `reschedule_outcomes` to `harness/verifiers_state.py`: on conflict no write and no later writes; on approval the row's new date equals the proposal; on decline nothing changed; no write outside the allowed id set; locked task produced an escalation record or an honest "no assignee"; a claimed handover without an escalation fails; for a live `fixture_owned` run, additionally assert the harness-owned project does not appear in a fresh `behind_schedule_projects`/`overloaded_next_week` call against the live company (fixes analysis finding G2) and that cleanup removed it
- [ ] T067 [P] [US5] Create `tests/test_critical_path.py` (hand-written): off-path change gives 0 days; on-path change gives the exact slip; moving a task earlier gives 0 slip; project with no chain returns `insufficient_data`; cancelled predecessors are handled
- [ ] T068 [P] [US6] Create `tests/test_reschedule.py` (hand-written): overload-driven proposal moves the lowest-impact task first; proposals carry `snapshot_updated_at` and `snapshot_status`; locked or out-of-seat task gets `writable_by_seat: false` with a reason

### Implementation

- [ ] T069 [US5] Implement `agent/domain/critical_path.py` (local what-if over the single-predecessor chain; compare with the platform critical-path result passed in) until T067 passes
- [ ] T070 [US6] Implement `agent/domain/reschedule.py` (`propose(snapshot, finding_ref)` returning `Proposal` records with writability classification) until T068 passes
- [ ] T071 [US5] Add tool `critical_path_check` to `agent/tools.py`: read the platform critical path as baseline, run the local what-if, return a `CriticalPathDelta`; no write
- [ ] T072 [US6] Add tools `propose_reschedule`, `apply_proposal` and `escalate` to `agent/tools.py`; `apply_proposal` requires `--apply`, shows the critical-path delta first, asks the operator `y/n`, then calls `guarded_update`; declined means no write
- [ ] T073 [US6] After an applied write, re-read the platform critical path and attach `platform_cp_after` to the `CriticalPathDelta`; report predicted versus actual
- [ ] T074 [US6] Add the proposals and escalations sections to finding assembly in `agent/findings.py`; make `record_finding` refuse until a required escalation has been attempted, and record a failed escalation as an outcome
- [ ] T075 [US6] Implement live fixture rows in `harness/fixtures.py`: rows this team creates carry `HARNESS_MARKER`, live in a dedicated project created by the harness (never an existing/shared project), and are the only rows a live harness run may write; every such task row's dates are set in the future (never overdue) and its project is excluded from `behind_schedule_projects`/`overloaded_next_week` scope by name/marker, so a live fixture run cannot change what either graded predicate sees elsewhere in the company; rows and the dedicated project are deleted in a `finally` block after the run, pass or fail; add `fixture_owned: true` handling to the runner
- [ ] T076 [US5] Run the five offline tasks until all `approve`; re-run Phases 3 and 4 tasks for regressions
- [ ] T077 [US6] Live `--apply` walkthrough on a harness-owned task only: confirm the post-write re-read, the audit-trail attribution, and cleanup; note platform limits (locked states, `reschedule_jobs` availability) in `gap_report.md`

**Checkpoint**: The agent proposes only changes it has checked, writes only through `guarded_update`, and never claims a change or a handover that did not happen.

---

## Phase 6: P4 - EVM proxy and delay narrative (US7 + US4)

**Goal**: Per-project cost health, and a grounded explanation of what drove a slip.

**Independent Test**: Offline tasks `evm_basic` and `delay_narrative_grounded` approve.

### Fixtures, verifiers and tests first

- [ ] T078 [P] [US7] Create `harness/fixtures/evm_basic.json`: projects with timesheets at known rates, partial completion, one over-spending project, one with missing budget; independently authored expected planned / actual / earned values
- [ ] T079 [P] [US4] Create `harness/fixtures/delay_basic.json`: a project with one primary blocker and two secondary causes, with dates
- [ ] T080 [P] [US7] Create `harness/tasks/evm_basic.json`; [P] [US4] create `harness/tasks/delay_narrative_grounded.json`
- [ ] T081 [US7] Add `evm_matches` to `harness/verifiers_state.py` (independent arithmetic: `actual = sum(hours * rate)`, `earned = percent_complete * budget`)
- [ ] T082 [US4] Add `delay_grounded` to `harness/verifiers_state.py`: every task and milestone id cited in the narrative exists in the project, the primary blocker is named first, secondary causes are labelled secondary, and no id outside the project appears
- [ ] T083 [P] [US7] Create `tests/test_evm.py` (hand-written): actual cost arithmetic, earned value rule, over-spending flag when earned < actual, `insufficient_data` when budget or rate is missing
- [ ] T084 [P] [US4] Create `tests/test_delay.py` (hand-written): primary versus secondary ordering, timeline sorted by date, every item carries a record id

### Implementation

- [ ] T085 [US7] Implement `agent/domain/evm.py` until T083 passes; extend `load_snapshot` scope `money` in `agent/data.py` (timesheets)
- [ ] T086 [US4] Implement `agent/domain/delay.py` (`delay_facts(snapshot, project_id)`) until T084 passes
- [ ] T087 [US7] Add tool `evm_summary` and [US4] tool `delay_facts` to `agent/tools.py`
- [ ] T088 [US4] Add the narrative instruction to the system prompt in `agent/loop.py`: use only fields from `delay_facts`, cite record ids, label primary and secondary
- [ ] T089 [US7] Run `evm_basic` and `delay_narrative_grounded` offline until `approve`; run one live read-only check of each on a real project and note differences in `gap_report.md`

**Checkpoint**: Cost health and delay explanations are available and checked against independently computed facts.

---

## Phase 7: P5 - Role-specific status report (US8)

**Goal**: The same facts, framed for a sponsor or for the project team.

**Independent Test**: Offline task `status_two_audiences` approves.

- [ ] T090 [P] [US8] Create `harness/fixtures/status_report.json` (reuses a behind project from `behind_basic.json` plus a canned `endpoint.projects.client_status_report` response) and `harness/tasks/status_two_audiences.json`
- [ ] T091 [US8] Add `status_same_facts` to `harness/verifiers_state.py`: both audience versions contain the same blocker names and dates; the sponsor version contains no task-id pattern; the team version names the blocking tasks and next actions
- [ ] T092 [P] [US8] Create `tests/test_status_facts.py` (hand-written): the fact object passed to the model for both audiences is identical (equal by value); only the audience label differs
- [ ] T093 [US8] Add tool `status_report_facts` to `agent/tools.py`: returns the platform report (when visible via `seat_capability`) merged with `DelayFacts` and `EvmRow`; if the report endpoint is not visible, say so and use the derived facts
- [ ] T094 [US8] Add the audience-rewrite instruction to the system prompt in `agent/loop.py` (same facts, different framing, no new facts)
- [ ] T095 [US8] Run `status_two_audiences` offline until `approve`; one live read-only run; optionally link the project's customer from `crm` if the entity is visible, skipping silently when it is not

**Checkpoint**: All five tiers are delivered and independently gradable.

---

## Phase 8: Polish and cross-cutting

- [ ] T096 [P] Create `harness/tasks/budget_exhausted_still_records.json` and `harness/tasks/slow_reads_deadline.json` (FakeMcp latency pushes past 180 s) with a verifier asserting a `partial` finding is stored and elapsed time is within the limit (spec SC-006, SC-008)
- [X] T097 [P] Create `tests/test_redaction.py` (hand-written): no password, bearer token or key-shaped string survives into `trace.jsonl` or the stored finding
- [ ] T098 [P] Create `docs/ARCHITECTURE.md` (layers, tool list, where to change what, modelled on Team 04's file) and `docs/BUGS_FILED.md` (platform defects found, each with a reproducible case)
- [ ] T099 Update `gap_report.md` with the final evidence-labelled limits found during implementation (allocation hours source, missing filters, locked states, any predicate mismatch)
- [ ] T100 Update `README.md`: new commands, the offline harness, a pointer to `.specify/memory/constitution.md`, and remove the plaintext passwords from the file (rotate them separately)
- [ ] T101 Run the complete offline suite (`pytest tests/ -q` and `python run.py test --offline`); every verdict must be `approve`
- [ ] T102 Run `specs/001-project-agent/quickstart.md` scenarios 0-7 end to end on Suryodaya and Keystone; fix any drift between the documents and the behaviour
- [ ] T103 Spot-check the new code against Constitution principles I-V (finding always stored, single write path, probe before access, escalate honestly, bounded run) and note the result in `specs/001-project-agent/checklists/requirements.md` Notes
- [ ] T104 A team member reads every test file labelled "(hand-written)" in Phases 2-6 (`tests/test_budget_dedup.py`, `test_guarded_update.py`, `test_capability_probe.py`, `test_escalation.py`, `test_findings_contract.py`, `test_integrity.py`, `test_behind.py`, `test_overload.py`, `test_critical_path.py`, `test_reschedule.py`, `test_evm.py`, `test_delay.py`, `test_status_facts.py`, `test_redaction.py`) and either signs off (file stays "(hand-written)") or relabels it "(AI-assisted)" in a header comment if it was not actually authored by a person; record the outcome per file in `specs/001-project-agent/checklists/requirements.md` Notes

---

## Dependencies and execution order

### Phase dependencies

- **Phase 1 -> Phase 2 -> everything else.** Phase 2 blocks all story phases.
- **Phase 3 (P1)** needs Phase 2 only. It is the MVP.
- **Phase 4 (P2)** needs Phase 2 only; it reuses `findings.py`, `tools.py`, `data.py` extension points, so run it after Phase 3 when working alone, or in parallel if two people split `tools.py` sections.
- **Phase 5 (P3)** needs Phase 2, and reads the results of Phases 3 and 4 (it proposes fixes for behind projects and overloaded employees). Start after both graded phases pass.
- **Phase 6 (P4)** needs Phase 2 and the snapshot from Phase 3 (`delay_facts` reuses its causes).
- **Phase 7 (P5)** needs Phase 6 (`DelayFacts`, `EvmRow`).
- **Phase 8** last.

### Inside each story

Fixtures, tasks and verifier first (seen failing) -> unit tests -> domain function -> tool -> finding assembly -> offline run -> live verify.

### Parallel opportunities

- Phase 1: T002, T003, T004, T008 together.
- Phase 2: T012, T013 together; the four test files T015-T018 together; T023, T025, T026, T028, T033 together.
- Phase 3: T036, T037, T038, T040, T041, T042 together, then T043 alone.
- Phase 4: T051, T052, T054 together.
- Phase 5: T061-T064, T067, T068 together.
- Phase 6: T078-T080, T083, T084 together; the EVM and delay branches can be done by two people.
- Different people can own different phases once Phase 2 is done, except where two tasks edit `agent/tools.py` or `agent/findings.py` (merge those sections carefully).

### Parallel example: Phase 3 start

```text
T036 harness/fixtures/behind_basic.json
T037 harness/fixtures/truncated_projects.json
T038 harness/tasks/behind_schedule_basic.json + behind_schedule_truncated.json
T040 tests/test_integrity.py
T041 tests/test_behind.py
T042 harness/tasks/refuse_payroll.json + refuse_manufacturing.json
```

## Implementation strategy

1. **MVP**: Phases 1, 2, 3. Both the loop and the first graded predicate are working and verified.
2. **Second graded answer**: Phase 4. After this, everything the evaluator scores today is covered.
3. **Safe action**: Phase 5, then the optional analysis and reporting layers (Phases 6, 7).
4. **Polish**: Phase 8.
5. At every checkpoint re-run all earlier offline tasks; a regression blocks the next phase.

## Notes

- Test and verifier tasks are hand-written by the team; mark any AI-assisted fixture with `"note": "AI-assisted"` in its JSON, as Team 04 does.
- No task writes to the shared platform except `record_finding` (our own `AgentMemory`), `guarded_update` on proposals the operator approved, and harness-owned fixture rows.
- Task T009 and T060 may change field names used by earlier tasks; update `data-model.md` and the fixtures in the same change.
