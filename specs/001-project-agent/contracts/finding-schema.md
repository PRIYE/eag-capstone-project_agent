# Contract: Persisted Finding

Stored as one `AgentMemory` row: `category: "fact"`, `source: "system"`,
`content: "PROJECT_AGENT_FINDING:" + <JSON>`. Verifiers and the harness find it by `run_id`.
If the live predicates turn out to read a different entity (research R3), only the
storage call changes; this shape stays.

```json
{
  "schema_version": 1,
  "run_id": "20261004-113000-suryodaya",
  "instance": "suryodaya",
  "as_of": "2026-10-04",
  "company": {"country": "IN", "currency": "INR"},
  "status": "complete",

  "behind_projects": [
    {
      "project_id": "PRJ-0007",
      "primary_cause": {"kind": "overdue_task", "task_id": "TSK-0123", "days_late": 12},
      "causes": [
        {"kind": "overdue_task", "task_id": "TSK-0123", "days_late": 12},
        {"kind": "no_assignee", "task_id": "TSK-0130"}
      ]
    }
  ],
  "insufficient_data_projects": ["PRJ-0042"],

  "window": ["2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09", "2026-10-10", "2026-10-11"],
  "overloaded_employees": [
    {
      "employee_id": "EMP-0003",
      "week_excess_h": 9.5,
      "days": [{"date": "2026-10-06", "allocated_h": 12, "capacity_h": 8, "excess_h": 4}]
    }
  ],
  "capacity_unknown_employees": ["EMP-0019"],

  "integrity_summary": {"no_assignee": 4, "no_due_date": 2, "effort_overrun": 3},
  "proposals": [{"task_id": "TSK-0130", "outcome": "proposed", "writable_by_seat": true}],
  "escalations": [{"raised": false, "reason": "no_assignee"}],
  "limits": {"not_visible": ["Employee"], "truncated": {}, "notes": []},
  "budget": {"steps_used": 6, "elapsed_s": 41.2}
}
```

## Rules

1. `status` is `complete`, `partial` (budget/deadline/model failure/truncated data), `escalated`, or `refused` (out-of-seat request).
2. `behind_projects[*].causes` is never empty, and at least one cause is dated (`overdue_task`, `missed_milestone`, `overdue_milestone`, `blocked_by_predecessor`).
3. `capacity_unknown_employees` and `overloaded_employees` are disjoint.
4. Every id in the finding exists in the snapshot used for the run.
5. Written exactly once per run; a retry after a transient failure keeps the same `run_id` and fields.
6. Contains no credentials and no free-text copied from untrusted record fields beyond ids and numbers.
