# Platform defects filed (Team 14 seat)

Reproducible cases only. None filed yet as formal tickets — each entry has the evidence to file one.

1. **`CalendarEvent.list` not in seat tool catalogue** (observed 2026-10-05, both instances via `tools/list`, 247 tools).
   Repro: `call_tool("CalendarEvent.list", {"limit": 3})` → `tool_not_available`, while `ProjectResourceAllocation`/`ProjectResourceProfile` list fine.
   Impact: overload capacity reads are structurally truncated for this seat; the agent reports `limits.truncated` + empty sets instead of guessing.
2. **`Task`/`Project` schemas omit `updated_at`, but live rows carry it** (observed 2026-10-05: `GET /api/schemas` has no `updated_at`; `Task.get` returns one).
   Impact: none on behavior (`guarded_update` uses it opportunistically), but schema consumers cannot rely on the snapshot for audit fields.
3. ~~**`GET /api/schemas` does not enumerate `Task.status` values**~~ **WITHDRAWN 2026-10-06 — do not file.**
   Correction: the `Task` schema's `flow` block (`TaskFlow`) lists all states: `todo`, `in_progress`, `in_review`, `done`, `completed`, `cancelled`, with transitions (`done → completed`, `completed → todo` reopen). The original check looked only at the field's `options`.
   Agent follow-up: treat `completed` as closed (see `bugs_files.md` N131).
4. **Fixture-ID grading gap (not a platform bug, recorded so it is not misfiled)**: the graded predicates have no platform endpoint; grading reads our `AgentMemory` row. Live `overload` is empty-by-data (zero allocations/profiles + defect 1), which is correct output, not a failure.
5. **Question: what does reserved behavior `trackable` mean, and when will it be enabled?** (observed 2026-10-06 in `GET /api/schemas`).
   `trackable` is in `reserved_behaviors` for 139 entities incl. `Project`, `Task`, `Milestone`, active on none; no definition in the schema.
   Ask: if it is a field-level change log, enable it on `Task`/`Milestone` and make it readable by the Projects seat — needed for progress tracking, change control and delay analysis (`gap_report_v2.md` §2a).
