# Phase 1 Data Model: Project Agent (Seat 14)

Two groups: **platform entities** the agent reads (and, narrowly, writes), whose field
names come from `gap_report.md` and must be confirmed against `GET /api/schemas` (see
research.md, "Items to confirm first"); and **agent-side structures** the domain layer
passes around.

## 1. Platform entities (read unless stated)

| Entity | Fields the agent relies on | Used by |
|--------|---------------------------|---------|
| `Project` | `id`, `name`, `status` (planning / active / on_hold / completed / cancelled — confirmed `GET /api/schemas` 2026-10-04 both instances), `budget_amount`, `budget_hours`, `estimated_cost`, `end_date` (confirmed; there is no `finish_date`), `start_date` (no `updated_at` in live schema — `guarded_update` falls back to `status` comparison when `snapshot_updated_at` is None) | behind, EVM, status report |
| `Task` | `id`, `title` (confirmed; live field is `title`, not `name`), `project_id`, `status` (type `state`; exact vocabulary not enumerated in schemas — observed live, treat `done`/`cancelled` as closed), `due_date`, `start_date`, `assignee_id`, `depends_on_task_id` (single predecessor), `parent_task_id`, `milestone_id`, `budget_hours`, `estimated_hours`, `logged_hours`, `billed_hours`, `rate`, `sort_order` (no `updated_at` in live schema). **Written** by reschedule (`due_date`, `assignee_id`) via `guarded_update` only. | integrity, behind, critical path, reschedule, EVM |
| `Milestone` | `id`, `name`, `project_id`, `status` (upcoming / reached / missed — confirmed), `due_date` (confirmed; live field is `due_date`, not `date`) | behind, delay |
| `ProjectResourceAllocation` | `id`, `task_id` (required), `calendar_event_id` (required) (confirmed; no direct hours or employee field — hours come from the linked `CalendarEvent`) | overload |
| `CalendarEvent` | `start_at`, `end_at` (type `text`, confirmed), `timezone` (confirmed; allocation hours = block overlap per day) | overload |
| `ProjectResourceProfile` | `employee_id` (required, confirmed), `monday_hours` ... `sunday_hours` (confirmed) | overload |
| `Timesheet` | `task_id` + `project_id` (required), `date` (required), `hours` (required), `rate`, `amount`, `employee_id` (confirmed) | EVM |
| `AgentMemory` | `content` (required richtext), `category` (preference / fact / instruction / context / relationship), `source` (extracted / manual / system), `importance` (number — platform rejects strings), `is_active`, `expires_at`. **Written** only by `record_finding`. | persisted finding |
| Escalation endpoints | assignee list, raise, update | escalation |

Relationship summary: `Project 1-* Task`, `Project 1-* Milestone`,
`Task 0..1 -> Task` (single predecessor), `Task 1-* ProjectResourceAllocation -> CalendarEvent`,
`Employee 0..1 ProjectResourceProfile`, `Task 1-* Timesheet`.

## 2. Agent-side structures (pure data, in `agent/domain/`)

### Snapshot
The fetched, immutable input to every domain function.
- `as_of: date` - injected "today" (never read from the clock inside `domain/`)
- `projects, tasks, milestones, allocations, events, profiles, timesheets: list[dict]`
- `truncated: dict[str, bool]` - per entity, `fetched < total`
- `company: {id, currency, country}`

### IntegrityFlag
`{task_id, project_id, kind, detail}` where `kind` is one of `no_assignee`, `no_due_date`,
`predecessor_cancelled`, `predecessor_overdue`, `effort_overrun`.
Rule: `effort_overrun` when `logged_hours > 1.5 * reference_hours`, where `reference_hours`
is `budget_hours` else `estimated_hours`; skipped (with a `no_baseline_hours` note) if both are
0 or missing. One task can carry several flags; each is its own record (spec US3).

### BehindProject
`{project_id, name, causes: [Cause], primary_cause}`
`Cause = {kind, task_id?, milestone_id?, days_late?, detail}` with `kind` in
`overdue_task`, `missed_milestone`, `overdue_milestone`, `blocked_by_predecessor`,
plus contributing `effort_overrun`, `no_assignee`, `no_due_date`.
Invariant: at least one *dated* cause. A project with no tasks and no milestones is
reported under `insufficient_data`, never as behind or on track.

### OverloadResult
`{window: [date x7], overloaded: [EmployeeLoad], capacity_unknown: [employee_id], within_capacity_count}`
`EmployeeLoad = {employee_id, days: [{date, allocated_h, capacity_h, excess_h}], week_excess_h, projects: [project_id]}`
Invariants: allocation hours are summed across **all** projects; `capacity_unknown` ids are never in `overloaded`.

### Proposal
`{task_id, field_changes, snapshot_updated_at, snapshot_status, writable_by_seat, why_not_writable?, predicted_finish_delta_days, on_critical_path}`
State machine of one proposal:
`proposed -> (approved | declined)`; `approved -> re-read -> (applied | changed_underneath | write_rejected | refused)`;
`applied -> verified (post-write re-read matches) | write_not_persisted`.
After one `changed_underneath`, all remaining proposals in the run become `refused`.

### CriticalPathDelta
`{project_id, baseline_finish, predicted_finish, delta_days, task_on_path, platform_cp_before, platform_cp_after?}`
`platform_cp_after` is filled only after an applied write.

### EvmRow
`{project_id, planned_cost, actual_cost, earned_value, cpi, status}` where
`actual_cost = sum(timesheet hours * rate)`, `earned_value = percent_complete * budget`,
`percent_complete` = done-hours-weighted share of task budget hours (documented rule),
`status` in `over_spending` (earned < actual), `on_budget`, `insufficient_data`.

### DelayFacts
`{project_id, primary_blocker, secondary: [Cause], timeline: [{date, event}]}` - the only
input the narrative tool may use. Every item cites a record id.

### Finding (persisted; see contracts/finding-schema.md)
`{schema_version, run_id, instance, as_of, status (complete | partial | escalated), behind_projects, overloaded_employees, capacity_unknown, integrity_flags_summary, proposals, escalations, limits (not_visible, truncated), budget_used}`

### RunBudget / ReadDedup / WriteGate
- `RunBudget{max_steps=20, deadline_s=180, steps_used, started_at}` with `exhausted()`, `must_finalize()`.
- `ReadDedup{seen: {(tool, args_hash): result_summary}}`.
- `WriteGate{conflict_seen: bool, allowed_ids: set}`; `conflict_seen` is monotonic within a run.

## 3. Validation rules traced to the spec

| Rule | Spec |
|------|------|
| Every behind project has >= 1 dated cause | FR-001, SC-007 |
| Overload is summed across all projects, per day | FR-005, edge case |
| Capacity-unknown excluded from overloaded, listed separately | FR-006 (clarified) |
| Overrun threshold 150% | FR-004 (clarified) |
| No write without re-read; conflict stops all later writes | FR-008, SC-004 |
| Run ends with a finding within 3 minutes | FR-003, FR-014, SC-006, SC-008 |
