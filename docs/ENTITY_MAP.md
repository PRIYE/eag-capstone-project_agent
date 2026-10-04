# Entity Map

This file is meant to be generated/updated by `scripts/snapshot_schemas.py`
against a live AgentSwitch instance (tasks.md T008/T009) and by `python
run.py check` (T010). **Neither has been run yet** - this implementation
pass had no network access to a real AgentSwitch instance or verified
`.env` credentials, so this file currently records what is *assumed*
(from `gap_report.md` and `data-model.md`), not what is *confirmed*.

## T010a - GATE: predicate source confirmation (UNRESOLVED)

**Status: NOT CONFIRMED.** `tasks.md` marks T010a as a gate blocking
T046/T057 (finding assembly). It could not be closed in this pass
because closing it requires one of: the live API explorer/`redoc`,
course staff, or a deliberate probing call against a running instance -
none of which were reachable from this environment.

What was assumed instead (research.md R3), and built so it stays
swappable:

- `project.behind_schedule` and `project.overloaded_next_week` read the
  `AgentMemory` row this agent writes via `record_finding`
  (`content: "PROJECT_AGENT_FINDING:" + JSON`, see
  `contracts/finding-schema.md`).
- The predicate expects the nested shape in that contract (`causes[]`
  per behind project, `days[]` per overloaded employee), not a flat id
  list.

**Before trusting a live grading run**, someone with platform access
must:
1. Run `python scripts/snapshot_schemas.py --instance suryodaya` (and
   `--instance keystone`) and compare the `AgentMemory` schema and any
   `endpoint.*` predicate-adjacent routes against the assumption above.
2. Run `python run.py check --instance suryodaya` and confirm
   `AgentMemory.create` is visible to this seat (`OK` line in its
   output) and note the escalation-assignee endpoint's real name if it
   differs from `endpoint.agent_governance.escalations.assignees`.
3. If the real predicate reads something else, the only code that
   should change is the storage call in `agent/findings.py::record_finding`
   (and, if the top-level fields differ, `assemble_finding`'s return
   shape) - `validate_finding` and the domain layer should not need to
   change.
4. Update this section with the confirmed source and re-run
   `python run.py test --offline` to confirm no regression, then do a
   live `python run.py agent` + `python run.py verify <run_dir>` pass.

## Assumed entity shapes (from gap_report.md / data-model.md, NOT yet schema-verified)

| Entity | Fields this agent reads/writes |
|---|---|
| `Project` | `id`, `name`, `status`, `budget_amount`, `budget_hours`, `estimated_cost`, `updated_at` |
| `Task` | `id`, `project_id`, `status`, `due_date`, `assignee_id`, `depends_on_task_id`, `budget_hours`, `estimated_hours`, `logged_hours`, `billed_hours`, `rate`, `updated_at` (write: `due_date`, `assignee_id` via `guarded_update` only) |
| `Milestone` | `id`, `project_id`, `status` (`upcoming`/`reached`/`missed`), `date` |
| `ProjectResourceAllocation` | `id`, `employee_id` (or `resource_id`), `task_id`, `calendar_event_id` |
| `CalendarEvent` | `id`, `start`, `end`, `hours` |
| `ProjectResourceProfile` | `employee_id`, `monday_hours` ... `sunday_hours` |
| `Timesheet` | `hours`, `rate`, `amount`, task/project reference |
| `AgentMemory` | `content`, `category`, `source`, `importance`, `is_active` (write only, via `record_finding`) |

## Known limits (carried from research.md / gap_report.md, not yet re-verified live)

- Default MCP list page size is 20 (max 1000); this agent always calls
  with `limit=200` via `call_tool_all` and surfaces `truncated` when a
  read came back short even at that size.
- Escalation assignee endpoint name is unconfirmed; `agent/safety.py::escalate`
  calls `endpoint.agent_governance.escalations.assignees` / `.raise` and
  treats any failure or empty list as an honest `no_assignee`, never a
  fabricated handover - so a name mismatch degrades to "no assignee"
  rather than a wrong claim.
