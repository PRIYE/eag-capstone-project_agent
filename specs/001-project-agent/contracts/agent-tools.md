# Contract: Agent Tools (what the model may call)

The model can call only these tools. Each maps to one function in `agent/domain/` or
`agent/safety.py`. None accepts a URL, an entity name or a raw filter; arguments are
small and typed. JSON-Schema-style argument shapes are given in compact form.

| Tool | Arguments | Returns | Notes |
|------|-----------|---------|-------|
| `company_context` | none | `{company, country, currency, as_of}` | Called first, every run |
| `load_snapshot` | `{scope: "projects" \| "capacity" \| "money"}` | counts, `truncated` flags, `snapshot_id` | Performs the paginated reads once; later tools use the cached snapshot |
| `schedule_integrity` | `{project_id?: string}` | `IntegrityFlag[]`, summary by kind | Overrun threshold fixed at 150% |
| `behind_schedule_projects` | none | `BehindProject[]`, `insufficient_data[]` | **Graded** |
| `overloaded_next_week` | `{start?: date}` | `OverloadResult` | **Graded**; default window is tomorrow + 6 days |
| `critical_path_check` | `{task_id: string, new_due_date: date}` | `CriticalPathDelta` | Local what-if; platform CP shown as baseline |
| `propose_reschedule` | `{finding_ref: "overload" \| "behind", employee_id? , task_id?}` | `Proposal[]` | Each carries `writable_by_seat` and snapshot stamps |
| `apply_proposal` | `{task_id: string}` | outcome: `applied` \| `changed_underneath` \| `refused` \| `write_rejected` \| `write_not_persisted` | Requires `--apply`; per-write operator `y/n`; goes through `guarded_update` |
| `evm_summary` | `{project_id?: string}` | `EvmRow[]` | |
| `delay_facts` | `{project_id: string}` | `DelayFacts` | Input for the narrative; model must cite ids |
| `status_report_facts` | `{project_id: string}` | platform report + `DelayFacts` + `EvmRow` | Model rewrites for audience, same facts |
| `seat_capability` | `{entity: string}` | `{visible, reason: "ok" \| "not_visible" \| "unknown_name"}` | 403/404 never merged |
| `escalate` | `{reason: string, reason_code}` | `{raised, number?, assignee?}` or `{raised:false, reason:"no_assignee"}` | |
| `record_finding` | `Finding` (see finding-schema.md) | `{agent_memory_id, run_id}` | **Mandatory, exactly once**; refused until a required escalation was attempted |

## Loop-level contract

- Max 20 model turns and 180 s. Tool calls requested in the same turn run in parallel.
- Identical repeated read -> `{"note": "already read this run"}` and no network call.
- In the last 2 turns or last 20 s, the loop sets forced `tool_choice = record_finding`.
- If the model or network fails, the loop builds a `partial` finding itself from stored domain results.
- Any text the model emits after `record_finding` is the operator-facing summary; it adds no facts beyond the finding.
