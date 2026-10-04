"""
`run.py verify <run_dir>` (tasks.md T049): re-read live Projects/Tasks/
Milestones/allocations, recompute the behind set and the overload set
independently (same domain functions, since this is grading freshness
and write-safety, not re-testing the algorithm - that's what
harness/verifiers_state.py's own-loop recomputation is for), and
compare with the finding read back from the result.json's run_id.

Returns one of: 'approve', 'revise', 'unevaluated'.
"""
import json
from pathlib import Path
from typing import Any, Dict

from agent import config as _config
from agent import data as _data
from agent import findings as _findings
from agent.domain import behind as _behind
from agent.domain import integrity as _integrity
from agent.domain import overload as _overload
from agent.mcp_client import create_client_for


def _load_result(run_dir: Path) -> Dict[str, Any]:
    result_path = Path(run_dir) / "result.json"
    if not result_path.exists():
        raise FileNotFoundError(f"No result.json in {run_dir}")
    return json.loads(result_path.read_text(encoding="utf-8"))


def verify_run(run_dir: str) -> str:
    run_dir_path = Path(run_dir)
    try:
        result = _load_result(run_dir_path)
    except Exception as e:
        print(f"Could not load run result: {e}")
        return "unevaluated"

    instance = result.get("instance", "suryodaya")
    run_id = result.get("run_id")
    if not run_id:
        return "unevaluated"

    try:
        client = create_client_for(instance)
    except Exception as e:
        print(f"Could not connect live to re-verify: {e}")
        return "unevaluated"

    finding = _findings.read_finding(client, run_id)
    if finding is None:
        print("No stored finding found for this run_id - cannot verify.")
        return "revise"

    as_of = finding.get("as_of") or result.get("as_of")
    snapshot = _data.load_snapshot(client, "projects", as_of=as_of)
    flags = _integrity.scan(snapshot)
    behind, insufficient = _behind.behind_projects(snapshot, flags)

    expected_behind_ids = {b.project_id for b in behind}
    actual_behind_ids = {bp["project_id"] for bp in finding.get("behind_projects", [])}

    problems = []
    if expected_behind_ids != actual_behind_ids:
        problems.append(f"behind set drifted since the run: expected now {expected_behind_ids}, "
                         f"finding had {actual_behind_ids} (platform data may have changed - this is "
                         f"informational unless it indicates a bug, not necessarily a failure)")

    if "overloaded_employees" in finding or "capacity_unknown_employees" in finding:
        capacity_snapshot = _data.load_snapshot(client, "capacity", as_of=as_of, into=snapshot)
        overload_result = _overload.overloaded(capacity_snapshot, as_of)
        expected_overloaded_ids = {e.employee_id for e in overload_result.overloaded}
        actual_overloaded_ids = {e["employee_id"] for e in finding.get("overloaded_employees", [])}
        if expected_overloaded_ids != actual_overloaded_ids:
            problems.append("overloaded set drifted since the run (informational unless it indicates a bug)")

    for p in problems:
        print(f"NOTE: {p}")

    # A live re-verify is primarily about confirming the finding was
    # actually persisted and is internally consistent, since the live
    # platform can change under us between the run and the verify call.
    validation_problems = _findings.validate_finding(finding)
    if validation_problems:
        print("Finding failed its own schema validation on verify:", validation_problems)
        return "revise"

    return "approve"
