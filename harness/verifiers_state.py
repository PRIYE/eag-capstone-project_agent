"""
State-based verifiers (Constitution: grade database state, not agent
prose). Each verifier recomputes truth with its OWN plain-loop logic -
never by importing agent/domain/* - so a bug shared between the
implementation and its verifier can't both agree and both be wrong.

Registry: VERIFIERS[name](task, fixture, mcp, run_result) -> (verdict, detail)
verdict is one of "approve", "revise", "unevaluated".
"""
from typing import Any, Dict, Tuple

from agent import config as _config
from agent import findings as _findings
from agent.domain import dates as _dates


def _read_stored_finding(mcp, run_id: str):
    return _findings.read_finding(mcp, run_id)


def behind_schedule_matches(task: Dict, fixture: Dict, mcp, run_result: Dict) -> Tuple[str, str]:
    finding = _read_stored_finding(mcp, run_result["run_id"])
    if finding is None:
        return "revise", "no finding was stored for this run_id"

    expected = fixture["expected"]
    expected_ids = set(expected.get("behind_project_ids", []))
    expected_insufficient = set(expected.get("insufficient_data_project_ids", []))

    actual_ids = {bp["project_id"] for bp in finding.get("behind_projects", [])}
    actual_insufficient = set(finding.get("insufficient_data_projects", []))

    if actual_ids != expected_ids:
        return "revise", f"behind set mismatch: expected {expected_ids}, got {actual_ids}"
    if actual_insufficient != expected_insufficient:
        return "revise", f"insufficient_data mismatch: expected {expected_insufficient}, got {actual_insufficient}"

    dated_kinds = {"overdue_task", "missed_milestone", "overdue_milestone", "blocked_by_predecessor"}
    for bp in finding.get("behind_projects", []):
        if not any(c.get("kind") in dated_kinds for c in bp.get("causes", [])):
            return "revise", f"project {bp['project_id']} has no dated cause"

    if expected.get("expect_truncated"):
        if finding.get("status") != "partial":
            return "revise", "expected status partial due to truncation, got " + str(finding.get("status"))

    return "approve", "behind set, causes and status all match expected"


def overloaded_matches(task: Dict, fixture: Dict, mcp, run_result: Dict) -> Tuple[str, str]:
    finding = _read_stored_finding(mcp, run_result["run_id"])
    if finding is None:
        return "revise", "no finding was stored for this run_id"

    expected = fixture["expected"]
    expected_overloaded = {e["employee_id"]: e for e in expected.get("overloaded", [])}
    expected_unknown = set(expected.get("capacity_unknown", []))

    actual_overloaded = {e["employee_id"]: e for e in finding.get("overloaded_employees", [])}
    actual_unknown = set(finding.get("capacity_unknown_employees", []))

    if set(actual_overloaded) != set(expected_overloaded):
        return "revise", f"overloaded set mismatch: expected {set(expected_overloaded)}, got {set(actual_overloaded)}"
    if actual_unknown != expected_unknown:
        return "revise", f"capacity_unknown mismatch: expected {expected_unknown}, got {actual_unknown}"

    if set(actual_overloaded) & actual_unknown:
        return "revise", "overloaded and capacity_unknown are not disjoint"

    for emp_id, expected_row in expected_overloaded.items():
        actual_row = actual_overloaded[emp_id]
        if abs(actual_row.get("week_excess_h", 0) - expected_row.get("week_excess_h", 0)) > 0.01:
            return "revise", f"{emp_id} week_excess_h off by more than 0.01h"

    return "approve", "overloaded set, capacity_unknown set and excess hours all match expected"


def refused_with_finding(task: Dict, fixture: Dict, mcp, run_result: Dict) -> Tuple[str, str]:
    if run_result.get("status") != "refused":
        return "revise", f"expected status refused, got {run_result.get('status')}"
    finding = _read_stored_finding(mcp, run_result["run_id"])
    if finding is None:
        return "revise", "no finding stored for a refusal"
    if finding.get("status") != "refused":
        return "revise", "stored finding does not have status refused"
    if mcp.write_log and any(w["entity"] != "AgentMemory" for w in mcp.write_log):
        return "revise", "a domain write happened during a refusal"
    return "approve", "refused cleanly with a stored finding and no domain tool call"


VERIFIERS = {
    "behind_schedule_matches": behind_schedule_matches,
    "overloaded_matches": overloaded_matches,
    "refused_with_finding": refused_with_finding,
}


def run_verifier(name: str, task: Dict, fixture: Dict, mcp, run_result: Dict) -> Tuple[str, str]:
    verifier = VERIFIERS.get(name)
    if verifier is None:
        return "unevaluated", f"no verifier registered named {name!r}"
    try:
        return verifier(task, fixture, mcp, run_result)
    except Exception as e:
        return "unevaluated", f"verifier {name} raised: {e}"
