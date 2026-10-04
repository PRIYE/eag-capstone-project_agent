"""
Harness runner (tasks.md T027). Supports:
  --offline  (default): build a FakeMcp from a fixture and a
             ScriptedModel from the task's `script`, run agent.loop
             exactly as it runs live, grade with harness/verifiers_state.py.
  --live:    run against the real platform via agent.mcp_client +
             agent.ai_models (requires .env credentials and network).

Every run writes harness/runs/<timestamp>-<instance>/{task.json,
trace.jsonl, result.json, verdict.json} in that order (fsync'd before
verdict.json is written), so a crash mid-run never leaves a stale
verdict.json implying success.
"""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.redact import redact

RUNS_DIR = Path(__file__).resolve().parent / "runs"
TASKS_DIR = Path(__file__).resolve().parent / "tasks"


def _load_task(task_id: str) -> Dict[str, Any]:
    path = TASKS_DIR / f"{task_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"No such harness task: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _list_task_ids() -> List[str]:
    if not TASKS_DIR.exists():
        return []
    return sorted(p.stem for p in TASKS_DIR.glob("*.json"))


def _endpoint_ok(payload):
    """Canned offline endpoint response for task-level `endpoints` setup."""
    from agent.mcp_client import MCPResult
    return MCPResult(success=True, data=payload)


def _make_run_dir(instance: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = RUNS_DIR / f"{stamp}-{instance}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _write_trace_event(run_dir: Path, event: Dict[str, Any]) -> None:
    event = dict(event)
    event["ts"] = datetime.now(timezone.utc).isoformat()
    safe_event = redact(event)
    path = run_dir / "trace.jsonl"
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(safe_event, default=str) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _run_offline_task(task_id: str, instance: str) -> Dict[str, Any]:
    from agent.loop import run_agent
    from harness.fakes import FakeMcp, ScriptedModel
    from harness.fixtures import load_fixture
    from harness import verifiers_state

    task = _load_task(task_id)
    run_dir = _make_run_dir(instance)
    (run_dir / "task.json").write_text(json.dumps(redact(task), indent=2), encoding="utf-8")

    fixture = load_fixture(task["fixture"]) if task.get("fixture") else {"data": {}, "expected": {}}
    mcp = FakeMcp(fixture["data"], entity_statuses=fixture.get("entity_statuses", {}),
                  entity_total_overrides=fixture.get("entity_total_overrides", {}),
                  latency_s=float(task.get("latency_s", 0.0)))
    mcp.data.setdefault("AgentMemory", [])

    # Task-level offline setup (documented in harness/tasks/README.md):
    # canned endpoint responses (e.g. escalation assignees) and programmed
    # concurrent edits applied on the next read of a row.
    for ep_name, ep_payload in (task.get("endpoints") or {}).items():
        payload = ep_payload
        mcp.register_endpoint(ep_name, lambda args, _p=payload: _endpoint_ok(_p))
    for edit in task.get("on_read_edits") or []:
        updates = dict(edit.get("set", {}))
        mcp.on_read(edit["entity"], edit["id"], lambda row, _u=updates: row.update(_u))

    script = task.get("script", ["STOP"])
    model = ScriptedModel(script=script, final_answer=task.get("final_answer", "Done."))

    def on_event(event):
        _write_trace_event(run_dir, event)

    from agent import safety as _safety
    budget = None
    if task.get("deadline_s"):
        # Offline-only test hook (T096): a short wall clock so deadline
        # behavior is gradable without waiting out the 180 s live budget.
        budget = _safety.RunBudget(deadline_s=float(task["deadline_s"]))

    start = time.monotonic()
    run_result = run_agent(
        mcp, model, task["prompt"], instance=instance,
        as_of=fixture.get("as_of") or task.get("as_of"),
        on_event=on_event,
        apply_writes=bool(task.get("allow_apply")),
        allowed_write_ids=set(task.get("allow_write_ids", [])),
        budget=budget,
    )
    run_result["mode"] = "offline"
    elapsed = time.monotonic() - start

    verifier_name = task.get("verifier")
    if verifier_name:
        verdict, detail = verifiers_state.run_verifier(verifier_name, task, fixture, mcp, run_result)
    else:
        verdict, detail = ("approve", "no verifier registered for this task")

    result = {
        "task_id": task_id,
        "mode": "offline",
        "instance": instance,
        "run_id": run_result["run_id"],
        "status": run_result["status"],
        "summary": run_result["summary"],
        "elapsed_s": round(elapsed, 2),
    }
    result_path = run_dir / "result.json"
    result_path.write_text(json.dumps(redact(result), indent=2), encoding="utf-8")
    with open(result_path, "a") as f:
        f.flush()
        os.fsync(f.fileno())

    verdict_payload = {"verdict": verdict, "detail": detail}
    (run_dir / "verdict.json").write_text(json.dumps(verdict_payload, indent=2), encoding="utf-8")

    return {"task_id": task_id, "verdict": verdict, "detail": detail, "run_dir": str(run_dir)}


def _run_live_task(task_id: str, instance: str) -> Dict[str, Any]:
    from agent.loop import run_agent
    from agent.mcp_client import create_client_for
    from agent.ai_models import create_model
    from harness import verifiers_state
    from harness.fixtures import load_fixture

    task = _load_task(task_id)
    if task.get("mode") == "offline_only":
        return {"task_id": task_id, "verdict": "unevaluated", "detail": "offline-only task, skipped in --live",
                "run_dir": None}

    run_dir = _make_run_dir(instance)
    (run_dir / "task.json").write_text(json.dumps(redact(task), indent=2), encoding="utf-8")

    client = create_client_for(instance)
    model = create_model()

    # T075: live harness-owned rows (dedicated HARNESS_MARKER project +
    # future-dated task). The ONLY rows a live harness run may write;
    # deleted in a finally block, pass or fail.
    owned_project_id = owned_task_id = None
    allowed_write_ids = set()
    if task.get("fixture_owned"):
        from harness.fixtures import create_owned_rows, delete_owned_rows  # noqa: F401
        from agent import config as _config
        owned_project_id, owned_task_id = create_owned_rows(client, _config.HARNESS_MARKER)
        allowed_write_ids = {owned_task_id}

    def on_event(event):
        _write_trace_event(run_dir, event)

    start = time.monotonic()
    try:
        run_result = run_agent(client, model, task["prompt"], instance=instance, on_event=on_event,
                               apply_writes=False, allowed_write_ids=allowed_write_ids)
    finally:
        if owned_project_id and owned_task_id:
            from harness.fixtures import delete_owned_rows
            delete_owned_rows(client, owned_project_id, owned_task_id)
    run_result["mode"] = "live"
    elapsed = time.monotonic() - start

    verdict, detail = "unevaluated", "live verification requires harness/verify.py (run.py verify <run_dir>)"
    fixture = None
    if task.get("fixture"):
        try:
            fixture = load_fixture(task["fixture"])
        except Exception:
            fixture = None
    if fixture and task.get("verifier"):
        verdict, detail = verifiers_state.run_verifier(task["verifier"], task, fixture, client, run_result)

    result = {
        "task_id": task_id, "mode": "live", "instance": instance,
        "run_id": run_result["run_id"], "status": run_result["status"],
        "summary": run_result["summary"], "elapsed_s": round(elapsed, 2),
    }
    (run_dir / "result.json").write_text(json.dumps(redact(result), indent=2), encoding="utf-8")
    (run_dir / "verdict.json").write_text(json.dumps({"verdict": verdict, "detail": detail}, indent=2), encoding="utf-8")

    return {"task_id": task_id, "verdict": verdict, "detail": detail, "run_dir": str(run_dir)}


def run_tasks(mode: str = "offline", task_id: Optional[str] = None, instance: str = "suryodaya") -> Dict[str, str]:
    """Returns {task_id: verdict}. Prints a short line per task."""
    task_ids = [task_id] if task_id else _list_task_ids()
    if not task_ids:
        print("No harness tasks found under harness/tasks/*.json")
        return {}

    verdicts: Dict[str, str] = {}
    for tid in task_ids:
        try:
            if mode == "live":
                outcome = _run_live_task(tid, instance)
            else:
                outcome = _run_offline_task(tid, instance)
        except Exception as e:
            outcome = {"task_id": tid, "verdict": "unevaluated", "detail": f"runner error: {e}", "run_dir": None}

        verdicts[tid] = outcome["verdict"]
        print(f"{tid}: {outcome['verdict']} - {outcome['detail']}")

    return verdicts


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--task", default=None)
    parser.add_argument("--instance", default="suryodaya")
    args = parser.parse_args()

    verdicts = run_tasks(mode="live" if args.live else "offline", task_id=args.task, instance=args.instance)
    all_approved = all(v == "approve" for v in verdicts.values())
    print(f"\n{'ALL APPROVED' if all_approved else 'SOME TASKS DID NOT APPROVE'}")


if __name__ == "__main__":
    main()
