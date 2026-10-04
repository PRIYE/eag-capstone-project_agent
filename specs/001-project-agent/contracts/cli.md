# Contract: Command-Line Interface (`run.py`)

Extends the existing `run.py` (`check`, `agent`, `test`).

| Command | Behaviour | Exit code |
|---------|-----------|-----------|
| `python run.py check [--instance suryodaya\|keystone]` | Authenticate, list tools, probe `AgentMemory.create` visibility and the escalation endpoints; prints seat capabilities | 0 ok, 2 auth/probe failure |
| `python run.py agent "<question>" [--instance ...] [--apply] [--escalate]` | One bounded run. Read-only unless `--apply`; each write asks `y/n`. `--escalate` allows raising one real escalation. Prints the summary, finding id and `trace` path. Default question is the graded request | 0 finding stored (`complete`/`escalated`/`refused`), 1 `partial`, 2 no finding could be stored |
| `python run.py test --offline [--task ID]` | Runs harness tasks against `FakeMcp` + fixtures; writes nothing to the platform | 0 all approve, 1 any revise/unevaluated |
| `python run.py test --live [--task ID] [--instance ...]` | Runs against the platform; read-only unless a task is marked `fixture_owned`, in which case it touches only rows this team created and removes them afterwards | same |
| `python run.py verify <run_dir>` | Re-grades a stored run from its `result.json` and the database, without re-running the agent | 0 approve |

## Run directory

`harness/runs/<timestamp>-<instance>/` containing `task.json`, `trace.jsonl` (written event
by event), `result.json` (fsynced **before** grading), `verdict.json`
(`approve` \| `revise` \| `unevaluated`; `unevaluated` never counts as a pass).

## Environment (names only; values stay in `.env`)

`AS_URL`, `AS_EMAIL`, `AS_PASSWORD`, `AS_KEYSTONE_URL`, `AS_KEYSTONE_PASSWORD`,
`MODEL_PROVIDER`, `MODEL_NAME`, provider key variables. Traces redact all of them.
