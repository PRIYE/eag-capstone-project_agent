# Bugs reported on AgentSwitch: status tracker (Team 14, Projects seat)

Source: `List of Bugs.xlsx`, the platform bug tracker export (snapshot taken 2026-10-06).
This file tracks bugs **already reported** and their current status. Candidate defects that have
repro steps but are **not yet filed** live in [`BUGS_FILED.md`](BUGS_FILED.md).

## Summary

| Status | Count |
|---|---|
| Live on server (fixed) | 4 (N146, R15, N130, N131) |
| In review | 1 (N374) |
| Decided, no change | 1 (N389) |
| **Total** | **6** (5 reported by Team 14, 1 internal) |

## Register

| ID | Bug | Reported by | Severity | Status | Release / stream | Evidence |
|---|---|---|---|---|---|---|
| N374 | Duplicate project milestones allowed | Team 14 | Medium | In review | — · Release 8 · student reports | reported `d4b981b2` · 27 Sep |
| N146 | A task cannot be assigned to anyone without HR access | Team 14 | **High** | Live on server | — · Next release · student reports | Assignee search now uses the names-only people directory, checked with the seat's roles |
| R15 | Approved timesheets could be edited | Internal | Medium | Live on server | Release 1 (17 Sep 2026, 18:40 IST) · Wave 2 | `a9d93f27a` |
| N130 | Searching the hours drill-down does not find employees or projects | Team 14 | Low | Live on server | — · Next release · student reports | Fixed: the hours search matches the employee and project shown |
| N131 | Tasks have both "Done" and "Completed", with no explanation | Team 14 | Low | Live on server | — · Next release · student reports | Fixed: the app now explains the difference between Done and Completed |
| N389 | How is a timesheet approved? (question) | Team 14 | Low | Decided, no change | — · Release 8 · student reports | reported `5ebd69d2` · 27 Sep |

## Details

### N374: Duplicate project milestones allowed. *In review*
The platform accepts more than one milestone with the same identity on a project.
**Agent impact:** `behind.py` counts missed milestones, so duplicates could double-count one slip. Until this is fixed, dedupe milestones by (project, name, due_date) before counting.

### N146: Task cannot be assigned without HR access. *Live on server* (High)
While creating a task, the assignee list was empty because it read the employee list, which is behind
HR/payroll permissions. Saving then failed with a bare "Validation failed". The fix was a
names-only people directory that any seat can read, rather than payroll access (which would expose salaries).
**Agent impact:** `escalate()` / `no_assignee` handling should re-check live; assignee lookups should use the people directory.

### R15: Approved timesheets could be edited. *Live on server* (Internal)
Economic fields now lock once a timesheet is approved or invoiced.
**Agent impact:** EVM actual cost (from Timesheet `hours`/`amount`) is now stable after approval.

### N130: Hours drill-down search finds nothing. *Live on server*
On the Projects dashboard, searching Hours This Week by employee or project returned nothing (numbers like 1 or 2 matched, unclearly).
UI-only; no agent impact.

### N131: "Done" vs "Completed" task states. *Live on server*
31 tasks were Done and 4 were Completed, and a new task could not be set to Completed. The app now explains the difference.
**Agent impact (open action):** the domain code treats only `done`/`cancelled` as closed
(`behind.py`, `critical_path.py`, `reschedule.py`, `integrity.py`; `evm.py` uses only `done`).
Tasks in `completed` are therefore treated as **open**, can be counted as overdue, and are left out of earned value.
This links to [`BUGS_FILED.md`](BUGS_FILED.md) #3 (status values not enumerated in schemas).

### N389: How is a timesheet approved? *Decided, no change*
Answer: Logged → Approved by the project manager through the timesheet flow. This was a question, not a defect.

## Not yet filed
See [`BUGS_FILED.md`](BUGS_FILED.md): `CalendarEvent.list` not in the seat catalogue; `updated_at` missing from
schemas but present on rows; `Task.status` values not enumerated.
