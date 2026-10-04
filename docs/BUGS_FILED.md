# Platform defects filed (Team 14 seat)

Reproducible cases only. None filed yet as formal tickets — each entry has the evidence to file one.

1. **`CalendarEvent.list` not in seat tool catalogue** (observed 2026-10-05, both instances via `tools/list`, 247 tools).
   Repro: `call_tool("CalendarEvent.list", {"limit": 3})` → `tool_not_available`, while `ProjectResourceAllocation`/`ProjectResourceProfile` list fine.
   Impact: overload capacity reads are structurally truncated for this seat; the agent reports `limits.truncated` + empty sets instead of guessing.
2. **`Task`/`Project` schemas omit `updated_at`, but live rows carry it** (observed 2026-10-05: `GET /api/schemas` has no `updated_at`; `Task.get` returns one).
   Impact: none on behavior (`guarded_update` uses it opportunistically), but schema consumers cannot rely on the snapshot for audit fields.
3. **`GET /api/schemas` does not enumerate `Task.status` values** (type `state`, no options list; observed 2026-10-04).
   Impact: closed-state set (`done`/`cancelled`) is observed-live, not schema-guaranteed; a new terminal state would silently change behind-schedule classification.
4. **Fixture-ID grading gap (not a platform bug, recorded so it is not misfiled)**: the graded predicates have no platform endpoint; grading reads our `AgentMemory` row. Live `overload` is empty-by-data (zero allocations/profiles + defect 1), which is correct output, not a failure.
