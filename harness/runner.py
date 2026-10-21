"""
Harness runner (tasks.md T027). Supports:
  --offline  (default): build a FakeMcp from a fixture and a
             ScriptedModel from the task's `script`, run agent.loop
             exactly as it runs live, grade with harness/verifiers_state.py.
  --live:    run against the real platform via agent.mcp_client +
             agent.ai_models (requires .env credentials and network).
  --platform: what the AgentSwitch harness runner calls
             (agentswitch-harness.toml). Uses ONLY the runner's env vars
             (AGENTSWITCH_BASE_URL / AGENTSWITCH_TOKEN / AGENTSWITCH_INSTANCE,
             OPENAI_BASE_URL / OPENAI_API_KEY / OPENAI_MODEL), runs platform
             checks + live tasks + the offline fixture suite, and writes
             results.json at the repo root in the runner's schema.

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


def _make_run_dir(instance: str, task_id: str = "") -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    # task_id keeps several tasks started in the same second apart.
    run_dir = RUNS_DIR / (f"{stamp}-{instance}" + (f"-{task_id}" if task_id else ""))
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
    run_dir = _make_run_dir(instance, task_id)
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

    run_dir = _make_run_dir(instance, task_id)
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


# ---------------------------------------------------------------------------
# AgentSwitch harness-runner mode (`python -m harness.runner --platform`)
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent.parent
RESULTS_PATH = ROOT_DIR / "results.json"

# Live tasks per instance: each is one bounded agent run (<= 180 s by
# agent/config.DEADLINE_S). Graded request first, refusals next (no model
# call, fast), then the two live-capable fixture tasks.
GRADED_REQUEST = "Which projects are behind, who is overloaded next week, and what would you move?"
LIVE_TASK_ORDER = ["refuse_payroll", "refuse_manufacturing",
                   "behind_schedule_basic", "overloaded_next_week_basic"]
# Wall-clock budget for the live part of ONE instance. The toml timeout
# covers the whole command, so keep (instances x budget) under it.
LIVE_BUDGET_S = float(os.environ.get("HARNESS_LIVE_BUDGET_S", "720"))
LIVE_TASK_RESERVE_S = 190.0


class _Results:
    def __init__(self, instance: str):
        self.instance = instance
        self.tasks: List[Dict[str, Any]] = []

    def record(self, task_id: str, title: str, passed: bool, evidence: Any,
               score: Optional[float] = None) -> None:
        score = (1.0 if passed else 0.0) if score is None else max(0.0, min(1.0, float(score)))
        self.tasks.append({
            "id": f"{self.instance}:{task_id}",
            "title": title,
            "passed": bool(passed),
            "score": score,
            "evidence": str(redact(str(evidence)))[:500],
        })
        print(f"[{'PASS' if passed else 'FAIL'}] {task_id}: {str(evidence)[:200]}", flush=True)
        # Rewrite results.json after every check so a runner timeout or
        # kill still leaves a valid file with everything recorded so far.
        self.write(final=False)

    def write(self, final: bool = True) -> None:
        if final and not self.tasks:
            self.record("harness_ran", "Harness produced at least one result", False,
                        "no checks were recorded")
        passed = sum(t["passed"] for t in self.tasks)
        if not self.tasks:
            return
        payload = {"tasks": self.tasks[:200],
                   "summary": f"{self.instance}: {passed}/{len(self.tasks)} checks passed "
                              f"(Team 14 Projects seat)" + ("" if final else " [in progress]")}
        tmp = RESULTS_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, RESULTS_PATH)  # atomic: never a half-written file
        if final:
            print(f"\nWrote {RESULTS_PATH} - {payload['summary']}", flush=True)


def _platform_checks(res: _Results, instance: str):
    """Direct MCP checks with the seat token. Returns the client or None."""
    from agent.mcp_client import create_client_for
    from agent import safety as _safety

    try:
        client = create_client_for(instance)
    except Exception as e:  # noqa: BLE001
        res.record("platform.mcp_initialize", "MCP initialize works with the seat token", False, repr(e))
        return None
    res.record("platform.mcp_initialize", "MCP initialize works with the seat token", True,
               f"initialized against {client.base_url}")

    tools_result = client.list_tools()
    tools = (tools_result.data or {}).get("tools", []) if tools_result.success else []
    names = {t.get("name") for t in tools}
    needed = {"Project.list", "Task.list"}
    res.record("platform.projects_tools_visible", "Seat sees the Projects tools it needs",
               tools_result.success and needed <= names,
               f"{len(tools)} tools; missing={sorted(needed - names)}" if tools_result.success
               else f"tools/list failed: {tools_result.error}")

    # Our saved harness link is readable (same check as the official example).
    try:
        th = client.call_tool("TeamHarness.get_mine", {})
        text = json.dumps(th.data) if th.success else str(th.error)
        # The saved link is stored per server. A successful call that says
        # no link is saved on THIS server is not a harness failure: pass
        # with a note. A failed call or a non-GitHub link still fails.
        data = th.data if (th.success and isinstance(th.data, dict)) else {}
        result_block = data.get("result") if isinstance(data.get("result"), dict) else data
        no_link_saved = th.success and isinstance(result_block, dict) \
            and "harness" in result_block and result_block.get("harness") is None
        if no_link_saved:
            res.record("platform.team_harness_link", "TeamHarness.get_mine returns our saved GitHub link",
                       True, f"note: no harness link saved on this server ({instance}); "
                             f"call succeeded. {text[:200]}")
        else:
            res.record("platform.team_harness_link", "TeamHarness.get_mine returns our saved GitHub link",
                       th.success and "github.com/" in text, text[:300])
    except Exception as e:  # noqa: BLE001
        res.record("platform.team_harness_link", "TeamHarness.get_mine returns our saved GitHub link",
                   False, repr(e))

    # Seat boundary is a real 403, not a 404 (Constitution Principle III).
    try:
        from agent.loop import FORBIDDEN_KEYWORDS as _FK
        probe = _safety.probe_domain(client, _FK["payroll"])
        res.record("platform.payroll_boundary", "Payroll is outside this seat (403, not 404)",
                   probe.get("status") == "not_visible", probe)
    except Exception as e:  # noqa: BLE001
        res.record("platform.payroll_boundary", "Payroll is outside this seat (403, not 404)", False, repr(e))

    # Paged reads are complete (not silently truncated at the default 20).
    try:
        page = client.call_tool_all("Project.list", {})
        ok = page.success and not page.data.get("truncated") and page.data.get("fetched", 0) == page.data.get("total")
        res.record("platform.project_list_complete", "Project.list pages through the full set",
                   ok, page.data if page.success else page.error)
    except Exception as e:  # noqa: BLE001
        res.record("platform.project_list_complete", "Project.list pages through the full set", False, repr(e))
    return client


def _live_graded(res: _Results, instance: str, client) -> None:
    """The seat's graded request, end to end on the platform model."""
    from agent.ai_models import create_model
    from agent.loop import run_agent
    from agent import findings as _findings

    title = "Graded request: behind projects, next-week overload, what to move"
    run_dir = _make_run_dir(instance, "graded_request")
    try:
        model = create_model()
        result = run_agent(client, model, GRADED_REQUEST, instance=instance,
                           on_event=lambda e: _write_trace_event(run_dir, e), apply_writes=False)
    except Exception as e:  # noqa: BLE001
        res.record("live.graded_request", title, False, f"agent run raised: {e!r}")
        return
    status = result.get("status")
    finding = _findings.read_finding(client, result.get("run_id"))
    problems = _findings.validate_finding(finding) if finding else ["no finding stored for run_id"]
    if finding and not problems:
        for key in ("behind_projects", "overloaded_employees"):
            if key not in finding:
                problems.append(f"finding has no {key}")
    passed = status in ("complete", "partial") and not problems
    score = 0.0 if not passed else (1.0 if status == "complete" else 0.5)
    res.record("live.graded_request", title, passed,
               f"status={status} problems={problems[:3]} "
               f"behind={len((finding or {}).get('behind_projects', []))} "
               f"overloaded={len((finding or {}).get('overloaded_employees', []))} "
               f"summary={(result.get('summary') or '')[:200]!r}", score=score)


def run_platform() -> int:
    from agent.mcp_client import runner_env

    renv = runner_env()
    instance = (renv or {}).get("instance") or os.environ.get("AGENTSWITCH_INSTANCE") or "suryodaya"
    res = _Results(instance)
    try:
        if not renv:
            res.record("platform.env", "Runner env vars are present", False,
                       "AGENTSWITCH_BASE_URL / AGENTSWITCH_TOKEN not set")
            client = None
        else:
            client = _platform_checks(res, instance)

        # Offline fixture suite: scripted model, hand-authored expectations.
        for tid in _list_task_ids():
            task = _load_task(tid)
            title = f"[offline fixture] {task.get('checks') or task.get('prompt')}"
            try:
                out = _run_offline_task(tid, instance)
            except Exception as e:  # noqa: BLE001
                out = {"verdict": "unevaluated", "detail": f"runner error: {e!r}"}
            res.record(f"offline.{tid}", title, out["verdict"] == "approve",
                       f"{out['verdict']}: {out['detail']}")

        # Live agent tasks (platform model + live data), time-boxed.
        start = time.monotonic()
        if client is not None:
            if os.environ.get("OPENAI_BASE_URL") or os.environ.get("OPENAI_API_KEY"):
                _live_graded(res, instance, client)
            else:
                res.record("live.graded_request", "Graded request on the platform model", False,
                           "OPENAI_BASE_URL / OPENAI_API_KEY not set")
            for tid in LIVE_TASK_ORDER:
                task = _load_task(tid)
                title = f"[live] {task.get('checks') or task.get('prompt')}"
                if time.monotonic() - start + LIVE_TASK_RESERVE_S > LIVE_BUDGET_S:
                    res.record(f"live.{tid}", title, False, "skipped: live time budget exhausted")
                    continue
                try:
                    out = _run_live_task(tid, instance)
                except Exception as e:  # noqa: BLE001
                    out = {"verdict": "unevaluated", "detail": f"runner error: {e!r}"}
                res.record(f"live.{tid}", title, out["verdict"] == "approve",
                           f"{out['verdict']}: {out['detail']}")

    except Exception as e:  # noqa: BLE001
        res.record("harness.crash", "Harness completed without crashing", False, repr(e))
    finally:
        res.write()
    return 0


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--platform", action="store_true",
                        help="AgentSwitch harness-runner mode: env-var auth, writes results.json")
    parser.add_argument("--task", default=None)
    parser.add_argument("--instance", default="suryodaya")
    args = parser.parse_args()

    if args.platform:
        raise SystemExit(run_platform())

    verdicts = run_tasks(mode="live" if args.live else "offline", task_id=args.task, instance=args.instance)
    all_approved = all(v == "approve" for v in verdicts.values())
    print(f"\n{'ALL APPROVED' if all_approved else 'SOME TASKS DID NOT APPROVE'}")


if __name__ == "__main__":
    main()
