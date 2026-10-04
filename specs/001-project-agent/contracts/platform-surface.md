# Contract: Platform Surface per Capability

Derived from the "buildable now" list in `/gap_report.md`. For each capability: what the
agent **reads**, what it **writes** (if anything), and the safety rule that applies.
Tool names follow the `Entity.operation` form the existing client already calls. Entities
and fields marked *(verify)* are confirmed in the first implementation task.

All list reads use `limit=200` with offset paging and compare fetched count to `total`.

| # | Capability (spec) | Reads | Writes | Safety rule |
|---|-------------------|-------|--------|-------------|
| 1 | Schedule integrity scan (FR-004, US3) | `Task.list`, `Project.list` | none | read-only; flag truncation |
| 2 | Behind-schedule detection (FR-001, US1) **graded** | `Project.list`, `Task.list`, `Milestone.list` | `AgentMemory.create` (finding) | finding mandatory; dated cause required |
| 3 | Resource overload next week (FR-002/5/6, US2) **graded** | `ProjectResourceAllocation.list` (`task_id`+`calendar_event_id`), `CalendarEvent.list` (`start_at`/`end_at`/`timezone` — confirmed 2026-10-04), `ProjectResourceProfile.list` (`employee_id`+weekday hours) | `AgentMemory.create` (finding) | sum across all projects; unknown capacity separated |
| 4 | Critical-path-aware change check (FR-007, US5) | `endpoint.projects.critical_path` (before; after only if a write was applied), `Task.list` for the project | none (evaluation is local) | no write needed to evaluate; no write-then-revert |
| 5 | Reschedule proposals (FR-009, US6) | `Task.get` (fresh), `Task.list` | `Task.update` (`due_date`, `assignee_id`) | `guarded_update` only; opt-in; allowed-id set; stop after first conflict |
| 6 | EVM proxy (FR-010, US7) | `Project.list`, `Task.list`, `Timesheet.list` | none | read-only; `insufficient_data` when budget or rate missing |
| 7 | Delay narrative (FR-011, US4) | `Task.list`, `Milestone.list` (already fetched for #2) | none | LLM sees only `DelayFacts` |
| 8 | Audience status report (FR-012, US8) | `endpoint.projects.client_status_report` | none | same facts for every audience |
| 9 | Context and capability (FR-013, FR-015) | company context via `company_context` tool, `tools/list`, REST status probe on `GET /api/<entity>` (confirmed 2026-10-04) | none | 403 -> `not_visible`, 404 -> `unknown_name` |
| 10 | Escalation (FR-009) | `endpoint.agent_governance.escalations.assignees` / `.raise` / `.update` (confirmed visible 2026-10-04 both instances) | raise escalation | no assignee -> say so |
| 11 | CRM link (gap report: project -> customer) | seat has `crm` in `allowed_apps` (confirmed 2026-10-04); entities probed at runtime | none | optional; skipped if not visible; never blocks the graded answers |

## Seat boundary (must refuse, never work around)

Payroll, manufacturing (work orders), accounting. The agent probes first; if the probe
confirms the entity is outside the seat, it answers with the boundary statement and
records a `refused` finding.

## Explicitly not used

Anything on `AgentSwitch_team04-main`'s seat, `Task.update` outside a proposal, deleting
records, and any entity reachable only by guessing a name.
