# Harness task format

Each file in `harness/tasks/*.json` describes one gradable offline (or
live) scenario. Mirrors Team 04's `harness/tasks/README.md`.

```json
{
  "id": "behind_schedule_basic",
  "note": "hand-written",
  "instances": ["suryodaya", "keystone"],
  "mode": "offline",
  "prompt": "Which projects are behind schedule?",
  "fixture": "behind_basic",
  "script": [
    {"name": "company_context", "arguments": {}},
    {"name": "load_snapshot", "arguments": {"scope": "projects"}},
    {"name": "schedule_integrity", "arguments": {}},
    {"name": "behind_schedule_projects", "arguments": {}},
    "STOP"
  ],
  "verifier": "behind_schedule_matches",
  "checks": "Behind set, dated causes, and status (complete/partial) all match the fixture's independently authored `expected` block."
}
```

Fields:

- `id`: must equal the filename (without `.json`).
- `note`: `"hand-written"` or `"AI-assisted"` - see tasks.md's note on hand-written credit.
- `instances`: informational; which real instances this task is meaningful against in `--live` mode.
- `mode`: `"offline"` (default) or `"offline_only"` (skipped entirely by `--live`, e.g. truncation/latency injection tasks that have no live equivalent).
- `prompt`: the question text passed to `agent.loop.run_agent`.
- `fixture`: name of a file in `harness/fixtures/` (without `.json`); omit for a task with no fixture.
- `script`: an ordered list of tool calls for `harness.fakes.ScriptedModel` to replay in `--offline` mode. Use the string `"STOP"` to signal "give the final answer now" and `"LOOP_FOREVER"` for bounded-run tests. Ignored in `--live` mode (a real model decides what to call).
- `verifier`: a function name registered in `harness/verifiers_state.py` (state-based) or `harness/verifiers.py` (prose-based, for refusal/data-reread checks carried over from the original harness).
- `checks`: a one-line human description of what the verifier actually checks, for anyone reading the task file without reading the verifier code.
