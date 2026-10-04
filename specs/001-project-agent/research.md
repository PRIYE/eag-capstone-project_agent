# Phase 0 Research: Project Agent (Seat 14)

No `NEEDS CLARIFICATION` markers remained in the Technical Context. The items below are
design decisions, plus a short list of **facts that must be confirmed against the live
schema in the first implementation task** (marked *to verify*). Those facts come from
`gap_report.md` and `Objective.md`, not from a live call made while planning.

## R1. Layering - how closely to mirror Team 04

- **Decision**: Keep Team 04's four layers (transport / domain / loop / harness) and its rule that the model only picks tools; split `domain` into a package by capability.
- **Rationale**: Team 04's `domain.py` is about 940 lines. We have eight capabilities, and splitting keeps each pure and independently testable. It also lets the two graded predicates ship without the other six.
- **Alternatives considered**: One `domain.py` (rejected: too large to test by capability). An agent framework (rejected: the brief asks for our own loop, and Team 04 shows a plain loop is enough).

## R2. Build on the existing scaffold, don't restart

- **Decision**: Extend `agent/mcp_client.py`, `agent/ai_models.py`, `harness/runner.py`; rewrite `agent/loop.py`.
- **Rationale**: The client already handles the real response envelope (`structuredContent`, `isError`), pagination (`call_tool_all`) and `.env` loading. Observed gaps in the current `loop.py`: hard-coded 10 iterations, no wall clock, no persisted finding, sequential tool calls, tool results appended as free text. These are exactly what the spec's FR-003 / FR-014 and SC-006 / SC-008 require.
- **Alternatives considered**: Rewrite everything (rejected: discards working auth and pagination).

## R3. Where the finding is persisted

- **Decision**: Write the finding to `AgentMemory` as a prefixed JSON document (Team 04's pattern), keyed by a `run_id`, with machine-readable id lists (`behind_project_ids`, `overloaded_employee_ids`, `capacity_unknown_employee_ids`) alongside the causes.
- **Rationale**: `gap_report.md` states `AgentMemory` is private to Team 14, and Team 04 grades the same way. Predicates read database state, so a structured row beats prose.
- **GATE - must confirm before Phase 3/4 finding assembly ships (tasks.md T010a)**: this is an assumption, not a confirmed fact. (a) our seat can call `AgentMemory.create`; (b) what the real `project.behind_schedule` and `project.overloaded_next_week` predicates actually read — if it is a different entity, or if the predicate expects a different field shape (e.g., a flat id array vs. our nested `causes` objects), every offline harness task can pass while both graded answers still fail live, because the offline fixtures grade against our own assumed shape. The platform's API explorer, `/redoc`, and the bug button are the route to confirm this; if the real source differs, only the storage call in `agent/findings.py` changes — the finding's internal shape stays, but `tasks.md T046`/`T057` (which mirror this shape into the finding) must not be treated as "done" until this gate passes.
- **Alternatives considered**: `AgentSession` / job result rows (kept as a secondary mirror if the predicate reads them); a local file (rejected: not database state).

## R4. Definition of "behind schedule"

- **Decision**: A project is behind when it has at least one of: an open task (status not `done` / `cancelled`) with `due_date` before today; a milestone with status `missed`, or `upcoming` with a date before today; a task whose predecessor (`depends_on_task_id`) is cancelled or overdue and which is itself not done. Effort overrun (>150%, clarified) and missing assignee / due date are reported as **contributing causes and integrity flags**, and are not by themselves sufficient to put a project on the behind list.
- **Rationale**: The predicate decides from the database alone, so the list must rest on dated facts. Overrun and unassigned tasks are risk signals, not lateness. Every listed project carries at least one dated cause (spec FR-001, SC-007).
- **To verify**: exact status vocabulary for Task / Project / Milestone from `GET /api/schemas`; whether `Project` carries its own end date that should also be compared.
- **Alternatives considered**: Count integrity flags as "behind" (rejected: inflates false positives against a dated predicate).

## R5. Definition of "overloaded next week"

- **Decision**: Window = the 7 calendar days after today (spec Assumption). For each employee and each day, `allocated_hours(day)` = sum over all their `ProjectResourceAllocation` rows (across all projects) of the hours the linked calendar time block occupies on that day; capacity = the matching weekday field of `ProjectResourceProfile` (`monday_hours` ... `sunday_hours`). Overloaded = any day with allocated > capacity. Report per-day excess and the weekly excess. Employees with allocations but no profile go to `capacity_unknown` only (clarified).
- **Rationale**: `gap_report.md` identifies exactly these entities. Summing across projects satisfies the spec edge case. Per-day comparison matches "daily capacity" in FR-005.
- **To verify**: how an allocation's hours are expressed (via `CalendarEvent` start/end per `gap_report.md`, or a direct hours field); time-zone of those events; whether multi-day events must be split across days; whether part-day or cancelled events exist.
- **Alternatives considered**: Weekly-total comparison (rejected: hides a single overbooked day).

## R6. Critical-path "before / after" without a dry-run endpoint

- **Decision**: The platform exposes `endpoint.projects.critical_path` (read) but no preview. So: (1) read the platform critical path as the baseline; (2) compute the what-if locally in `domain/critical_path.py` by applying the proposed date in memory to the single-predecessor task chain and recomputing the finish date; (3) only if the operator approves and the write passes `guarded_update`, re-read the platform critical path and report the actual change next to the predicted one.
- **Rationale**: Simulating by writing and rolling back would violate Principle II/VII and pollute the shared audit trail. The data model has one predecessor per task, so a local longest-path computation is exact for this model.
- **Alternatives considered**: Write then revert (rejected); trust the platform alone (rejected: no way to predict before committing).

## R7. Bounded run: step budget and 3-minute limit

- **Decision**: 20 model turns, 180 s monotonic deadline, tool calls in one model turn executed in parallel (thread pool), page fetches parallelised after the first page reveals `total`. At 2 turns or 20 s left, force `record_finding` through forced `tool_choice`; on model or network failure, write a `partial` finding from whatever domain results exist.
- **Rationale**: The existing loop is sequential with a 10-turn cap and can end with nothing stored. Team 04 forces the finding near the budget; the same mechanism meets SC-006 and SC-008. Heavy computation is done in `domain/`, not by repeated model turns, so a typical graded run needs about 4 to 6 turns.
- **Alternatives considered**: Larger step budget (rejected: it moves the failure to the clock).

## R8. Detecting truncated data

- **Decision**: Every list read compares fetched count to the reported `total`; a mismatch is surfaced in the finding as `data_truncated` and the run is marked `partial`.
- **Rationale**: The platform default page is 20; silently analysing 20 of 101 projects would produce a wrong, confident answer, which the brief says fails.

## R9. Capability and refusal handling

- **Decision**: Reuse Team 04's idea, adapted: `probe_capability(entity, op)` consults the live tool list, then REST status for the entity (403 = outside seat -> `not_visible`; 404 = unknown name). Requests for payroll or manufacturing are refused with a one-line boundary statement before any tool call, driven by the same probe, not by a keyword list alone.
- **Rationale**: Constitution Principle III and spec FR-013. The existing `harness/tasks.json` already contains refusal tasks to keep.

## R10. Offline harness design

- **Decision**: `FakeMcp` implements the same `call_tool` / `call_tool_all` surface as the real client and serves JSON fixtures; it can inject a concurrent edit between a read and a write. Each fixture carries an independently authored `expected` block. Verifiers recompute truth from the fixture with a **different code path** than `domain/` (plain loops), then compare with the finding the agent stored.
- **Rationale**: Mirrors Team 04's runner / fixture / verifier split and keeps Principle VII: offline mode never writes to the shared platform. Verifier independence stops a domain bug from grading itself as correct.
- **Alternatives considered**: Create rows on the live tenant for fixtures (Team 04 does this for its own rows); kept only as an opt-in live mode for rows this team creates and cleans up.

## R11. LLM role

- **Decision**: The model decides which tool to call next and writes the closing summary and the two narrative products (delay narrative, audience status). The narrative tools receive structured facts from `domain/delay.py` and are told to use no fact outside them; the sponsor and team versions are generated from the same fact object.
- **Rationale**: Keeps correctness in testable code (spec FR-011, FR-012) and leaves only wording to the model.

## R12. Secrets hygiene (observation, no scope change)

- **Decision**: Do not copy `.env` values into specs, docs, traces or fixtures. Traces redact `Authorization` and any key-shaped strings.
- **Rationale**: `.env` and `README.md` currently hold live credentials and API keys. Rotating them is the owner's call; the plan only ensures our new artifacts do not spread them.

## Items to confirm first (feeds the first task)

1. Fetch `GET /api/schemas` once and snapshot Task, Project, Milestone, ProjectResourceAllocation, ProjectResourceProfile, CalendarEvent, Timesheet, AgentMemory into `docs/ENTITY_MAP.md`; correct the field names used in `data-model.md` if they differ.
2. Confirm `AgentMemory.create` works for this seat on both instances.
3. Confirm the response shape of `endpoint.projects.critical_path` and `endpoint.projects.client_status_report`.
4. Confirm the escalation endpoints are visible to this seat (Team 04 used `endpoint.agent_governance.escalations.*`).
